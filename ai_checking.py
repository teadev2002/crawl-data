import json
import time
import os
import re
import sys
import shutil
import unicodedata
from urllib.parse import quote_plus, unquote

# Cấu hình stdout/stderr sang UTF-8 để hiển thị tiếng Việt mượt mà trên console Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

# Import Google GenAI SDK (google-genai hoặc google-generativeai)
HAS_GENAI = False
genai_module = None

try:
    from google import genai
    genai_module = "google.genai"
    HAS_GENAI = True
except Exception:
    try:
        import google.generativeai as genai_old
        genai_module = "google.generativeai"
        HAS_GENAI = True
    except Exception:
        HAS_GENAI = False

def load_config():
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Lỗi khi đọc file cấu hình '{config_file}': {e}")
            sys.exit(1)
    return {}

CONFIG = load_config()
TARGET_JSON_FILE = CONFIG.get("output_file", "hotels.json")

STANDARD_KEYS = ["stt", "title", "email", "phone", "address", "url", "totalScore", "website", "facebook", "categoryName", "source", "isFlag"]

def get_gemini_client():
    api_key = (
        CONFIG.get("gemini_api_key") or
        CONFIG.get("google_api_key") or
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_API_KEY") or
        ""
    ).strip()

    if not api_key:
        print("[!] Chưa cấu hình Gemini API Key. Bạn vui lòng điền API Key vào file 'config.json' (trường 'gemini_api_key').")
        return None, ""

    if not HAS_GENAI:
        print("[!] Thư viện 'google-genai' hoặc 'google-generativeai' chưa được cài đặt.")
        return None, api_key

    try:
        if genai_module == "google.genai":
            client = genai.Client(api_key=api_key)
            return client, api_key
        elif genai_module == "google.generativeai":
            import google.generativeai as genai_old
            genai_old.configure(api_key=api_key)
            model = genai_old.GenerativeModel("gemini-1.5-flash")
            return model, api_key
    except Exception as e:
        print(f"[!] Lỗi khi khởi tạo Gemini Client: {e}")
        return None, api_key

def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', ' ', str(text))
    return re.sub(r'\s+', ' ', cleaned).strip()

def strip_vietnamese_accents(s):
    if not s: return ""
    nfkd = unicodedata.normalize('NFD', s)
    return "".join([c for c in nfkd if unicodedata.category(c) != 'Mn']).lower().strip()

def fix_vietnamese_abbreviations(text):
    """Tự động sửa lỗi chính tả, chuẩn hóa các từ viết tắt phổ biến trong địa chỉ/tên địa điểm Việt Nam."""
    if not text:
        return ""
    
    t = text
    replacements = [
        (r'\bTP\.?\s*HCM\b', 'Thành phố Hồ Chí Minh', re.IGNORECASE),
        (r'\bTP\.?\s*Hà Nội\b', 'Thành phố Hà Nội', re.IGNORECASE),
        (r'\bTP\.?\s*Đà Nẵng\b', 'Thành phố Đà Nẵng', re.IGNORECASE),
        (r'\bTP\.?\s*Nha Trang\b', 'Thành phố Nha Trang', re.IGNORECASE),
        (r'\bTP\.?\s*Cần Thơ\b', 'Thành phố Cần Thơ', re.IGNORECASE),
        (r'\bTP\.?\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Thành phố \1', 0),
        (r'\bQ\.?\s*(\d+|[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Quận \1', 0),
        (r'\bP\.?\s*(\d+|[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Phường \1', 0),
        (r'\bTX\.?\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Thị xã \1', 0),
        (r'\bH\.?\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Huyện \1', 0),
        (r'\bĐ\.?\s*([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐa-zàáâãèéêìíòóôõùúýđ]+)', r'Đường \1', 0),
        (r'\bKS\b', 'Khách sạn', re.IGNORECASE),
        (r'\bNhà Nghỉ\b', 'Nhà nghỉ', re.IGNORECASE),
    ]

    for pattern, replacement, flags in replacements:
        try:
            t = re.sub(pattern, replacement, t, flags=flags)
        except Exception:
            pass

    return clean_text(t)

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

