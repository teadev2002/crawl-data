import json
import time
import os
import re
import sys
import random
import base64
from urllib.parse import unquote, urljoin, urlparse, parse_qs
from playwright.sync_api import sync_playwright

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

# Nhập cấu hình trình duyệt và file lưu dữ liệu từ map_scraper.py (sử dụng chung config.json)
try:
    from map_scraper import USE_MY_CHROME_PROFILE, CHROME_PROFILE_PATH, CONFIG
except ImportError:
    CONFIG = load_config()
    USE_MY_CHROME_PROFILE = CONFIG.get("USE_MY_CHROME_PROFILE", False)
    CHROME_PROFILE_PATH = CONFIG.get("CHROME_PROFILE_PATH", r"C:\Users\admin1\AppData\Local\Google\Chrome\User Data")

TARGET_JSON_FILE = CONFIG.get("output_file", "hotels.json")

# Danh sách tên miền bên thứ ba bị chặn (tuyệt đối không truy cập để cào email)
THIRD_PARTY_BLOCKLIST = [
    "booking.com", "bluepillow.com", "foody.vn", "shopeefood.vn",
    "agoda.com", "traveloka.com", "tripadvisor.com", "tripadvisor.com.vn",
    "vntrip.vn", "klook.com"
]

STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

def format_standard_record(r, default_stt=1):
    """Đảm bảo bản ghi tuân thủ đúng 100% 12 trường tiêu chuẩn và thứ tự khóa, loại bỏ hoàn toàn cuisineType"""
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

def check_and_handle_captcha(page):
    """Kiểm tra nếu trang hiện tại bị Google chặn Captcha (google.com/sorry/index)"""
    try:
        current_url = page.url.lower()
        is_captcha = "google.com/sorry" in current_url
        if not is_captcha:
            if page.locator('#captcha-form, .g-recaptcha, iframe[src*="recaptcha"]').count() > 0:
                is_captcha = True
                
        if is_captcha:
            print("\n" + "=" * 65)
            print("[!] PHÁT HIỆN CAPTCHA GOOGLE (google.com/sorry/index)!")
            print("[*] Vui lòng giải Captcha trực tiếp trên màn hình trình duyệt.")
            print("=" * 65)
            

                    
            print("[*] Tạm dừng 3 giây để người dùng thao tác giải Captcha...")
            for sec in range(3, 0, -1):
                print(f"    -> Đang chờ: {sec} giây...  ", end="\r")
                time.sleep(1)
            print("\n[*] Hết 3 giây tạm dừng. Tiếp tục tiến trình...\n")
            return True
    except Exception:
        pass
    return False

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

def accept_google_consent(page) -> bool:
    """Tự động click nút chấp nhận điều khoản Google bằng JS."""
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

def find_emails_in_text(text):
    """Tìm tất cả các email hợp lệ trong văn bản, loại bỏ các email mẫu/rác"""
    if not text:
        return []
    emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    valid_emails = []
    
    discard_words = {
        "example", "domain", "email.com", "yourdomain", "sentry.io",
        "wixpress", "test", "demo", "placeholder"
    }
    
    for email in emails:
        email_lower = email.lower()
        if not any(word in email_lower for word in discard_words):
            ext = email_lower.split('.')[-1]
            if ext not in ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'css', 'js', 'pdf']:
                valid_emails.append(email)
    return list(set(valid_emails))

def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

def extract_fb_url_from_page(page, engine: str = "generic") -> str | None:
    """Trích xuất link Facebook hợp lệ từ kết quả tìm kiếm (Bỏ qua AI Copilot/Ads và hỗ trợ giải mã Base64/Redirect)."""
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
            # Bỏ qua link nằm trong khung AI Copilot / AI Overview
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

            # Giải mã Google redirect /url?q=...
            if '/url?q=' in href_lower or '/url?q=' in href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    if 'q' in qs:
                        actual_href = unquote(qs['q'][0])
                except Exception:
                    pass

            # Giải mã DuckDuckGo redirect uddg=...
            elif 'uddg=' in href_lower or 'uddg=' in href:
                try:
                    qs = parse_qs(urlparse(href).query)
                    if 'uddg' in qs:
                        actual_href = unquote(qs['uddg'][0])
                except Exception:
                    pass

            # Giải mã Bing redirect base64 u=a1...
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

