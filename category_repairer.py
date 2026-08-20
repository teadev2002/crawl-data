import json
import time
import os
import re
import sys
from playwright.sync_api import sync_playwright

# Cấu hình hiển thị đúng tiếng Việt UTF-8 trên Terminal Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Đọc cấu hình từ config.json
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
USE_MY_CHROME_PROFILE = CONFIG.get("USE_MY_CHROME_PROFILE", False)
CHROME_PROFILE_PATH = CONFIG.get("CHROME_PROFILE_PATH", "")
TARGET_JSON_FILE = CONFIG.get("output_file", "hotels.json")

def clean_text(text):
    """Loại bỏ các ký tự xuống dòng, khoảng trắng thừa, ký tự ẩn và các icon đặc biệt"""
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

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

def safe_read_json(file_path, retries=15, delay=0.15):
    """
    Đọc file JSON an toàn với cơ chế thử lại. 
    Tự động phục hồi sửa lỗi nếu file bị dính 'JSONDecodeError: Extra data' do phiên chạy cũ bị ngắt đột ngột.
    """
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
                                # Phục hồi tự động cắt bỏ phần dư thừa phía sau mảng JSON đầu tiên
                                valid_json = content[:jde.pos].strip()
                                data = json.loads(valid_json)
                                # Lưu lại file sạch ngay lập tức
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
    """
    Ghi file JSON an toàn nguyên tử (Atomic Write) thông qua tệp tạm (.tmp) và os.replace
    để chống rách file/Extra data khi 2 luồng cùng làm việc.
    """
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

def safe_save_category(target_file, target_stt, target_url, category_name):
    """
    Lưu Real-Time 1 categoryName mới vào target_file một cách an toàn bằng Nguyên tử (Atomic Write).
    """
    records = safe_read_json(target_file)
    if not records or not isinstance(records, list):
        return False
        
    updated = False
    for r in records:
        if isinstance(r, dict):
            match_stt = str(r.get("stt", "")) == str(target_stt)
            match_url = target_url and r.get("url", "") == target_url
            if match_stt or match_url:
                r["categoryName"] = category_name
                updated = True
                break
            
    if updated:
        formatted_records = [format_standard_record(r, idx + 1) for idx, r in enumerate(records)]
        return safe_write_json(target_file, formatted_records)
    return False

def extract_booking_url(source_str):
    if not source_str:
        return ""
    m = re.search(r'https?://[^\s]+\.booking\.com/[^\s]+', str(source_str))
    if m:
        return m.group(0)
    if "booking.com" in str(source_str).lower():
        cleaned = re.sub(r'^Booking:\s*', '', str(source_str), flags=re.IGNORECASE).strip()
        if cleaned.startswith("http"):
            return cleaned
    return ""

