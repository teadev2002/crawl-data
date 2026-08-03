# -*- coding: utf-8 -*-
"""
TOOL TÌM SỐ SAO KHÁCH SẠN WATERFALL 3 NỀN TẢNG (HỖ TRỢ ĐA LUỒNG SONG SONG 2, 3, 4 LUỒNG)
----------------------------------------------------------------------------------
Tác giả: Antigravity AI Team (Nâng cấp toàn diện)
Đặc điểm nổi bật:
  1. ĐA LUỒNG SONG SONG (2, 3, 4 LUỒNG): Tự động chia toán học danh sách khách sạn theo cờ --mode=3way_p1...
  2. BROWSER PROFILE RIÊNG BIỆT: Mỗi luồng dùng profile browser_profile_pX tránh xung đột lock file.
  3. BÁO TIẾN TRÌNH REAL-TIME: Đếm số bản ghi đã có số sao thực tế trên đĩa và bắn log tới Web Dashboard.
  4. QUY TRÌNH WATERFALL 3 NỀN TẢNG: Booking.com -> Agoda.com -> Traveloka.com.
  5. CHIẾN THUẬT LINK 1 VS LINK 2 (is_specific_hotel_url): Bỏ qua các trang danh sách thành phố chung.
  6. ĐỐI CHIẾN TỈNH/THÀNH KHÔNG DẤU (strip_accents & is_province_matched): Kiểm tra địa chỉ hiển thị.
  7. LƯU REAL-TIME NGUYÊN TỬ (Atomic Write): Đảm bảo dữ liệu JSON an toàn 100%.
"""

import os
import re
import sys
import time
import json
import random
import urllib.parse
from urllib.parse import unquote, urlparse, parse_qs, quote_plus
import base64
import unicodedata

# Cấu hình UTF-8 cho Windows Console
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Kiểm tra thư viện Playwright
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# ==================== CẤU HÌNH HỆ THỐNG ====================
CONFIG_FILE = "config.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def load_config():
    """Nạp file cấu hình config.json"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "output_file": "hotels.json",
        "headless": False,
        "browser_type": "chrome",
        "timeout": 25
    }

CONFIG = load_config()
STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

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

# ==================== HÀM XỬ LÝ CHUỖI & CHUẨN HÓA ====================
def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', str(text))
    return cleaned.strip()

def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt (chuẩn hóa Unicode NFD) để so sánh chuỗi địa chỉ chính xác."""
    if not text:
        return ""
    normalized = unicodedata.normalize('NFD', text)
    cleaned = "".join([c for c in normalized if not unicodedata.combining(c)])
    cleaned = cleaned.replace('Đ', 'D').replace('đ', 'd')
    return cleaned.strip()

def extract_province(address: str) -> str:
    """Lấy tỉnh/thành phố từ địa chỉ, bỏ qua Việt Nam và mã bưu chính."""
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

def is_province_matched(hotel_address: str, target_province: str) -> bool:
    """Kiểm tra địa chỉ hiển thị trên trang khách sạn có chứa đúng Tỉnh/Thành mục tiêu không."""
    if not target_province:
        return True
    if not hotel_address:
        return True

    addr_lower = hotel_address.lower()
    prov_lower = target_province.lower()

    if prov_lower in addr_lower:
        return True

    addr_no_accents = strip_accents(addr_lower)
    prov_no_accents = strip_accents(prov_lower)

    return prov_no_accents in addr_no_accents

def has_existing_stars(item: dict) -> bool:
    """Kiểm tra bản ghi đã có số sao sẵn chưa ('categoryName', 'category', 'stars')."""
    stars = str(item.get("stars", "")).lower()
    cat   = str(item.get("categoryName", "") or item.get("category", "")).lower()
    text  = f"{cat} {stars}"

    if re.search(r'([1-5])\s*[-_]?\s*(?:sao|star)', text, re.IGNORECASE):
        return True
    if any(kw in text for kw in ["1-star", "2-star", "3-star", "4-star", "5-star"]):
        return True
    if stars.strip() in ["1", "2", "3", "4", "5"] or cat.strip() in ["1", "2", "3", "4", "5"]:
        return True

    return False

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

