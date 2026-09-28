import json
import time
import os
import re
import sys
import unicodedata
from urllib.parse import unquote

# Cấu hình hiển thị tiếng Việt UTF-8 mượt mà trên console Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from playwright.sync_api import sync_playwright

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

def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', ' ', str(text))
    return re.sub(r'\s+', ' ', cleaned).strip()

def format_standard_record(r, default_stt=1):
    formatted = {}
    for key in STANDARD_KEYS:
        if key == "stt":
            formatted[key] = r.get("stt", default_stt)
        elif key == "isFlag":
            formatted[key] = bool(r.get("isFlag", False))
        elif key == "source":
            formatted[key] = r.get("source", "vntour") or "vntour"
        elif key == "totalScore":
            formatted[key] = ""
        else:
            val = r.get(key, "")
            formatted[key] = val if val is not None else ""
    return formatted

def safe_read_records(file_path):
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            try:
                data = json.loads(content)
            except json.JSONDecodeError as jde:
                if "Extra data" in str(jde):
                    data = json.loads(content[:jde.pos].strip())
                else:
                    return []
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []

def safe_save_record(output_file, new_record):
    """Lưu 1 bản ghi mới vào file JSON nguyên tử bằng file tạm (.tmp)"""
    try:
        records = safe_read_records(output_file)
        if not isinstance(records, list):
            records = []

        formatted = format_standard_record(new_record, len(records) + 1)
        
        # Lọc trùng lặp theo title & phone hoặc address
        title_new = str(formatted.get("title", "")).strip().lower()
        address_new = str(formatted.get("address", "")).strip().lower()
        
        is_duplicate = False
        for r in records:
            if not isinstance(r, dict):
                continue
            r_title = str(r.get("title", "")).strip().lower()
            r_address = str(r.get("address", "")).strip().lower()
            if title_new and r_title == title_new and (not address_new or r_address == address_new):
                is_duplicate = True
                break

        if not is_duplicate:
            records.append(formatted)

            temp_file = f"{output_file}.tmp_vntour_{os.getpid()}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

            replaced = False
            for _ in range(5):
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
        print(f"[!] Lỗi ghi file nguyên tử VNTOUR: {e}")
    return False

def determine_category_name(card_locator, current_rate_id=None):
    """Xác định categoryName dựa trên icon ảnh số sao trong thẻ cơ sở"""
    try:
        img_locator = card_locator.locator('img[src*="star.png"]').first
        if img_locator.count() > 0:
            src = img_locator.get_attribute('src') or ""
            if "5star.png" in src:
                return "5-star hotel"
            elif "4star.png" in src:
                return "4-star hotel"
            elif "3star.png" in src:
                return "3-star hotel"
            elif "2star.png" in src:
                return "2-star hotel"
            elif "1star.png" in src:
                return "1-star hotel"
    except Exception:
        pass

    rate_map = {
        "rate0": "5-star hotel",
        "rate1": "4-star hotel",
        "rate2": "3-star hotel",
        "rate3": "2-star hotel",
        "rate4": "1-star hotel",
    }
    if current_rate_id in rate_map:
        return rate_map[current_rate_id]

    return "hotel"

