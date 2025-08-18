# -*- coding: utf-8 -*-
"""
Coupang 상품 상세가 수집기 (로그인 유지 지원, 미설정시 게스트로 진행)
- 최초 1회: --login-setup(선택) → storage_state 저장 (와우/쿠폰 반영 원하면 로그인 권장)
- 이후: KR/US × PC/Mobile 4조합으로 가격 수집 (US IP는 차단/리캡차 가능)
- 스케줄: 기본 0·3·6·9…시 정각 반복, --once 로 1회만 실행 가능
- 결과: ./outputs/coupang_detail_prices.csv
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
STORAGE_PATH = Path(os.getenv("STORAGE_COUPANG") or "./storage/coupang_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "coupang_detail_prices.csv"

COUPANG_URL = os.getenv("COUPANG_URL", "").strip()

UA = {
    "pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

PRICE_SELECTORS = [
    "span.total-price", "strong.total-price", "strong.price-value",
    "[data-test='point-price']", "span:has-text('원')", "strong:has-text('원')", "div:has-text('원')",
    "meta[property='og:price:amount']",
]

def seconds_until_next_3h():
    now = datetime.now()
    next_block = (now.hour // 3 + 1) * 3
    t = now.replace(minute=0, second=0, microsecond=0)
    if next_block >= 24: t = (t + timedelta(days=1)).replace(hour=0)
    else: t = t.replace(hour=next_block)
    return max(1, int((t - now).total_seconds()))

def parse_money(text: str):
    t = (text or "").replace("\u00a0", " ").strip()
    m = re.search(r"([\d.,]+)\s*원", t)
    if m: return int(re.sub(r"[^\d]", "", m.group(1))), "KRW"
    m = re.search(r"([₩$€£])\s*([\d.,]+)", t)
    if m:
        cur = {"₩":"KRW","$":"USD","€":"EUR","£":"GBP"}.get(m.group(1),"CUR")
        return int(re.sub(r"[^\d]","",m.group(2))), cur
    return None, None

async def goto_with_retry(page, url, referer=None, retries=2):
    last=None
    for _ in range(retries+1):
        try:
            await page.goto(url, wait_until="load", referer=referer); return
        except Exception as e:
            last=e; await page.wait_for_timeout(3000)
    raise last

async def new_context(pw, region: str, device: str):
    browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    storage = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
    ctx = await browser.new_context(
        user_agent=UA[device], viewport=VIEWPORT[device], locale="ko-KR", timezone_id="Asia/Seoul",
        proxy={"server": PROXY[region]} if PROXY[region] else None, storage_state=storage
    )
    ctx.set_default_navigation_timeout(120_000); ctx.set_default_timeout(120_000)
    return browser, ctx

async def login_setup_once():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        ctx = await browser.new_context(user_agent=UA["pc"], viewport=VIEWPORT["pc"], locale="ko-KR", timezone_id="Asia/Seoul",
                                        proxy={"server": PROXY["KR"]} if PROXY["KR"] else None)
        ctx.set_default_navigation_timeout(120_000); ctx.set_default_timeout(120_000)
        page = await ctx.new_page()
        await goto_with_retry(page, "https://www.coupang.com/", referer="https://www.google.com/")
        print("[로그인 설정] 쿠팡 로그인(와우/2FA 포함) 완료 후 터미널에 Enter"); input()
        await ctx.storage_state(path=str(STORAGE_PATH))
        print(f"[로그인 설정] 저장 완료: {STORAGE_PATH.resolve()}")
        await ctx.close(); await browser.close()

async def scrape_once(ctx, region, device, url: str):
    page = await ctx.new_page()
    await goto_with_retry(page, url, referer="https://www.google.com/")
    # 캡차/차단 체크(간단)
    if "captcha" in page.url.lower():
        raise RuntimeError("쿠팡이 봇/해외 접속으로 차단했습니다. KR 프록시 또는 수동 통과 필요.")

    # 가격 대기
    for _ in range(60):
        try:
            if await page.locator("meta[property='og:price:amount']").count() > 0: break
        except: pass
        for sel in PRICE_SELECTORS:
            try:
                if await page.locator(sel).count() > 0: break
            except: pass
        else:
            await page.wait_for_timeout(1000); continue
        break

    # meta 우선
    price_text = None
    try:
        amount = await page.locator("meta[property='og:price:amount']").first.get_attribute("content")
        currency = await page.locator("meta[property='og:price:currency']").first.get_attribute("content")
        if amount: price_text = f"{amount} {currency or ''}"
    except: pass

    if not price_text:
        for sel in PRICE_SELECTORS:
            try:
                els = page.locator(sel); n = await els.count()
                for i in range(min(n, 12)):
                    t = (await els.nth(i).inner_text()).strip()
                    if re.search(r"\d", t) and ("원" in t or re.search(r"[₩$€£]", t)):
                        price_text = t; break
                if price_text: break
            except: pass

    if not price_text:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await page.screenshot(path=f"screenshot_coupang_no_price_{region}_{device}_{ts}.png", full_page=True)
        raise RuntimeError("가격 텍스트를 찾지 못함")

    price, currency = parse_money(price_text)
    row = {
        "site": "coupang",
        "item": urlparse(page.url).path,
        "price": price,
        "currency": currency or "KRW",
        "meta": json.dumps({"raw_price_text": price_text, "url": page.url}, ensure_ascii=False),
        "region": region, "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close(); return row

async def run_once():
    if not COUPANG_URL: raise RuntimeError("COUPANG_URL(.env)이 비어있어요.")
    combos = [{"region":"KR","device":"pc"},{"region":"KR","device":"mobile"},{"region":"US","device":"pc"},{"region":"US","device":"mobile"}]
    results=[]
    async with async_playwright() as pw:
        async def worker(c):
            try:
                browser, ctx = await new_context(pw, c["region"], c["device"])
                try:
                    r = await scrape_once(ctx, c["region"], c["device"], COUPANG_URL); results.append(r)
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
        w = seconds_until_next_3h(); print(f"[Scheduler] 다음 실행까지 {w}초 대기 (0·3·6·9…시).")
        await asyncio.sleep(w); await run_once()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="브라우저에서 쿠팡 로그인 후 storage_state 저장(선택)")
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
