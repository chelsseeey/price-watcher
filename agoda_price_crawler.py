# agoda_price_crawler.py
import os, re, json, argparse, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

from dotenv import load_dotenv
import pandas as pd
from playwright.async_api import async_playwright

load_dotenv()

# -------------------------
# 환경설정
# -------------------------
PROXY = {"KR": os.getenv("PROXY_KR") or None, "US": os.getenv("PROXY_US") or None}
PROXY_USER = {"KR": os.getenv("PROXY_KR_USER"), "US": os.getenv("PROXY_US_USER")}
PROXY_PASS = {"KR": os.getenv("PROXY_KR_PASS"), "US": os.getenv("PROXY_US_PASS")}

STORAGE_PATH = Path(os.getenv("STORAGE_AGODA") or "./storage/agoda_login.json")
STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)

OUT_DIR = Path("./outputs"); OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_PATH = OUT_DIR / "agoda_detail_prices.csv"

AGODA_URL = os.getenv("AGODA_URL", "").strip()

UA = {
    "pc": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "mobile": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
}
VIEWPORT = {"pc": {"width": 1366, "height": 768}, "mobile": {"width": 390, "height": 844}}

# 후보 셀렉터(백업용)
PRICE_SELECTORS = [
    "[data-selenium*='price']",
    "[data-selenium*='finalPrice']",
    "[data-selenium*='grandTotal']",
    "[class*='Price']",
    "span:has-text('원')",
    "div:has-text('원')",
    "strong:has-text('원')",
    "[data-testid*='price']",
]

# -------------------------
# 유틸리티
# -------------------------
"""
def seconds_until_next_1h():
    now = datetime.now()
    base = now.replace(minute=0, second=0, microsecond=0)
    run_time = base + timedelta(hours=1)
    return max(1, int((run_time - now).total_seconds())) """
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
    if text is None:
        return None, None
    t = str(text)
    # 공백류 정규화
    t = t.replace("\u00a0", " ").replace("\u202f", " ").strip()

    # 1) "#### 원" 패턴
    m = re.search(r"([\d.,]+)\s*원", t)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(1))
        if digits:
            return int(digits), "KRW"

    # 2) 통화기호 + 숫자
    m = re.search(r"([₩$€£])\s*([\d.,]+)", t)
    if m:
        digits = re.sub(r"[^\d]", "", m.group(2))
        if digits:
            cur = {"₩": "KRW", "$": "USD", "€": "EUR", "£": "GBP"}.get(m.group(1), None)
            return int(digits), cur or None

    # 3) 백업: 문장 내 모든 숫자 덩어리에서 가장 긴(자릿수 큰) 것 선택
    nums = re.findall(r"[\d][\d.,]*", t)
    nums = [re.sub(r"[^\d]", "", x) for x in nums]
    nums = [x for x in nums if x]  # 빈 문자열 제거
    if nums:
        # 길이(자릿수) 큰 것을 우선, 동률이면 값이 작은 걸 선택
        nums.sort(key=lambda s: (-len(s), int(s)))
        return int(nums[0]), None

    return None, None


def parse_meta_from_url(url: str):
    try:
        q = parse_qs(urlparse(url).query)
        return {
            "checkin": (q.get("checkin") or [""])[0],
            "checkout": (q.get("checkout") or [""])[0],
            "adults": (q.get("adults") or [""])[0],
            "rooms": (q.get("rooms") or [""])[0],
        }
    except Exception:
        return {}

async def goto_with_retry(page, url, referer=None, retries=3):
    last=None
    for _ in range(retries+1):
        try:
            await page.goto(url, wait_until="domcontentloaded", referer=referer)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except:
                pass
            return
        except Exception as e:
            last=e
            await page.wait_for_timeout(3000)
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

async def get_attr_or_none(page, selector: str, name: str, timeout: int = 1500):
    try:
        if hasattr(page, "is_closed") and page.is_closed(): return None
        loc = page.locator(selector).first
        try:
            if await loc.count() == 0: return None
        except: return None
        return await loc.get_attribute(name, timeout=timeout)
    except Exception: return None

def _walk_price(obj):
    try:
        if isinstance(obj, dict):
            for k in ["price", "priceAmount", "amount", "totalPrice", "finalPrice", "grandTotal", "value", "amountTotal"]:
                if k in obj and isinstance(obj[k], (int, float, str)):
                    val, cur = parse_money(str(obj[k]))
                    if val:
                        cur2 = obj.get("priceCurrency") or obj.get("currency") or obj.get("currencyCode")
                        if cur is None and cur2: cur = cur2
                        return val, cur
            if "offers" in obj:
                val = _walk_price(obj["offers"])
                if val: return val
            for v in obj.values():
                val = _walk_price(v)
                if val: return val
        elif isinstance(obj, list):
            for it in obj:
                val = _walk_price(it)
                if val: return val
    except Exception:
        return None
    return None

