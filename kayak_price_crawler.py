# -*- coding: utf-8 -*-
"""
Kayak 항공권 상세가 수집기 (로그인 유지 버전)
- 최초 1회: --login-setup 로 브라우저에서 로그인 → storage_state 파일 저장
- 이후: 같은 storage_state 로 4조합(KR/US × PC/Mobile) 동시 수집
- 스케줄: 기본 0·3·6·9…시 정각 반복, --once 로 1회만 실행 가능
- 결과: ./outputs/kayak_detail_prices.csv

"""

import os, re, json, argparse, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import quote

from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

load_dotenv()

# ---------- 환경 ----------
PROXY = {"KR": os.getenv("PROXY_KR") or None, "US": os.getenv("PROXY_US") or None}
PROXY_USER = {"KR": os.getenv("PROXY_KR_USER"), "US": os.getenv("PROXY_US_USER")}
PROXY_PASS = {"KR": os.getenv("PROXY_KR_PASS"), "US": os.getenv("PROXY_US_PASS")}

STORAGE_PATH = Path(os.getenv("STORAGE_PATH") or "./storage/kayak_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "kayak_detail_prices.csv"

ORI = (os.getenv("KAYAK_ORI") or "ICN").strip()
DST = (os.getenv("KAYAK_DST") or "BWN").strip()
DATE = (os.getenv("KAYAK_DATE") or "2025-11-12").strip()   # YYYY-MM-DD
PAX  = int(os.getenv("KAYAK_PAX") or "2")
CUR  = (os.getenv("KAYAK_CURRENCY") or "KRW").strip().upper()
AIRLINE_HINT = (os.getenv("KAYAK_AIRLINE") or "").strip()   # 예: "로열브루나이" / "Royal Brunei"

UA = {
    "pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

# ---------- 유틸 ----------
def seconds_until_next_10m():
    now = datetime.now()
    base = now.replace(second=0, microsecond=0)
    next_min = ((now.minute // 10) + 1) * 10
    if next_min >= 60:
        run_time = (base + timedelta(hours=1)).replace(minute=0)
    else:
        run_time = base.replace(minute=next_min)
    return max(1, int((run_time - now).total_seconds()))

def build_kayak_url():
    # 예: https://www.kayak.co.kr/flights/ICN-BWN/2025-11-12/2adults?fs=stops=0&currency=KRW&lang=ko
    base = f"https://www.kayak.co.kr/flights/{quote(ORI)}-{quote(DST)}/{DATE}/{PAX}adults"
    qs = f"?fs=stops=0&currency={CUR}&lang=ko"
    return base + qs

def parse_money(text: str):
    t = (text or "").replace("\u00a0", " ").strip()
    m = re.search(r"([0-9][0-9,]*)\s*원", t)
    if m: return int(m.group(1).replace(",", "")), "KRW"
    m = re.search(r"([₩$€£])\s*([0-9][0-9,]*)", t)
    if m:
        cur = {"₩":"KRW","$":"USD","€":"EUR","£":"GBP"}.get(m.group(1), None)
        return int(m.group(2).replace(",", "")), cur
    m = re.search(r"([0-9][0-9,]*)", t)
    if m: return int(m.group(1).replace(",", "")), None
    return None, None

def looks_ad(text: str) -> bool:
    s = (text or "").lower()
    return any(k in s for k in ["광고", "sponsored", "sponsor", "ad "])

def airline_matches(text: str) -> bool:
    if not AIRLINE_HINT: return True
    return (AIRLINE_HINT.lower() in (text or "").lower())

async def goto_with_retry(page, url, referer=None, retries=3):
    last=None
    for _ in range(retries+1):
        try:
            await page.goto(url, wait_until="domcontentloaded", referer=referer)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except: pass
            return
        except Exception as e:
            last=e; await page.wait_for_timeout(3000)
    raise last

async def safe_screenshot(page, path, full=True):
    try:
        if hasattr(page, "is_closed") and page.is_closed(): return False
        await page.screenshot(path=path, full_page=full); return True
    except Exception as e:
        print(f"[WARN] screenshot failed: {e}"); return False

async def save_artifacts(page, prefix):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    await safe_screenshot(page, f"{prefix}_{ts}.png", full=True)
    try:
        if not page.is_closed():
            Path(f"{prefix}_{ts}.html").write_text(await page.content(), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] save html failed: {e}")

# ---------- 셀렉터(모바일/PC 겸용) ----------
CARD_SELECTOR = ", ".join([
    "[data-resultid]",                          # 데스크톱
    "[data-testid*='resultCard']",              # 데스크톱/모바일 A/B
    "article[aria-label]",                      # 모바일 리스트
    "li[role='article']",                       # 모바일 리스트(구버전)
    "[class*='resultCard']"                     # 백업
])

# 카드 내부에서 가격 텍스트를 발견하기 위한 정규식
PRICE_IN_CARD_RE = re.compile(r"(?:₩\s*[0-9][0-9,]*|[$€£]\s*[0-9][0-9,]*|[0-9][0-9,]*\s*원)")

async def extract_card_price_text(card_el) -> tuple[int|None, str|None, str]:
    """카드 하나에서 광고/항공사 조건 점검 후, 가격 텍스트를 뽑아 숫자 반환"""
    try:
        text = await card_el.inner_text()
    except Exception:
        return None, None, ""

    if looks_ad(text):                # 광고 제외
        return None, None, text
    if not airline_matches(text):     # 항공사 힌트(옵션)
        return None, None, text

    # 카드 내에서 '가격스러운' 텍스트만 추출
    m = PRICE_IN_CARD_RE.search(text)
    if not m:
        return None, None, text
    val, cur = parse_money(m.group(0))
    return val, cur, text

# ---------- 브라우저 ----------
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

# ---------- 로그인(선택) ----------
async def login_setup_once():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(user_agent=UA["pc"], viewport=VIEWPORT["pc"], locale="ko-KR", timezone_id="Asia/Seoul",
                                        proxy={"server": PROXY["KR"]} if PROXY["KR"] else None)
        ctx.set_default_navigation_timeout(180_000); ctx.set_default_timeout(180_000)
        page = await ctx.new_page()
        await goto_with_retry(page, "https://www.kayak.co.kr", referer="https://www.google.com/")
        print("[로그인 설정] Kayak에 로그인(언어/통화 KRW 확인) 후 Enter"); input()
        await ctx.storage_state(path=str(STORAGE_PATH))
        print(f"[로그인 설정] 저장 완료: {STORAGE_PATH.resolve()}")
        await ctx.close(); await browser.close()

# ---------- 본 수집 ----------
async def scrape_once(ctx, region, device):
    page = await ctx.new_page()
    url = build_kayak_url()
    await goto_with_retry(page, url, referer="https://www.google.com/")

    # 결과 카드 대기
    for _ in range(60):
        try:
            n = await page.locator(CARD_SELECTOR).count()
            if n > 0: break
        except: pass
        await page.wait_for_timeout(1000)

    n = 0
    try:
        n = await page.locator(CARD_SELECTOR).count()
    except: pass
    if n == 0:
        await save_artifacts(page, f"kayak_no_cards_{region}_{device}")
        raise RuntimeError("검색 결과 카드를 찾지 못함")

    # 상위 20개 카드 스캔 (모바일/PC 혼용)
    prices = []
    max_scan = min(n, 20)
    for i in range(max_scan):
        card = page.locator(CARD_SELECTOR).nth(i)
        try:
            await card.scroll_into_view_if_needed(timeout=2000)
        except: pass
        val, cur, raw = await extract_card_price_text(card)
        if val:
            prices.append((val, cur or CUR, raw, i))

    if not prices:
        await save_artifacts(page, f"kayak_no_price_{region}_{device}")
        raise RuntimeError("가격 텍스트를 찾지 못함(광고/항공사 필터 후 빈 결과)")

    # 규칙: 최저가 선택
    price, currency, raw, idx = min(prices, key=lambda x: x[0])

    row = {
        "site": "kayak",
        "route": f"{ORI}-{DST}",
        "date": DATE,
        "pax": PAX,
        "price": price,                 # 보통 1인 기준 금액
        "currency": currency or CUR,
        "meta": json.dumps({
            "raw_card_text": raw[:4000],
            "card_index": idx,
            "filters": {"airline_hint": AIRLINE_HINT or None, "ad_skipped": True, "stops": 0},
            "url": url
        }, ensure_ascii=False),
        "region": region, "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close()
    return row

# ---------- 실행 ----------
async def run_once():
    combos = [
        {"region":"KR","device":"pc"},
        {"region":"KR","device":"mobile"},
        {"region":"US","device":"pc"},
        {"region":"US","device":"mobile"},
    ]
    results=[]
    async with async_playwright() as pw:
        sem = asyncio.Semaphore(2)
        async def worker(c):
            async with sem:
                try:
                    browser, ctx = await new_context(pw, c["region"], c["device"])
                    try:
                        r = await scrape_once(ctx, c["region"], c["device"])
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
        w = seconds_until_next_10m()
        print(f"[Scheduler] 다음 실행까지 {w}초 대기 (매 10분: :00/:10/:20/:30/:40/:50).")
        await asyncio.sleep(w)
        await run_once()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="Kayak 로그인 상태 저장(선택)")
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