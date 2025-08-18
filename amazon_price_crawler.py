# -*- coding: utf-8 -*-
"""
Amazon 상품 상세가 수집기 (로그인 유지 지원)
- 최초 1회: --login-setup → 브라우저에서 아마존 로그인(2FA 포함) → storage_state 저장
- 이후: KR/US × PC/Mobile 4조합으로 가격 수집
- 스케줄: 기본 0·3·6·9…시 정각 반복, --once 로 1회만 실행 가능
- 결과: ./outputs/amazon_detail_prices.csv
"""

import os, re, json, argparse, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse

from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

load_dotenv()

PROXY = {"KR": os.getenv("PROXY_KR") or None, "US": os.getenv("PROXY_US") or None}
STORAGE_PATH = Path(os.getenv("STORAGE_AMAZON") or "./storage/amazon_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "amazon_detail_prices.csv"
AMAZON_URL = os.getenv("AMAZON_URL", "").strip()

UA = {
    "pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

PRICE_SELECTORS = [
    "#corePriceDisplay_desktop_feature_div .a-offscreen",
    "#corePrice_feature_div .a-offscreen",
    ".a-price .a-offscreen",
    "#apex_desktop .a-offscreen",
    "span.a-price-whole",  # (백업) 분리된 정수부
]

# ---------- 유틸 ----------
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

def parse_money(text: str):
    t = (text or "").replace("\u00a0", " ").strip()
    m = re.search(r"([\d.,]+)\s*원", t)
    if m: return int(re.sub(r"[^\d]","",m.group(1))), "KRW"
    m = re.search(r"([₩$€£])\s*([\d.,]+)", t)
    if m:
        cur = {"₩":"KRW","$":"USD","€":"EUR","£":"GBP"}.get(m.group(1),"CUR")
        return int(re.sub(r"[^\d]","",m.group(2))), cur
    # "1,234.56" 같은 형식(통화기호 없음)도 허용
    m = re.search(r"([\d.,]+)", t)
    if m: return int(re.sub(r"[^\d]", "", m.group(1))), None
    return None, None

async def goto_with_retry(page, url, referer=None, retries=3):
    last=None
    for _ in range(retries+1):
        try:
            await page.goto(url, wait_until="load", referer=referer); return
        except Exception as e:
            last=e; await page.wait_for_timeout(3000)
    raise last

async def safe_screenshot(page, path, full=True):
    try:
        if hasattr(page, "is_closed") and page.is_closed(): return False
        await page.screenshot(path=path, full_page=full); return True
    except Exception: return False

async def save_artifacts(page, prefix):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    await safe_screenshot(page, f"{prefix}_{ts}.png", full=True)
    try:
        if not page.is_closed():
            Path(f"{prefix}_{ts}.html").write_text(await page.content(), encoding="utf-8")
    except Exception: pass

# ---------- 브라우저/컨텍스트 ----------
async def new_context(pw, region: str, device: str):
    browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    storage = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
    ctx = await browser.new_context(
        user_agent=UA[device], viewport=VIEWPORT[device],
        locale="ko-KR", timezone_id="Asia/Seoul",
        proxy={"server": PROXY[region]} if PROXY[region] else None,
        storage_state=storage,  # 로그인 유지(있으면)
    )
    ctx.set_default_navigation_timeout(180_000)
    ctx.set_default_timeout(180_000)
    return browser, ctx

# ---------- 로그인 저장(1회) ----------
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

# ---------- 본 수집 ----------
async def scrape_once(ctx, region, device, url: str):
    page = await ctx.new_page()
    await goto_with_retry(page, url, referer="https://www.google.com/")

    # 봇/캡차 감지
    try:
        body = (await page.content()).lower()
        if "not a robot" in body or "enter the characters you see below" in body:
            raise RuntimeError("Amazon이 봇/해외 접속으로 차단했습니다. 프록시/수동 통과 필요.")
    except Exception: pass

    # 가격 요소 대기
    for _ in range(60):
        ok=False
        for sel in PRICE_SELECTORS:
            try:
                if await page.locator(sel).count() > 0: ok=True; break
            except: pass
        if ok: break
        await page.wait_for_timeout(1000)

    # 가격 텍스트 추출
    price_text = None
    for sel in PRICE_SELECTORS:
        try:
            els = page.locator(sel); n = await els.count()
            for i in range(min(n, 12)):
                t = (await els.nth(i).inner_text()).strip()
                if re.search(r"\d", t):
                    price_text = t; break
            if price_text: break
        except: pass

    # a-price-whole + a-price-fraction 조합(백업)
    if not price_text:
        try:
            whole = await page.locator("span.a-price-whole").first.inner_text()
            frac  = await page.locator("span.a-price-fraction").first.inner_text()
            price_text = f"${whole}.{frac}"
        except Exception: pass

    if not price_text:
        await save_artifacts(page, f"screenshot_amazon_no_price_{region}_{device}")
        raise RuntimeError("가격 텍스트를 찾지 못함")

    price, currency = parse_money(price_text)
    row = {
        "site": "amazon",
        "item": urlparse(page.url).path,
        "price": price,
        "currency": currency or "USD",
        "meta": json.dumps({"raw_price_text": price_text, "url": page.url}, ensure_ascii=False),
        "region": region, "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close()
    return row

async def run_once():
    if not AMAZON_URL: raise RuntimeError("AMAZON_URL(.env)이 비어있어요.")
    combos = [{"region":"KR","device":"pc"},{"region":"KR","device":"mobile"},{"region":"US","device":"pc"},{"region":"US","device":"mobile"}]
    results=[]
    async with async_playwright() as pw:
        sem = asyncio.Semaphore(2)  # 동시 2개(안정성)
        async def worker(c):
            async with sem:
                try:
                    browser, ctx = await new_context(pw, c["region"], c["device"])
                    try:
                        r = await scrape_once(ctx, c["region"], c["device"], AMAZON_URL); results.append(r)
                        print(f"[OK][{c['region']}/{c['device']}] {r['price']} {r['currency']}")
                    finally:
                        await ctx.close(); await browser.close()
                except Exception as e:
                    print(f"[FAIL]{c}: {e}")
        await asyncio.gather(*[worker(c) for c in combos])

    if results:
        df = pd.DataFrame(results)
        if CSV_PATH.exists(): pd.concat([pd.read_csv(CSV_PATH), df], ignore_index=True).to_csv(CSV_PATH, index=False)
        else: df.to_csv(CSV_PATH, index=False)
        print(f"Saved -> {CSV_PATH.resolve()}")

async def scheduler():
    await run_once()
    while True:
        wait_s = seconds_until_next_30m()
        print(f"[Scheduler] 다음 실행까지 {wait_s}초 대기 (매 30분: :00 / :30).")
        await asyncio.sleep(wait_s)
        await run_once()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="브라우저에서 아마존 로그인 후 storage_state 저장")
    p.add_argument("--once", action="store_true", help="1회만 실행 후 종료")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        if args.login_setup: asyncio.run(login_setup_once())
        elif args.once: asyncio.run(run_once())
        else: asyncio.run(scheduler())
    except KeyboardInterrupt:
        print("\n[종료] 사용자에 의해 중단되었습니다.")
