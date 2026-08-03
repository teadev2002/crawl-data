import sys
import time
import json
import re
import os
from urllib.parse import unquote

# Cấu hình hiển thị đúng tiếng Việt UTF-8 trên Terminal Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

# ==================== NẠP CẤU HÌNH TỪ FILE CONFIG.JSON ====================
def get_default_chrome_profile_path():
    """Tự động xác định đường dẫn thư mục Chrome User Data trên Windows"""
    if sys.platform.startswith('win'):
        user_profile = os.environ.get('USERPROFILE')
        if user_profile:
            return os.path.join(user_profile, 'AppData', 'Local', 'Google', 'Chrome', 'User Data')
    return r"C:\Users\admin1\AppData\Local\Google\Chrome\User Data"

def load_config():
    """Nạp cấu hình từ file config.json. Nếu không tìm thấy file hoặc thiếu từ khóa, báo lỗi và dừng chương trình."""
    config_file = "config.json"
    
    if not os.path.exists(config_file):
        print(f"\n[!] Lỗi: Không tìm thấy file cấu hình '{config_file}'!")
        print("[*] Vui lòng đảm bảo file 'config.json' nằm cùng thư mục với tool.")
        print("[*] Chương trình dừng chạy.")
        sys.exit(1)
        
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        search_queries = config.get("search_queries", [])
        if not search_queries or len(search_queries) == 0:
            print(f"\n[!] Lỗi: Không tìm thấy danh sách địa điểm cần tìm kiếm ('search_queries') trong file '{config_file}'!")
            print("[*] Vui lòng bổ sung từ khóa tìm kiếm vào file config.json trước khi chạy.")
            print("[*] Chương trình dừng chạy.")
            sys.exit(1)
            
        # Điền mặc định cho các trường khác nếu thiếu để tránh lỗi hệ thống
        if "USE_MY_CHROME_PROFILE" not in config:
            config["USE_MY_CHROME_PROFILE"] = False
        if "CHROME_PROFILE_PATH" not in config:
            config["CHROME_PROFILE_PATH"] = get_default_chrome_profile_path()
        if "max_results" not in config:
            config["max_results"] = 100
        if "output_file" not in config:
            config["output_file"] = "hotels-TayNinh.json"
            
        return config
    except Exception as e:
        print(f"\n[!] Lỗi khi đọc file cấu hình '{config_file}': {e}")
        print("[*] Vui lòng kiểm tra định dạng file config.json (đảm bảo đúng cú pháp JSON).")
        print("[*] Chương trình dừng chạy.")
        sys.exit(1)

# Nạp cấu hình toàn cục ngay khi module chạy/được import
CONFIG = load_config()
USE_MY_CHROME_PROFILE = CONFIG.get("USE_MY_CHROME_PROFILE", False)
CHROME_PROFILE_PATH = CONFIG.get("CHROME_PROFILE_PATH", "")

STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

SERVICE_KEYWORDS_MAP = {
    "hotel": [
        "hotel", "motel", "khach san", "khách sạn", "nha nghi", "nhà nghỉ",
        "homestay", "home stay", "condotel", "phòng nghỉ",
        "phong nghi", "lưu trú", "luu tru","bungalow", "N/A"
    ],
    "spa": [
        "spa", "massage", "mat xa", "mat-xa", "mát xa", "masage", "chăm sóc da",
        "cham soc da", "skincare", "skin care", "facial", "face care", "trị liệu",
        "tri lieu", "therapy", "wellness", "wellness center", "thẩm mỹ", "tham my",
        "thẩm mỹ viện", "tham my vien", "viện thẩm mỹ", "vien tham my", "beauty",
        "beauty salon", "beauty center", "beauty clinic", "clinic", "aesthetic",
        "aesthetic clinic", "cosmetic", "cosmetic clinic", "làm đẹp", "lam dep",
        "chăm sóc sắc đẹp", "cham soc sac dep", "beauty care", "nail", "nails",
        "nail spa", "nail salon", "mi", "eyelash", "lash", "brow", "phun xăm",
        "phun xam", "gội đầu dưỡng sinh", "goi dau duong sinh", "dưỡng sinh",
        "duong sinh", "head spa", "hair spa", "sauna", "steam", "onsen", "N/A"
    ],
    "restaurant": [
        "restaurant", "resto", "nha hang", "nhà hàng", "quan an", "quán ăn",
        "am thuc", "ẩm thực", "dining", "eatery", "food", "seafood", "steakhouse",
        "bbq", "barbecue", "grill", "hotpot", "lau", "lẩu", "buffet", "fine dining",
        "casual dining", "com", "cơm", "nuong", "nướng", "hai san", "hải sản",
        "oc", "ốc", "ga ran", "gà rán", "chay", "vegetarian", "vegan",
        "hotel restaurant", "N/A"
    ]
}

