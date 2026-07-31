import json
import time
import os
import re
import sys

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

def clean_text(text):
    """Loại bỏ các ký tự xuống dòng, khoảng trắng thừa, ký tự ẩn và các icon đặc biệt"""
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

def repair_records():
    target_file = TARGET_JSON_FILE
    if not os.path.exists(target_file):
        print(f"[!] Không tìm thấy file dữ liệu '{target_file}' để sửa đổi.")
        return
        
    print(f"[*] Đang đọc file dữ liệu: {target_file}")
    with open(target_file, 'r', encoding='utf-8') as f:
        records = json.load(f)

    if isinstance(records, list):
        records = [format_standard_record(r, idx + 1) for idx, r in enumerate(records) if isinstance(r, dict)]
        
    # Lọc ra các bản ghi bị N/A ở tiêu đề hoặc địa chỉ
    repair_indices = []
    for idx, r in enumerate(records):
        title = str(r.get("title", "")).strip()
        address = str(r.get("address", "")).strip()
        if title == "N/A" or address == "N/A":
            repair_indices.append((idx, r))
            
    total_need_repair = len(repair_indices)
    print(f"[*] [Info_Repair] Tổng số bản ghi trong file: {len(records)}")
    print(f"[*] [Info_Repair] Phát hiện {total_need_repair} bản ghi bị dính lỗi 'N/A' cần phục hồi.")
    
    if total_need_repair == 0:
        print("[*] [Info_Repair] Không có bản ghi nào bị lỗi N/A. Chương trình kết thúc.")
        return
        
    with sync_playwright() as p:
        if USE_MY_CHROME_PROFILE:
            print(f"[*] [Info_Repair] Đang mở Google Chrome thật tại: {CHROME_PROFILE_PATH}...")
            context = p.chromium.launch_persistent_context(
                CHROME_PROFILE_PATH,
                channel="chrome",
                headless=False
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            print("[*] [Info_Repair] Đang mở trình duyệt ảo mặc định...")
            try:
                browser = p.chromium.launch(headless=False)
            except Exception as launch_err:
                print(f"[!] [Info_Repair] Cảnh báo không thể mở Chromium mặc định ({launch_err}). Chuyển sang dùng Chrome hệ thống...")
                browser = p.chromium.launch(channel="chrome", headless=False)
            context = browser.new_context()
            page = context.new_page()
            
        repaired_count = 0
        
        for index_in_file, r in repair_indices:
            url = r.get("url", "")
            stt = r.get("stt")
            if not url:
                print(f"[-] [Info_Repair] Bỏ qua STT {stt} do không có trường URL.")
                continue
                
            print(f"\n[*] [Info_Repair] Đang phục hồi [{repaired_count + 1}/{total_need_repair}] - STT {stt}: {url}")
            try:
                page.goto(url)
                # Chờ trang tải trong 1.5 giây theo yêu cầu
                time.sleep(1)
                
                # 1. Tên cơ sở (Tiêu đề)
                title_raw = page.locator('h1').first.inner_text() if page.locator('h1').count() > 0 else "N/A"
                title = clean_text(title_raw)
                
                # 2. Địa chỉ
                address_elements = page.locator('button[data-item-id^="address"]').all()
                address_raw = address_elements[0].inner_text() if address_elements else "N/A"
                address = clean_text(address_raw)
                
                # 3. Số điện thoại
                phone_elements = page.locator('button[data-item-id^="phone"]').all()
                phone_raw = phone_elements[0].inner_text() if phone_elements else ""
                phone = re.sub(r'[^0-9+]', '', phone_raw) if phone_raw else ""
                
                # 4. Website
                website_elements = page.locator('a[data-item-id="authority"], a[aria-label*="Website"], a[aria-label*="Trang web"], a[aria-label*="website"], a[aria-label*="trang web"]').all()
                website = website_elements[0].get_attribute('href') if website_elements else ""
                
                # 5. Rating
                rating_text = (
                    page.locator('div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="sao"]')
                    .first.get_attribute('aria-label')
                    if page.locator('div[role="img"][aria-label*="stars"], div[role="img"][aria-label*="sao"]').count() > 0
                    else ""
                )
                rating = ""
                rating_match = re.search(r'(\d+[\.,]\d+|\d+)', rating_text)
                if rating_match:
                    rating_val = rating_match.group(1).replace(',', '.')
                    rating = f"{float(rating_val):.1f}"
                    
                # Cập nhật thông tin vào record
                r["title"] = title
                r["address"] = address
                if phone:
                    r["phone"] = phone
                if website:
                    if "facebook.com" in website.lower():
                        r["facebook"] = website
                        r["website"] = ""
                    else:
                        r["website"] = website
                if rating:
                    r["totalScore"] = rating
                    
                repaired_count += 1
                print(f"✓ [Info_Repair] Real-Time Save (Đã sửa {repaired_count}/{total_need_repair} bản ghi N/A): STT {stt}: Tên: '{title}' | SĐT: '{phone}' | ĐC: '{address}'")
                
                # Ghi đè cập nhật lại file JSON lập tức theo chuẩn 12 trường
                formatted_records = [format_standard_record(rec, idx + 1) for idx, rec in enumerate(records)]
                with open(target_file, 'w', encoding='utf-8') as f:
                    json.dump(formatted_records, f, ensure_ascii=False, indent=2)
                    
            except Exception as crawl_err:
                print(f"[!] [Info_Repair] Lỗi khi cào lại thông tin cho STT {stt}: {crawl_err}")
                
        # Đóng trình duyệt
        if USE_MY_CHROME_PROFILE:
            context.close()
        else:
            browser.close()
            
    print(f"\n[+] PHỤC HỒI HOÀN TẤT! Đã sửa xong {repaired_count}/{total_need_repair} bản ghi bị lỗi.")

if __name__ == "__main__":
    repair_records()