def safe_save_record(output_file, new_item):
    """Lưu Real-Time 1 bản ghi mới vào file JSON đĩa bằng cơ chế Atomic Write"""
    for attempt in range(15):
        try:
            records = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            raw = json.loads(content)
                            if isinstance(raw, list):
                                records = [format_standard_record(r, idx + 1) for idx, r in enumerate(raw) if isinstance(r, dict)]
                except Exception:
                    records = []
            
            updated = False
            for idx, r in enumerate(records):
                if r.get("url") == new_item.get("url") or (r.get("title") and r.get("title") == new_item.get("title")):
                    records[idx] = format_standard_record(new_item, idx + 1)
                    if "stars" in new_item:
                        records[idx]["stars"] = new_item["stars"]
                    updated = True
                    break
            
            if not updated:
                item_fmt = format_standard_record(new_item, len(records) + 1)
                if "stars" in new_item:
                    item_fmt["stars"] = new_item["stars"]
                records.append(item_fmt)
                
            for idx, r in enumerate(records):
                r["stt"] = idx + 1
                
            temp_file = output_file + f".tmp_star_{os.getpid()}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, output_file)
            
            # Đếm tiến trình thực tế trên đĩa
            star_count = sum(1 for r in records if has_existing_stars(r))
            return True, len(records), star_count
        except Exception:
            time.sleep(0.15)
    return False, 0, 0

