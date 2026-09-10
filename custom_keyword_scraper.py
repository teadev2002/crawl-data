import sys
import time
import json
import re
import os
from urllib.parse import quote_plus, unquote

# Cấu hình hiển thị UTF-8 trên Terminal Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException, WebDriverException

# ==================== NẠP CẤU HÌNH TỪ FILE CONFIG.JSON ====================
def get_default_chrome_profile_path():
    """Tự động xác định đường dẫn thư mục Chrome Remote Debug Profile trên Windows"""
    if sys.platform.startswith('win'):
        user_profile = os.environ.get('USERPROFILE')
        if user_profile:
            return os.path.join(user_profile, 'AppData', 'Local', 'Google', 'Chrome', 'User Data Debug')
    return r"C:\Users\admin1\AppData\Local\Google\Chrome\User Data Debug"

def load_config():
    """Nạp cấu hình từ file config.json"""
    config_file = "config.json"
    if not os.path.exists(config_file):
        print(f"\n[!] Lỗi: Không tìm thấy file cấu hình '{config_file}'!")
        sys.exit(1)
        
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # Sử dụng chung mảng search_queries (fallback sang key_research nếu search_queries rỗng)
        queries = config.get("search_queries", [])
        if not queries:
            queries = config.get("key_research", [])
            
        if not queries:
            print(f"\n[!] Lỗi: Không tìm thấy 'search_queries' hoặc 'key_research' trong '{config_file}'!")
            sys.exit(1)
            
        config["active_queries"] = queries
        
        if "USE_MY_CHROME_PROFILE" not in config:
            config["USE_MY_CHROME_PROFILE"] = True
        if "CHROME_PROFILE_PATH" not in config or not config.get("CHROME_PROFILE_PATH"):
            config["CHROME_PROFILE_PATH"] = get_default_chrome_profile_path()
        if "max_results" not in config:
            config["max_results"] = 200
        if "output_file" not in config:
            config["output_file"] = "custom_keyword_results.json"
            
        return config
    except Exception as e:
        print(f"\n[!] Lỗi khi đọc file cấu hình '{config_file}': {e}")
        sys.exit(1)

CONFIG = load_config()
STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