def crawl_website_for_email(page, url):
    """Cào email từ trang web chính và các trang liên hệ con (Contact, About...)"""
    if not url or any(block_domain in url.lower() for block_domain in THIRD_PARTY_BLOCKLIST):
        return None, ""

    print(f"  -> Đang truy cập trang web: {url}")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1.5)
        
        content = page.content()
        emails = find_emails_in_text(content)
        if emails:
            return emails[0], f"Trang web chính: {url}"

        contact_links = page.locator('a[href*="contact"], a[href*="lien-he"], a[href*="gioi-thieu"], a[href*="about"]').all()
        for link in contact_links[:2]:
            try:
                sub_url = link.get_attribute('href')
                if sub_url:
                    full_sub_url = urljoin(url, sub_url)
                    print(f"    -> Thử kiểm tra trang con: {full_sub_url}")
                    page.goto(full_sub_url, wait_until='domcontentloaded', timeout=10000)
                    time.sleep(1.5)
                    sub_content = page.content()
                    sub_emails = find_emails_in_text(sub_content)
                    if sub_emails:
                        return sub_emails[0], f"Trang con liên hệ: {full_sub_url}"
            except Exception:
                continue

    except Exception as e:
        print(f"    [!] Không thể truy cập trang web {url}: {e}")

    return None, ""