def format_standard_record(r, default_stt=1):
    formatted = {}
    for key in STANDARD_KEYS:
        if key == "stt":
            formatted[key] = r.get("stt", default_stt)
        elif key == "isFlag":
            formatted[key] = bool(r.get("isFlag", False))
        elif key == "totalScore":
            formatted[key] = ""
        else:
            val = r.get(key, "")
            formatted[key] = val if val is not None else ""
    return formatted

def safe_save_record(output_file, updated_item):
    if not os.path.exists(output_file):
        return False
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            records = json.load(f)

        target_stt = updated_item.get("stt")
        target_title = updated_item.get("title", "").strip().lower()
        updated = False

        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue
            r_stt = r.get("stt")
            r_title = str(r.get("title", "")).strip().lower()
            if (target_stt is not None and r_stt == target_stt) or (r_title and r_title == target_title):
                for k in STANDARD_KEYS:
                    if k in updated_item and updated_item[k] != "" and k != "totalScore":
                        r[k] = updated_item[k]
                r["totalScore"] = ""  # Đảm bảo totalScore luôn rỗng
                records[idx] = format_standard_record(r, r.get("stt", idx + 1))
                updated = True
                break

        if updated:
            temp_file = f"{output_file}.tmp_aicheck_{os.getpid()}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

            replaced = False
            for sub_attempt in range(5):
                try:
                    os.replace(temp_file, output_file)
                    replaced = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.3)

            if not replaced:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)
                if os.path.exists(temp_file):
                    try: os.remove(temp_file)
                    except Exception: pass
            return True
    except Exception as e:
        print(f"[!] Lỗi ghi file nguyên tử AI Checking: {e}")
    return False

def query_gemini_chatbox(client, user_query_prompt):
    """
    Gửi prompt dạng Chat Box tới Gemini AI và nhận phản hồi theo đúng cấu trúc:
    Thông tin địa điểm:
    - Tên: ...
    - Địa chỉ: ...
    - Số điện thoại: ...
    - Đánh giá: ...
    - Xem trên bản đồ: https://www.google.com/maps/place/...
    """
    prompt = (
        f"Đóng vai trợ lý AI tra cứu bản đồ địa điểm tại Việt Nam. Hãy trả lời câu hỏi Chatbox dưới đây:\n"
        f"Lệnh hỏi từ User: \"{user_query_prompt}\"\n\n"
        f"Hãy tự động sửa lỗi chính tả/viết tắt nếu có và trả lời CHÍNH XÁC theo cấu trúc dưới đây:\n"
        f"Thông tin địa điểm:\n"
        f"- Tên: [Tên đầy đủ của địa điểm]\n"
        f"- Địa chỉ: [Địa chỉ đầy đủ]\n"
        f"- Số điện thoại: [Số điện thoại hoặc Rỗng nếu không có]\n"
        f"- Đánh giá: 4.0 ⭐\n"
        f"- Xem trên bản đồ: [Link Google Maps đầy đủ dạng https://www.google.com/maps/place/...]\n\n"
        f"Lưu ý: Bắt buộc phải có đường link https://www.google.com/maps/place/... ở phần Xem trên bản đồ."
    )

    if not client:
        return ""

    try:
        if genai_module == "google.genai":
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            return response.text if response else ""
        elif genai_module == "google.generativeai":
            response = client.generate_content(prompt)
            return response.text if response else ""
    except Exception as err:
        print(f"[{mode_tag}] [!] Gemini API Exception: {err}")
        pass
    
    return ""

