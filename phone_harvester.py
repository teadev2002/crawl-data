import json
import time
import os
import re
import sys
import random
import base64
import unicodedata
from urllib.parse import unquote, urljoin, urlparse, parse_qs
from playwright.sync_api import sync_playwright

def strip_apartment_tag(s):
    if not s: return ""
    return re.sub(r'\s*\(\s*#\s*căn\s*[-\s]?hộ\s*\)|\s*\(\s*#\s*can\s*[-\s]?ho\s*\)', '', str(s), flags=re.IGNORECASE).strip()

def strip_vietnamese_accents(s):
    if not s: return ""
    nfkd = unicodedata.normalize('NFD', s)
    return "".join([c for c in nfkd if unicodedata.category(c) != 'Mn']).lower().strip()

def calculate_title_similarity(title1, title2):
    """Tính tỷ lệ % giống nhau giữa 2 tên cơ sở"""
    t1 = strip_vietnamese_accents(title1)
    t2 = strip_vietnamese_accents(title2)
    if not t1 or not t2:
        return 0
    words1 = set(re.findall(r'\w+', t1))
    words2 = set(re.findall(r'\w+', t2))
    if not words1 or not words2:
        return 0
    overlap = len(words1.intersection(words2))
    total = max(len(words1), len(words2))
    return int((overlap / total) * 100)