PROVINCE_BOUNDS_MAP = {
    "An Giang": {"bounds": [10.15, 10.96, 104.70, 105.60], "keywords": ["an giang", "long xuyên", "châu đốc"]},
    "Bắc Ninh": {"bounds": [20.95, 21.30, 106.85, 107.25], "keywords": ["bắc ninh", "bac ninh"]},
    "Cà Mau": {"bounds": [8.50, 9.35, 104.20, 105.40], "keywords": ["cà mau", "ca mau"]},
    "Cao Bằng": {"bounds": [22.35, 23.15, 105.25, 106.55], "keywords": ["cao bằng", "cao bang"]},
    "Đắc Lắk": {"bounds": [12.15, 13.40, 107.50, 109.15], "keywords": ["đắk lắk", "dak lak", "đắc lắc", "buôn ma thuột"]},
    "Điện Biên": {"bounds": [20.85, 22.55, 102.15, 103.65], "keywords": ["điện biên", "dien bien"]},
    "Đồng Nai": {"bounds": [10.35, 11.55, 106.70, 107.95], "keywords": ["đồng nai", "dong nai", "biên hòa"]},
    "Đồng Tháp": {"bounds": [10.10, 10.95, 105.10, 105.95], "keywords": ["đồng tháp", "dong thap", "cao lãnh", "sa đéc"]},
    "Gia Lai": {"bounds": [13.00, 14.60, 107.45, 108.95], "keywords": ["gia lai", "pleiku"]},
    "Hà Tĩnh": {"bounds": [17.90, 18.65, 105.05, 106.50], "keywords": ["hà tĩnh", "ha tinh"]},
    "Hưng Yên": {"bounds": [20.60, 21.00, 105.85, 106.25], "keywords": ["hưng yên", "hung yen"]},
    "Khánh Hòa": {"bounds": [11.75, 12.85, 108.70, 109.50], "keywords": ["khánh hòa", "khanh hoa", "nha trang", "cam ranh"]},
    "Lai Châu": {"bounds": [21.65, 22.85, 102.30, 103.85], "keywords": ["lai châu", "lai chau"]},
    "Lạng Sơn": {"bounds": [21.35, 22.45, 106.10, 107.45], "keywords": ["lạng sơn", "lang son"]},
    "Lào Cai": {"bounds": [22.10, 22.85, 103.50, 104.65], "keywords": ["lào cai", "lao cai", "sa pa", "sapa"]},
    "Lâm Đồng": {"bounds": [11.20, 12.35, 107.25, 108.75], "keywords": ["lâm đồng", "lam dong", "đà lạt", "bảo lộc"]},
    "Nghệ An": {"bounds": [18.55, 19.95, 103.85, 105.85], "keywords": ["nghệ an", "nghe an", "vinh"]},
    "Ninh Bình": {"bounds": [20.00, 20.45, 105.50, 106.15], "keywords": ["ninh bình", "ninh binh"]},
    "Phú Thọ": {"bounds": [20.90, 21.75, 104.80, 105.45], "keywords": ["phú thọ", "phu tho", "việt trì"]},
    "Quảng Ngãi": {"bounds": [14.60, 15.45, 108.35, 109.10], "keywords": ["quảng ngãi", "quang ngai"]},
    "Quảng Ninh": {"bounds": [20.65, 21.60, 106.45, 108.10], "keywords": ["quảng ninh", "quang ninh", "hạ long", "cẩm phả"]},
    "Quảng Trị": {"bounds": [16.30, 17.20, 106.40, 107.40], "keywords": ["quảng trị", "quang tri", "đông hà"]},
    "Sơn La": {"bounds": [20.65, 21.90, 103.15, 105.05], "keywords": ["sơn la", "son la", "mộc châu"]},
    "Tây Ninh": {"bounds": [10.95, 11.80, 105.75, 106.50], "keywords": ["tây ninh", "tay ninh"]},
    "Thái Nguyên": {"bounds": [21.30, 22.05, 105.45, 106.25], "keywords": ["thái nguyên", "thai nguyen"]},
    "Thanh Hóa": {"bounds": [19.30, 20.65, 104.35, 106.05], "keywords": ["thanh hóa", "thanh hoa", "sầm sơn"]},
    "Thành phố Cần Thơ": {"bounds": [9.90, 10.35, 105.20, 105.90], "keywords": ["cần thơ", "can tho", "ninh kiều", "cái răng", "bình thủy", "ô môn"]},
    "Thành phố Đà Nẵng": {"bounds": [15.90, 16.25, 107.80, 108.35], "keywords": ["đà nẵng", "da nang", "sơn trà", "ngũ hành sơn"]},
    "Thành phố Hà Nội": {"bounds": [20.55, 21.40, 105.25, 106.05], "keywords": ["hà nội", "ha noi", "hanoi", "hoàn kiếm", "ba đình", "cầu giấy"]},
    "Thành phố Hải Phòng": {"bounds": [20.50, 21.05, 106.40, 107.15], "keywords": ["hải phòng", "hai phong", "đồ sơn", "cát bà"]},
    "Thành phố Hồ Chí Minh": {"bounds": [10.35, 11.20, 106.35, 107.05], "keywords": ["hồ chí minh", "ho chi minh", "hcm", "sài gòn", "sai gon", "thủ đức"]},
    "Thành phố Huế": {"bounds": [16.00, 16.80, 107.00, 107.85], "keywords": ["huế", "thừa thiên huế", "thua thien hue"]},
    "Tuyên Quang": {"bounds": [21.50, 22.65, 105.00, 105.75], "keywords": ["tuyên quang", "tuyen quang"]},
    "Vĩnh Long": {"bounds": [9.90, 10.35, 105.70, 106.15], "keywords": ["vĩnh long", "vinh long"]}
}