async def extract_price_json(page):
    # 1) JSON-LD
    try:
        n = await page.locator("script[type='application/ld+json']").count()
        for i in range(n):
            try:
                txt = await page.locator("script[type='application/ld+json']").nth(i).inner_text()
                data = json.loads(txt)
                found = _walk_price(data)
                if found:
                    v, c = found
                    return v, c, "ld+json"
            except Exception:
                pass
    except Exception:
        pass
    # 2) Next.js
    for sel in ["script#__NEXT_DATA__", "script[id*='__NEXT_DATA__']"]:
        try:
            txt = await page.locator(sel).first.inner_text()
            data = json.loads(txt)
            found = _walk_price(data)
            if found:
                v, c = found
                return v, c, "__NEXT_DATA__"
        except Exception:
            pass
    return None, None, None

async def scroll_soft(page, steps=6, dy=1000, pause=400):
    for _ in range(steps):
        try:
            await page.mouse.wheel(0, dy)
        except Exception:
            pass
        await page.wait_for_timeout(pause)

# === 모바일 전용: 가시성/취소선/쿠폰 배제 + '1박당' 근접 스코어 ===
async def _pick_price_v2(page):
    bad_kw = ["할인", "적용됨", "쿠폰", "리워드", "캐시백", "%", "즉시 할인"]
    candidates = await page.evaluate("""
    (badKw) => {
      const getText = (el) => (el.innerText || el.textContent || "").trim();
      const isVisible = (el) => {
        const st = getComputedStyle(el);
        if (st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity || "1") < 0.2) return false;
        const r = el.getBoundingClientRect();
        return (r.width > 0 && r.height > 0);
      };
      const hasLineThrough = (el) => {
        const st = getComputedStyle(el);
        if ((st.textDecorationLine || "").includes("line-through")) return true;
        for (let p = el; p; p = p.parentElement) {
          const c = (p.className || "").toString().toLowerCase();
          if (c.includes("strike") || c.includes("original") || c.includes("wasprice")) return true;
          const st2 = getComputedStyle(p);
          if ((st2.textDecorationLine || "").includes("line-through")) return true;
        }
        return false;
      };
      const includesBad = (t) => badKw.some(k => t.includes(k));

      const all = Array.from(document.querySelectorAll("*")).filter(isVisible);
      const moneyRegex = /([₩$€£]\\s*)?[\\d.,]+\\s*원?/;
      const hasNightLabel = (el) => {
        const txt = (getText(el) || "");
        if (txt.includes("1박당") || txt.includes("1박 당") || txt.toLowerCase().includes("per night")) return true;
        for (let p = el.parentElement; p; p = p.parentElement) {
          const t = getText(p);
          if (t.includes("1박당") || t.includes("1박 당") || t.toLowerCase().includes("per night")) return true;
        }
        return false;
      };

      const items = [];
      for (const el of all) {
        const t = getText(el).replace(/\\u00a0|\\u202f/g, " ").trim();
        if (!moneyRegex.test(t)) continue;
        if (includesBad(t)) continue;
        if (hasLineThrough(el)) continue;
        if (el.getAttribute("aria-hidden") === "true" || el.getAttribute("aria-hidden") === "1") continue;

        const st = getComputedStyle(el);
        let score = parseFloat(st.fontSize || "14");
        if (hasNightLabel(el)) score += 50;
        items.push({ text: t, score });
      }
      return items;
    }
    """, bad_kw)

    scored = []
    for it in candidates:
        val, cur = parse_money(it["text"])
        if not val:
            continue
        scored.append((it["score"], val, cur, it["text"]))

    if not scored:
        return None
    scored.sort(key=lambda x: (-x[0], x[1]))  # 점수↓, 동점이면 금액↑중 최소
    return scored[0][3]

# -------------------------
# 브라우저/컨텍스트
# -------------------------
async def new_context(pw, region: str, device: str):
    if not STORAGE_PATH.exists():
        raise RuntimeError("로그인 상태 파일이 없습니다. 먼저 --login-setup 실행하세요.")
    browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
    proxy_cfg = {"server": PROXY[region]} if PROXY[region] else None
    if proxy_cfg and PROXY_USER[region] and PROXY_PASS[region]:
        proxy_cfg["username"] = PROXY_USER[region]
        proxy_cfg["password"] = PROXY_PASS[region]
    ctx = await browser.new_context(
        user_agent=UA[device], viewport=VIEWPORT[device],
        locale="ko-KR", timezone_id="Asia/Seoul",
        proxy=proxy_cfg, storage_state=str(STORAGE_PATH)
    )
    ctx.set_default_navigation_timeout(180_000)
    ctx.set_default_timeout(180_000)
    return browser, ctx

# -------------------------
# 로그인 저장(최초 1회)
# -------------------------
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
        await goto_with_retry(page, "https://www.agoda.com/ko-kr/", referer="https://www.google.com/")
        # 쿠키 동의/팝업 닫기(있으면)
        for txt in ["동의", "同意", "Accept", "확인", "OK"]:
            try:
                await page.locator(f"button:has-text('{txt}')").first.click(timeout=2000)
            except: pass
        print("[로그인 설정] 아고다 로그인 완료 후 터미널에 Enter"); input()
        await ctx.storage_state(path=str(STORAGE_PATH))
        print(f"[로그인 설정] 저장 완료: {STORAGE_PATH.resolve()}")
        await ctx.close(); await browser.close()

