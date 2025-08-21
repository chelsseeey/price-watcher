# -*- coding: utf-8 -*-
"""
Amazon 상품 상세가 수집기 (로그인 유지 지원)
- 최초 1회: --login-setup → 브라우저에서 아마존 로그인(2FA 포함) → storage_state 저장
- 이후: KR/US × PC/Mobile 4조합으로 가격 수집
- 결과: ./outputs/amazon_detail_prices.csv
"""

import os, re, json, argparse, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

# -------------------- 설정 로드 --------------------
load_dotenv()

PROXY = {"KR": os.getenv("PROXY_KR") or None, "US": os.getenv("PROXY_US") or None}
PROXY_USER = {"KR": os.getenv("PROXY_KR_USER"), "US": os.getenv("PROXY_US_USER")}
PROXY_PASS = {"KR": os.getenv("PROXY_KR_PASS"), "US": os.getenv("PROXY_US_PASS")}

STORAGE_PATH = Path(os.getenv("STORAGE_AMAZON") or "./storage/amazon_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "amazon_detail_prices.csv"
AMAZON_URL = (os.getenv("AMAZON_URL") or "").strip()

UA = {
    "pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

# 가격 후보(단가 섞이지 않도록 컨텍스트 한정)
PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div span.a-price .a-offscreen",
    "#apex_desktop span.a-price .a-offscreen",
    "#corePrice_feature_div span.a-price .a-offscreen",
    "#priceblock_ourprice",
    "#priceblock_dealprice",
    "span.a-price .a-offscreen",  # 백업
]

UNIT_HINTS = [
    "/", " per ", " / ", "each", "개당", "당", "시트", "sheet", "count", "ea",
    "oz", "ounce", "lb", "ml", "g ", "kg", "100", "팩", "pack", "롤", "롤당"
]
SHIP_HINTS = ["배송", "shipping", "delivery", "fees", "수입", "관세", "요금"]

# -------------------- 유틸 --------------------
def seconds_until_next_30m():
    from datetime import datetime, timedelta
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    # 다음 :00 또는 :30 정각으로 정렬
    if now.minute < 30:
        run_time = base.replace(minute=30)
    else:
        run_time = (base + timedelta(hours=1)).replace(minute=0)
    return max(1, int((run_time - now).total_seconds()))

async def goto_with_retry(page, url, referer=None, retries=3):
    last=None
    for _ in range(retries+1):
        try:
            await page.goto(url, wait_until="load", referer=referer)
            return
        except Exception as e:
            last = e
            await page.wait_for_timeout(3000)
    raise last

async def safe_screenshot(page, path, full=True):
    try:
        if hasattr(page, "is_closed") and page.is_closed():
            return False
        await page.screenshot(path=path, full_page=full)
        return True
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}")
        return False

async def save_artifacts(page, prefix):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    await safe_screenshot(page, f"{prefix}_{ts}.png", full=True)
    try:
        if not page.is_closed():
            Path(f"{prefix}_{ts}.html").write_text(await page.content(), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] save html failed: {e}")

def looks_like_unit_price(t: str) -> bool:
    s = (t or "").lower().strip()
    return any(h in s for h in (h.lower() for h in UNIT_HINTS))

def looks_like_shipping(t: str) -> bool:
    s = (t or "").lower().strip()
    return any(h in s for h in (h.lower() for h in SHIP_HINTS))

def parse_money_precise(text: str):
    """$12.34, ₩12,345, 12.34 모두 안전 파싱 (소수 유지)"""
    if not text: return None, None
    t = text.replace("\u00a0", " ").strip()
    m = re.search(r"([₩$€£])\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", t)
    if m:
        sym, num = m.group(1), m.group(2)
        cur = {"₩":"KRW","$":"USD","€":"EUR","£":"GBP"}.get(sym, None)
        try: return float(Decimal(num.replace(",", ""))), cur
        except InvalidOperation: return None, cur
    m = re.search(r"([0-9][0-9,]*)\s*원", t)
    if m: return float(m.group(1).replace(",", "")), "KRW"
    m = re.search(r"([0-9][0-9,]*(?:\.[0-9]{1,2})?)", t)
    if m:
        try: return float(Decimal(m.group(1).replace(",", ""))), None
        except InvalidOperation: return None, None
    return None, None

# -------------------- 브라우저 컨텍스트 --------------------
async def new_context(pw, region: str, device: str):
    browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    proxy_cfg = {"server": PROXY[region]} if PROXY[region] else None
    if proxy_cfg and PROXY_USER[region] and PROXY_PASS[region]:
        proxy_cfg["username"] = PROXY_USER[region]
        proxy_cfg["password"] = PROXY_PASS[region]
    storage = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
    ctx = await browser.new_context(
        user_agent=UA[device], viewport=VIEWPORT[device],
        locale="ko-KR", timezone_id="Asia/Seoul",
        proxy=proxy_cfg, storage_state=storage
    )
    ctx.set_default_navigation_timeout(180_000)
    ctx.set_default_timeout(180_000)
    return browser, ctx