def repair_categories(mode="top", source_type="google_maps"):
    global USE_MY_CHROME_PROFILE
    if mode == "bottom" or source_type == "booking":
        USE_MY_CHROME_PROFILE = False

    target_file = TARGET_JSON_FILE
    if not os.path.exists(target_file):
        print(f"[!] Không tìm thấy file dữ liệu '{target_file}' được cấu hình trong config.json.")
        print("[*] Vui lòng kiểm tra lại tên file trong config.json.")
        return
        
    print(f"[*] [{mode.upper()}] Đang đọc file dữ liệu: {target_file} (Nguồn: {source_type.upper()})")
    records = safe_read_json(target_file)

    if records is None or not isinstance(records, list):
        print(f"[!] Lỗi: Không thể đọc dữ liệu danh sách từ file '{target_file}'.")
        return

    # Tự động đồng bộ cấu trúc: Đảm bảo trường categoryName xuất hiện ngay sau trường title
    updated_structure = False
    new_records = []
    for r in records:
        if isinstance(r, dict):
            if "categoryName" not in r:
                updated_r = {}
                for k, v in r.items():
                    updated_r[k] = v
                    if k == "title":
                        updated_r["categoryName"] = ""
                if "categoryName" not in updated_r:
                    updated_r["categoryName"] = ""
                r = updated_r
                updated_structure = True
        new_records.append(r)
    records = new_records

    if updated_structure:
        try:
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print("[*] Đã tự động đồng bộ chèn trường 'categoryName' vào tất cả các bản ghi.")
        except Exception as e:
            print(f"[!] Lỗi khi đồng bộ file ban đầu: {e}")

    # Lọc ra các bản ghi cần phục hồi categoryName
    repair_indices = []
    for idx, r in enumerate(records):
        if isinstance(r, dict):
            cat = str(r.get("categoryName", "")).strip()
            # Ở chế độ booking hoặc khi cat rỗng/N/A hoặc dính 5-star hotel nghi ngờ
            if source_type == "booking" or not cat or cat in ["N/A", "5-star hotel"]:
                repair_indices.append((idx, r))

    total_need_repair = len(repair_indices)
    midpoint = total_need_repair // 2 if total_need_repair > 1 else 1

    if mode == "bottom":
        target_repair = list(reversed(repair_indices[midpoint:])) if total_need_repair > 1 else repair_indices
        print(f"[*] Chế độ quét: LUỒNG BOTTOM (QUÉT TỪ DƯỚI LÊN). Quét {len(target_repair)} bản ghi thuộc nửa sau (Từ mốc {midpoint + 1} -> {total_need_repair})...")
        repair_indices = target_repair
    else:
        target_repair = repair_indices[:midpoint] if total_need_repair > 1 else repair_indices
        print(f"[*] Chế độ quét: LUỒNG TOP (QUÉT TỪ TRÊN XUỐNG). Quét {len(target_repair)} bản ghi thuộc nửa đầu (Từ mốc 1 -> {len(target_repair)})...")
        repair_indices = target_repair

    total_need_repair = len(repair_indices)
    total_file_records = len(records)
    cat_count_initial = sum(1 for r in records if isinstance(r, dict) and str(r.get("categoryName", "")).strip() not in ["", "N/A"])
    pct_initial = (cat_count_initial / total_file_records * 100) if total_file_records > 0 else 0

    print(f"[CAT_{mode.upper()}] Tổng số bản ghi trong file: {total_file_records}")
    print(f"[*] [{mode.upper()}] Phát hiện {total_need_repair} bản ghi cần phục hồi 'categoryName'.")
    print(f"[CAT_{mode.upper()}] Tiến trình: {cat_count_initial} / {total_file_records} bản ghi ({pct_initial:.1f}%)")

    if total_need_repair == 0:
        print("[CAT_REPAIR] HẠNG MỤC CÁC BẢN GHI ĐÃ ĐẦY ĐỦ! Tất cả bản ghi đều đã có 'categoryName'.")
        return

    with sync_playwright() as p:
        if USE_MY_CHROME_PROFILE and source_type != "booking":
            print(f"[*] [{mode.upper()}] Đang mở Google Chrome thật tại: {CHROME_PROFILE_PATH}...")
            context = p.chromium.launch_persistent_context(
                CHROME_PROFILE_PATH,
                channel="chrome",
                headless=False
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            print(f"[*] [{mode.upper()}] Đang mở trình duyệt ảo mặc định ({source_type.upper()})...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()

        repaired_count = 0

        for idx_attempt, (index_in_file, r) in enumerate(repair_indices):
            stt = r.get("stt", index_in_file + 1)
            title = r.get("title", "Khởi tạo")
            
            if source_type == "booking":
                target_url = extract_booking_url(r.get("source", "")) or extract_booking_url(r.get("url", ""))
                if not target_url:
                    print(f"[-] [{mode.upper()}] Bỏ qua STT {stt} do không tìm thấy link Booking.com trong trường source/url.")
                    continue
            else:
                target_url = r.get("url", "")
                if not target_url:
                    print(f"[-] [{mode.upper()}] Bỏ qua STT {stt} do không có trường URL.")
                    continue

            print(f"\n[*] [{mode.upper()}] [CategoryName {source_type.upper()}] Đang phục hồi [{repaired_count + 1}/{total_need_repair}] - STT {stt}: {title}")
            try:
                page.goto(target_url, wait_until='domcontentloaded', timeout=60000)
                time.sleep(1.5)

                cat_text = ""
                if source_type == "booking":
                    # BÓC TÁCH SỐ SAO / RATING STARS TỪ TRANG BOOKING.COM
                    try:
                        star_loc = page.locator('[data-testid="rating-stars"], [data-testid="quality-rating"], [aria-label*="trên 5 sao"], [aria-label*="out of 5 stars"], [aria-label*="sao"]').first
                        if star_loc.count() > 0:
                            aria_label = star_loc.get_attribute('aria-label') or star_loc.inner_text() or ""
                            star_match = re.search(r'(\d+)\s*(?:trên|out of|\/|\s*sao|\s*stars?)', aria_label, re.IGNORECASE)
                            if star_match:
                                star_num = int(star_match.group(1))
                                if 1 <= star_num <= 5:
                                    cat_text = f"{star_num}-star hotel"
                    except Exception:
                        pass

                    if not cat_text:
                        type_loc = page.locator('[data-testid="property-type"], .hp__hotel-title-badge').first
                        if type_loc.count() > 0:
                            cat_text = clean_text(type_loc.inner_text())

                    if not cat_text:
                        cat_text = "Hotel"
                else:
                    # 1. Bộ chọn chính: Nút category dưới h1
                    cat_elements = page.locator('button[jsaction*="category"], button[data-item-id*="category"]').all()
                    if cat_elements:
                        cat_text = clean_text(cat_elements[0].inner_text())

                    # 2. Bộ chọn dự phòng: Quét văn bản dòng rating cạnh dấu chấm (·)
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

                category_found = cat_text if cat_text else "N/A"
                
                # Lưu đè Real-Time an toàn bằng safe_save_category
                saved = safe_save_category(target_file, stt, r.get("url"), category_found)
                if saved:
                    repaired_count += 1
                    print(f"✓ [{mode.upper()}] Real-Time Save STT {stt}: [{title}] -> categoryName: '{category_found}'")
                else:
                    print(f"[!] [{mode.upper()}] Lỗi lưu STT {stt} ({title}) sau 15 lần thử.")

            except Exception as crawl_err:
                print(f"[!] [{mode.upper()}] Lỗi khi cào categoryName cho STT {stt}: {crawl_err}")

            total_scanned = min(total_file_records, cat_count_initial + (idx_attempt + 1))
            pct_scanned = (total_scanned / total_file_records * 100) if total_file_records > 0 else 0
            print(f"[CAT_{mode.upper()}] Tiến trình: {total_scanned} / {total_file_records} bản ghi đã quét ({pct_scanned:.1f}%)")

        # Đóng trình duyệt
        if USE_MY_CHROME_PROFILE and source_type != "booking":
            context.close()
        else:
            browser.close()

    print(f"\n[+] [{mode.upper()}] PHỤC HỒI HOÀN TẤT! Đã bổ sung xong {repaired_count}/{total_need_repair} bản ghi.")

if __name__ == "__main__":
    mode = "top"
    source_type = "google_maps"
    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=")[1].lower()
        elif arg.startswith("--source_type="):
            source_type = arg.split("=")[1].lower()
        elif arg.lower() in ["top", "bottom"]:
            mode = arg.lower()
        elif arg.lower() in ["booking", "google_maps", "maps"]:
            source_type = "booking" if arg.lower() == "booking" else "google_maps"
            
    repair_categories(mode=mode, source_type=source_type)