# -------------------------
# 본 수집
# -------------------------
async def scrape_once(ctx, region, device, url: str):
    page = await ctx.new_page()
    await goto_with_retry(page, url, referer="https://www.google.com/")

    # 간단 차단/봇 감지
    try:
        body = (await page.content()).lower()
        if "captcha" in body or "are you a robot" in body or "bot" in body:
            raise RuntimeError("Agoda가 봇/해외 접속으로 차단했습니다. 프록시/수동 통과 필요.")
    except Exception: pass

    # 로딩/레이지로드
    await scroll_soft(page, steps=6, dy=1000, pause=400)

    # 1) DOM 대기
    for _ in range(45):
        seen = False
        for sel in PRICE_SELECTORS:
            try:
                if await page.locator(sel).count() > 0:
                    seen = True; break
            except:
                pass
        if seen: break
        await page.wait_for_timeout(1000)

    # 2) 모바일 우선 추출(가시/근접/취소선·쿠폰 제외)
    price_text = None
    if device == "mobile":
        price_text = await _pick_price_v2(page)

    # 3) 백업(PC/모바일 공통, 취소선/쿠폰 제외)
    if not price_text:
        for sel in PRICE_SELECTORS:
            try:
                els = page.locator(sel); n = await els.count()
                for i in range(min(n, 40)):
                    e = els.nth(i)
                    t = (await e.inner_text()).strip()
                    if not (re.search(r"\d", t) and ("원" in t or re.search(r"[₩$€£]", t))):
                        continue
                    deco = await e.evaluate("el => getComputedStyle(el).textDecorationLine || ''")
                    if "line-through" in (deco or ""):
                        continue
                    cls = (await e.get_attribute("class") or "").lower()
                    if any(k in cls for k in ["strike","original","before","wasprice"]):
                        continue
                    if any(k in t for k in ["할인", "적용됨", "쿠폰", "리워드", "캐시백", "%", "즉시 할인"]):
                        continue
                    price_text = t; break
                if price_text: break
            except:
                pass

    # 4) JSON 백업
    price_from = None
    if not price_text:
        v, c, source = await extract_price_json(page)
        if v:
            price_text = f"{v} {c or ''}"
            price_from = source

    if not price_text:
        await save_artifacts(page, f"screenshot_agoda_no_price_{region}_{device}")
        raise RuntimeError("가격 텍스트를 찾지 못함")

    price, currency = parse_money(price_text)
    meta = parse_meta_from_url(page.url)
    meta.update({
        "raw_price_text": price_text,
        "url": page.url,
        "from": price_from or "dom",
    })
    row = {
        "site": "agoda",
        "item": urlparse(page.url).path,
        "price": price,
        "currency": (currency or "KRW"),
        "meta": json.dumps(meta, ensure_ascii=False),
        "region": region, "device": device,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    await page.close(); return row

# -------------------------
# 실행(once/scheduler)
# -------------------------
async def run_once(serial: bool = False):
    if not AGODA_URL: raise RuntimeError("AGODA_URL(.env)이 비어있어요.")
    combos = [
        {"region":"KR","device":"pc"},
        {"region":"KR","device":"mobile"},
        {"region":"US","device":"pc"},
        {"region":"US","device":"mobile"},
    ]
    results = []
    async with async_playwright() as pw:
        sem = asyncio.Semaphore(2)
        async def worker(c):
            async with sem:
                try:
                    browser, ctx = await new_context(pw, c["region"], c["device"])
                    try:
                        r = await scrape_once(ctx, c["region"], c["device"], AGODA_URL); results.append(r)
                        print(f"[OK][{c['region']}/{c['device']}] {r['price']} {r['currency']} ({json.loads(r['meta'])['from']})")
                    finally:
                        await ctx.close(); await browser.close()
                except Exception as e:
                    print(f"[FAIL]{c}: {e}")
                    return e

        if serial:
            for c in combos:
                await worker(c)
        else:
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

"""async def scheduler(serial: bool = False):
    await run_once(serial=serial)
    while True:
        wait_s = seconds_until_next_1h()
        print(f"[Scheduler] 다음 실행까지 {wait_s}초 대기")
        await asyncio.sleep(wait_s)
        await run_once(serial=serial)"""
async def scheduler(serial: bool = False):
    await run_once(serial=serial)
    while True:
        wait_s = seconds_until_next_30m()
        print(f"[Scheduler] 다음 실행까지 {wait_s}초 대기 (매 30분: :00 / :30).")
        await asyncio.sleep(wait_s)
        await run_once(serial=serial)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--login-setup", action="store_true", help="브라우저에서 아고다 로그인 후 storage_state 저장")
    p.add_argument("--once", action="store_true", help="1회만 실행 후 종료")
    p.add_argument("--serial", action="store_true", help="4조합 직렬 실행(디버그용)")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    try:
        if args.login_setup: asyncio.run(login_setup_once())
        elif args.once: asyncio.run(run_once(serial=args.serial))
        else: asyncio.run(scheduler())
    except KeyboardInterrupt:
        print("\n[종료] 사용자에 의해 중단되었습니다.")