def run_vntour_harvester(province_code="48,49", output_file=None):
    if not output_file:
        output_file = TARGET_JSON_FILE

    mode_tag = "VNTOUR_HARVESTER"
    print(f"[{mode_tag}] Khởi chạy Cào VNTour (csdl.vietnamtourism.gov.vn)... Mã tỉnh chọn: '{province_code}' | File lưu: '{output_file}'")

    if not os.path.exists(output_file):
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[{mode_tag}] Đã tự động tạo file kết quả mới: '{output_file}'")
        except Exception as e:
            print(f"[{mode_tag}] [!] Lỗi tạo file: {e}")

    max_results = CONFIG.get("max_results", 2000)

    with sync_playwright() as p:
        print(f"[{mode_tag}] Đang mở trình duyệt ảo Playwright Chromium...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="vi-VN",
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.pages[0] if context.pages else context.new_page()

        target_vntour_url = "https://csdl.vietnamtourism.gov.vn/cslt/?csrf_name=ab8c87e2cbe855ba8b7cd4fbe70ef549&rate%5B%5D=1"
        print(f"[{mode_tag}] Điều hướng đến trang web: {target_vntour_url}")
        
        RATES_TO_SCRAPE = [
            {"id": "rate0", "label": "5 sao"},
            {"id": "rate1", "label": "4 sao"},
            {"id": "rate2", "label": "3 sao"},
            {"id": "rate3", "label": "2 sao"},
            {"id": "rate4", "label": "1 sao"},
            {"id": "rate5", "label": "Đạt chuẩn phục vụ KDL"},
            {"id": "rate6", "label": "Khác"},
        ]

        scraped_total = 0
        try:
            page.goto(target_vntour_url, wait_until='domcontentloaded', timeout=45000)
            time.sleep(2.5)

            for rate_idx, rate_info in enumerate(RATES_TO_SCRAPE, 1):
                rate_id = rate_info["id"]
                rate_label = rate_info["label"]
                print(f"\n[{mode_tag}] [{rate_idx}/{len(RATES_TO_SCRAPE)}] === TIẾN HÀNH CÀO BỘ LỌC: '{rate_label}' ({rate_id}) ===")

                # 1. Chọn tỉnh thành trong select#province
                prov_select = page.locator('select#province, select[name="province"]').first
                if prov_select.count() > 0:
                    print(f"[{mode_tag}] Đang chọn tỉnh/thành phố với giá trị: '{province_code}'...")
                    prov_select.select_option(value=province_code)
                    time.sleep(1.0)
                else:
                    print(f"[{mode_tag}] [!] Cảnh báo: Không tìm thấy ô chọn select#province!")

                # 2. Chọn bộ lọc rateX (input#rateX / label[for="rateX"])
                rate_el = page.locator(f'label[for="{rate_id}"]').first
                if rate_el.count() == 0:
                    rate_el = page.locator(f'input#{rate_id}').first
                if rate_el.count() > 0:
                    print(f"[{mode_tag}] Đang chọn bộ lọc '{rate_label}'...")
                    try:
                        rate_el.click(force=True)
                    except Exception:
                        page.evaluate(f"() => {{ const el = document.querySelector('label[for=\"{rate_id}\"]') || document.querySelector('input#{rate_id}'); if (el) el.click(); }}")
                    time.sleep(0.5)
                else:
                    print(f"[{mode_tag}] [!] Cảnh báo: Không tìm thấy phần tử bộ lọc '{rate_id}', chuyển bộ lọc tiếp theo...")
                    continue

                # 3. Click nút Tra cứu (button#searchbutton)
                search_btn = page.locator('button#searchbutton, button[data-button-value="cslt"]').first
                if search_btn.count() > 0:
                    print(f"[{mode_tag}] Đang bấm nút Tra cứu cho bộ lọc '{rate_label}'...")
                    try:
                        search_btn.click(force=True)
                    except Exception:
                        page.evaluate("() => { const el = document.querySelector('button#searchbutton, button[data-button-value=\"cslt\"]'); if (el) el.click(); }")
                    time.sleep(3.5)
                else:
                    print(f"[{mode_tag}] [!] Cảnh báo: Không tìm thấy nút Tra cứu button#searchbutton!")

                # Đọc tổng số kết quả hiển thị trên header nếu có
                total_count_header = page.locator('h5.shorting-title').first
                if total_count_header.count() > 0:
                    header_text = clean_text(total_count_header.inner_text())
                    print(f"[{mode_tag}] Thông báo hệ thống ({rate_label}): {header_text}")
                
                page_num = 1

                while True:
                    # Đợi các thẻ kết quả hiển thị
                    page.wait_for_selector('.verticle-listing-caption, .shorting-title', timeout=15000)
                    cards = page.locator('.verticle-listing-caption').all()
                    print(f"[{mode_tag}] --- [{rate_label}] TRANG {page_num}: Phát hiện {len(cards)} cơ sở trên trang này ---")

                    if not cards:
                        print(f"[{mode_tag}] Không tìm thấy cơ sở nào cho '{rate_label}' trên trang {page_num}.")
                        break

                    for idx, card in enumerate(cards, 1):
                        try:
                            # 1. Title
                            h4_a = card.locator('h4 a').first
                            title = clean_text(h4_a.inner_text()) if h4_a.count() > 0 else ""
                            if not title:
                                continue

                            # 2. CategoryName
                            category_name = determine_category_name(card, current_rate_id=rate_id)

                            # 3. Address
                            address = ""
                            addr_el = card.locator('i.fa-map-marker').first
                            if addr_el.count() > 0:
                                parent_txt = clean_text(card.locator('xpath=./*[contains(., "Địa chỉ") or .//i[contains(@class, "fa-map-marker")]]').first.inner_text()) if card.locator('xpath=./*[contains(., "Địa chỉ") or .//i[contains(@class, "fa-map-marker")]]').count() > 0 else ""
                                if not parent_txt:
                                    parent_txt = clean_text(card.inner_text())
                                addr_match = re.search(r'Địa chỉ:\s*(.*?)(?:Điện thoại|Email|Website|\n|$)', parent_txt, re.IGNORECASE | re.DOTALL)
                                if addr_match:
                                    address = clean_text(addr_match.group(1))
                                else:
                                    address = re.sub(r'.*?Địa chỉ:\s*', '', parent_txt, flags=re.IGNORECASE).strip()

                            # 4. Phone
                            phone = ""
                            phone_el = card.locator('i.fa-phone').first
                            if phone_el.count() > 0:
                                card_txt = clean_text(card.inner_text())
                                phone_match = re.search(r'Điện thoại(?:\s*cố định|\s*di động)?:\s*([0-9\s\.\-\+]{6,25})', card_txt, re.IGNORECASE)
                                if phone_match:
                                    phone = clean_text(phone_match.group(1))

                            # 5. Email
                            email = ""
                            email_el = card.locator('i.fa-envelope-o, i.fa-envelope').first
                            if email_el.count() > 0:
                                card_txt = clean_text(card.inner_text())
                                email_match = re.search(r'Email:\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', card_txt, re.IGNORECASE)
                                if email_match:
                                    email = clean_text(email_match.group(1))

                            # 6. Website
                            website = ""
                            web_el = card.locator('i.fa-globe').first
                            if web_el.count() > 0:
                                web_link = card.locator('a[href*="http"]').first
                                if web_link.count() > 0:
                                    website = web_link.get_attribute('href') or clean_text(web_link.inner_text())
                                if not website:
                                    card_txt = clean_text(card.inner_text())
                                    web_match = re.search(r'Website:\s*(https?://[^\s\n]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}[^\s\n]*)', card_txt, re.IGNORECASE)
                                    if web_match:
                                        website = clean_text(web_match.group(1))

                            record = {
                                "stt": scraped_total + 1,
                                "title": title,
                                "email": email,
                                "phone": phone,
                                "address": address,
                                "url": "",
                                "totalScore": "",
                                "website": website,
                                "facebook": "",
                                "categoryName": category_name,
                                "source": "vntour",
                                "isFlag": False
                            }

                            saved = safe_save_record(output_file, record)
                            if saved:
                                scraped_total += 1
                                print(f"[{mode_tag}] ✓ Real-Time Save #{scraped_total} [{rate_label} - Trang {page_num} - STT {idx}]: '{title}' | Category: '{category_name}' | Addr: '{address[:35]}...' | Phone: '{phone}'")

                        except Exception as item_err:
                            print(f"[{mode_tag}] [!] Lỗi bóc tách cơ sở thứ {idx} trang {page_num} ({rate_label}): {item_err}")

                    # Kiểm tra phân trang (Pagination)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1.5)

                    pagination_ul = page.locator('ul.pagination').first
                    if pagination_ul.count() == 0:
                        print(f"[{mode_tag}] Không tìm thấy thanh phân trang ul.pagination cho '{rate_label}'. Hoàn thành bộ lọc này!")
                        break

                    # Tìm nút trang tiếp theo (trang page_num + 1 hoặc nút '>')
                    next_page_num = page_num + 1
                    next_page_str = str(next_page_num)

                    next_link = pagination_ul.locator(f'a[data-ci-pagination-page="{next_page_str}"], a[rel="next"], a.page-link:has-text(">"), a:has-text(">"), a:has-text("»")').first
                    if next_link.count() == 0:
                        next_link = pagination_ul.locator('a').filter(has_text=re.compile(rf'^\s*{next_page_str}\s*$')).first

                    if next_link.count() > 0:
                        print(f"[{mode_tag}] ➔ [{rate_label}] Bấm chuyển sang trang tiếp theo ({next_page_num})...")
                        try:
                            next_link.click(force=True)
                        except Exception:
                            page.evaluate("(el) => el.click()", next_link.element_handle())
                        page_num = next_page_num
                        time.sleep(3.5)
                    else:
                        print(f"[{mode_tag}] [✓] Đã cào xong toàn bộ {page_num} trang kết quả cho bộ lọc '{rate_label}'!")
                        break

        except Exception as crawl_err:
            print(f"[{mode_tag}] [!] Lỗi trong quá trình cào VNTour: {crawl_err}")
        finally:
            try:
                browser.close()
            except Exception:
                pass

    print(f"\n[{mode_tag}] HOÀN THÀNH CÀO VNTOUR!")
    print(f"[{mode_tag}] Tổng cộng đã lưu: {scraped_total} cơ sở vào file '{output_file}'.")

if __name__ == "__main__":
    out_file = CONFIG.get("output_file", "hotels.json")
    prov_code = "48,49"
    for arg in sys.argv[1:]:
        if arg.startswith("--province="):
            prov_code = arg.split("=")[1]
        elif arg.endswith(".json"):
            out_file = arg
    run_vntour_harvester(province_code=prov_code, output_file=out_file)