def get_province_info(selected_province):
    """Ánh xạ linh hoạt tên Tỉnh/Thành truyền vào (alias) tới cấu hình PROVINCE_BOUNDS_MAP"""
    if not selected_province:
        return None
    prov = str(selected_province).strip()
    if prov in PROVINCE_BOUNDS_MAP:
        return PROVINCE_BOUNDS_MAP[prov]
        
    clean_name = re.sub(r'^(TP\.?|Thành phố\s*|Tỉnh\s*)', '', prov, flags=re.IGNORECASE).strip().lower()
    
    for key, info in PROVINCE_BOUNDS_MAP.items():
        key_clean = re.sub(r'^(TP\.?|Thành phố\s*|Tỉnh\s*)', '', key, flags=re.IGNORECASE).strip().lower()
        if clean_name == key_clean or clean_name in key_clean or key_clean in clean_name:
            return info
        for kw in info.get("keywords", []):
            kw_clean = kw.lower().strip()
            if clean_name == kw_clean or clean_name in kw_clean or kw_clean in clean_name:
                return info
    return None

def extract_lat_lng(url):
    """Trích xuất vĩ độ (lat) và kinh độ (lng) từ Google Maps URL"""
    if not url:
        return None, None
    m3d = re.search(r'!3d(-?\d+(?:\.\d+)?)', url)
    m4d = re.search(r'!4d(-?\d+(?:\.\d+)?)', url)
    if m3d and m4d:
        try:
            return float(m3d.group(1)), float(m4d.group(1))
        except Exception:
            pass
    mat = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if mat:
        try:
            return float(mat.group(1)), float(mat.group(2))
        except Exception:
            pass
    mll = re.search(r'(?:ll|center)=(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if mll:
        try:
            return float(mll.group(1)), float(mll.group(2))
        except Exception:
            pass
    return None, None

def is_allowed_location(url, address, selected_province=None):
    """
    Kiểm tra xem địa điểm có nằm đúng trong phạm vi Tỉnh / Thành phố đã chọn hay không.
    Ưu tiên 1: Tọa độ Bounding Box (Lat/Lng). Nếu nằm trong [min_lat <= lat <= max_lat] và [min_lng <= lng <= max_lng] -> Chấp nhận địa điểm ngay lập tức (return True).
    Ưu tiên 2: Từ khóa tên Tỉnh/Thành trong địa chỉ (Address).
    """
    if not selected_province:
        selected_province = CONFIG.get("target_province", "all")
    selected_province = str(selected_province).strip()
    
    if selected_province in ["all", "none", "off", "all_provinces", ""]:
        return True
        
    info = get_province_info(selected_province)
    
    # 1. ƯU TIÊN KIỂM TRA TỌA ĐỘ BOUDING BOX (Lat, Lng Check)
    lat, lng = extract_lat_lng(url)
    if info and lat is not None and lng is not None:
        min_lat, max_lat, min_lng, max_lng = info["bounds"]
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return True

    # 2. KIỂM TRA TỪ KHÓA TÊN TỈNH/THÀNH TRONG ĐỊA CHỈ (Address Check)
    addr_lower = (address or "").lower()
    if info:
        if any(kw in addr_lower for kw in info["keywords"]):
            return True
    else:
        sel_lower = re.sub(r'^(TP\.?|Thành phố\s*|Tỉnh\s*)', '', selected_province, flags=re.IGNORECASE).strip().lower()
        if sel_lower and sel_lower in addr_lower:
            return True
            
    if (not address or address == "N/A") and lat is None and lng is None:
        return True

    return False

def clean_text(text):
    """Loại bỏ ký tự xuống dòng, khoảng trắng thừa, icon glyphs và ký tự ẩn"""
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff\ue000-\uffff]', ' ', text)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned.strip()

def extract_title_from_url(url):
    """Trích xuất và giải mã tên địa điểm từ Google Maps URL nếu DOM H1 không phản hồi"""
    if not url:
        return ""
    try:
        match = re.search(r'/maps/place/([^/@?]+)', url)
        if match:
            raw_title = match.group(1)
            decoded = unquote(raw_title).replace('+', ' ')
            return clean_text(decoded)
    except Exception:
        pass
    return ""

def format_standard_record(r, default_stt=1):
    """Đảm bảo bản ghi tuân thủ đúng 100% 12 trường tiêu chuẩn"""
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
    """Lưu Real-Time 1 bản ghi mới vào file an toàn bằng Atomic Write (.tmp)"""
    for attempt in range(15):
        try:
            records = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            raw_records = json.loads(content)
                            if isinstance(raw_records, list):
                                records = [format_standard_record(r, idx + 1) for idx, r in enumerate(raw_records) if isinstance(r, dict)]
                except Exception:
                    records = []
                    
            records.append(format_standard_record(new_item, len(records) + 1))
            for idx, r in enumerate(records):
                r["stt"] = idx + 1
                
            temp_file = output_file + f".tmp_{os.getpid()}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, output_file)
            return True, len(records)
        except Exception:
            time.sleep(0.15)
    return False, 0