def is_allowed_title(title, target_service=None):
    """Kiểm tra tên cơ sở có chứa ít nhất một trong các từ khóa thuộc dịch vụ đang chọn (không phân biệt hoa/thường)"""
    if not title or title.strip() in ["", "N/A", "n/a"]:
        return True
        
    if not target_service:
        target_service = CONFIG.get("target_service", "hotel")
    target_service = str(target_service).lower().strip()
    
    # Nếu target_service là "none" (tắt cả 3 dịch vụ) -> Cho phép cào tất cả các địa điểm
    if target_service in ["none", "off", "all", "disabled"]:
        return True
    
    keywords = SERVICE_KEYWORDS_MAP.get(target_service, SERVICE_KEYWORDS_MAP["hotel"])
    title_lower = title.lower().strip()
    
    return any(kw in title_lower for kw in keywords)

HOTEL_CORE_CATEGORY_KEYWORDS = [
    "hotel", "motel", "homestay", "home stay",
    "khách sạn", "khach san", "nhà nghỉ", "nha nghi", "condotel"
]

def is_allowed_category(cat_text, target_service=None):
    """
    Kiểm tra categoryName có chứa từ khóa loại hình cốt lõi hay không (áp dụng riêng cho chế độ 'hotel').
    """
    if not target_service:
        target_service = CONFIG.get("target_service", "hotel")
    target_service = str(target_service).lower().strip()

    if target_service in ["none", "off", "all", "disabled"]:
        return True

    # Chỉ áp dụng lọc categoryName khi chế độ đang là hotel
    if target_service == "hotel":
        if not cat_text or cat_text.strip() in ["", "N/A", "n/a"]:
            return False
        cat_lower = cat_text.lower().strip()
        return any(kw in cat_lower for kw in HOTEL_CORE_CATEGORY_KEYWORDS)
        
    return True

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

def extract_lat_lng(url):
    """Trích xuất vĩ độ (lat) và kinh độ (lng) từ Google Maps URL"""
    if not url:
        return None, None
    m34 = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', url)
    if m34:
        return float(m34.group(1)), float(m34.group(2))
    mat = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', url)
    if mat:
        return float(mat.group(1)), float(mat.group(2))
    return None, None

def is_allowed_location(url, address, selected_province=None):
    """
    Kiểm tra xem địa điểm có nằm đúng trong phạm vi Tỉnh / Thành phố đã chọn hay không.
    """
    if not selected_province:
        selected_province = CONFIG.get("target_province", "all")
    selected_province = str(selected_province).strip()
    
    if selected_province in ["all", "none", "off", "all_provinces", ""]:
        return True
        
    info = PROVINCE_BOUNDS_MAP.get(selected_province)
    if not info:
        sel_lower = selected_province.lower().replace("thành phố", "").replace("tỉnh", "").strip()
        return sel_lower in address.lower() if address else True
        
    # 1. Kiểm tra từ khóa tên Tỉnh/Thành trong địa chỉ (Address Check)
    addr_lower = (address or "").lower()
    if any(kw in addr_lower for kw in info["keywords"]):
        return True
        
    # 2. Kiểm tra Khung Tọa độ địa lý Bounding Box (Lat, Lng Check)
    lat, lng = extract_lat_lng(url)
    if lat is not None and lng is not None:
        min_lat, max_lat, min_lng, max_lng = info["bounds"]
        if min_lat <= lat <= max_lat and min_lng <= lng <= max_lng:
            return True
            
    return False

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

