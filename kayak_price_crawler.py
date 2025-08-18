# -*- coding: utf-8 -*-
"""
Kayak 항공권 상세가 수집기 (로그인 유지 버전)
- 최초 1회: --login-setup 로 브라우저에서 로그인 → storage_state 파일 저장
- 이후: 같은 storage_state 로 4조합(KR/US × PC/Mobile) 동시 수집
- 스케줄: 기본 0·3·6·9…시 정각 반복, --once 로 1회만 실행 가능
- 결과: ./outputs/kayak_detail_prices.csv

.env 예시:
  PROXY_KR=
  PROXY_US=
  STORAGE_PATH=./storage/kayak_login.json
  KAYAK_ORI=ICN
  KAYAK_DST=BWN
  KAYAK_DATE=2025-11-12
  KAYAK_PAX=2
"""

import os, re, json, argparse, asyncio
from pathlib import Path
from datetime import datetime, timedelta

from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

# =========================
# 환경설정
# =========================
load_dotenv()

PROXY = {"KR": os.getenv("PROXY_KR") or None, "US": os.getenv("PROXY_US") or None}

STORAGE_PATH = Path(os.getenv("STORAGE_PATH") or "./storage/kayak_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "kayak_detail_prices.csv"

ORI  = os.getenv("KAYAK_ORI",  "ICN")
DST  = os.getenv("KAYAK_DST",  "BWN")
DATE = os.getenv("KAYAK_DATE", "2025-11-12")
PAX  = int(os.getenv("KAYAK_PAX", "2"))

UA = {
    "pc": "Mozilla/5.0~ (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

RESULT_CARD_SELECTORS = [
    "[data-testid='resultCard']",
    "[data-resultid]",
    "[aria-label='Result card']",
    "[id^='resultCard']",
]
PRICE_SELECTORS = [
    "[data-testid='offerPrice']",
    "[data-testid*='price']",
    "button:has-text('예약')",
    "strong:has-text('원')",
    "span:has-text('원')",
    "div:has-text('원')",
]

# =========================
# 유틸
# =========================
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

def kayak_search_url(ori, dst, date, pax):
    return f"https://www.kayak.co.kr/flights/{ori}-{dst}/{date}?adults={pax}&sort=bestflight_a"

def parse_money(text: str):
    t = text.replace("\u00a0", " ").strip()
    m = re.search(r"([\d.,]+)\s*원", t)
    if m:
        val = int(re.sub(r"[^\d]", "", m.group(1)))
        return val, "KRW"
    m = re.search(r"([₩$€£])\s*([\d.,]+)", t)
    if m:
        sym, num = m.group(1), m.group(2)
        cur = {"₩": "KRW", "$": "USD", "€": "EUR", "£": "GBP"}.get(sym, "CUR")
        val = int(re.sub(r"[^\d]", "", num))
        return val, cur
    return None, None

async def goto_with_retry(page, url, referer=None, retries=2):
    last_err = None
    for _ in range(retries + 1):
        try:
            await page.goto(url, wait_until="load", referer=referer)
            return
        except Exception as e:
            last_err = e
            await page.wait_for_timeout(3000)
    raise last_err

async def count_any(page, selectors):
    for sel in selectors:
        try:
            c = await page.locator(sel).count()
            if c > 0:
                return c, sel
        except Exception:
            pass
    return 0, None

async def first_locator(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if await loc.count() > 0:
                return loc, sel
        except Exception:
            pass
    return None, None

# =========================
# 브라우저/컨텍스트 (로그인 유지)
# =========================
async def new_browser_context(pw, region: str, device: str, storage_path: Path):
    if not storage_path.exists():
        raise RuntimeError("로그인 상태 파일이 없습니다. 먼저 `python kayak_price_crawler.py --login-setup` 실행하세요.")
    browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    ctx = await browser.new_context(
        user_agent=UA[device],
        viewport=VIEWPORT[device],
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        proxy={"server": PROXY[region]} if PROXY[region] else None,
        storage_state=str(storage_path),  # ✅ 쿠키+localStorage까지 그대로 로드 → 로그인 유지
    )
    ctx.set_default_navigation_timeout(120_000)
    ctx.set_default_timeout(120_000)
    return browser, ctx

# =========================
# 로그인 저장(최초 1회)
# =========================
async def login_setup_once():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(
            user_agent=UA["pc"],
            viewport=VIEWPORT["pc"],
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            proxy={"server": PROXY["KR"]} if PROXY["KR"] else None,
        )
        ctx.set_default_navigation_timeout(120_000)
        ctx.set_default_timeout(120_000)

        page = await ctx.new_page()
        await goto_with_retry(page, "https://www.kayak.co.kr", referer="https://www.google.com/", retries=2)

        # (있으면) 쿠키 동의 배너 닫기
        try:
            await page.locator("button:has-text('동의')").first.click(timeout=3000)
        except Exception:
            pass

        print("[로그인 설정] 브라우저에서 카약에 로그인(계정/2FA) 완료 후, 이 터미널에 Enter를 눌러 주세요.")
        input()

        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await ctx.storage_state(path=str(STORAGE_PATH))  # ✅ 파일로 저장
        print(f"[로그인 설정] 저장 완료: {STORAGE_PATH.resolve()}")

        await ctx.close(); await browser.close()

# =========================
# 크롤링 본체
# =========================
async def scrape_detail_price(ctx, region, device, ori, dst, date, pax):
    page = await ctx.new_page()
    url = kayak_search_url(ori, dst, date, pax)
    await goto_with_retry(page, url, referer="https://www.google.com/", retries=2)

    # 결과 카드 로딩 대기
    for _ in range(60):
        cnt, _ = await count_any(page, RESULT_CARD_SELECTORS)
        if cnt > 0:
            break
        await page.wait_for_timeout(1000)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f"screenshot_no_cards_{region}_{device}_{ts}.png", full_page=True)
        raise RuntimeError("검색 결과 카드를 찾지 못함")

    cards_loc, _ = await first_locator(page, RESULT_CARD_SELECTORS)
    total = await cards_loc.count()
    target_idx = 0
    for i in range(min(total, 12)):
        try:
            txt = (await cards_loc.nth(i).inner_text()).lower()
            if "직항" in txt or "nonstop" in txt:
                target_idx = i; break
        except Exception:
            pass
    await cards_loc.nth(target_idx).click()

    # 상세 가격 대기
    for _ in range(60):
        cnt, _ = await count_any(page, PRICE_SELECTORS + ["text=원"])
        if cnt > 0:
            break
        await page.wait_for_timeout(1000)

    price_text = None
    for sel in PRICE_SELECTORS:
        try:
            els = page.locator(sel)
            n = await els.count()
            for i in range(min(n, 10)):
                t = (await els.nth(i).inner_text()).strip()
                if re.search(r"\d", t) and ("원" in t or re.search(r"[₩$€£]", t)):
                    price_text = t; break
            if price_text: break
        except Exception:
            pass

    if not price_text:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f"screenshot_no_price_{region}_{device}_{ts}.png", full_page=True)
        raise RuntimeError("가격 텍스트를 찾지 못함")

    price, currency = parse_money(price_text)
    per_person = 1 if "1인당" in (await page.content()) else None

    row = {
        "site": "kayak",
        "route": f"{ori}-{dst}",
        "date": date,
        "pax": pax,
        "price": price,
        "currency": currency or "KRW",
        "meta": json.dumps({
            "raw_price_text": price_text,
            "url": page.url,
            "region": region,
            "device": device,
            "per_person": per_person,
        }, ensure_ascii=False),
        "region": region,
        "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close()
    return row

# =========================
# 실행(once/scheduler)
# =========================
async def run_once():
    combos = [
        {"region": "KR", "device": "pc"},
        {"region": "KR", "device": "mobile"},
        {"region": "US", "device": "pc"},
        {"region": "US", "device": "mobile"},
    ]
    results = []
    async with async_playwright() as pw:
        async def worker(combo):
            try:
                browser, ctx = await new_browser_context(pw, combo["region"], combo["device"], STORAGE_PATH)
                try:
                    row = await scrape_detail_price(ctx, combo["region"], combo["device"], ORI, DST, DATE, PAX)
                    results.append(row)
                    print(f"[OK] {combo} -> {row['price']} {row['currency']}")
                finally:
                    await ctx.close(); await browser.close()
            except Exception as e:
                print(f"[FAIL] {combo}: {e}")

        await asyncio.gather(*[worker(c) for c in combos])

    if results:
        df = pd.DataFrame(results)
        if CSV_PATH.exists():
            old = pd.read_csv(CSV_PATH)
            pd.concat([old, df], ignore_index=True).to_csv(CSV_PATH, index=False)
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

# =========================
# 엔트리포인트
# =========================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="브라우저에서 로그인 후 storage_state 저장")
    p.add_argument("--once", action="store_true", help="4조합 1회만 실행하고 종료")
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