def get_total_file_records(output_file):
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, list):
                        return len(data)
        except Exception:
            pass
    return 0

def extract_unique_key(url):
    """Trích xuất khóa định danh duy nhất của địa điểm từ Google Maps URL"""
    if not url:
        return ""
    match_place_id = re.search(r'query_place_id=([^&]+)', url)
    if match_place_id:
        return match_place_id.group(1)
    match_place_id_2 = re.search(r'place_id=([^&]+)', url)
    if match_place_id_2:
        return match_place_id_2.group(1)
    match_fid = re.search(r'!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match_fid:
        return match_fid.group(1)
    match_cid = re.search(r'!1s([0x0-9a-fA-F]+)', url)
    if match_cid:
        return match_cid.group(1)
    normalized = url.split('?')[0].split('&')[0]
    normalized = re.sub(r'/@[0-9.-]+,[0-9.-]+,[0-9a-zA-Z.]+', '', normalized)
    return normalized

def extract_place_id(url):
    match = re.search(r'place_id=([^&]+)', url)
    return match.group(1) if match else None

def init_selenium_chrome():
    """Khởi tạo Selenium WebDriver: Khởi chạy Google Chrome tiêu chuẩn"""
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--start-maximized")
    options.add_argument("--lang=vi-VN")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    use_profile = CONFIG.get("USE_MY_CHROME_PROFILE", False)
    if use_profile:
        profile_path = CONFIG.get("CHROME_PROFILE_PATH", get_default_chrome_profile_path())
        if os.path.exists(profile_path):
            options.add_argument(f"--user-data-dir={profile_path}")
            print(f"[*] Khởi chạy Google Chrome Selenium với Profile tại: {profile_path}")
    else:
        print("[*] Khởi chạy Google Chrome Selenium tiêu chuẩn...")
        
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def run_custom_keyword_scraper(queries=None, max_results=None, output_file=None, mode="top"):
    if not queries:
        queries = CONFIG.get("active_queries", [])
    if not max_results:
        max_results = CONFIG.get("max_results", 200)
    if not output_file:
        output_file = CONFIG.get("output_file", "custom_keyword_results.json")
        
    mode_tag = "KEYWORD_SCRAPER"
    print(f"[{mode_tag}] Khởi chạy cào từ khóa tự do bằng Selenium Google Chrome...")
    print(f"[{mode_tag}] Số từ khóa: {len(queries)} | Chỉ tiêu: {max_results} | File lưu: '{output_file}'")
    
    # 0. Khởi tạo file xuất dữ liệu lập tức nếu chưa có
    if not os.path.exists(output_file):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[{mode_tag}] Đã tạo file kết quả mới: '{output_file}'")
        except Exception as e:
            print(f"[{mode_tag}] [!] Lỗi tạo file: {e}")
            
    # 1. Nạp bộ nhớ lọc trùng lặp cho file kết quả hiện tại
    existing_keys = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
                if isinstance(existing_records, list):
                    for r in existing_records:
                        if isinstance(r, dict) and "url" in r:
                            key = extract_unique_key(r["url"])
                            if key:
                                existing_keys.add(key)
        except Exception:
            pass

    print(f"[{mode_tag}] Đã nạp {len(existing_keys)} mã địa điểm độc nhất từ '{output_file}' vào bộ nhớ chống trùng lặp.")
    
    driver = init_selenium_chrome()
    saved_count = 0
    
    try:
        for q_idx, query in enumerate(queries):
            file_total = get_total_file_records(output_file)
            if saved_count >= max_results or file_total >= max_results:
                print(f"[{mode_tag}] [+] Đã đạt chỉ tiêu tối đa ({file_total}/{max_results}). Hoàn thành!")
                break
                
            search_url = f"https://www.google.com/maps/search/{quote_plus(query)}?hl=vi"
            print(f"\n[{mode_tag}] --- Đang quét từ khóa ({q_idx+1}/{len(queries)}): '{query}' ---")
            try:
                driver.get(search_url)
            except (NoSuchWindowException, WebDriverException):
                print(f"[{mode_tag}] [!] Cửa sổ Google Chrome đã bị đóng hoặc mất kết nối. Dừng tiến trình.")
                break
            time.sleep(3.5)
            
            # Tự động từ chối/chấp nhận cookie dialog nếu hiển thị
            try:
                consent_btns = driver.find_elements(By.CSS_SELECTOR, 'form button[aria-label*="Đồng ý"], form button[aria-label*="Accept"], button[jsaction*="consent"]')
                for btn in consent_btns:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1.0)
                        break
            except (NoSuchWindowException, WebDriverException):
                print(f"[{mode_tag}] [!] Cửa sổ Google Chrome đã bị đóng hoặc mất kết nối.")
                break
            except Exception:
                pass
            
            # GIAI ĐOẠN 1: CUỘN VÀ THU THẬP LINK MAPS CANDIDATES
            candidate_urls = []
            no_change_count = 0
            last_dom_count = 0
            
            # Kiểm tra trường hợp tìm kiếm chuyển hướng thẳng tới 1 địa điểm cụ thể
            try:
                curr_url = driver.current_url or ""
            except (NoSuchWindowException, WebDriverException):
                print(f"[{mode_tag}] [!] Cửa sổ Google Chrome đã bị đóng hoặc mất kết nối.")
                break

            if "/maps/place/" in curr_url:
                print(f"[{mode_tag}] Từ khóa '{query}' chuyển hướng trực tiếp tới 1 địa điểm cụ thể.")
                k = extract_unique_key(curr_url)
                if not k or k not in existing_keys:
                    candidate_urls.append(curr_url)
            else:
                for scroll_step in range(250):
                    if saved_count >= max_results or get_total_file_records(output_file) >= max_results:
                        break
                        
                    # Ưu tiên bóc tách trực tiếp toàn bộ 100% thẻ class="hfpxzc" qua JavaScript Chrome DOM engine
                    try:
                        js_res = driver.execute_script("""
                            const els = document.querySelectorAll('a.hfpxzc, a[href*="/maps/place/"], a.hfSlid, div.Nv2pk a');
                            const links = [];
                            els.forEach(el => {
                                if (el.href && el.href.includes('/maps/place/')) {
                                    links.push(el.href);
                                }
                            });
                            return { total_dom: els.length, links: links };
                        """) or {}
                        
                        dom_links = js_res.get("links", [])
                        total_dom = js_res.get("total_dom", 0)
                        
                        for href in dom_links:
                            key = extract_unique_key(href)
                            if key and key in existing_keys:
                                continue
                            if href not in candidate_urls:
                                candidate_urls.append(href)
                                
                        # Đếm no_change_count dựa theo TỔNG SỐ PHẦN TỬ DOM TRÊN TRANG để tránh bị dừng cuộn sớm
                        if total_dom > 0 and total_dom == last_dom_count:
                            no_change_count += 1
                            if no_change_count >= 20:
                                break
                        else:
                            if total_dom > 0:
                                no_change_count = 0
                                last_dom_count = total_dom
                    except (NoSuchWindowException, WebDriverException):
                        print(f"[{mode_tag}] [!] Cửa sổ Google Chrome đã bị đóng. Dừng cào dữ liệu.")
                        break
                    except Exception:
                        pass
                        
                    # Kiểm tra thông báo đã đến cuối danh sách
                    try:
                        end_els = driver.find_elements(By.XPATH, "//*[contains(text(), 'cuối danh sách') or contains(text(), 'end of the list') or contains(text(), 'Không còn kết quả')]")
                        if end_els and len(end_els) > 0 and end_els[0].is_displayed():
                            print(f"[{mode_tag}] Đã cuộn tới cuối danh sách kết quả Google Maps.")
                            break
                    except (NoSuchWindowException, WebDriverException):
                        break
                    except Exception:
                        pass

                    # Thực hiện cuộn bảng feed kết quả (kết hợp cuộn lăn chuột và cuộn đáy)
                    try:
                        feed = driver.find_elements(By.CSS_SELECTOR, 'div[role="feed"], div.m6QEdf[aria-label]')
                        if feed:
                            if scroll_step % 4 == 0:
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", feed[0])
                            else:
                                driver.execute_script("arguments[0].scrollTop += 800;", feed[0])
                        else:
                            driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.PAGE_DOWN)
                    except (NoSuchWindowException, WebDriverException):
                        break
                    except Exception:
                        pass
                    time.sleep(1.8)

            print(f"[{mode_tag}] Từ khóa '{query}': Thu thập được tổng cộng {len(candidate_urls)} link ứng viên độc nhất. Tiến hành bóc tách chi tiết...")
            
            # GIAI ĐOẠN 2: BÓC TÁCH CHI TIẾT VÀ LƯU REAL-TIME
            for i, url in enumerate(candidate_urls):
                file_total = get_total_file_records(output_file)
                if saved_count >= max_results or file_total >= max_results:
                    break
                    
                key = extract_unique_key(url)
                if key and key in existing_keys:
                    continue
                    
                print(f"[{mode_tag}] Đang crawl [{i+1}/{len(candidate_urls)}]: {url[:70]}...")
                try:
                    driver.get(url)
                    time.sleep(2.5)
                    
                    # Bóc tách Tên (h1)
                    title = "N/A"
                    try:
                        h1_els = driver.find_elements(By.CSS_SELECTOR, 'h1.DUwfe, h1.fontHeadlineLarge, h1, div.DUwfe, span.DUwfe')
                        if h1_els:
                            for el in h1_els:
                                txt = clean_text(el.text)
                                if txt:
                                    title = txt
                                    break
                    except Exception:
                        pass
                        
                    if not title or title == "N/A":
                        title = extract_title_from_url(url) or extract_title_from_url(driver.current_url)

                    if not title or title == "N/A":
                        print(f"[{mode_tag}] [-] Bỏ qua trang không hiển thị H1 hợp lệ.")
                        continue
                        
                    # Bóc tách CategoryName
                    category_name = ""
                    try:
                        cat_els = driver.find_elements(By.CSS_SELECTOR, 'button[jsaction*="category"], button[data-item-id*="category"]')
                        if cat_els:
                            category_name = clean_text(cat_els[0].text)
                    except Exception:
                        pass
                        
                    # Bóc tách Địa chỉ (Chiến lược 4 Lớp Dự Phòng)
                    address = "N/A"
                    try:
                        # Lớp 1: Thẻ con .Io6YTe (chứa chuỗi địa chỉ sạch không dính icon)
                        io_els = driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id^="address"] .Io6YTe, button[aria-label*="Địa chỉ"] .Io6YTe, button[aria-label*="Address"] .Io6YTe, [data-item-id^="address"] .Io6YTe')
                        if io_els:
                            for io in io_els:
                                t = clean_text(io.text)
                                if t and len(t) > 3:
                                    address = t
                                    break
                                    
                        # Lớp 2: Thuộc tính aria-label của nút địa chỉ
                        if not address or address == "N/A":
                            aria_els = driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id^="address"], button[aria-label*="Địa chỉ"], button[aria-label*="Address"], button[data-tooltip*="Địa chỉ"], button[data-tooltip*="Address"]')
                            for a_el in aria_els:
                                aria_val = a_el.get_attribute("aria-label") or a_el.get_attribute("data-tooltip") or ""
                                clean_aria = re.sub(r'^(Địa chỉ|Address):\s*', '', clean_text(aria_val), flags=re.IGNORECASE).strip()
                                if clean_aria and len(clean_aria) > 3:
                                    address = clean_aria
                                    break
                                    
                        # Lớp 3: Selector mở rộng tiêu chuẩn
                        if not address or address == "N/A":
                            addr_els = driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id^="address"], div.fontBodyMedium[aria-label*="Địa chỉ"]')
                            if addr_els:
                                address = clean_text(addr_els[0].text)
                                
                        # Lớp 4: Truy vấn trực tiếp bằng JS DOM Engine
                        if not address or address == "N/A":
                            js_addr = driver.execute_script("""
                                const btn = document.querySelector('button[data-item-id^="address"], button[aria-label*="Địa chỉ"], button[aria-label*="Address"], button[data-tooltip*="Địa chỉ"]');
                                if (btn) {
                                    const io = btn.querySelector('.Io6YTe');
                                    if (io && io.innerText && io.innerText.trim().length > 3) return io.innerText.trim();
                                    const aria = btn.getAttribute('aria-label') || btn.getAttribute('data-tooltip') || '';
                                    if (aria) return aria.replace(/^(Địa chỉ|Address):\\s*/i, '').trim();
                                    if (btn.innerText) return btn.innerText.trim();
                                }
                                return '';
                            """)
                            if js_addr:
                                address = clean_text(js_addr)
                    except Exception:
                        pass
                        
                    # Kiểm tra lọc khu vực Tỉnh / Thành phố & Tọa độ Bounding Box
                    target_prov = CONFIG.get("target_province", "all")
                    current_url = driver.current_url or url
                    if not is_allowed_location(current_url, address, target_prov):
                        print(f"[-] [{mode_tag}] Bỏ qua '{title}' (Địa chỉ: '{address}'): Nằm ngoài khu vực tỉnh thành đã chọn ({target_prov}).")
                        continue
                        
                    # Bóc tách Số điện thoại
                    phone = ""
                    try:
                        phone_els = driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id^="phone"], button[aria-label*="Số điện thoại"], button[aria-label*="Phone"]')
                        if phone_els:
                            phone_raw = phone_els[0].get_attribute('aria-label') or phone_els[0].text
                            phone = re.sub(r'[^0-9+]', '', phone_raw)
                    except Exception:
                        pass
                        
                    # Bóc tách Website
                    website = ""
                    try:
                        web_els = driver.find_elements(By.CSS_SELECTOR, 'a[data-item-id="authority"], a[aria-label*="Website"], a[aria-label*="Trang web"], a[aria-label*="website"]')
                        if web_els:
                            website = web_els[0].get_attribute('href') or ""
                    except Exception:
                        pass
                        
                    # Bóc tách Rating
                    rating = ""
                    try:
                        rate_els = driver.find_elements(By.CSS_SELECTOR, 'div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="sao"]')
                        if rate_els:
                            r_text = rate_els[0].get_attribute('aria-label') or ""
                            r_match = re.search(r'(\d+[\.,]\d+|\d+)', r_text)
                            if r_match:
                                rating = f"{float(r_match.group(1).replace(',', '.')):.1f}"
                    except Exception:
                        pass
                        
                    place_id = extract_place_id(url)
                    item_url = f"https://www.google.com/maps/search/?api=1&query={title.replace(' ', '%20')}&query_place_id={place_id}" if place_id else url
                    
                    final_key = extract_unique_key(item_url)
                    if final_key and final_key in existing_keys:
                        continue
                        
                    item = format_standard_record({
                        "stt": saved_count + 1,
                        "title": title,
                        "email": "",
                        "phone": phone,
                        "address": address,
                        "url": item_url,
                        "totalScore": rating,
                        "website": website,
                        "facebook": "",
                        "categoryName": category_name,
                        "source": "",
                        "isFlag": False
                    })
                    
                    saved_ok, file_tot = safe_save_record(output_file, item)
                    if saved_ok:
                        saved_count += 1
                        if final_key:
                            existing_keys.add(final_key)
                        print(f"✓ [{mode_tag}] Real-Time Save #{file_tot}: {title} | SĐT: {phone} | Category: {category_name}")
                except (NoSuchWindowException, WebDriverException):
                    print(f"[{mode_tag}] [!] Cửa sổ Chrome bị đóng khi đang crawl chi tiết.")
                    break
                except Exception as err:
                    print(f"[{mode_tag}] [!] Lỗi bóc tách URL: {err}")
                    continue
    except (NoSuchWindowException, WebDriverException):
        print(f"[{mode_tag}] [!] Tiến trình cào đã dừng do trình duyệt bị đóng.")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
            
    print(f"\n[{mode_tag}] HOÀN TẤT CÀO TỪ KHÓA TỰ DO! Đã lưu {saved_count} bản ghi vào '{output_file}'.")

if __name__ == "__main__":
    run_custom_keyword_scraper()