def safe_save_record(output_file, new_item):
    """
    Lưu Real-Time 1 bản ghi mới vào file output_file một cách an toàn bằng Nguyên tử (Atomic Write).
    """
    for attempt in range(15):
        try:
            records = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            try:
                                raw_records = json.loads(content)
                            except json.JSONDecodeError as jde:
                                if "Extra data" in str(jde):
                                    raw_records = json.loads(content[:jde.pos].strip())
                                else:
                                    raw_records = []
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
    """Đếm tổng số bản ghi thực tế hiện đang có trong file kết quả output_file"""
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

def extract_place_id(url):
    """Trích xuất place_id từ URL"""
    match = re.search(r'place_id=([^&]+)', url)
    return match.group(1) if match else None

def extract_unique_key(url):
    """
    Trích xuất khóa định danh duy nhất của địa điểm từ Google Maps URL để so sánh trùng lặp.
    Hỗ trợ cả Link chia sẻ (query_place_id=ChIJ...) và Link trực tiếp chứa mã FID/CID (!1s0x...:0x...).
    """
    if not url:
        return ""
    # 1. Tìm query_place_id (trong share URL)
    match_place_id = re.search(r'query_place_id=([^&]+)', url)
    if match_place_id:
        return match_place_id.group(1)
    # 2. Tìm place_id trong query parameters khác
    match_place_id_2 = re.search(r'place_id=([^&]+)', url)
    if match_place_id_2:
        return match_place_id_2.group(1)
    # 3. Tìm FID/CID đầy đủ dạng tọa độ lục phân trong tham số data (!1s0x[hex]:0x[hex])
    match_fid = re.search(r'!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-F]+)', url)
    if match_fid:
        return match_fid.group(1)
    # 4. Tìm CID đơn lẻ dạng mã số thập lục phân (!1s0x[hex])
    match_cid = re.search(r'!1s([0x0-9a-fA-F]+)', url)
    if match_cid:
        return match_cid.group(1)
    # 5. Nếu không khớp các mẫu trên, chuẩn hóa và loại bỏ các tham số tracking, ngôn ngữ thừa
    normalized = url.split('?')[0].split('&')[0]
    normalized = re.sub(r'/@[0-9.-]+,[0-9.-]+,[0-9a-zA-Z.]+', '', normalized)
    return normalized

def clean_text(text):
    """Loại bỏ các ký tự xuống dòng, khoảng trắng thừa, ký tự ẩn và các icon đặc biệt (\ue000-\uf8ff)"""
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

def create_browser_session(p):
    """Khởi tạo phiên trình duyệt mới cho Playwright (hỗ trợ cả Chrome thật và Chromium mặc định) với tối ưu hóa chặn tài nguyên nặng"""
    if USE_MY_CHROME_PROFILE:
        print(f"Đang mở Google Chrome thật tại đường dẫn: {CHROME_PROFILE_PATH}...")
        context = p.chromium.launch_persistent_context(
            CHROME_PROFILE_PATH,
            channel="chrome",
            headless=False
        )
        page = context.pages[0] if context.pages else context.new_page()
        browser = None
    else:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--js-flags=--max-old-space-size=512"
            ]
        )
        context = browser.new_context()
        page = context.new_page()

    # Tối ưu siêu tốc (Asset Blocking): Chặn tải hình ảnh, font chữ, media không cần thiết cho bóc tách văn bản
    def block_unnecessary_assets(route, request):
        if request.resource_type in ["image", "media", "font"]:
            route.abort()
        else:
            route.continue_()

    try:
        context.route("**/*", block_unnecessary_assets)
    except Exception:
        pass

    return browser, context, page

