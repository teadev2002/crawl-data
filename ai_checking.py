import json
import time
import os
import re
import sys
import shutil
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

# Import google.genai SDK
try:
    from google import genai
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
        CONFIG.get("openai_api_key") or
        os.environ.get("GEMINI_API_KEY") or
        os.environ.get("GOOGLE_API_KEY") or
        ""
    ).strip()

    if not HAS_GENAI:
        print("[!] Thư viện 'google-genai' chưa sẵn sàng.")
        return None, api_key

    if not api_key:
        print("[!] Chưa cấu hình Gemini API Key trong config.json (trường 'gemini_api_key').")
        return None, ""

    try:
        client = genai.Client(api_key=api_key)
        return client, api_key
    except Exception as e:
        print(f"[!] Lỗi khi khởi tạo Gemini Client: {e}")
        return None, api_key

def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

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

def safe_save_record(output_file, updated_item):
    if not os.path.exists(output_file):
        return False
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            records = json.load(f)

        target_url = updated_item.get("url")
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
                    if k in updated_item and updated_item[k] != "":
                        r[k] = updated_item[k]
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

def generate_maps_search_query_with_gemini(client, title, address):
    """BƯỚC 2: Gọi Gemini API tạo câu lệnh tìm kiếm Google Maps tối ưu"""
    if not client:
        return f"{title} {address} map"

    prompt = (
        f"Hãy tạo 1 câu lệnh tìm kiếm Google Maps ngắn gọn, tối ưu nhất dựa trên:\n"
        f"Tên cơ sở: {title}\n"
        f"Địa chỉ: {address}\n"
        f"Yêu cầu: Kết hợp tên cơ sở + địa chỉ ngắn + từ khóa 'map'. Chỉ trả về câu lệnh thuần văn bản, không markdown."
    )

    try:
        interaction = client.interactions.create(
            model="gemini-3.5-flash",
            input=prompt
        )
        res_text = clean_text(interaction.output_text)
        return res_text if res_text else f"{title} {address} map"
    except Exception:
        try:
            interaction = client.interactions.create(
                model="gemini-2.5-flash",
                input=prompt
            )
            res_text = clean_text(interaction.output_text)
            return res_text if res_text else f"{title} {address} map"
        except Exception:
            return f"{title} {address} map"

def evaluate_match_score_with_gemini(client, booking_title, booking_address, maps_title, maps_address):
    """BƯỚC 4: Gọi Gemini API đánh giá % trùng khớp giữa Booking và Google Maps"""
    if not client:
        # Fallback từ vựng cơ bản nếu không có API Key
        import unicodedata
        def strip(s):
            nfkd = unicodedata.normalize('NFD', s)
            return "".join([c for c in nfkd if unicodedata.category(c) != 'Mn']).lower().strip()
        t1, t2 = set(re.findall(r'\w+', strip(booking_title))), set(re.findall(r'\w+', strip(maps_title)))
        if not t1 or not t2: return 0
        ratio = len(t1.intersection(t2)) / max(len(t1), 1) * 100
        return int(ratio)

    prompt = (
        f"So sánh độ tương đồng (0 đến 100%) giữa 2 địa điểm dưới đây:\n\n"
        f"ĐỊA ĐIỂM A (Booking.com):\n"
        f"- Tên: {booking_title}\n"
        f"- Địa chỉ: {booking_address}\n\n"
        f"ĐỊA ĐIỂM B (Google Maps):\n"
        f"- Tên: {maps_title}\n"
        f"- Địa chỉ: {maps_address}\n\n"
        f"Yêu cầu: Trả về duy nhất 1 con số nguyên đại diện cho phần trăm trùng khớp (ví dụ: 85). Không kèm chữ khác."
    )

    try:
        interaction = client.interactions.create(
            model="gemini-3.5-flash",
            input=prompt
        )
        match = re.search(r'(\d+)', interaction.output_text)
        if match:
            return int(match.group(1))
    except Exception:
        try:
            interaction = client.interactions.create(
                model="gemini-2.5-flash",
                input=prompt
            )
            match = re.search(r'(\d+)', interaction.output_text)
            if match:
                return int(match.group(1))
        except Exception:
            pass
    return 50