if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters);
"""

def load_config():
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

CONFIG = load_config()
TARGET_JSON_FILE = CONFIG.get("output_file", "hotels.json")

THIRD_PARTY_BLOCKLIST = [
    "booking.com", "bluepillow.com", "foody.vn", "shopeefood.vn",
    "agoda.com", "traveloka.com", "tripadvisor.com", "tripadvisor.com.vn",
    "vntrip.vn", "klook.com"
]

STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

def format_standard_record(r, default_stt=1):
    formatted = {}
    for key in STANDARD_KEYS:
        if key == "stt":
            formatted[key] = r.get("stt", default_stt)
        elif key == "isFlag":
            formatted[key] = bool(r.get("isFlag", False))
        else:
            val = r.get(key, "")
            formatted[key] = val if val is not None else ""
    return formatted

def extract_province(address: str) -> str:
    if not address or address == "N/A":
        return ""
    skip_words = {"vietnam", "viet nam", "việt nam", "vn"}
    parts = [p.strip() for p in address.split(',') if p.strip()]
    for part in reversed(parts):
        if part.lower() in skip_words:
            continue
        if part.replace(' ', '').isdigit():
            continue
        cleaned = re.sub(r'\s+\d{4,6}$', '', part).strip()
        if cleaned:
            return cleaned
    return ""

def accept_google_consent(page) -> bool:
    try:
        clicked = page.evaluate("""
            () => {
                const keywords = ['accept all', 'chấp nhận tất cả', 'i agree', 'đồng ý', 'agree', 'accept', 'chấp nhận'];
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    const txt = (btn.innerText || btn.textContent || '').toLowerCase().trim();
                    if (keywords.some(k => txt.includes(k))) {
                        btn.click();
                        return true;
                    }
                }
                const form = document.querySelector('form[action*="consent"]');
                if (form) {
                    const sub = form.querySelector('button[type="submit"], input[type="submit"]');
                    if (sub) { sub.click(); return true; }
                }
                return false;
            }
        """)
        if clicked:
            time.sleep(1.5)
            return True
    except Exception:
        pass
    return False

def check_and_handle_captcha(page):
    try:
        current_url = page.url.lower()
        is_captcha = "google.com/sorry" in current_url
        if not is_captcha:
            if page.locator('#captcha-form, .g-recaptcha, iframe[src*="recaptcha"]').count() > 0:
                is_captcha = True
                
        if is_captcha:
            print("\n" + "=" * 65)
            print("[!] PHÁT HIỆN CAPTCHA GOOGLE (google.com/sorry/index)!")
            print("[*] Tạm dừng 3 giây để người dùng thao tác giải Captcha...")
            for sec in range(3, 0, -1):
                print(f"    -> Đang chờ: {sec} giây...  ", end="\r")
                time.sleep(1)
            print("\n[*] Hết 3 giây tạm dừng. Tiếp tục tiến trình...\n")
            return True
    except Exception:
        pass
    return False

def extract_vietnam_phone_numbers(text: str) -> list[str]:
    """
    Trích xuất và chuẩn hóa các số điện thoại hợp lệ của Việt Nam từ chuỗi văn bản.
    """
    if not text:
        return []
    raw_matches = re.findall(r'(?:\+?84|0)[\s.-]?(?:\(?\d{2,4}\)?)[\s.-]?\d{3,4}[\s.-]?\d{3,4}', text)
    found = []
    for m in raw_matches:
        digits = re.sub(r'\D', '', m)
        if digits.startswith('84'):
            digits = '0' + digits[2:]
        if len(digits) in [10, 11] and digits.startswith(('03', '05', '07', '08', '09', '02', '01')):
            if digits not in found:
                found.append(digits)
    return found

def merge_phone_numbers(existing_phone: str, new_phone: str) -> tuple[str, bool]:
    """
    Nếu existing_phone rỗng -> gán new_phone.
    Nếu existing_phone đã có và new_phone chưa có -> ghép nối dạng "existing | new_phone".
    Nếu new_phone trùng -> giữ nguyên. Trả về (updated_phone, is_changed).
    """
    if not new_phone or new_phone.strip() == "":
        return existing_phone, False
    
    existing_clean = (existing_phone or "").strip()
    new_clean = new_phone.strip()

    if not existing_clean:
        return new_clean, True

    existing_list = [p.strip() for p in existing_clean.split('|') if p.strip()]

    def to_canonical(p):
        d = re.sub(r'\D', '', p)
        if d.startswith('84'):
            d = '0' + d[2:]
        return d

    canonical_existing = [to_canonical(p) for p in existing_list]
    canonical_new = to_canonical(new_clean)

    if canonical_new in canonical_existing:
        return existing_clean, False

    updated_phone = f"{existing_clean} | {new_clean}"
    return updated_phone, True

def merge_source(existing_source: str, phone_source_tag: str) -> str:
    existing_clean = (existing_source or "").strip()
    tag_clean = (phone_source_tag or "").strip()
    
    if not tag_clean:
        return existing_clean
    if not existing_clean:
        return tag_clean
    if tag_clean in existing_clean:
        return existing_clean
    return f"{existing_clean} | {tag_clean}"

def extract_fb_url_from_page(page, engine: str = "generic") -> str | None:
    locators_to_try = []
    if engine == "google":
        locators_to_try = ['#rso a', 'div.g a', '.MjjYud a', 'a']
    elif engine == "bing":
        locators_to_try = ['#b_results li.b_algo a', '.b_algo a', 'a']
    elif engine == "ddg":
        locators_to_try = ['.results a', '.result a', '#links a', 'a']
    else:
        locators_to_try = ['#rso a', '#b_results li.b_algo a', '.results a', 'a']

    candidate_links = []
    for loc in locators_to_try:
        try:
            links = page.locator(loc).all()
            if links:
                candidate_links.extend(links)
                if loc != 'a':
                    break
        except Exception:
            continue

    if not candidate_links:
        try:
            candidate_links = page.locator('a').all()
        except Exception:
            candidate_links = []

    for link in candidate_links:
        try:
            is_copilot = False
            try:
                is_copilot = page.evaluate("""
                    (el) => {
                        let curr = el;
                        while (curr && curr !== document.body) {
                            const idStr   = (curr.id || '').toLowerCase();
                            const clsStr  = (curr.className || '').toString().toLowerCase();
                            const tagName = (curr.tagName || '').toLowerCase();
                            if (
                                idStr.includes('copilot') || clsStr.includes('copilot') ||
                                idStr.includes('sydney')  || clsStr.includes('sydney')  ||
                                idStr.includes('ai_')     || clsStr.includes('ai-overview') ||
                                tagName.includes('cib-')
                            ) {
                                return true;
                            }
                            curr = curr.parentElement;
                        }
                        return false;
                    }
                """, link.element_handle())
            except Exception:
                pass

            if is_copilot:
                continue

            href = link.get_attribute('href') or ''
            href_lower = href.lower()
            actual_href = href

            if '/url?q=' in href_lower or '/url?q=' in href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    if 'q' in qs:
                        actual_href = unquote(qs['q'][0])
                except Exception:
                    pass
            elif 'uddg=' in href_lower or 'uddg=' in href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    if 'uddg' in qs:
                        actual_href = unquote(qs['uddg'][0])
                except Exception:
                    pass
            elif 'bing.com/ck/a' in href_lower and 'u=a1' in href_lower:
                try:
                    qs = parse_qs(urlparse(href).query)
                    if 'u' in qs:
                        u_val = qs['u'][0]
                        if u_val.startswith('a1'):
                            raw_b64 = u_val[2:] + '=='
                            decoded = base64.b64decode(raw_b64).decode('utf-8', errors='ignore')
                            if 'facebook.com' in decoded.lower():
                                actual_href = decoded
                except Exception:
                    pass

            actual_lower = actual_href.lower()
            if (
                'facebook.com/' in actual_lower
                and 'google.com' not in actual_lower
                and 'bing.com' not in actual_lower
                and 'duckduckgo.com' not in actual_lower
                and 'microsoft.com' not in actual_lower
                and 'copilot' not in actual_lower
                and '/l.php' not in actual_lower
                and not any(block in actual_lower for block in ["/sharer", "/share", "/dialog", "/groups", "/events", "/ads", "/help", "/login", "/policies"])
            ):
                return actual_href
        except Exception:
            continue
    return None

def crawl_website_for_phone(page, url):
    if not url or any(block_domain in url.lower() for block_domain in THIRD_PARTY_BLOCKLIST):
        return None, ""

    print(f"  -> Đang truy cập trang web cào phone: {url}")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1.5)
        
        content = page.content()
        phones = extract_vietnam_phone_numbers(content)
        if phones:
            return phones[0], f"phone_web: {url}"

        contact_links = page.locator('a[href*="contact"], a[href*="lien-he"], a[href*="gioi-thieu"], a[href*="about"]').all()
        for link in contact_links[:2]:
            try:
                sub_url = link.get_attribute('href')
                if sub_url:
                    full_sub_url = urljoin(url, sub_url)
                    print(f"    -> Thử kiểm tra trang con cào phone: {full_sub_url}")
                    page.goto(full_sub_url, wait_until='domcontentloaded', timeout=10000)
                    time.sleep(1.5)
                    sub_content = page.content()
                    sub_phones = extract_vietnam_phone_numbers(sub_content)
                    if sub_phones:
                        return sub_phones[0], f"phone_web: {full_sub_url}"
            except Exception:
                continue

    except Exception as e:
        print(f"    [!] Không thể truy cập trang web {url}: {e}")

    return None, ""

def extract_phone_from_facebook_dom(page, target_title: str = "") -> str | None:
    """
    Định vị trực tiếp thẻ img chứa Icon Điện thoại của Facebook (src chứa 'aa_l5zrpN2S' hoặc icon phone)
    và trích xuất SĐT từ thẻ container cha tương ứng, có kiểm tra Title Matching (h1) với target_title >= 50%.
    """
    try:
        data = page.evaluate(r"""
            () => {
                const h1El = document.querySelector('h1.html-h1, h1');
                const fbTitle = h1El ? (h1El.innerText || h1El.textContent || '').trim() : '';

                const imgs = Array.from(document.querySelectorAll('img'));
                let targetImg = imgs.find(img => {
                    const src = img.src || '';
                    return src.includes('aa_l5zrpN2S') || src.includes('aa_l5zrpN2S.webp') || (src.includes('rsrc.php') && src.includes('phone'));
                });

                if (!targetImg) {
                    const infoRows = document.querySelectorAll('div.x9f619, div[data-aria-label], div[role="main"]');
                    for (const row of infoRows) {
                        const img = row.querySelector('img');
                        if (img && img.src && (img.src.includes('aa_l5zrpN2S') || img.src.includes('phone'))) {
                            targetImg = img;
                            break;
                        }
                    }
                }

                let phoneText = '';
                if (targetImg) {
                    let parent = targetImg.closest('div.x9f619') || targetImg.closest('div.x1xmf6yo') || targetImg.parentElement;
                    if (parent && parent.parentElement) {
                        const txt = parent.innerText || parent.textContent || '';
                        if (/\d/.test(txt)) phoneText = txt;
                        else {
                            const parent2 = parent.parentElement;
                            phoneText = parent2.innerText || parent2.textContent || '';
                        }
                    } else if (parent) {
                        phoneText = parent.innerText || parent.textContent || '';
                    }
                }
                return { fbTitle: fbTitle, phoneText: phoneText };
            }
        """)

        if data and isinstance(data, dict):
            fb_title = data.get("fbTitle", "")
            phone_text = data.get("phoneText", "")

            if target_title and fb_title:
                sim = calculate_title_similarity(target_title, fb_title)
                if sim < 50:
                    print(f"    [!] Cảnh báo: Tên Fanpage Facebook ('{fb_title}') không khớp tên cơ sở mục tiêu ('{target_title}') (Độ khớp {sim}% < 50%). Bỏ qua Fanpage này!")
                    return None
                else:
                    print(f"    [✓] Xác nhận Fanpage chính chủ: '{fb_title}' khớp tên với '{target_title}' (Độ khớp: {sim}% >= 50%)")

            if phone_text:
                valid_phones = extract_vietnam_phone_numbers(phone_text)
                if valid_phones:
                    return valid_phones[0]
    except Exception:
        pass
    return None

def crawl_facebook_for_phone(page, fb_url, target_title: str = ""):
    if not fb_url or "facebook.com" not in fb_url.lower():
        return None, ""

    clean_url = fb_url.split('?')[0].rstrip('/')
    print(f"  -> Đang kiểm tra Facebook Fanpage cào phone: {clean_url}")
    try:
        page.goto(clean_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(2)
        
        # 1. Thử qua liên kết tel:
        try:
            tel_elements = page.locator('a[href^="tel:"]').all()
            for el in tel_elements:
                try:
                    href = el.get_attribute('href') or ''
                    phone_raw = href.replace('tel:', '').strip()
                    valid_phones = extract_vietnam_phone_numbers(phone_raw)
                    if valid_phones:
                        return valid_phones[0], f"phone_fb: {clean_url}"
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Định vị chính xác qua thẻ img Icon Phone aa_l5zrpN2S của Facebook kèm kiểm tra h1 >= 50%
        dom_phone = extract_phone_from_facebook_dom(page, target_title=target_title)
        if dom_phone:
            return dom_phone, f"phone_fb: {clean_url}"

        # 3. Chuyển sang trang /about và áp dụng định vị Icon Phone tương tự
        about_url = clean_url + '/about'
        page.goto(about_url, wait_until='domcontentloaded', timeout=12000)
        time.sleep(2)
        about_dom_phone = extract_phone_from_facebook_dom(page, target_title=target_title)
        if about_dom_phone:
            return about_dom_phone, f"phone_fb: {about_url}"

    except Exception as e:
        print(f"    [!] Lỗi khi cào Facebook {clean_url}: {e}")

    return None, ""

def crawl_trip_via_google_maps(page, maps_url):
    """
    Truy cập Google Maps place URL có sẵn trong bản ghi, tìm mục "Kết quả bổ sung trên web" (h2.QmVJeb),
    nhấp vào liên kết Trip.com (span.QVR4f), và trích xuất SĐT từ class chuyên dụng của Trip.com:
    .hotelContact_descriptionInfo-tel__ti6FG / .hotelContact_real-tel-text__3lcAp
    """
    if not maps_url or "google.com/maps" not in maps_url.lower():
        return None, ""

    print(f"  -> [Google Maps ➔ Trip.com] Đang truy cập Google Maps place: {maps_url[:65]}...")
    try:
        page.goto(maps_url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(2)

        # 1. Tìm mục "Kết quả bổ sung trên web" và liên kết Trip.com
        trip_link_loc = page.locator('a:has(span.QVR4f:has-text("Trip.com")), a[href*="trip.com"]:has-text("Trip.com"), a[href*="trip.com"]').first

        trip_target_url = None
        if trip_link_loc.count() > 0:
            try:
                trip_target_url = trip_link_loc.get_attribute('href')
            except Exception:
                pass

        if not trip_target_url:
            try:
                page.evaluate("""
                    () => {
                        const sidePanel = document.querySelector('div[role="main"], div.m6QErf');
                        if (sidePanel) sidePanel.scrollTop = sidePanel.scrollHeight;
                    }
                """)
                time.sleep(1.5)
                trip_link_loc = page.locator('a:has(span.QVR4f:has-text("Trip.com")), a[href*="trip.com"]').first
                if trip_link_loc.count() > 0:
                    trip_target_url = trip_link_loc.get_attribute('href')
            except Exception:
                pass

        if trip_target_url:
            print(f"    [✓] Đã tìm thấy liên kết Trip.com trong 'Kết quả bổ sung trên web': {trip_target_url[:65]}...")
            page.goto(trip_target_url, wait_until='domcontentloaded', timeout=20000)
            time.sleep(2.5)

            # 2. Định vị SĐT trên trang chi tiết Trip.com
            phone_text = page.evaluate(r"""
                () => {
                    const el = document.querySelector('.hotelContact_real-tel-text__3lcAp, .hotelContact_descriptionInfo-tel__ti6FG');
                    if (el) return el.innerText || el.textContent || '';
                    const telDivs = document.querySelectorAll('div[class*="hotelContact"], div[class*="real-tel"]');
                    for (const d of telDivs) {
                        const txt = d.innerText || d.textContent || '';
                        if (/\d/.test(txt)) return txt;
                    }
                    return '';
                }
            """)

            if phone_text:
                valid_phones = extract_vietnam_phone_numbers(phone_text)
                if valid_phones:
                    print(f"    [✓] Đã cào thành công SĐT từ Trip.com: '{valid_phones[0]}'")
                    return valid_phones[0], f"phone_trip: {trip_target_url}"
            else:
                body_text = page.locator('body').inner_text()
                valid_phones = extract_vietnam_phone_numbers(body_text)
                if valid_phones:
                    print(f"    [✓] Đã cào SĐT từ trang Trip.com (body text): '{valid_phones[0]}'")
                    return valid_phones[0], f"phone_trip: {trip_target_url}"

    except Exception as e:
        print(f"    [!] Lỗi khi cào Trip.com qua Google Maps: {e}")

    return None, ""

def search_bing_for_facebook(page, title, address):
    province = extract_province(address)
    query = f'{title} {province} facebook'.strip() if province else f'{title} facebook'
    print(f"    -> [Bing Fallback] Tìm Facebook với từ khóa: {query}")
    try:
        url_bing = f"https://www.bing.com/search?q={query.replace(' ', '+')}"
        page.goto(url_bing, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1.5)
        fb_url = extract_fb_url_from_page(page, engine="bing")
        if fb_url:
            return fb_url
    except Exception as e:
        print(f"    [!] Lỗi khi tìm Facebook trên Bing: {e}")
    return None

def search_ddg_for_facebook(page, title, address):
    province = extract_province(address)
    query = f'{title} {province} facebook'.strip() if province else f'{title} facebook'
    print(f"    -> [DuckDuckGo Fallback] Tìm Facebook với từ khóa: {query}")
    try:
        url_ddg = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        page.goto(url_ddg, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1.5)
        fb_url = extract_fb_url_from_page(page, engine="ddg")
        if fb_url:
            return fb_url
    except Exception as e:
        print(f"    [!] Lỗi khi tìm Facebook trên DuckDuckGo: {e}")
    return None

def search_google_for_facebook(page, title, address):
    province = extract_province(address)
    query = f'{title} {province} facebook'.strip() if province else f'{title} facebook'
    print(f"  -> Đang tìm Facebook trên Google với từ khóa: {query}")
    fb_url = None
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=vi"
        page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        accept_google_consent(page)
        is_captcha = check_and_handle_captcha(page)
        time.sleep(1.5)

        if not is_captcha:
            fb_url = extract_fb_url_from_page(page, engine="google")
    except Exception as e:
        print(f"    [!] Lỗi khi tìm kiếm Facebook trên Google: {e}")

    if not fb_url:
        fb_url = search_bing_for_facebook(page, title, address)

    if not fb_url:
        fb_url = search_ddg_for_facebook(page, title, address)

    return fb_url

def search_google_for_phone(page, title, address):
    province = extract_province(address)
    query = f'"{title}" sdt'
    print(f"  -> Đang tìm Phone trên Google với từ khóa: {query}")
    try:
        search_url = f"https://www.google.com/search?q={quote_plus(query)}&hl=vi"
        page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        accept_google_consent(page)
        check_and_handle_captcha(page)
        time.sleep(1.5)

        # 1. Định vị Google AI Overview tại class div.n6owBd.awi2gc
        ai_overview_text = page.evaluate(r"""
            () => {
                const nodes = document.querySelectorAll('div.n6owBd.awi2gc, div.n6owBd, div.Fzsovc');
                for (const node of nodes) {
                    const txt = (node.innerText || node.textContent || '').trim();
                    if (txt.length > 10) {
                        return txt;
                    }
                }
                return '';
            }
        """)

        if ai_overview_text:
            sim_title = calculate_title_similarity(title, ai_overview_text)
            clean_title = strip_vietnamese_accents(title)
            clean_ai = strip_vietnamese_accents(ai_overview_text)
            
            has_title_match = (sim_title >= 40) or (clean_title in clean_ai)
            
            has_province_match = True
            if province:
                clean_prov = strip_vietnamese_accents(province)
                has_province_match = (clean_prov in clean_ai)

            if has_title_match and has_province_match:
                ai_phones = extract_vietnam_phone_numbers(ai_overview_text)
                if ai_phones:
                    print(f"    [✓] Tìm thấy SĐT từ Google AI Overview (Khớp Tên & Tỉnh thành): '{ai_phones[0]}'")
                    return ai_phones[0], "phone_google: AI Overview"
            else:
                print(f"    [!] AI Overview không đủ điều kiện đối chiếu (Sim: {sim_title}%, Prov Match: {has_province_match}). Chuyển sang Snippet.")

        # 2. Đọc Snippet kết quả tìm kiếm chuẩn
        snippets_text = page.evaluate(r"""
            () => {
                const el = document.querySelector('#rso, #main, div.g');
                return el ? (el.innerText || el.textContent || '') : '';
            }
        """)
        if snippets_text:
            phones = extract_vietnam_phone_numbers(snippets_text)
            if phones:
                return phones[0], "phone_google: Snippet"
    except Exception as e:
        print(f"    [!] Lỗi khi tìm phone trên Google: {e}")

    # 3. Trip.com Fallback
    print("    -> [Trip.com Fallback] Đang thử tìm phone gian hàng trên Trip.com...")
    query_trip = f'"{title}" trip.com'
    try:
        search_url_trip = f"https://www.google.com/search?q={quote_plus(query_trip)}&hl=vi"
        page.goto(search_url_trip, wait_until='domcontentloaded', timeout=15000)
        accept_google_consent(page)
        time.sleep(1.5)

        content_trip = page.content()
        phones_trip = extract_vietnam_phone_numbers(content_trip)
        if phones_trip:
            return phones_trip[0], "phone_trip: Snippet"

        links = page.locator('a[href*="trip.com"]').all()
        trip_url = None
        for link in links:
            try:
                href = link.get_attribute('href') or ''
                if href and "trip.com" in href.lower() and "/search" not in href.lower() and "google.com" not in href.lower():
                    trip_url = href
                    break
            except Exception:
                continue

        if trip_url:
            print(f"    -> Đang truy cập liên kết Trip.com: {trip_url}")
            page.goto(trip_url, wait_until='domcontentloaded', timeout=15000)
            time.sleep(2)
            page_text = page.locator('body').inner_text()
            found_phones_trip = extract_vietnam_phone_numbers(page_text)
            if found_phones_trip:
                return found_phones_trip[0], f"phone_trip: {trip_url}"

    except Exception as e:
        print(f"    [!] Lỗi khi tìm kiếm phone trên Trip.com: {e}")

    return None, ""

def safe_read_json(file_path, retries=15, delay=0.15):
    for _ in range(retries):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        try:
                            data = json.loads(content)
                        except json.JSONDecodeError as jde:
                            if "Extra data" in str(jde):
                                data = json.loads(content[:jde.pos].strip())
                                safe_write_json(file_path, data)
                                print(f"[*] [Tự động phục hồi] Đã sửa lỗi Extra data cho file '{file_path}'.")
                            else:
                                raise
                        if isinstance(data, list):
                            return data
        except Exception:
            time.sleep(delay)
    return None

def safe_write_json(file_path, data, retries=15, delay=0.15):
    temp_file = file_path + f".tmp_{os.getpid()}"
    for _ in range(retries):
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, file_path)
            return True
        except Exception:
            time.sleep(delay)
    if os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except Exception:
            pass
    return False

def safe_save_phone(target_file, target_stt, target_title, target_url, new_phone, phone_source_tag, discovered_facebook=""):
    records = safe_read_json(target_file)
    if not records or not isinstance(records, list):
        return False, 0, 0, ""
        
    updated = False
    flagged_count = 0
    total_records = len(records)
    target_title_clean = str(target_title or "").strip().lower()
    final_phone_str = ""

    for idx, r in enumerate(records):
        if isinstance(r, dict):
            r_stt = str(r.get("stt", idx + 1))
            r_url = str(r.get("url", ""))
            r_title = str(r.get("title", "")).strip().lower()

            is_match = False
            if r_stt == str(target_stt):
                is_match = True
            elif target_url and r_url == str(target_url):
                is_match = True
            elif target_title_clean and r_title == target_title_clean:
                is_match = True

            if is_match:
                existing_p = r.get("phone", "")
                merged_p, is_changed = merge_phone_numbers(existing_p, new_phone)
                final_phone_str = merged_p

                if is_changed:
                    r["phone"] = merged_p
                    if phone_source_tag:
                        r["source"] = merge_source(r.get("source", ""), phone_source_tag)
                    updated = True

                if discovered_facebook:
                    r["facebook"] = discovered_facebook
                    if "facebook.com" in str(r.get("website", "")).lower():
                        r["website"] = ""

            if r.get("phone") and str(r.get("phone")).strip() != "":
                flagged_count += 1

    if updated:
        formatted_records = [format_standard_record(r, i + 1) for i, r in enumerate(records)]
        saved = safe_write_json(target_file, formatted_records)
        return saved, flagged_count, total_records, final_phone_str
    return False, flagged_count, total_records, final_phone_str

def harvest_phones(mode="top"):
    target_file = TARGET_JSON_FILE
    if not os.path.exists(target_file):
        print(f"[!] Không tìm thấy file dữ liệu '{target_file}' được cấu hình trong config.json.")
        print("[*] Vui lòng chạy cào địa điểm trước để tạo file này.")
        return
        
    print(f"[*] [{mode.upper()}] Đang đọc file dữ liệu cào SĐT: {target_file}")
    records = safe_read_json(target_file)

    if records is None or not isinstance(records, list):
        print(f"[!] Lỗi: Không thể đọc dữ liệu danh sách từ file '{target_file}'.")
        return
        
    formatted_records = [format_standard_record(r, idx + 1) for idx, r in enumerate(records) if isinstance(r, dict)]
    safe_write_json(target_file, formatted_records)
    records = formatted_records
        
    to_process_indices = []
    for idx, r in enumerate(records):
        if isinstance(r, dict):
            to_process_indices.append((idx, r))
        
    total_need_process = len(to_process_indices)
    midpoint = total_need_process // 2 if total_need_process > 1 else 1

    if mode == "bottom":
        target_items = list(reversed(to_process_indices[midpoint:])) if total_need_process > 1 else to_process_indices
        print(f"[*] Chế độ quét SĐT: LUỒNG BOTTOM (CHROMIUM ẢO - QUÉT TỪ DƯỚI LÊN). Quét {len(target_items)} bản ghi thuộc nửa sau...")
    elif mode == "top":
        target_items = to_process_indices[:midpoint] if total_need_process > 1 else to_process_indices
        print(f"[*] Chế độ quét SĐT: LUỒNG TOP (CHROMIUM ẢO - QUÉT TỪ TRÊN XUỐNG). Quét {len(target_items)} bản ghi thuộc nửa đầu...")
    else:
        target_items = to_process_indices
        print(f"[*] Chế độ quét SĐT: ĐƠN LUỒNG (CHROMIUM ẢO). Quét {len(target_items)} bản ghi...")
    
    print(f"[*] [PHONE_HARVEST] Tổng số bản ghi trong file: {len(records)}")
    
    if len(target_items) == 0:
        print(f"[*] [PHONE_HARVEST] [{mode.upper()}] Không có bản ghi nào cần quét. Chương trình kết thúc.")
        return

    with sync_playwright() as p:
        print(f"[*] [PHONE_HARVEST] [{mode.upper()}] Đang mở Trình duyệt ảo Chromium...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else context.new_page()

        success_count = 0
        total_items_count = len(target_items)
        for idx_in_loop, (index_in_file, item) in enumerate(target_items, 1):
            stt = item.get("stt", index_in_file + 1)
            title = item.get("title", "Không rõ tên")
            website = item.get("website", "")
            facebook = item.get("facebook", "")
            address = item.get("address", "")
            current_phone = item.get("phone", "")

            pct = (idx_in_loop / total_items_count) * 100
            print(f"[*] [PHONE_HARVEST] [{mode.upper()}] Đang xử lý STT {stt}/{len(records)}: '{title}' (SĐT hiện có: '{current_phone}')...")

            phone_found = None
            source_found = ""
            discovered_facebook = facebook

            url = item.get("url", "")

            search_title = strip_apartment_tag(title)

            # 1. Quét qua Facebook / Website chính nếu có
            if facebook and facebook.strip() != "":
                phone_found, source_found = crawl_facebook_for_phone(page, facebook, target_title=search_title)
            elif website and website.strip() != "":
                if "facebook.com" in website.lower():
                    discovered_facebook = website
                    phone_found, source_found = crawl_facebook_for_phone(page, website, target_title=search_title)
                else:
                    phone_found, source_found = crawl_website_for_phone(page, website)

            # 2. (MỚI NÂNG CẤP) Quét gian hàng Trip.com qua Google Maps place URL có sẵn
            if not phone_found and url and "google.com/maps" in url.lower():
                phone_found, source_found = crawl_trip_via_google_maps(page, url)

            # 3. Tìm Facebook qua Search Engines nếu chưa có Facebook
            if not phone_found and (not discovered_facebook or discovered_facebook.strip() == ""):
                fb_url = search_google_for_facebook(page, search_title, address)
                if fb_url:
                    discovered_facebook = fb_url
                    phone_found, source_found = crawl_facebook_for_phone(page, fb_url, target_title=search_title)

            # 4. Tìm trực tiếp qua Google Search (AI Overview & Snippets)
            if not phone_found:
                phone_found, source_found = search_google_for_phone(page, search_title, address)
            if phone_found:
                saved, flagged_count, total_recs, final_p = safe_save_phone(
                    target_file, stt, title, url, phone_found, source_found, discovered_facebook
                )
                if saved:
                    success_count += 1
                    print(f"✓ [PHONE_HARVEST] [{mode.upper()}] Real-Time Save (SĐT mới): [{title}] -> Phone: '{final_p}' (Nguồn: {source_found})")
                else:
                    print(f"[-] [PHONE_HARVEST] [{mode.upper()}] SĐT trùng hoặc không đổi: [{title}] -> Phone: '{current_phone}'")
            else:
                print(f"[-] [PHONE_HARVEST] [{mode.upper()}] Không tìm thấy SĐT mới cho STT {stt} ({title}).")

            print(f"[*] [PHONE_HARVEST] [{mode.upper()}] Hoàn thành 1 bản ghi ({idx_in_loop}/{total_items_count})")
            time.sleep(random.uniform(2.0, 3.5))

        browser.close()

    print(f"\n[+] [{mode.upper()}] QUÉT SỐ ĐIỆN THOẠI HOÀN TẤT! Đã bổ sung/cập nhật {success_count} số điện thoại mới.")

if __name__ == "__main__":
    mode = "top"
    for idx, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--mode="):
            mode = arg.split("=")[1].lower()
        elif arg == "--mode" and idx < len(sys.argv) - 1:
            mode = sys.argv[idx + 1].lower()
        elif arg.lower() in ["top", "bottom", "normal"]:
            mode = arg.lower()

    if mode not in ["top", "bottom", "normal"]:
        mode = "top"

    harvest_phones(mode)