def scrape_google_maps_multi(queries, max_results=400, output_file="hotels.json", mode="top"):
    results = []
    place_urls = []
    
    # 0. Khởi tạo file output_file lập tức ở giây đầu tiên nếu chưa tồn tại
    if not os.path.exists(output_file):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[*] Đã tự động tạo mới file kết quả: {output_file}")
        except Exception as e:
            print(f"[!] Không thể khởi tạo file kết quả: {e}")

    total_queries_count = len(queries)

    match_way = re.match(r'^(?:(\d+)way_)?p(\d+)$', mode.lower())
    if match_way:
        total_w = int(match_way.group(1)) if match_way.group(1) else 5
        w_idx = int(match_way.group(2)) - 1
        start_idx = (w_idx * total_queries_count) // total_w
        end_idx = ((w_idx + 1) * total_queries_count) // total_w
        target_queries = queries[start_idx:end_idx]
        print(f"[*] Chế độ quét: LUỒNG {total_w}-WAY [{mode.upper()}]. Quét {len(target_queries)}/{total_queries_count} từ khóa thuộc phân đoạn {w_idx + 1}/{total_w} (Từ khóa {start_idx + 1} -> {end_idx})...")
        queries = target_queries
    elif mode == "bottom":
        midpoint = total_queries_count // 2 if total_queries_count > 1 else 1
        target_queries = list(reversed(queries[midpoint:])) if total_queries_count > 1 else queries
        print(f"[*] Chế độ quét: LUỒNG BOTTOM (QUÉT TỪ DƯỚI LÊN). Quét {len(target_queries)} từ khóa thuộc nửa sau (Từ khóa {midpoint + 1} -> {total_queries_count})...")
        queries = target_queries
    else:
        midpoint = total_queries_count // 2 if total_queries_count > 1 else 1
        target_queries = queries[:midpoint] if total_queries_count > 1 else queries
        print(f"[*] Chế độ quét: LUỒNG TOP (QUÉT TỪ TRÊN XUỐNG). Quét {len(target_queries)} từ khóa thuộc nửa đầu (Từ khóa 1 -> {len(target_queries)})...")
        queries = target_queries
        
    # 1. Đọc danh sách cũ và quét thư mục để chống trùng lặp chỉ MỘT LẦN khi khởi động
    existing_records = []
    existing_keys = set()
    
    # A. Đọc file kết quả đích (nếu đã có sẵn từ trước)
    dest_file_existed = os.path.exists(output_file)
    if dest_file_existed:
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_records = json.load(f)
                if isinstance(existing_records, list):
                    for r in existing_records:
                        if isinstance(r, dict) and "url" in r:
                            key = extract_unique_key(r["url"])
                            if key:
                                existing_keys.add(key)
            print(f"[*] Tìm thấy file kết quả cũ '{output_file}' chứa {len(existing_records)} địa điểm.")
        except Exception as e:
            print(f"[!] Lỗi khi đọc file kết quả cũ '{output_file}': {e}.")
        
    # B. Quét tất cả các file JSON khác trong thư mục để lọc trùng toàn diện
    other_json_keys_count = 0
    try:
        # Lấy danh sách tất cả các file json trong thư mục hiện tại
        all_json_files = [f for f in os.listdir('.') if f.endswith('.json')]
        # Bỏ qua file config.json và file output_file đích
        exclude_files = {"config.json", os.path.basename(output_file)}
        other_json_files = [f for f in all_json_files if f not in exclude_files]
        
        for json_file in other_json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    other_records = json.load(f)
                    if isinstance(other_records, list):
                        for r in other_records:
                            if isinstance(r, dict) and "url" in r:
                                key = extract_unique_key(r["url"])
                                if key and key not in existing_keys:
                                    existing_keys.add(key)
                                    other_json_keys_count += 1
            except Exception as read_other_err:
                print(f"[!] Bỏ qua file '{json_file}' khi quét lọc trùng do lỗi đọc: {read_other_err}")
                
        if other_json_files:
            print(f"[*] Đã quét {len(other_json_files)} file JSON khác trong thư mục, nạp thêm {other_json_keys_count} URL độc nhất để chống trùng lặp.")
    except Exception as scan_err:
        print(f"[!] Không thể quét các file JSON khác trong thư mục: {scan_err}")
        
    print(f"[*] Tổng số URL nạp vào bộ nhớ để chống trùng lặp: {len(existing_keys)} địa điểm.")

    print(f"[*] [MAP] Số kết quả tối đa: {max_results}")
    thread_target = max_results
    target_urls_collection_limit = max_results
    print(f"[*] [{mode.upper()}] Mục tiêu thu thập liên kết của luồng này: {target_urls_collection_limit} URLs")

    with sync_playwright() as p:
        browser, context, page = create_browser_session(p)
        
        # Vòng lặp quét qua từng khu vực truy vấn
    with sync_playwright() as p:
        browser, context, page = create_browser_session(p)
        thread_saved_count = 0
        
        # Vòng lặp quét bù đắp liên tục từng từ khóa tìm kiếm cho tới khi đạt đủ chỉ tiêu thread_target
        for q_index, query in enumerate(queries):
            file_total = get_total_file_records(output_file)
            if thread_saved_count >= thread_target or file_total >= max_results:
                print(f"\n[+] [{mode.upper()}] Tổng số bản ghi trong file đã đạt chỉ tiêu tối đa ({file_total}/{max_results} bản ghi)! Hoàn thành!")
                break

            print(f"\n--- [{mode.upper()}] Đang quét khu vực ({q_index + 1}/{len(queries)}): {query} (Đã lưu: {thread_saved_count}/{thread_target}) ---")
            try:
                page.goto(f"https://www.google.com/maps/search/{query.replace(' ', '+')}", wait_until='domcontentloaded', timeout=60000)
            except Exception as goto_err:
                print(f"   [!] Cảnh báo: Tải trang tìm kiếm chậm (Timeout): {goto_err}")
                if any(kw in str(goto_err).lower() for kw in ["closed", "connection", "target", "driver"]):
                    print("   [*] Mất kết nối trình duyệt. Đang tự động mở lại phiên trình duyệt mới...")
                    try:
                        if context: context.close()
                        if browser: browser.close()
                    except Exception:
                        pass
                    time.sleep(2)
                    browser, context, page = create_browser_session(p)
                    continue
            time.sleep(1.2)
            
            # Chờ feed hiển thị
            try:
                page.wait_for_selector('div[role="feed"]', timeout=4000)
            except Exception:
                pass
                
            # 1. Thu thập liên kết cho từ khóa hiện tại
            current_query_urls = []
            no_change_count = 0
            last_count = 0
            
            for scroll_step in range(12):
                if thread_saved_count >= thread_target or get_total_file_records(output_file) >= max_results:
                    break
                try:
                    links = page.locator('a[href*="/maps/place/"]').all()
                    for link in links:
                        try:
                            href = link.get_attribute('href')
                            if href:
                                key = extract_unique_key(href)
                                if key and key in existing_keys:
                                    continue
                                if href not in current_query_urls:
                                    current_query_urls.append(href)
                        except Exception:
                            continue
                except Exception:
                    pass

                cur_cnt = len(current_query_urls)
                if cur_cnt == last_count:
                    no_change_count += 1
                    if no_change_count >= 3:
                        break
                else:
                    no_change_count = 0
                    last_count = cur_cnt

                feed_locator = page.locator('div[role="feed"]').first
                if feed_locator.count() > 0:
                    try:
                        page.evaluate('(el) => el.scrollTop = el.scrollHeight', feed_locator.element_handle())
                    except Exception:
                        page.keyboard.press('End')
                else:
                    page.keyboard.press('End')
                    
                page.evaluate("window.scrollBy(0, 3000)")
                time.sleep(0.8)

            print(f"[*] [{mode.upper()}] Từ khóa '{query}': Thu thập được {len(current_query_urls)} liên kết ứng viên mới. Tiến hành bóc tách chi tiết...")

            # 2. Bóc tách chi tiết & Lưu Real-Time cho từng URL của từ khóa này
            for i, url in enumerate(current_query_urls):
                file_total = get_total_file_records(output_file)
                if thread_saved_count >= thread_target or file_total >= max_results:
                    print(f"\n[+] [{mode.upper()}] Tổng số bản ghi trong file đã đạt chỉ tiêu tối đa ({file_total}/{max_results} bản ghi)! Hoàn thành!")
                    break

                key = extract_unique_key(url)
                if key:
                    if os.path.exists(output_file):
                        try:
                            with open(output_file, 'r', encoding='utf-8') as f:
                                latest_recs = json.load(f)
                                if isinstance(latest_recs, list):
                                    for lr in latest_recs:
                                        if isinstance(lr, dict) and "url" in lr:
                                            lk = extract_unique_key(lr["url"])
                                            if lk:
                                                existing_keys.add(lk)
                        except Exception:
                            pass
                            
                if key and key in existing_keys:
                    continue

                print(f"[{mode.upper()}] Đang crawl [{i+1}/{len(current_query_urls)}]: {url}")
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_selector('h1', timeout=1500)
                except Exception as goto_err:
                    pass
                time.sleep(0.3)

                title_raw = page.locator('h1').first.inner_text() if page.locator('h1').count() > 0 else "N/A"
                title = clean_text(title_raw)

                # Category Name (Loại hình kinh doanh)
                cat_text = ""
                cat_elements = page.locator('button[jsaction*="category"], button[data-item-id*="category"]').all()
                if cat_elements:
                    cat_text = clean_text(cat_elements[0].inner_text())

                if not cat_text:
                    try:
                        header_text = page.locator('div[role="main"]').first.inner_text()
                        if "·" in header_text:
                            for line in header_text.split('\n'):
                                if "·" in line:
                                    parts = line.split("·")
                                    if len(parts) > 1:
                                        candidate = parts[1].strip()
                                        if candidate and len(candidate) < 60:
                                            cat_text = clean_text(candidate)
                                            break
                    except Exception:
                        pass
                
                title_ok = is_allowed_title(title)
                cat_ok = is_allowed_category(cat_text)
                
                if not (title_ok or cat_ok):
                    print(f"[-] [{mode.upper()}] Bỏ qua '{title}' (Category: '{cat_text}'): Không thỏa mãn từ khóa chỉ định ở Tên lẫn Loại hình.")
                    continue
                
                address_elements = page.locator('button[data-item-id^="address"]').all()
                address_raw = address_elements[0].inner_text() if address_elements else "N/A"
                address = clean_text(address_raw)

                # Kiểm tra lọc khu vực Tỉnh / Thành phố
                if not is_allowed_location(url, address):
                    sel_prov = CONFIG.get("target_province", "all")
                    print(f"[-] [{mode.upper()}] Bỏ qua '{title}' (Địa chỉ: '{address}'): Nằm ngoài khu vực tỉnh thành đã chọn ({sel_prov}).")
                    continue

                phone_elements = page.locator('button[data-item-id^="phone"]').all()
                phone_raw = phone_elements[0].inner_text() if phone_elements else ""
                phone = re.sub(r'[^0-9+]', '', phone_raw) if phone_raw else ""

                website_elements = page.locator('a[data-item-id="authority"], a[aria-label*="Website"], a[aria-label*="Trang web"], a[aria-label*="website"], a[aria-label*="trang web"]').all()
                website = website_elements[0].get_attribute('href') if website_elements else ""

                rating_text = (
                    page.locator('div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="sao"]')
                    .first.get_attribute('aria-label')
                    if page.locator('div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="sao"]').count() > 0
                    else ""
                )
                rating_match = re.search(r'(\d+[\.,]\d+|\d+)', rating_text)
                if rating_match:
                    rating_val = rating_match.group(1).replace(',', '.')
                    rating = f"{float(rating_val):.1f}"
                else:
                    rating = ""

                place_id = extract_place_id(url)
                item_url = f"https://www.google.com/maps/search/?api=1&query={title.replace(' ', '%20')}&query_place_id={place_id}" if place_id else url

                final_key = extract_unique_key(item_url)
                if final_key and final_key in existing_keys:
                    print(f"[-] Bỏ qua (Đã tồn tại trong danh sách cũ sau đối chiếu URL thực tế): {item_url}")
                    continue

                item = format_standard_record({
                    "stt": len(existing_records) + len(results) + 1,
                    "title": title,
                    "email": "",
                    "phone": phone,
                    "address": address,
                    "url": item_url,
                    "totalScore": rating,
                    "website": website,
                    "facebook": "",
                    "categoryName": cat_text,
                    "source": "",
                    "isFlag": False
                })

                saved_success, total_file_records = safe_save_record(output_file, item)
                if saved_success:
                    results.append(item)
                    thread_saved_count += 1
                    if final_key:
                        existing_keys.add(final_key)
                    print(f"✓ [{mode.upper()}] Real-Time Save #{total_file_records} (Luồng: {thread_saved_count}/{thread_target} bản ghi): {title} - {phone}")
                    if total_file_records >= max_results:
                        print(f"\n[+] [{mode.upper()}] Tổng số bản ghi trong file đã đạt chỉ tiêu tối đa ({total_file_records}/{max_results} bản ghi)! Hoàn thành!")
                        break
                else:
                    print(f"[-] Bỏ qua STT (Đã được luồng kia lưu trước): {title}")

        try:
            if context: context.close()
            if browser: browser.close()
        except Exception:
            pass

    print(f"\n[+] [{mode.upper()}] CÀO GOOGLE MAPS HOÀN TẤT! Luồng này đã đóng góp {thread_saved_count} bản ghi mới.")

    # Đọc lại toàn bộ bản ghi thực tế tích lũy hiện đang có trong file đĩa để thông báo kết quả chuẩn xác nhất (Read-Only)
    final_file_records = []
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    raw_recs = json.loads(content)
                    if isinstance(raw_recs, list):
                        final_file_records = raw_recs
        except Exception:
            pass

    print(f"Tổng số kết quả hiện tại trong file '{output_file}': {len(final_file_records)} địa điểm.")
    return final_file_records