def run_ai_checking(input_file=None):
    if not input_file:
        input_file = TARGET_JSON_FILE

    mode_tag = "AI_CHECKING"
    print(f"[{mode_tag}] Đã khởi chạy Chức Năng 'AI Checking' (Google Gemini API)...")

    if not os.path.exists(input_file):
        print(f"[{mode_tag}] Lỗi: Không tìm thấy file dữ liệu '{input_file}'!")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        records = json.load(f)

    total_records = len(records)
    print(f"[{mode_tag}] Đã đọc file '{input_file}' ({total_records} bản ghi).")

    client, api_key = get_gemini_client()
    if client:
        print(f"[{mode_tag}] ✓ Đã kết nối thành công Google Gemini Client (`gemini-3.5-flash`).")
    else:
        print(f"[{mode_tag}] [!] Không có Gemini API Key, chạy ở chế độ fallback từ vựng.")

    worker_profile_dir = os.path.join(os.getcwd(), "browser_profile_aicheck")

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
            booking_url = r.get("url", "")

            if not title:
                print(f"[{mode_tag}] [{idx+1}/{total_records}] Bỏ qua STT {stt} do không có Tên cơ sở.")
                continue

            print(f"\n[{mode_tag}] [{idx+1}/{total_records}] Đang kiểm tra STT {stt}: '{title}' | '{address}'")

            # BƯỚC 2: Gemini API tạo câu lệnh tìm kiếm Google Maps tối ưu
            search_query = generate_maps_search_query_with_gemini(client, title, address)
            print(f"[{mode_tag}] ➔ Query Google Maps từ Gemini: '{search_query}'")

            # BƯỚC 3: Truy vấn Google Maps cào dữ liệu Candidate
            maps_url = f"https://www.google.com/maps/search/{quote_plus(search_query)}"
            candidate = {
                "google_maps_url": "",
                "title": "",
                "address": "",
                "phone": "",
                "totalScore": "",
                "website": "",
                "facebook": ""
            }

            try:
                page.goto(maps_url, wait_until='domcontentloaded', timeout=35000)
                time.sleep(2.0)

                # Nếu rơi vào danh sách địa điểm, click địa điểm đầu tiên
                feed_locator = page.locator('div[role="feed"]')
                if feed_locator.count() > 0:
                    first_card = page.locator('a[href*="/maps/place/"]').first
                    if first_card.count() > 0:
                        first_card.click()
                        time.sleep(2.0)

                candidate["google_maps_url"] = page.url

                # Bóc tách Tên trên Google Maps
                h1_el = page.locator('h1.DUwfe, h1.fontHeadlineLarge').first
                if h1_el.count() > 0:
                    candidate["title"] = clean_text(h1_el.inner_text())

                # Bóc tách SĐT
                phone_btn = page.locator('button[data-tooltip*="phone"], button[data-item-id*="phone"]').first
                if phone_btn.count() > 0:
                    candidate["phone"] = clean_text(phone_btn.inner_text())

                # Bóc tách Địa chỉ
                addr_btn = page.locator('button[data-item-id="address"]').first
                if addr_btn.count() > 0:
                    candidate["address"] = clean_text(addr_btn.inner_text())

                # Bóc tách Rating
                score_el = page.locator('div.F7v250, span.ceNzKf').first
                if score_el.count() > 0:
                    candidate["totalScore"] = clean_text(score_el.inner_text())

                # Bóc tách Website
                web_btn = page.locator('a[data-item-id="authority"]').first
                if web_btn.count() > 0:
                    candidate["website"] = web_btn.get_attribute('href') or ""

            except Exception as crawl_err:
                print(f"[{mode_tag}] Lỗi cào Google Maps candidate: {crawl_err}")

            # BƯỚC 4: Gemini API chấm điểm tương đồng (% Match Score)
            maps_title_check = candidate["title"] if candidate["title"] else title
            maps_addr_check = candidate["address"] if candidate["address"] else address
            match_score = evaluate_match_score_with_gemini(client, title, address, maps_title_check, maps_addr_check)
            print(f"[{mode_tag}] ➔ Gemini AI Match Score: {match_score}% (Ngưỡng yêu cầu: >=70%)")

            # BƯỚC 5: Đánh giá ngưỡng >= 70% & Ghi đè trường url bằng Link Google Maps
            if match_score >= 70:
                matched_count += 1
                
                # Lưu đè đường link Google Maps vào trường `url` theo đúng yêu cầu
                if candidate["google_maps_url"]:
                    r["url"] = candidate["google_maps_url"]
                
                if candidate["phone"]:
                    r["phone"] = candidate["phone"]
                if candidate["totalScore"]:
                    r["totalScore"] = candidate["totalScore"]
                if candidate["website"]:
                    r["website"] = candidate["website"]
                if candidate["facebook"]:
                    r["facebook"] = candidate["facebook"]

                # Lưu link Booking gốc ở trường source
                old_source = r.get("source", "")
                if booking_url and "booking.com" in booking_url.lower():
                    r["source"] = f"Booking: {booking_url} | Google Maps: {candidate['google_maps_url']}"
                elif not old_source:
                    r["source"] = f"Google Maps: {candidate['google_maps_url']}"

                safe_save_record(input_file, r)
                print(f"[{mode_tag}] ✓ MATCH GE 70% (#{matched_count}): Ghi đè url Google Maps & SĐT '{candidate['phone']}' thành công!")
            else:
                print(f"[{mode_tag}] [-] Không đạt ngưỡng 70% ({match_score}%). Giữ nguyên dữ liệu Booking gốc.")

            pct = ((idx + 1) / total_records * 100)
            print(f"[{mode_tag}] Tiến trình: {idx + 1} / {total_records} bản ghi đã quét ({pct:.1f}%)")

        try:
            context.close()
        except Exception: pass
        try:
            if os.path.exists(worker_profile_dir):
                shutil.rmtree(worker_profile_dir, ignore_errors=True)
        except Exception: pass

    print(f"\n[{mode_tag}] HOÀN THÀNH AI CHECKING!")
    print(f"[{mode_tag}] Số bản ghi đạt khớp >=70% và được ghi đè: {matched_count}/{total_records}")
    print(f"[{mode_tag}] File '{input_file}' đã được làm sạch và bổ sung link Google Maps + SĐT chuẩn xác!")

if __name__ == "__main__":
    out_file = CONFIG.get("output_file", "hotels.json")
    for arg in sys.argv[1:]:
        if arg.endswith(".json"):
            out_file = arg
    run_ai_checking(out_file)