def crawl_facebook_for_email(page, fb_url):
    """Trích xuất email từ trang Facebook Fanpage (Quét mailto & body text)"""
    if not fb_url or "facebook.com" not in fb_url.lower():
        return None, ""

    clean_url = fb_url.split('?')[0].rstrip('/')
    print(f"  -> Đang kiểm tra Facebook Fanpage: {clean_url}")
    try:
        page.goto(clean_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(2)
        
        # 1. Tìm thẻ <a href="mailto:...">
        try:
            mailto_elements = page.locator('a[href^="mailto:"]').all()
            for el in mailto_elements:
                try:
                    href = el.get_attribute('href') or ''
                    email = href.replace('mailto:', '').split('?')[0].strip()
                    if email and '@' in email:
                        valid_emails = find_emails_in_text(email)
                        if valid_emails:
                            return valid_emails[0], f"Facebook Mailto: {clean_url}"
                except Exception:
                    continue
        except Exception:
            pass

        # 2. Quét regex trong toàn bộ văn bản hiển thị
        content = page.content()
        emails = find_emails_in_text(content)
        if emails:
            return emails[0], f"Facebook Fanpage: {clean_url}"

        about_url = clean_url + '/about'
        page.goto(about_url, wait_until='domcontentloaded', timeout=12000)
        time.sleep(2)
        about_content = page.content()
        about_emails = find_emails_in_text(about_content)
        if about_emails:
            return about_emails[0], f"Facebook About: {about_url}"

    except Exception as e:
        print(f"    [!] Lỗi khi cào Facebook {clean_url}: {e}")

    return None, ""

def search_bing_for_facebook(page, title, address):
    """Cỗ máy tìm kiếm dự phòng 1: Bing Search để tìm Fanpage Facebook (có giải mã Base64)"""
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
    """Cỗ máy tìm kiếm dự phòng 2: DuckDuckGo Search để tìm Fanpage Facebook"""
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
    """Tìm kiếm trang Facebook chính chủ của địa điểm (Google -> Bing Fallback -> DuckDuckGo Fallback)"""
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

    # Nếu Google bị vướng CAPTCHA hoặc không tìm thấy, tự động gọi cỗ máy tìm kiếm dự phòng Bing
    if not fb_url:
        fb_url = search_bing_for_facebook(page, title, address)

    # Nếu Bing vẫn không tìm thấy, gọi cỗ máy dự phòng DuckDuckGo
    if not fb_url:
        fb_url = search_ddg_for_facebook(page, title, address)

    return fb_url

def search_google_for_email(page, title, address):
    """Tìm kiếm email trực tiếp trên Google Snippet & Trip.com"""
    province = extract_province(address)
    query = f'{title} {province} email'.strip() if province else f'{title} email'
    print(f"  -> Đang tìm Email trực tiếp trên Google với từ khóa: {query}")
    try:
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=vi"
        page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        accept_google_consent(page)
        check_and_handle_captcha(page)
        time.sleep(1.5)

        content = page.content()
        emails = find_emails_in_text(content)
        if emails:
            return emails[0], "Google Search Snippet"
    except Exception as e:
        print(f"    [!] Lỗi khi tìm email trên Google: {e}")

    # LƯỢT DỰ PHÒNG 2: TÌM KIẾM TRÊN TRIP.COM
    print("    -> [Trip.com Fallback] Đang thử tìm email gian hàng trên Trip.com...")
    query_trip = f'{title} {province} trip.com'.strip() if province else f'{title} trip.com'
    try:
        search_url_trip = f"https://www.google.com/search?q={query_trip.replace(' ', '+')}&hl=vi"
        page.goto(search_url_trip, wait_until='domcontentloaded', timeout=15000)
        accept_google_consent(page)
        time.sleep(1.5)

        content_trip = page.content()
        emails_trip = find_emails_in_text(content_trip)
        if emails_trip:
            return emails_trip[0], "Trip.com Snippet"

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
            found_emails_trip = find_emails_in_text(page_text)
            if found_emails_trip:
                return found_emails_trip[0], f"Trip.com: {trip_url}"

    except Exception as e:
        print(f"    [!] Lỗi khi tìm kiếm trên Trip.com: {e}")

    return None, ""

# ATOMIC SAFE FILE IO
def safe_read_json(file_path, retries=15, delay=0.15):
    """Đọc file JSON an toàn với cơ chế thử lại và tự sửa lỗi Extra data"""
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
    """Ghi file JSON an toàn nguyên tử (Atomic Write via os.replace)"""
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

def safe_save_email(target_file, target_stt, target_title, target_url, update_data):
    """Lưu Real-Time 1 kết quả email cào được vào target_file bằng Atomic Write và trả về số bản ghi isFlag=True"""
    records = safe_read_json(target_file)
    if not records or not isinstance(records, list):
        return False, 0, 0
        
    updated = False
    flagged_count = 0
    total_records = len(records)

    target_title_clean = str(target_title or "").strip().lower()

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
                r["email"] = update_data.get("email", r.get("email", ""))
                r["source"] = update_data.get("source", r.get("source", ""))
                if update_data.get("facebook"):
                    r["facebook"] = update_data["facebook"]
                    if "facebook.com" in str(r.get("website", "")).lower():
                        r["website"] = ""
                r["isFlag"] = True
                updated = True

            if r.get("isFlag") is True:
                flagged_count += 1

    if updated:
        formatted_records = [format_standard_record(r, i + 1) for i, r in enumerate(records)]
        saved = safe_write_json(target_file, formatted_records)
        return saved, flagged_count, total_records
    return False, flagged_count, total_records

def harvest_emails(mode="top"):
    global USE_MY_CHROME_PROFILE
    if mode == "bottom":
        USE_MY_CHROME_PROFILE = False

    target_file = TARGET_JSON_FILE
    if not os.path.exists(target_file):
        print(f"[!] Không tìm thấy file dữ liệu '{target_file}' được cấu hình trong config.json.")
        print("[*] Vui lòng chạy cào địa điểm trước bằng map_scraper.py để tạo file này, hoặc kiểm tra lại tên file.")
        return
        
    print(f"[*] [{mode.upper()}] Đang đọc file dữ liệu: {target_file}")
    records = safe_read_json(target_file)

    if records is None or not isinstance(records, list):
        print(f"[!] Lỗi: Không thể đọc dữ liệu danh sách từ file '{target_file}'.")
        return
        
    formatted_records = [format_standard_record(r, idx + 1) for idx, r in enumerate(records) if isinstance(r, dict)]
    safe_write_json(target_file, formatted_records)
    records = formatted_records
        
    find_all = CONFIG.get("findAll", False)
    find_next = CONFIG.get("findNext", True)
    
    to_process_indices = []
    for idx, r in enumerate(records):
        if isinstance(r, dict):
            if find_all is True and find_next is False:
                if not r.get("email") or str(r.get("email")).strip() == "":
                    to_process_indices.append((idx, r))
            else:
                if not r.get("isFlag") or r.get("isFlag") is not True:
                    to_process_indices.append((idx, r))
        
    total_need_process = len(to_process_indices)
    midpoint = total_need_process // 2 if total_need_process > 1 else 1

    if mode == "bottom":
        target_items = list(reversed(to_process_indices[midpoint:])) if total_need_process > 1 else to_process_indices
        print(f"[*] Chế độ quét: LUỒNG BOTTOM (QUÉT TỪ DƯỚI LÊN). Quét {len(target_items)} bản ghi thuộc nửa sau...")
    elif mode == "top":
        target_items = to_process_indices[:midpoint] if total_need_process > 1 else to_process_indices
        print(f"[*] Chế độ quét: LUỒNG TOP (QUÉT TỪ TRÊN XUỐNG). Quét {len(target_items)} bản ghi thuộc nửa đầu...")
    else:
        target_items = to_process_indices
        print(f"[*] Chế độ quét: ĐƠN LUỒNG. Quét {len(target_items)} bản ghi...")
    
    print(f"[*] [EMAIL_HARVEST] Tổng số bản ghi trong file: {len(records)}")
    print(f"[*] [EMAIL_HARVEST] [{mode.upper()}] Phát hiện tổng cộng {total_need_process} bản ghi thiếu email cần xử lý.")
    
    if len(target_items) == 0:
        print(f"[*] [EMAIL_HARVEST] [{mode.upper()}] Không có bản ghi nào cần quét email trong mốc này. Chương trình kết thúc.")
        return

    with sync_playwright() as p:
        use_chrome = USE_MY_CHROME_PROFILE and mode in ["top", "normal"]
        
        if use_chrome:
            print(f"[*] [EMAIL_HARVEST] [{mode.upper()}] Đang mở Google Chrome thật tại: {CHROME_PROFILE_PATH}...")
            context = p.chromium.launch_persistent_context(
                CHROME_PROFILE_PATH,
                channel="chrome",
                headless=False
            )
        else:
            print(f"[*] [EMAIL_HARVEST] [{mode.upper()}] Đang mở trình duyệt ảo mặc định...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()

        # Áp dụng Stealth Script giấu dấu vết Bot tự động
        context.add_init_script(STEALTH_SCRIPT)
        page = context.pages[0] if context.pages else context.new_page()

        success_count = 0
        for index_in_file, item in target_items:
            stt = item.get("stt", index_in_file + 1)
            title = item.get("title", "Không rõ tên")
            website = item.get("website", "")
            facebook = item.get("facebook", "")
            address = item.get("address", "")

            # Kiểm tra chéo Real-Time trước khi cào
            already_done = False
            try:
                check_records = safe_read_json(target_file)
                if check_records and isinstance(check_records, list):
                    url_item = item.get("url", "")
                    title_clean = str(title or "").strip().lower()
                    for idx_cr, cr in enumerate(check_records):
                        if isinstance(cr, dict):
                            match_stt = str(cr.get("stt", idx_cr + 1)) == str(stt)
                            match_url = url_item and cr.get("url", "") == url_item
                            match_title = title_clean and str(cr.get("title", "")).strip().lower() == title_clean
                            if match_stt or match_url or match_title:
                                if cr.get("isFlag") is True and (find_all is False or (cr.get("email") and str(cr.get("email")).strip() != "")):
                                    already_done = True
                                    break
            except Exception:
                pass

            if already_done:
                print(f"[-] [EMAIL_HARVEST] [{mode.upper()}] Bỏ qua STT {stt}/{len(records)}: Đã được luồng kia quét email trước.")
                continue

            print(f"\n[*] [EMAIL_HARVEST] [{mode.upper()}] Đang xử lý STT {stt}/{len(records)}: {title}...")

            email_found = None
            source_found = ""
            discovered_facebook = facebook

            # Bước 1: Quét trực tiếp qua website/Facebook nếu có
            if facebook and facebook.strip() != "":
                email_found, source_found = crawl_facebook_for_email(page, facebook)
            elif website and website.strip() != "":
                if "facebook.com" in website.lower():
                    discovered_facebook = website
                    email_found, source_found = crawl_facebook_for_email(page, website)
                else:
                    email_found, source_found = crawl_website_for_email(page, website)

            # Bước 2: Tìm kiếm Facebook trên Google (Tự động chuyển sang Bing/DuckDuckGo nếu dính CAPTCHA)
            if not email_found and (not discovered_facebook or discovered_facebook.strip() == ""):
                fb_url = search_google_for_facebook(page, title, address)
                if fb_url:
                    discovered_facebook = fb_url
                    email_found, source_found = crawl_facebook_for_email(page, fb_url)

            # Bước 3: Tìm kiếm email chung qua Google Search / Trip.com
            if not email_found:
                email_found, source_found = search_google_for_email(page, title, address)

            # Cập nhật kết quả Real-Time bằng Atomic Write
            update_data = {
                "email": email_found if email_found else "",
                "source": source_found if email_found else "",
                "facebook": discovered_facebook if discovered_facebook else facebook,
                "isFlag": True
            }

            url = item.get("url", "")
            saved, flagged_count, total_recs = safe_save_email(target_file, stt, title, url, update_data)
            if saved:
                if email_found:
                    success_count += 1
                    print(f"✓ [EMAIL_HARVEST] [{mode.upper()}] Real-Time Save (Đã quét {flagged_count}/{total_recs} bản ghi): [{title}] -> Email: '{email_found}' (Nguồn: {source_found})")
                else:
                    print(f"✓ [EMAIL_HARVEST] [{mode.upper()}] Real-Time Save (Đã quét {flagged_count}/{total_recs} bản ghi): [{title}] -> Đã đánh dấu (Không có email)")
            else:
                print(f"[!] [{mode.upper()}] Lỗi lưu STT {stt} ({title}).")

            # Tạo độ trễ ngẫu nhiên mô phỏng người dùng thật
            time.sleep(random.uniform(2.5, 4.5))

        # Đóng trình duyệt
        if use_chrome:
            context.close()
        else:
            browser.close()

    print(f"\n[+] [{mode.upper()}] QUÉT EMAIL HOÀN TẤT! Đã tìm thấy {success_count} email mới.")

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

    harvest_emails(mode)
