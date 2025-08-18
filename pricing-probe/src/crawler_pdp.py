import re, io
from playwright.sync_api import sync_playwright
from selectolax.parser import HTMLParser
from PIL import Image
import pytesseract

from .utils_common import jitter, clean_price_text
from .artifacts import artifact_paths, save_html, save_binary, save_csv

def _ua_from_preset(ua_presets, key):
    return ua_presets.get(key, ua_presets.get("desktop"))

def build_browser_context(pw, profile, ua_presets, proxy_url=None):
    user_agent = _ua_from_preset(ua_presets, profile.get("user_agent", "desktop"))
    locale = profile.get("accept_language", "en-US,en;q=0.9")
    tz = profile.get("timezone", "UTC")
    context_args = {
        "user_agent": user_agent,
        "locale": locale,
        "timezone_id": tz,
        "viewport": {"width": 1366, "height": 768} if profile.get("user_agent")=="desktop" else {"width": 390, "height": 844},
    }
    if proxy_url:
        context_args["proxy"] = {"server": proxy_url}
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(**context_args)
    return browser, context

def try_click_cookie_consent(page):
    selectors = ['#onetrust-accept-btn-handler','button#onetrust-accept-btn-handler','button:has-text("동의")','button:has-text("Accept")','[data-testid="cookie-accept"]']
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.click(timeout=1000)
                page.wait_for_timeout(300)
                break
        except Exception:
            pass

def wait_price_candidates(page):
    candidates = ["span[data-selenium='finalPrice']","span.final-price","span[data-component='Price'] span","[data-selenium='PriceDisplay'] span",".PriceDisplay span","div[data-selenium='room-grid-item']"]
    for sel in candidates:
        try:
            page.wait_for_selector(sel, timeout=5000)
            return sel
        except Exception:
            continue
    return None

def scan_text_for_krw(text):
    for p in [r"₩\s*([\d,]+(?:\.\d+)?)", r"([\d,]+(?:\.\d+)?)\s*원"]:
        m = re.search(p, text)
        if m:
            raw = m.group(0)
            num = m.group(1).replace(',', '')
            return num, raw
    return None, None