def extract_map_url_and_info_from_ai_response(ai_response_text):
    """Trích xuất link Google Maps URL, SĐT, Tên & Địa chỉ từ đoạn văn bản phản hồi của Gemini AI"""
    result = {
        "map_url": "",
        "phone": "",
        "name": "",
        "address": ""
    }
    if not ai_response_text:
        return result

    # 1. Trích xuất Google Maps URL bằng Regex
    url_match = re.search(r'https?://(?:www\.)?google\.[a-z\.]+/maps/(?:place|search)/[^\s\)\>\]"\'`]+', ai_response_text)
    if url_match:
        result["map_url"] = url_match.group(0).rstrip('.,;)')
    else:
        url_match2 = re.search(r'https?://maps\.google\.[a-z\.]+/?[^\s\)\>\]"\'`]+', ai_response_text)
        if url_match2:
            result["map_url"] = url_match2.group(0).rstrip('.,;)')

    # 2. Trích xuất SĐT
    phone_match = re.search(r'(?:Số điện thoại|Phone|SĐT)\s*:\s*([\d\s\.\-\+\(\)]+)', ai_response_text, re.IGNORECASE)
    if phone_match:
        raw_p = clean_text(phone_match.group(1))
        digits = re.sub(r'\D', '', raw_p)
        if len(digits) >= 9:
            result["phone"] = digits

    # 3. Trích xuất Tên
    name_match = re.search(r'(?:Tên|Name)\s*:\s*([^\n]+)', ai_response_text, re.IGNORECASE)
    if name_match:
        result["name"] = clean_text(name_match.group(1))

    # 4. Trích xuất Địa chỉ
    addr_match = re.search(r'(?:Địa chỉ|Address)\s*:\s*([^\n]+)', ai_response_text, re.IGNORECASE)
    if addr_match:
        result["address"] = clean_text(addr_match.group(1))

    return result

def evaluate_match_score_with_gemini(client, booking_title, booking_address, maps_title, maps_address):
    """Đánh giá % trùng khớp (>= 50%) giữa dữ liệu gốc và dữ liệu Google Maps bằng Gemini AI"""
    clean_bt = fix_vietnamese_abbreviations(booking_title)
    clean_ba = fix_vietnamese_abbreviations(booking_address)
    clean_mt = fix_vietnamese_abbreviations(maps_title)
    clean_ma = fix_vietnamese_abbreviations(maps_address)

    if not client:
        return calculate_title_similarity(clean_bt + " " + clean_ba, clean_mt + " " + clean_ma)

    prompt = (
        f"Hãy so sánh độ tương đồng (từ 0% đến 100%) giữa 2 địa điểm dưới đây, tự động bỏ qua lỗi viết tắt/chính tả:\n\n"
        f"ĐỊA ĐIỂM DỮ LIỆU GỐC:\n"
        f"- Tên: {clean_bt}\n"
        f"- Địa chỉ: {clean_ba}\n\n"
        f"ĐỊA ĐIỂM TÌM THẤY TRÊN GOOGLE MAPS:\n"
        f"- Tên: {clean_mt}\n"
        f"- Địa chỉ: {clean_ma}\n\n"
        f"Yêu cầu: Trả về DUY NHẤT 1 con số nguyên biểu diễn phần trăm trùng khớp (ví dụ: 85). Không kèm bất kỳ ký tự nào khác."
    )

    try:
        if genai_module == "google.genai":
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            match = re.search(r'(\d+)', response.text)
            if match:
                return int(match.group(1))
        elif genai_module == "google.generativeai":
            response = client.generate_content(prompt)
            match = re.search(r'(\d+)', response.text)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    
    return calculate_title_similarity(clean_bt, clean_mt)