# ==================== KHU VỰC KHỞI CHẠY SCRIPT ====================
if __name__ == "__main__":
    # Đọc tham số dòng lệnh --mode top / --mode bottom
    mode = "top"
    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=")[1].lower()
        elif arg.lower() in ["top", "bottom"]:
            mode = arg.lower()

    # Ép dùng trình duyệt cách ly để cả 2 luồng TOP & BOTTOM khởi chạy song song 100% không bị vướng Chrome Profile Lock
    if mode in ["top", "bottom"]:
        USE_MY_CHROME_PROFILE = False

    # Nạp danh sách từ khóa và cấu hình từ file config.json
    search_queries = CONFIG.get("search_queries", [])
    max_results = CONFIG.get("max_results", 100)
    output_filename = CONFIG.get("output_file", "hotels-TayNinh.json")
    
    target_province = CONFIG.get("target_province", "all")
    print(f"[*] Đã nạp cấu hình thành công từ file config.json.")
    print(f"[*] Chế độ khởi chạy: {mode.upper()}")
    print(f"[*] Giới hạn Tỉnh/Thành phố: {target_province}")
    print(f"[*] Số từ khóa tìm kiếm: {len(search_queries)}")
    print(f"[*] Số kết quả tối đa: {max_results}")
    print(f"[*] File lưu dữ liệu: {output_filename}")
    print(f"[*] Sử dụng profile Chrome: {USE_MY_CHROME_PROFILE}")
    
    # Chạy scraper
    scrape_google_maps_multi(search_queries, max_results=max_results, output_file=output_filename, mode=mode)