# -------------------- 로그인 저장 (1회) --------------------
async def login_setup_once():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent=UA["pc"], viewport=VIEWPORT["pc"],
            locale="ko-KR", timezone_id="Asia/Seoul",
            proxy={"server": PROXY["KR"]} if PROXY["KR"] else None,
        )
        ctx.set_default_navigation_timeout(180_000); ctx.set_default_timeout(180_000)
        page = await ctx.new_page()
        await goto_with_retry(page, "https://www.amazon.com/-/ko/", referer="https://www.google.com/")
        print("[로그인 설정] 아마존에 로그인(2FA 포함) 완료 후 터미널에 Enter"); input()
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(STORAGE_PATH))
        print(f"[로그인 설정] 저장 완료: {STORAGE_PATH.resolve()}")
        await ctx.close(); await browser.close()

# -------------------- 본 수집 --------------------
async def scrape_once(ctx, region, device, url: str):
    page = await ctx.new_page()
    await goto_with_retry(page, url, referer="https://www.google.com/")

    # 간단한 차단/캡차 감지
    try:
        body = (await page.content()).lower()
        if "not a robot" in body or "enter the characters you see below" in body:
            raise RuntimeError("Amazon이 봇/해외 접속으로 차단했습니다. 프록시/수동 통과 필요.")
    except Exception:
        pass

    # 가격 요소 대기
    for _ in range(60):
        ok = False
        for sel in PRICE_SELECTORS:
            try:
                if await page.locator(sel).count() > 0:
                    ok = True; break
            except: pass
        if ok: break
        await page.wait_for_timeout(1000)

    # 후보 수집(단가/배송비 제외)
    candidates = []
    for sel in PRICE_SELECTORS:
        try:
            els = page.locator(sel)
            n = await els.count()
            for i in range(min(n, 20)):
                t = (await els.nth(i).inner_text()).strip()
                if not re.search(r"\d", t): 
                    continue
                if looks_like_unit_price(t) or looks_like_shipping(t):
                    continue
                val, cur = parse_money_precise(t)
                if val:
                    candidates.append((val, cur, t))
        except: 
            pass

    # 백업: 정수/소수부 조합
    if not candidates:
        try:
            whole = await page.locator("span.a-price-whole").first.inner_text()
            frac  = await page.locator("span.a-price-fraction").first.inner_text()
            t = f"${whole}.{frac}"
            if not looks_like_unit_price(t):
                val, cur = parse_money_precise(t)
                if val:
                    candidates.append((val, cur, t))
        except: 
            pass

    if not candidates:
        await save_artifacts(page, f"screenshot_amazon_no_price_{region}_{device}")
        raise RuntimeError("가격 텍스트를 찾지 못함")

    # 너무 작은 단가(예: 1.27)는 제외 → 남은 것 중 첫 값 사용
    filtered = [c for c in candidates if c[0] >= 5]
    price, currency, raw = (filtered[0] if filtered else candidates[0])

    row = {
        "site": "amazon",
        "item": urlparse(page.url).path,
        "price": price,                       # float (소수 유지)
        "currency": currency or "USD",
        "meta": json.dumps({"raw_price_text": raw, "url": page.url}, ensure_ascii=False),
        "region": region, "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close()
    return row

# -------------------- 실행 루프 --------------------
async def run_once():
    if not AMAZON_URL:
        raise RuntimeError("AMAZON_URL(.env)이 비어 있습니다.")
    combos = [
        {"region":"KR","device":"pc"},
        {"region":"KR","device":"mobile"},
        {"region":"US","device":"pc"},
        {"region":"US","device":"mobile"},
    ]
    results=[]
    async with async_playwright() as pw:
        sem = asyncio.Semaphore(2)  # 동시 2개로 안정성
        async def worker(c):
            async with sem:
                try:
                    browser, ctx = await new_context(pw, c["region"], c["device"])
                    try:
                        r = await scrape_once(ctx, c["region"], c["device"], AMAZON_URL)
                        results.append(r)
                        print(f"[OK][{c['region']}/{c['device']}] {r['price']} {r['currency']}")
                    finally:
                        await ctx.close(); await browser.close()
                except Exception as e:
                    print(f"[FAIL]{c}: {e}")
                    return e
        rs = await asyncio.gather(*[worker(c) for c in combos], return_exceptions=True)
        for r in rs:
            if isinstance(r, Exception):
                print(f"[WARN] worker error: {r}")

    if results:
        df = pd.DataFrame(results)
        if CSV_PATH.exists():
            pd.concat([pd.read_csv(CSV_PATH), df], ignore_index=True).to_csv(CSV_PATH, index=False)
        else:
            df.to_csv(CSV_PATH, index=False)
        print(f"Saved -> {CSV_PATH.resolve()}")
    else:
        print("[WARN] 저장할 결과가 없습니다.")

async def scheduler():
    await run_once()
    while True:
        wait_s = seconds_until_next_30m()
        print(f"[Scheduler] 다음 실행까지 {wait_s}초 대기 (매 30분: :00 / :30).")
        await asyncio.sleep(wait_s)
        await run_once()
        
# -------------------- CLI --------------------
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="브라우저에서 아마존 로그인 후 storage_state 저장")
    p.add_argument("--once", action="store_true", help="1회만 실행 후 종료")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        if args.login_setup:
            asyncio.run(login_setup_once())
        elif args.once:
            asyncio.run(run_once())
        else:
            asyncio.run(scheduler())
    except KeyboardInterrupt:
        print("\n[종료] 사용자에 의해 중단되었습니다.")