def run_ai_checking(input_file=None):
    if not input_file:
        input_file = TARGET_JSON_FILE

    mode_tag = "AI_CHECKING"
    print(f"[{mode_tag}] Đã khởi chạy Chức Năng 8: AI Checking (Google Gemini Chat Box)...")

    if not os.path.exists(input_file):
        print(f"[{mode_tag}] Lỗi: Không tìm thấy file dữ liệu '{input_file}'!")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        records = json.load(f)

    total_records = len(records)
    print(f"[{mode_tag}] Đã đọc file dữ liệu '{input_file}' ({total_records} bản ghi).")

    client, api_key = get_gemini_client()
    if client:
        print(f"[{mode_tag}] ✓ Đã kết nối thành công Google Gemini Flash Client.")
    else:
        print(f"[{mode_tag}] [!] Chưa nhận diện API Key trong config.json, đang chạy chế độ fallback.")

    worker_profile_dir = os.path.join(os.getcwd(), f"browser_profile_aicheck_{os.getpid()}")
    if os.path.exists(worker_profile_dir):
        try:
            shutil.rmtree(worker_profile_dir, ignore_errors=True)
        except Exception:
            pass

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            worker_profile_dir,
            headless=CONFIG.get("headless", False),
            slow_mo=50,
            locale="vi-VN",
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            args=["--disable-blink-features=AutomationControlled", "--disable-gpu", "--no-sandbox"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        matched_count = 0

        for idx, r in enumerate(records):
            if not isinstance(r, dict):
                continue

            title = r.get("title", "")
            address = r.get("address", "")
            stt = r.get("stt", idx + 1)
            original_booking_url = r.get("url", "")
            original_source = r.get("source", f"Booking: {original_booking_url}")

            if not title:
                print(f"[{mode_tag}] [{idx+1}/{total_records}] Bỏ qua STT {stt} do không có Tên cơ sở.")
                continue

            # BƯỚC 1: Tạo Prompt dạng Chatbox
            clean_t = fix_vietnamese_abbreviations(title)
            clean_a = fix_vietnamese_abbreviations(address)
            chat_user_prompt = f"{clean_t} {clean_a} map".strip()

            print(f"\n==================================================")
            print(f"💬 [USER CHATBOX]: \"{chat_user_prompt}\"")
            print(f"==================================================")

            # BƯỚC 2: Gemini AI phản hồi Chatbox theo chuẩn hình ảnh
            ai_response = query_gemini_chatbox(client, chat_user_prompt)

            if ai_response:
                print(f"🤖 [GEMINI AI PHẢN HỒI]:\n{ai_response}")
            else:
                print(f"🤖 [GEMINI AI PHẢN HỒI]: (Không tạo được response từ Gemini API, đang sử dụng fallback Google Maps)")

            # BƯỚC 3: Trích xuất Link URL Maps & SĐT từ câu trả lời của AI
            ai_extracted = extract_map_url_and_info_from_ai_response(ai_response)
            target_map_url = ai_extracted["map_url"]
            extracted_phone = ai_extracted["phone"]
            maps_title_from_ai = ai_extracted["name"]
            maps_addr_from_ai = ai_extracted["address"]
            extracted_website = ""

            # BƯỚC 4: Tìm kiếm trực tiếp trên Google Maps để quét danh sách & lớp xxVWCe
            search_maps_page_url = f"https://www.google.com/maps/search/{quote_plus(chat_user_prompt)}"
            try:
                page.goto(search_maps_page_url, wait_until='domcontentloaded', timeout=35000)
                time.sleep(2.0)

                # NẾU RƠI VÀO GIAO DIỆN DANH SÁCH (ROLE="FEED"), QUÉT QUA CÁC ITEM THẺ BÀI CLASS="xxVWCe"
                feed_locator = page.locator('div[role="feed"]')
                if feed_locator.count() > 0 or page.locator('.xxVWCe').count() > 0:
                    title_nodes = page.locator('.xxVWCe, div.qBF1Pd, a[href*="/maps/place/"]').all()
                    best_match_card = None
                    best_match_score = 0
                    best_card_title = ""

                    for t_node in title_nodes:
                        try:
                            card_text = clean_text(t_node.inner_text())
                            if not card_text: continue
                            
                            sim_score = calculate_title_similarity(title, card_text)
                            if sim_score >= 50 and sim_score > best_match_score:
                                best_match_score = sim_score
                                best_match_card = t_node
                                best_card_title = card_text
                        except Exception:
                            continue

                    if best_match_card and best_match_score >= 50:
                        print(f"[{mode_tag}] [+] Đã tìm thấy Item trong danh sách khớp class '.xxVWCe': '{best_card_title}' (Tỷ lệ khớp tên: {best_match_score}%)")
                        best_match_card.click()
                        time.sleep(2.0)

                target_map_url = page.url

                # Bóc tách Tên trên Google Maps
                h1_el = page.locator('h1.DUwfe, h1.fontHeadlineLarge').first
                if h1_el.count() > 0:
                    maps_title_from_ai = clean_text(h1_el.inner_text())

                # Bóc tách SĐT
                phone_btn = page.locator('button[data-tooltip*="phone"], button[data-item-id*="phone"]').first
                if phone_btn.count() > 0:
                    extracted_phone = clean_text(phone_btn.inner_text())

                # Bóc tách Địa chỉ
                addr_btn = page.locator('button[data-item-id="address"]').first
                if addr_btn.count() > 0:
                    maps_addr_from_ai = clean_text(addr_btn.inner_text())

                # Bóc tách Website
                web_btn = page.locator('a[data-item-id="authority"], a[aria-label*="website"], a[aria-label*="Trang web"]').first
                if web_btn.count() > 0:
                    extracted_website = web_btn.get_attribute('href') or ""

            except Exception as crawl_err:
                print(f"[{mode_tag}] [!] Lỗi cào Google Maps candidate: {crawl_err}")

            # BƯỚC 5: Tự động truy cập vào Link URL Maps để thực hiện Checking độ trùng khớp thực tế
            if target_map_url and "google.com/maps/place" in target_map_url:
                try:
                    page.goto(target_map_url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(1.5)

                    h1_el = page.locator('h1.DUwfe, h1.fontHeadlineLarge').first
                    if h1_el.count() > 0:
                        maps_title_from_ai = clean_text(h1_el.inner_text())

                    phone_btn = page.locator('button[data-tooltip*="phone"], button[data-item-id*="phone"]').first
                    if phone_btn.count() > 0:
                        extracted_phone = clean_text(phone_btn.inner_text())

                    addr_btn = page.locator('button[data-item-id="address"]').first
                    if addr_btn.count() > 0:
                        maps_addr_from_ai = clean_text(addr_btn.inner_text())

                    web_btn = page.locator('a[data-item-id="authority"], a[aria-label*="website"], a[aria-label*="Trang web"]').first
                    if web_btn.count() > 0:
                        extracted_website = web_btn.get_attribute('href') or ""
                except Exception:
                    pass

            # BƯỚC 6: Đánh giá Match Score (Yêu cầu >= 50%)
            check_t = maps_title_from_ai if maps_title_from_ai else title
            check_a = maps_addr_from_ai if maps_addr_from_ai else address
            match_score = evaluate_match_score_with_gemini(client, title, address, check_t, check_a)
            print(f"[{mode_tag}] ➔ Gemini AI Match Score: {match_score}% (Yêu cầu: >= 50%)")

            # BƯỚC 7: Xử lý HAPPY CASE (>= 50%) & WORST CASE (< 50%)
            if match_score >= 50 and target_map_url and "google.com/maps" in target_map_url:
                matched_count += 1
                print(f"[{mode_tag}] ✓ HAPPY CASE (>= 50%): Tìm thấy địa điểm trùng khớp trên Google Maps!")

                # ĐỔI FIELD `url` THÀNH LINK URL MAP KHI HAPPY CASE
                r["url"] = target_map_url
                
                # Bổ sung SĐT nếu có
                if extracted_phone:
                    digits = re.sub(r'\D', '', extracted_phone)
                    r["phone"] = digits if len(digits) >= 9 else extracted_phone

                # Bổ sung Website nếu có
                if extracted_website:
                    r["website"] = extracted_website

                # Bảo lưu link Booking gốc ở field source và totalScore = ""
                r["source"] = original_source
                r["totalScore"] = ""

                safe_save_record(input_file, r)
                print(f"[{mode_tag}] ✓ ĐÃ LƯU HAPPY CASE - Map URL='{r['url'][:45]}...' | Phone='{r['phone']}' | Website='{r.get('website', '')}'")
            else:
                print(f"[{mode_tag}] [-] WORST CASE (< 50% / Không thấy link): Giữ nguyên dữ liệu record gốc STT {stt}.")
                if not r.get("phone"):
                    r["phone"] = ""
                r["url"] = original_booking_url
                r["source"] = original_source
                r["totalScore"] = ""

            pct = ((idx + 1) / total_records * 100)
            print(f"[{mode_tag}] Tiến trình: {idx + 1} / {total_records} bản ghi ({pct:.1f}%)")

        try:
            context.close()
        except Exception: pass
        try:
            if os.path.exists(worker_profile_dir):
                shutil.rmtree(worker_profile_dir, ignore_errors=True)
        except Exception: pass

    print(f"\n[{mode_tag}] HOÀN THÀNH AI CHECKING!")
    print(f"[{mode_tag}] Số bản ghi đạt khớp >= 50% và được cập nhật link Google Maps: {matched_count}/{total_records}")
    print(f"[{mode_tag}] File '{input_file}' đã hoàn tất!")

if __name__ == "__main__":
    out_file = CONFIG.get("output_file", "hotels.json")
    for arg in sys.argv[1:]:
        if arg.endswith(".json"):
            out_file = arg
    run_ai_checking(out_file)