def scan_text_for_currency(text):
    patterns = [
        (r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", 'USD'),
        (r"₩\s*([\d,]+(?:\.\d+)?)", 'KRW'),
        (r"([\d,]+(?:\.\d+)?)\s*원", 'KRW'),
        (r"€\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{2})?)", 'EUR'),
    ]
    for patt, cur in patterns:
        m = re.search(patt, text or "")
        if m:
            raw = m.group(0)
            num = m.group(1).replace(',', '')
            return num, raw, cur
    return None, None, None

def dom_extract_price(html: str, selectors_conf: dict):
    tree = HTMLParser(html)
    for sel in selectors_conf.get("dom", {}).get("price", []):
        css = sel.get("css")
        if not css:
            continue
        node = tree.css_first(css)
        if node:
            text = node.text(strip=True)
            price = clean_price_text(text)
            if price:
                return price, text
    return None, None

def dom_extract_offers(html: str, selectors_conf: dict):
    tree = HTMLParser(html)
    res = []
    dom_conf = selectors_conf.get("dom", {}) or {}
    cards_sel = dom_conf.get("room_card", [])
    fields = dom_conf.get("fields", {})

    def get_text(node, sel_list):
        for s in sel_list or []:
            css = s.get("css")
            attr = s.get("attr")
            if not css:
                continue
            n = node.css_first(css)
            if n:
                if attr:
                    # attr 속성이 있으면 해당 속성값을 반환
                    t = n.attributes.get(attr)
                    if t:
                        return t
                else:
                    # 기존처럼 텍스트 반환
                    t = n.text(strip=True)
                    if t:
                        return t
        return None

    def get_many(node, sel_list):
        out = []
        for s in sel_list or []:
            css = s.get("css")
            if not css:
                continue
            for n in node.css(css):
                t = n.text(strip=True)
                if t:
                    out.append(t)
        return out

    def fallback_price_in_card(card_node):
        texts = []
        for n in card_node.css("*"):
            t = n.text(strip=True)
            if t:
                texts.append(t)
        best = None
        for t in texts:
            m = re.search(r"(₩\s*[\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?\s*원)", t)
            if m:
                score = 0
                if any(k in t for k in ["총","합계","세금","포함","total","Final","final"]):
                    score += 2
                if any(k in t for k in ["/박","1박","per night"]):
                    score += 1
                num = clean_price_text(t)
                if num:
                    cand = (score, float(num), t)
                    if best is None or cand > best:
                        best = cand
        if best:
            return best[1], best[2]
        return None, None

    found_any_card = False
    for cand in cards_sel:
        css = cand.get("css")
        if not css:
            continue
        for card in tree.css(css):
            found_any_card = True
            room_name = get_text(card, fields.get("room_name"))
            badges = get_many(card, fields.get("plan_badges"))
            plan_badges = "|".join(sorted(set(badges))) if badges else None
            price_total_raw = get_text(card, fields.get("price_total"))
            price_per_night_raw = get_text(card, fields.get("price_per_night"))

            total = clean_price_text(price_total_raw or "")
            per_night = clean_price_text(price_per_night_raw or "")

            if not (total or per_night):
                total, price_total_raw = fallback_price_in_card(card)

            res.append({
                "room_name": room_name,
                "plan_badges": plan_badges,
                "price_total": float(total) if total else None,
                "price_per_night": float(per_night) if per_night else None,
                "price_total_raw": price_total_raw,
                "price_per_night_raw": price_per_night_raw,
            })
    return res if (found_any_card and res) else None

def dom_extract_kayak_offers(html: str, selectors_conf: dict):
    tree = HTMLParser(html)
    res = []
    dom_conf = selectors_conf.get("dom", {}) or {}
    cards_sel = dom_conf.get("offer_card", [])
    fields = dom_conf.get("fields", {})

    def get_text(node, sel_list):
        for s in sel_list or []:
            css = s.get("css")
            attr = s.get("attr")
            if not css:
                continue
            n = node.css_first(css)
            if n:
                if attr:
                    # attr 속성이 있으면 해당 속성값을 반환
                    t = n.attributes.get(attr)
                    if t:
                        return t
                else:
                    # 기존처럼 텍스트 반환
                    t = n.text(strip=True)
                    if t:
                        return t
        return None

    def fallback_price(node):
        txt = node.text(separator=" ", strip=True)
        for patt in [r"₩\s*([\d,]+)", r"\$\s*([\d,]+(?:\.\d+)?)"]:
            m = re.search(patt, txt)
            if m:
                return m.group(1).replace(",", ""), m.group(0)
        return None, None

    found = False
    for cand in cards_sel:
        css = cand.get("css")
        if not css:
            continue
        for card in tree.css(css):
            found = True
            itinerary = get_text(card, fields.get("itinerary"))
            price_raw = get_text(card, fields.get("price_total"))
            stops = get_text(card, fields.get("stops"))
            duration = get_text(card, fields.get("duration"))

            price_num = clean_price_text(price_raw or "")
            if not price_num:
                price_num, price_raw = fallback_price(card)

            if price_num:
                res.append({
                    "itinerary": itinerary,
                    "stops": stops,
                    "duration": duration,
                    "price_total": float(price_num),
                    "price_total_raw": price_raw,
                })
    return res if (found and res) else None

def dom_extract_amazon_price(html: str, selectors_conf: dict):
    tree = HTMLParser(html)
    for sel in selectors_conf.get("dom", {}).get("price_total", []):
        css = sel.get("css")
        if not css:
            continue
        node = tree.css_first(css)
        if node:
            text = node.text(strip=True)
            price = clean_price_text(text)
            if price:
                return price, text
    return None, None

def dom_extract_kayak_min_header(html: str, selectors_conf: dict):
    tree = HTMLParser(html)
    dom_conf = selectors_conf.get("dom", {}) or {}
    hdr_list = dom_conf.get("min_price_header", [])
    for s in hdr_list:
        css = s.get("css")
        if not css:
            continue
        node = tree.css_first(css)
        if node:
            txt = node.text(strip=True)
            from .utils_common import clean_price_text
            num = clean_price_text(txt or "")
            if num:
                return float(num), txt
    wrapper = tree.css_first("#flight-results-list-wrapper")
    if wrapper:
        t = wrapper.text(separator=" ", strip=True)
        import re as _re
        m = _re.search(r"([\d,]+)\s*원", t)
        if m:
            return float(m.group(1).replace(",", "")), m.group(0)
    return None, None

def ocr_extract_price(image_bytes: bytes):
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        txt = pytesseract.image_to_string(img, lang="eng+kor")
        pr = clean_price_text(txt)
        return pr, txt[:200]
    except Exception:
        return None, None

def detect_currency(text: str):
    if not text:
        return None
    if '₩' in text or '원' in text or 'KRW' in text.upper():
        return 'KRW'
    if '$' in text or 'USD' in text.upper():
        return 'USD'
    if '€' in text or 'EUR' in text.upper():
        return 'EUR'
    return None

def fetch_pdp(platform: str, url: str, profile: dict, ua_presets: dict, selectors_conf: dict, data_dir: str, run_ts_dir: str, proxy_url=None, sku_id="SKU"):
    with sync_playwright() as pw:
        browser, context = build_browser_context(pw, profile, ua_presets, proxy_url)
        page = context.new_page()
        jitter((0.8, 2.0))
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        try_click_cookie_consent(page)
        for _ in range(5):
            page.mouse.wheel(0, 900)
            page.wait_for_timeout(350)
        try:
            page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        wait_price_candidates(page)

        html = page.content()
        paths = artifact_paths(data_dir, platform, run_ts_dir, profile["id"], sku_id)
        save_html(paths["html"], html)
        img_bytes = page.screenshot(full_page=True, type="png")
        save_binary(paths["img"], img_bytes)

        rec_currency = "KRW" if "agoda" in platform else (detect_currency(html) or "KRW" if "kayak" in platform else "USD" )

        if "agoda" in platform:
            offers = dom_extract_offers(html, selectors_conf)
            if offers:
                header = ["ts","platform","profile_id","sku_id","room_name","plan_badges","price_total","price_per_night","currency","source","url","artifact_html","artifact_img"]
                for off in offers:
                    row = {
                        "ts": paths["ts"],
                        "platform": platform,
                        "profile_id": profile["id"],
                        "sku_id": sku_id,
                        "room_name": off.get("room_name"),
                        "plan_badges": off.get("plan_badges"),
                        "price_total": off.get("price_total"),
                        "price_per_night": off.get("price_per_night"),
                        "currency": rec_currency,
                        "source": "dom",
                        "url": url,
                        "artifact_html": paths["html"],
                        "artifact_img": paths["img"],
                    }
                    save_csv(paths["csv"], header, row)
                totals = [o.get("price_total") for o in offers if o.get("price_total") is not None]
                perns = [o.get("price_per_night") for o in offers if o.get("price_per_night") is not None]
                summary_price = (min(totals) if totals else (min(perns) if perns else None))
                record = {
                    "source": "dom-multi",
                    "price_raw": None,
                    "price": summary_price,
                    "currency": rec_currency,
                    "artifact_html": paths["html"],
                    "artifact_img": paths["img"],
                }
                context.close(); browser.close()
                return record

        elif "amazon" in platform:
            rec_currency = "USD"

            # 1) DOM: 최신/레거시 컨테이너 대기 후 파싱
            try:
                page.wait_for_selector(
                    "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen, "
                    "#apex_desktop .a-price .a-offscreen, "
                    "#corePrice_feature_div .a-price .a-offscreen, "
                    "#priceblock_ourprice, #priceblock_dealprice, #priceblock_saleprice, "
                    "#price_inside_buybox, #tp_price_block_total_price, #newBuyBoxPrice",
                    timeout=15000
                )
            except Exception:
                pass
            for _ in range(4):
                page.mouse.wheel(0, 800)
                page.wait_for_timeout(250)

            # 상위에서 이미 생성된 paths 사용 (중복 호출 방지)
            # paths는 이미 상위에서 생성되어 있음
            
            # Amazon 전용 HTML과 스크린샷은 이미 상위에서 생성됨
            # 추가로 생성하지 않음

            price_num, price_raw = dom_extract_amazon_price(html, selectors_conf)
            source = "dom" if price_num is not None else None

            # 2) 텍스트 스캔 폴백
            if price_num is None:
                try:
                    body_text = page.inner_text("body")
                except Exception:
                    body_text = ""
                num, raw, cur = scan_text_for_currency(body_text)
                if num:
                    price_num = float(num)
                    price_raw = raw
                    rec_currency = cur or rec_currency
                    source = "text-scan"

            # 3) OCR 최후 폴백
            if price_num is None:
                p, raw = ocr_extract_price(img_bytes)
                if p:
                    price_num = float(p)
                    price_raw = raw
                    source = "ocr"

            if price_num is not None:
                header = ["ts","platform","profile_id","sku_id","price_total","currency","source","url","artifact_html","artifact_img"]
                row = {
                    "ts": paths["ts"],
                    "platform": platform,
                    "profile_id": profile["id"],
                    "sku_id": sku_id,
                    "price_total": price_num,
                    "currency": rec_currency,
                    "source": source or "unknown",
                    "url": url,
                    "artifact_html": paths["html"],
                    "artifact_img": paths["img"],
                }
                save_csv(paths["csv"], header, row)
                record = {
                    "source": source or "unknown",
                    "price_raw": price_raw,
                    "price": price_num,
                    "currency": rec_currency,
                    "artifact_html": paths["html"],
                    "artifact_img": paths["img"],
                }
                context.close(); browser.close()
                return record

            # 아무 것도 못 찾은 경우
            record = {
                "source": "unknown",
                "price_raw": None,
                "price": None,
                "currency": rec_currency,
                "artifact_html": paths["html"],
                "artifact_img": paths["img"],
            }
            context.close(); browser.close()
            return record

        elif "kayak" in platform:
            # Ensure results hydrate for DOM parsing
            try:
                page.wait_for_selector("#flight-results-list-wrapper", timeout=15000)
            except Exception:
                pass
            for _ in range(8):
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(300)
            try:
                page.wait_for_selector("[data-test-id='offer-card'], [data-test-id='OfferCard'], div.resultWrapper, #flight-results-list-wrapper [aria-label='최저가 순']", timeout=12000)
            except Exception:
                pass

            offers = dom_extract_kayak_offers(html, selectors_conf)
            if offers:
                try:
                    body_text = page.inner_text("body")
                except Exception:
                    body_text = ""
                cur = detect_currency(body_text) or rec_currency
                header = ["ts","platform","profile_id","sku_id","itinerary","stops","duration","price_total","currency","source","url","artifact_html","artifact_img"]
                for off in offers:
                    row = {
                        "ts": paths["ts"],
                        "platform": platform,
                        "profile_id": profile["id"],
                        "sku_id": sku_id,
                        "itinerary": off.get("itinerary"),
                        "stops": off.get("stops"),
                        "duration": off.get("duration"),
                        "price_total": off.get("price_total"),
                        "currency": cur,
                        "source": "dom",
                        "url": url,
                        "artifact_html": paths["html"],
                        "artifact_img": paths["img"],
                    }
                    save_csv(paths["csv"], header, row)
                totals = [o.get("price_total") for o in offers if o.get("price_total") is not None]
                summary_price = min(totals) if totals else None
                record = {
                    "source": "dom-multi",
                    "price_raw": None,
                    "price": summary_price,
                    "currency": cur,
                    "artifact_html": paths["html"],
                    "artifact_img": paths["img"],
                }
                context.close(); browser.close()
                return record

            # Fallback to header min-price (DOM) extraction, still DOM-only
            min_price, min_raw = dom_extract_kayak_min_header(html, selectors_conf)
            if min_price:
                record = {
                    "source": "dom-header",
                    "price_raw": min_raw,
                    "price": float(min_price),
                    "currency": rec_currency,
                    "artifact_html": paths["html"],
                    "artifact_img": paths["img"],
                }
                context.close(); browser.close()
                return record

        # Fallback for all platforms when DOM extraction fails
        try:
            full_text = page.inner_text('body')
        except Exception:
            full_text = ''
        
        price, raw_text = scan_text_for_krw(full_text)
        if price:
            source = "text-scan"
        else:
            price, raw_text = ocr_extract_price(img_bytes)
            source = "ocr" if price else "unknown"

        rec_price = float(price) if price else None
        record = {
            "source": source,
            "price_raw": raw_text,
            "price": rec_price,
            "currency": rec_currency,
            "artifact_html": paths["html"],
            "artifact_img": paths["img"],
        }
        context.close(); browser.close()
        return record