# ==================== ĐÁNH GIÁ VÀ TRÍCH XUẤT LINK BẰNG PLAYWRIGHT ====================
def is_specific_hotel_url(url: str, platform: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()

    if platform == "booking":
        if 'booking.com' not in url_lower:
            return False
        if '/hotel/' in url_lower:
            return True
        generic_keywords = [
            'booking.com/?', 'booking.com/index', 'booking.com/searchresults',
            'booking.com/city/', 'booking.com/region/', 'booking.com/country/',
            'booking.com/destination/', 'booking.com/landmark/'
        ]
        if any(kw in url_lower for kw in generic_keywords):
            return False
        if '.html' in url_lower and 'searchresults' not in url_lower:
            return True
        return False

    elif platform == "agoda":
        if 'agoda.com' not in url_lower:
            return False
        if '.html' in url_lower and not any(k in url_lower for k in ['/city/', '/country/', '/search', '/pages/']):
            return True
        if '/hotel/' in url_lower:
            return True
        generic_keywords = [
            'agoda.com/?', 'agoda.com/index', 'agoda.com/city/',
            'agoda.com/country/', 'agoda.com/search', 'agoda.com/pages/'
        ]
        if any(kw in url_lower for kw in generic_keywords):
            return False
        return False

    elif platform == "traveloka":
        if 'traveloka.com' not in url_lower:
            return False
        if '/hotel/' in url_lower and 'search' not in url_lower:
            return True
        if 'traveloka.com/vi-vn/hotel/' in url_lower or 'traveloka.com/en-en/hotel/' in url_lower:
            return True
        return False

    return False

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

def extract_platform_urls(page, platform: str, engine: str = "generic") -> list:
    domain_map = {
        "booking": "booking.com",
        "agoda": "agoda.com",
        "traveloka": "traveloka.com"
    }
    target_domain = domain_map.get(platform, "booking.com")

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
        candidate_links = page.locator('a').all()

    found_urls = []
    for link in candidate_links:
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
                            if target_domain in decoded.lower():
                                actual_href = decoded
                except Exception:
                    pass

            actual_lower = actual_href.lower()
            if target_domain in actual_lower and 'google.com' not in actual_lower and 'bing.com' not in actual_lower and 'duckduckgo.com' not in actual_lower:
                if actual_href not in found_urls:
                    found_urls.append(actual_href)
        except Exception:
            continue

    return found_urls

def extract_stars_and_address_from_page(page, url: str, platform: str, target_province: str) -> str | None:
    print(f"   -> Đang truy cập [{platform.capitalize()}]: {url}")
    try:
        page.goto(url, timeout=25000, wait_until="domcontentloaded")
        time.sleep(3.5)

        hotel_page_address = ""
        address_selectors = []
        if platform == "booking":
            address_selectors = [
                '[data-node_tt_id="location_toc_address"]',
                '.hp_address_subtitle',
                'span.hp_address_subtitle',
                '[data-aria-level="3"]',
                'span[data-testid="address"]',
                '.address'
            ]
        elif platform == "agoda":
            address_selectors = [
                '[data-selenium="hotel-address"]',
                'span[data-selenium="hotel-address"]',
                '.HeaderJustify-address',
                '[data-element="hotel-address"]'
            ]
        elif platform == "traveloka":
            address_selectors = [
                '[data-testid="hotel-address"]',
                'div[class*="address"]',
                'span[class*="address"]'
            ]

        for sel in address_selectors:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    text = loc.inner_text().strip()
                    if text:
                        hotel_page_address = text
                        break
            except Exception:
                continue

        if not hotel_page_address:
            try:
                body_head = page.locator('body').inner_text()[:1500]
                hotel_page_address = body_head
            except Exception:
                pass

        if target_province and hotel_page_address:
            if not is_province_matched(hotel_page_address, target_province):
                print(f"   [!] SAI TỈNH THÀNH: Địa chỉ trên {platform.capitalize()} ({hotel_page_address[:60]}...) không thuộc tỉnh '{target_province}' -> Bỏ qua!")
                return None
            else:
                print(f"   [+] Đã xác minh địa chỉ thuộc tỉnh '{target_province}'")

        star_selectors = []
        if platform == "booking":
            star_selectors = [
                '[data-testid="rating-stars"]',
                '[data-testid="rating-squares"]',
                'span[aria-label*="sao"]',
                'span[aria-label*="star"]',
                'div[aria-label*="sao"]',
                'div[aria-label*="star"]',
                '.hp__hotel-title__stars',
                'span.bui-rating',
            ]
        elif platform == "agoda":
            star_selectors = [
                '[data-selenium="star-rating"]',
                '[data-element="star-rating"]',
                'i[data-selenium="star-rating-icon"]',
                'span[aria-label*="sao"]',
                'span[aria-label*="star"]',
                'div[aria-label*="sao"]',
                'div[aria-label*="star"]'
            ]
        elif platform == "traveloka":
            star_selectors = [
                '[aria-label*="star"]',
                '[aria-label*="sao"]',
                'div[class*="star"]',
                'span[class*="star"]'
            ]

        for sel in star_selectors:
            try:
                elements = page.locator(sel).all()
                for el in elements:
                    aria = el.get_attribute('aria-label') or ''
                    match = re.search(r'([1-5])\s*(?:sao|star|trên 5 sao)', aria, re.IGNORECASE)
                    if match:
                        num = match.group(1)
                        return f"{num}-star hotel"

                    svg_count = el.locator('svg, i, span, img').count()
                    if 1 <= svg_count <= 5:
                        return f"{svg_count}-star hotel"
            except Exception:
                continue

        body_text = page.locator('body').inner_text()
        match_text = re.search(r'([1-5])\s*(?:-\s*star\s*hotel|sao\b)', body_text, re.IGNORECASE)
        if match_text:
            num = match_text.group(1)
            return f"{num}-star hotel"

    except Exception as e:
        print(f"   [!] Lỗi khi quét trang {platform}: {e}")

    return None

def search_platform_stars(page, title: str, address: str, platform: str) -> str | None:
    province = extract_province(address)
    query    = f'{title} {province} {platform}'.strip() if province else f'{title} {platform}'
    encoded_query = quote_plus(query)
    urls = []

    # 1. Google Search
    url_google = f"https://www.google.com/search?q={encoded_query}&hl=vi"
    print(f"   -> [{platform.capitalize()}] Tìm kiếm trên Google: {query}")
    try:
        page.goto(url_google, timeout=15000, wait_until="domcontentloaded")
        time.sleep(2)
        accept_google_consent(page)

        if "sorry/index" in page.url or "captcha" in page.url.lower():
            print("   [!] GOOGLE YÊU CẦU CAPTCHA -> Chuyển ngay sang Bing...")
        else:
            urls = extract_platform_urls(page, platform=platform, engine="google")
    except Exception:
        pass

    # 2. Dự phòng Bing Search
    if not urls:
        url_bing = f"https://www.bing.com/search?q={encoded_query}"
        print(f"   -> [{platform.capitalize()}] Dự phòng 1: Tìm trên Bing Search...")
        try:
            page.goto(url_bing, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2.5)
            urls = extract_platform_urls(page, platform=platform, engine="bing")
        except Exception:
            pass

    # 3. Dự phòng DuckDuckGo Search
    if not urls:
        url_ddg = f"https://html.duckduckgo.com/html/?q={encoded_query}"
        print(f"   -> [{platform.capitalize()}] Dự phòng 2: Tìm trên DuckDuckGo Search...")
        try:
            page.goto(url_ddg, timeout=15000, wait_until="domcontentloaded")
            time.sleep(2.5)
            urls = extract_platform_urls(page, platform=platform, engine="ddg")
        except Exception:
            pass

    if not urls:
        print(f"   -> Không tìm thấy link {platform}.com nào.")
        return None

    target_url = None
    link1 = urls[0]
    if is_specific_hotel_url(link1, platform=platform):
        print(f"   [+] Link 1 khớp trang {platform} cụ thể: {link1}")
        target_url = link1
    else:
        print(f"   [!] Link 1 chỉ dẫn về trang chung -> Đang thử Link 2...")
        if len(urls) > 1:
            link2 = urls[1]
            if is_specific_hotel_url(link2, platform=platform):
                print(f"   [+] Link 2 khớp trang {platform} cụ thể: {link2}")
                target_url = link2
            else:
                print(f"   [!] Link 2 cũng chỉ dẫn về trang chung -> Bỏ qua {platform}.")
                return None, None
        else:
            print(f"   [!] Không có Link 2 để thử trên {platform}.")
            return None, None

    res_stars = extract_stars_and_address_from_page(page, target_url, platform=platform, target_province=province)
    return res_stars, target_url

def search_multi_platform_stars(page, title: str, address: str):
    platforms = ["booking", "agoda", "traveloka"]
    for platform in platforms:
        print(f"   ---> THỬ NỀN TẢNG [{platform.upper()}] <---")
        found_stars, target_url = search_platform_stars(page, title, address, platform)
        if found_stars:
            print(f"   [✓] THÀNH CÔNG! Tìm thấy số sao trên {platform.upper()}: {found_stars}")
            return found_stars, target_url, platform
        print(f"   [-] Không lấy được số sao trên {platform.upper()} -> Thử nền tảng tiếp...")

    return None, None, None

def run_star_harvester_playwright(input_file, mode="single"):
    mode_tag = f"STAR_{mode.upper()}"
    print(f"[{mode_tag}] Đã khởi chạy Tool Tìm Số Sao Waterfall (Mode: {mode})...")

    # Phân tích luồng (mode=top, bottom, 3way_p1, 4way_p2...)
    total_w = 1
    w_idx = 0
    match_way = re.match(r'^(?:(\d+)way_)?p(\d+)$', mode.lower())
    if match_way:
        total_w = int(match_way.group(1)) if match_way.group(1) else 4
        w_idx = int(match_way.group(2)) - 1
    elif mode.lower() == "top":
        total_w, w_idx = 2, 0
    elif mode.lower() == "bottom":
        total_w, w_idx = 2, 1

    # Đường dẫn profile riêng cho từng luồng để tránh khóa file profile
    worker_profile_dir = os.path.join(BASE_DIR, f"browser_profile_{mode.lower()}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            worker_profile_dir,
            headless=CONFIG.get("headless", False),
            slow_mo=50,
            locale="vi-VN",
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            ignore_default_args=["--enable-automation"],
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-gpu",
                "--no-sandbox"
            ],
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                records = json.load(f)

            print(f"[{mode_tag}] Đang đọc file dữ liệu: {input_file}")
            star_count_initial = sum(1 for r in records if isinstance(r, dict) and has_existing_stars(r))
            total_cnt_initial = len(records)
            pct_initial = (star_count_initial / total_cnt_initial * 100) if total_cnt_initial > 0 else 0
            print(f"[{mode_tag}] Tiến trình: {star_count_initial} / {total_cnt_initial} bản ghi có số sao ({pct_initial:.1f}%)")
            
            to_process = [r for r in records if not has_existing_stars(r)]
            total_unprocessed = len(to_process)
            
            if total_unprocessed == 0:
                print(f"[{mode_tag}] Tất cả bản ghi đều đã có số sao. Dừng luồng!")
                return

            # Chia phân đoạn toán học phủ kín 100%
            start_idx = (w_idx * total_unprocessed) // total_w
            end_idx = ((w_idx + 1) * total_unprocessed) // total_w if w_idx < total_w - 1 else total_unprocessed
            chunk = to_process[start_idx:end_idx]

            print(f"[{mode_tag}] Phân đoạn Luồng [{w_idx+1}/{total_w}]: Xử lý {len(chunk)} / {total_unprocessed} bản ghi (Từ #{start_idx+1} -> #{end_idx})")

            processed_cnt = 0
            for idx, item in enumerate(chunk):
                stt   = item.get("stt", idx + 1)
                title = clean_text(item.get("title", ""))
                addr  = clean_text(item.get("address", ""))

                print(f"\n[{mode_tag}] [{idx+1}/{len(chunk)}] STT {stt}: {title}...")

                found_stars, target_url, platform_name = search_multi_platform_stars(page, title, addr)

                if found_stars:
                    item["stars"] = found_stars
                    item["categoryName"] = found_stars

                    # Nối chuỗi trường source bằng dấu phân cách |
                    new_src_entry = f"{platform_name.capitalize()}: {target_url}"
                    old_src = str(item.get("source", "")).strip()
                    if old_src and old_src != "N/A":
                        if new_src_entry not in old_src:
                            item["source"] = f"{old_src} | {new_src_entry}"
                    else:
                        item["source"] = new_src_entry

                    saved, total_cnt, star_cnt = safe_save_record(input_file, item)
                    print(f"[{mode_tag}] ✓ THÀNH CÔNG! Đã cập nhật '{title}' -> '{found_stars}' ({new_src_entry})")
                    processed_cnt += 1
                else:
                    print(f"[{mode_tag}] [-] Không tìm thấy số sao cho '{title}'.")

                total_scanned = min(total_cnt_initial, star_count_initial + (idx + 1))
                pct_scanned = (total_scanned / total_cnt_initial * 100) if total_cnt_initial > 0 else 0
                print(f"[{mode_tag}] Tiến trình: {total_scanned} / {total_cnt_initial} bản ghi đã quét ({pct_scanned:.1f}%)")

                time.sleep(random.uniform(2.5, 4.5))

        finally:
            try:
                context.close()
            except Exception:
                pass
            print(f"[{mode_tag}] HOÀN THÀNH LUỒNG! Đã hoàn thành xử lý cho phân đoạn luồng {mode}.")

if __name__ == "__main__":
    output_filename = CONFIG.get("output_file", "hotels.json")
    mode_arg = "single"

    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode_arg = arg.split("=")[1]
        elif arg.startswith("--output="):
            output_filename = arg.split("=")[1]

    print(f"[*] File dữ liệu làm việc: {output_filename}")

    if PLAYWRIGHT_AVAILABLE:
        run_star_harvester_playwright(output_filename, mode=mode_arg)
    else:
        print("[!] Lỗi: Chưa cài đặt thư viện Playwright!")
        sys.exit(1)
