import json
import time
import os
import re
import sys
import random
import shutil
from urllib.parse import unquote, quote_plus
from playwright.sync_api import sync_playwright

# Cấu hình stdout/stderr sang UTF-8 để hiển thị tiếng Việt mượt mà trên console Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

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

def clean_text(text: str) -> str:
    """Loại bỏ ký tự xuống dòng, khoảng trắng thừa."""
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', ' ', text)
    return re.sub(r'\s+', ' ', cleaned).strip()

def close_popups(page):
    """Tự động tắt các cửa sổ quảng cáo / đăng nhập / cookie popup của Booking.com."""
    try:
        page.evaluate("""
            () => {
                const closeBtns = document.querySelectorAll(
                    'div[role="dialog"] button[aria-label*="Bỏ qua"], ' +
                    'div[role="dialog"] button[aria-label*="Dismiss"], ' +
                    'div[role="dialog"] button[aria-label*="Close"], ' +
                    'div[role="dialog"] button[aria-label*="Đóng"], ' +
                    '#onetrust-accept-btn-handler, ' +
                    'button[data-testid="selection-modal-close-button"]'
                );
                for (const btn of closeBtns) {
                    const ariaLabel = (btn.getAttribute('aria-label') || '').toLowerCase();
                    const testId = (btn.getAttribute('data-testid') || '').toLowerCase();

                    if (btn.closest('[data-testid="property-card"]') || 
                        testId.includes('wishlist') || 
                        btn.classList.contains('fc63351294') ||
                        ariaLabel.includes('yêu thích') ||
                        ariaLabel.includes('wishlist') ||
                        ariaLabel.includes('lưu') ||
                        ariaLabel.includes('save')) {
                        continue;
                    }
                    try { btn.click(); } catch(e) {}
                }
            }
        """)
    except Exception:
        pass

def apply_hotel_type_filter(page, mode_tag="BOOKING_HARVESTER") -> bool:
    """Tích vào ô 'Khách sạn' trong Các bộ lọc phổ biến / Loại chỗ nghỉ."""
    try:
        close_popups(page)
        clicked = page.evaluate("""
            () => {
                const hotelTestId = document.querySelector('[data-testid="filter-item-ht_id:204"] input, [data-testid="filter-item-ht_id:204"]');
                if (hotelTestId) {
                    hotelTestId.click();
                    return true;
                }
                const labels = document.querySelectorAll('label, div[data-testid="filter-card"]');
                for (const l of labels) {
                    const txt = (l.innerText || l.textContent || '').trim().toLowerCase();
                    if (txt.includes('khách sạn') || txt.includes('hotels')) {
                        const input = l.querySelector('input') || l;
                        input.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        if clicked:
            time.sleep(2.5)
            close_popups(page)
            print(f"[{mode_tag}] [+] Đã tích chọn bộ lọc 'Khách sạn' thành công.")
            return True
    except Exception as e:
        print(f"[{mode_tag}] [!] Không click được bộ lọc Khách sạn: {e}")
    return False

def parse_booking_count(text: str) -> int:
    """
    Trích xuất số nguyên chuẩn từ văn bản Booking.com (xử lý các định dạng như 1.621, 3.707, 1,045).
    """
    if not text:
        return 0
    m = re.search(r'([\d.,]+)\s*(?:chỗ nghỉ|kết quả|properties|found)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'\(([\d.,]+)\)', text)
    if not m:
        m = re.search(r'([\d.,]+)', text)
    
    if m:
        num_str = m.group(1).replace('.', '').replace(',', '').strip()
        if num_str.isdigit():
            return int(num_str)
    return 0

def toggle_star_filter(page, star: int, enable: bool = True, mode_tag="BOOKING_HARVESTER") -> int:
    count = 0
    try:
        close_popups(page)
        res = page.evaluate(r"""
            (args) => {
                const starNum = args.star;
                const enable  = args.enable;
                
                const sel = `[data-testid="filter-item-class:${starNum}"], input[name="class=${starNum}"]`;
                let el = document.querySelector(sel);
                
                if (!el) {
                    const labels = document.querySelectorAll('label, div[data-testid="filter-card"]');
                    for (const l of labels) {
                        const txt = (l.innerText || l.textContent || '').trim().toLowerCase();
                        if (txt.includes(`${starNum} sao`) || txt.includes(`${starNum} star`)) {
                            el = l.querySelector('input') || l;
                            break;
                        }
                    }
                }
                
                let foundCount = 0;
                if (el) {
                    const parent = el.closest('label') || el.parentElement;
                    if (parent) {
                        const pTxt = parent.innerText || parent.textContent || '';
                        const m = pTxt.match(/\(([\d.,]+)\)/) || pTxt.match(/([\d.,]+)/);
                        if (m) {
                            const rawNum = m[1].replace(/\./g, '').replace(/,/g, '').trim();
                            if (/^\d+$/.test(rawNum)) foundCount = parseInt(rawNum, 10);
                        }
                    }
                    
                    const isChecked = el.checked || el.getAttribute('aria-checked') === 'true';
                    if (enable && !isChecked) {
                        el.click();
                    } else if (!enable && isChecked) {
                        el.click();
                    }
                }
                return { clicked: !!el, count: foundCount };
            }
        """, {"star": star, "enable": enable})

        if res and res.get("clicked"):
            time.sleep(2.5)
            close_popups(page)

            try:
                header_loc = page.locator('h1, [data-component="search-summary"]').first
                if header_loc.count() > 0:
                    h_text = header_loc.inner_text()
                    count = parse_booking_count(h_text)
            except Exception:
                pass

            if count == 0:
                count = res.get("count", 0)

            state_str = "TÍCH" if enable else "BỎ TÍCH"
            print(f"[{mode_tag}] [+] Đã {state_str} bộ lọc {star} sao. Số lượng Booking báo: {count} chỗ nghỉ.")
    except Exception as e:
        print(f"[{mode_tag}] [!] Lỗi khi đổi bộ lọc {star} sao: {e}")

    return count

def trigger_load_more_click(page):
    """Hàm helper kích hoạt nhấp nút 'Load more results' / 'Tải thêm kết quả' / 'Xem thêm kết quả' chuẩn xác."""
    try:
        return page.evaluate("""
            () => {
                const isLoadMore = (t) => {
                    const txt = (t || '').toLowerCase();
                    return txt.includes('load more') || 
                           txt.includes('tải thêm') || 
                           txt.includes('xem thêm') || 
                           txt.includes('more results');
                };

                const containers = document.querySelectorAll('div.c3bdfd4ac2');
                for (const c of containers) {
                    const btn = c.querySelector('button') || c.querySelector('span.ca2ca5203b');
                    if (btn) {
                        const txt = btn.innerText || btn.textContent || '';
                        if (isLoadMore(txt)) {
                            btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                            btn.click();
                            return true;
                        }
                    }
                }

                const buttons = document.querySelectorAll('button.a0ddd706cc, button.bbf83acb81, button:has(span.ca2ca5203b), button');
                for (const btn of buttons) {
                    const txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                    if (btn.closest('footer') || 
                        btn.closest('header') || 
                        btn.closest('aside') || 
                        btn.closest('[data-testid="filter-card"]') || 
                        btn.closest('.bd8754837d') ||
                        txt.includes('vnd') || 
                        txt.includes('usd') || 
                        txt.includes('eur') || 
                        txt.includes('gbp') ||
                        txt.includes('tìm chỗ nghỉ')) {
                        continue;
                    }
                    if (isLoadMore(txt)) {
                        btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                        btn.click();
                        return true;
                    }
                }
                return false;
            }
        """)
    except Exception:
        return False

def is_card_outside_region(page, card) -> bool:
    """
    Kiểm tra xem thẻ property card hiện tại có nằm sau banner thông báo
    "Chỗ nghỉ xung quanh... nằm ngoài..." (class b8f2b74cef / edd678b754) hay không.
    """
    try:
        is_outside = page.evaluate(r"""
            (cardEl) => {
                const banners = document.querySelectorAll('.b8f2b74cef, .edd678b754, [class*="b8f2b74cef"], [class*="edd678b754"], [data-testid="search-results-banner"]');
                for (const banner of banners) {
                    const text = (banner.innerText || banner.textContent || '').toLowerCase();
                    if (text.includes('xung quanh') || text.includes('nằm ngoài') || text.includes('outside') || text.includes('properties around')) {
                        const pos = banner.compareDocumentPosition(cardEl);
                        if ((pos & Node.DOCUMENT_POSITION_FOLLOWING) !== 0) {
                            return true;
                        }
                    }
                }
                return false;
            }
        """, card.element_handle())
        return bool(is_outside)
    except Exception:
        return False

def format_standard_record(r, default_stt=1):
    formatted = {}
    for key in STANDARD_KEYS:
        if key == "stt":
            formatted[key] = r.get("stt", default_stt)
        elif key == "isFlag":
            formatted[key] = bool(r.get("isFlag", False))
        elif key == "totalScore":
            formatted[key] = ""  # Không lấy field điểm số theo yêu cầu của người dùng
        else:
            val = r.get(key, "")
            formatted[key] = val if val is not None else ""
    return formatted

def safe_save_record(output_file, new_item):
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
            for k in STANDARD_KEYS:
                if k in new_item and new_item[k] != "" and k != "totalScore":
                    r[k] = new_item[k]
            records[idx] = format_standard_record(r, idx + 1)
            updated = True
            break

    if not updated:
        item_fmt = format_standard_record(new_item, len(records) + 1)
        records.append(item_fmt)

    for attempt in range(15):
        try:
            temp_file = f"{output_file}.tmp_booking_{os.getpid()}"
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

            return True, len(records)
        except Exception:
            time.sleep(0.2)
    return False, len(records)

def extract_detail_page(page, url):
    """
    Stage 2 Detail Extractor (Playwright Chromium):
    1. Title: `class="ddb12f4f86 pp-header__title"`
    2. Address: `<div class="b99b6ef58f cb4b7a25d9 b06461926f">` hoặc JSON-LD schema
    3. Apartment Check: CHỈ khi thẻ <span class="bui-button__text"> có nội dung "Đặt căn hộ của bạn"
       mới đánh dấu is_apartment = True. Nếu là "Đặt ngay" -> Giữ nguyên tiêu đề gốc.
    """
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
        time.sleep(2.5)
        close_popups(page)

        return page.evaluate("""
            () => {
                let res = { title: '', address: '', is_apartment: false };

                // 1. Tên cơ sở (title) từ class="ddb12f4f86 pp-header__title"
                const titleEl = document.querySelector('.ddb12f4f86, .pp-header__title, h2.pp-header__title, [data-testid="header-title"]');
                if (titleEl) {
                    res.title = titleEl.innerText.replace(/[\\n\\r\\t]+/g, ' ').trim();
                }

                // 2. Địa chỉ (address) từ JSON-LD schema
                const jsonLdScripts = document.querySelectorAll('script[type="application/ld+json"]');
                for (const script of jsonLdScripts) {
                    try {
                        const data = JSON.parse(script.innerText || script.textContent || '{}');
                        const items = Array.isArray(data) ? data : [data];
                        for (const item of items) {
                            if (item && item.address) {
                                if (typeof item.address === 'object' && item.address.streetAddress) {
                                    res.address = item.address.streetAddress.trim();
                                } else if (typeof item.address === 'string' && item.address.trim().length > 5) {
                                    res.address = item.address.trim();
                                }
                            }
                            if (!res.title && item && item.name) {
                                res.title = item.name.trim();
                            }
                        }
                        if (res.address) break;
                    } catch(e) {}
                }

                if (!res.address) {
                    const addrEls = document.querySelectorAll('div.b99b6ef58f.cb4b7a25d9, div.b99b6ef58f, span.hp_address_subtitle, [data-node_tt_id="location_score_tooltip"], [data-component="hotel-address"], button[data-testid="item-map-trigger"], .show_on_map_hp_link');
                    for (const el of addrEls) {
                        const clone = el.cloneNode(true);
                        const hiddenEls = clone.querySelectorAll('[aria-hidden="true"], .dcf8588897, script, style');
                        hiddenEls.forEach(h => h.remove());
                        const txt = (clone.innerText || clone.textContent || '').replace(/[\\n\\r\\t]+/g, ' ').replace(/\\s+/g, ' ').trim();
                        if (txt.length > 5 && !txt.toLowerCase().includes('hiển thị bản đồ')) {
                            res.address = txt;
                            break;
                        }
                    }
                }

                // 3. ĐỊNH VỊ CHÍNH XÁC THẺ: rating-squares (Đánh dấu căn hộ (#can-ho))
                // Nếu gặp rating-stars -> is_apartment = false (Xử lý bình thường)
                const hasRatingSquares = document.querySelector('[data-testid="rating-squares"], [data-testid*="rating-squares"]');
                if (hasRatingSquares) {
                    res.is_apartment = true;
                } else {
                    res.is_apartment = false;
                }

                return res;
            }
        """)
    except Exception:
        return {}

def run_booking_harvester(input_destination=None, output_file=None):
    if not output_file:
        output_file = TARGET_JSON_FILE

    if not input_destination:
        input_destination = CONFIG.get("target_province", "Ho Chi Minh City")
        if input_destination == "all":
            input_destination = "Ho Chi Minh City"

    mode_tag = "BOOKING_HARVESTER"
    print(f"[{mode_tag}] Đã khởi chạy Công Cụ Cào Dữ Liệu Booking.com Trực Tiếp (Stage 1 & Stage 2 Playwright)...")
    print(f"[{mode_tag}] Điểm đến mục tiêu: '{input_destination}' | File lưu: '{output_file}'")

    worker_profile_dir = os.path.join(os.getcwd(), f"browser_profile_booking_{os.getpid()}")
    if os.path.exists(worker_profile_dir):
        try:
            shutil.rmtree(worker_profile_dir, ignore_errors=True)
        except Exception:
            pass

    existing_records = []
    existing_urls = set()
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    raw = json.loads(content)
                    if isinstance(raw, list):
                        existing_records = raw
                        for r in raw:
                            if isinstance(r, dict) and r.get("url"):
                                existing_urls.add(r["url"].split('?')[0])
            print(f"[{mode_tag}] Đã tìm thấy {len(existing_records)} bản ghi cũ trong '{output_file}'.")
        except Exception as e:
            print(f"[{mode_tag}] [!] Lỗi đọc file cũ: {e}")

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
            target_url_cfg = CONFIG.get("target_url", "")
            if target_url_cfg and "booking.com" in target_url_cfg:
                search_url = target_url_cfg
            else:
                search_url = f"https://www.booking.com/searchresults.vi.html?ss={quote_plus(input_destination)}"

            print(f"[{mode_tag}] -> [STAGE 1] Đang truy cập Booking.com: {search_url}")
            page.goto(search_url, timeout=35000, wait_until="domcontentloaded")
            time.sleep(3.5)
            close_popups(page)

            grand_total_target = 0
            try:
                header_loc = page.locator('h1, [data-component="search-summary"]').first
                if header_loc.count() > 0:
                    h_text = header_loc.inner_text()
                    grand_total_target = parse_booking_count(h_text)
                    print(f"[{mode_tag}] [📍 TỔNG CHỖ NGHỈ MỤC TIÊU TỪ <h1>]: {grand_total_target} chỗ nghỉ tại '{input_destination}'")
            except Exception:
                pass

            print(f"[{mode_tag}] -> Đang áp dụng bộ lọc 'Khách sạn'...")
            apply_hotel_type_filter(page, mode_tag=mode_tag)

            star_tiers = [5, 4, 3, 2, 1]

            for star in star_tiers:
                print(f"\n==================================================")
                print(f"[{mode_tag}] [*] STAGE 1: ĐANG XỬ LÝ HẠNG {star} SAO...")
                print(f"==================================================")

                expected_count = toggle_star_filter(page, star=star, enable=True, mode_tag=mode_tag)

                if expected_count == 0:
                    print(f"[{mode_tag}] [-] Hạng {star} sao không có kết quả nào. Chuyển sang hạng sao tiếp theo...")
                    toggle_star_filter(page, star=star, enable=False, mode_tag=mode_tag)
                    continue

                print(f"[{mode_tag}] [*] Mục tiêu cào hạng {star} sao: {expected_count} chỗ nghỉ.")

                star_results_count = 0
                last_milestone = 0
                last_new_record_time = time.time()
                hit_outside_banner = False

                while star_results_count < expected_count:
                    close_popups(page)

                    cards = page.locator('[data-testid="property-card"]').all()

                    for card in cards:
                        if star_results_count >= expected_count:
                            break

                        # Kiểm tra nếu thẻ card hiện tại xuất hiện phía sau banner phân cách "Chỗ nghỉ xung quanh / nằm ngoài..."
                        if is_card_outside_region(page, card):
                            print(f"[{mode_tag}] [🛑 PHÁT HIỆN THÔNG BÁO NẰM NGOÀI KHU VỰC]: Đã chạm tới danh sách 'Chỗ nghỉ xung quanh / nằm ngoài'! Dừng cào hạng {star} sao ngay lập tức.")
                            hit_outside_banner = True
                            break

                        try:
                            title_loc = card.locator('[data-testid="title"]').first
                            if title_loc.count() == 0:
                                continue
                            title = clean_text(title_loc.inner_text())


                            link_loc = card.locator('a[data-testid="title-link"], a[href*="/hotel/"]').first
                            href = link_loc.get_attribute('href') if link_loc.count() > 0 else ""
                            if not href:
                                continue
                            clean_url = href.split('?')[0]

                            if not clean_url or clean_url in existing_urls:
                                continue

                            address_loc = card.locator('[data-testid="address"]').first
                            address = clean_text(address_loc.inner_text()) if address_loc.count() > 0 else ""

                            category_label = f"{star}-star hotel"
                            full_url = f"https://www.booking.com{href}" if href.startswith('/') else href

                            item = {
                                "title": title,
                                "address": address,
                                "url": full_url,
                                "totalScore": "",
                                "categoryName": category_label,
                                "source": f"Booking: {full_url}"
                            }

                            saved, total_file = safe_save_record(output_file, item)
                            existing_urls.add(clean_url)
                            star_results_count += 1
                            last_new_record_time = time.time()
                            print(f"[{mode_tag}] ✓ Hạng {star} sao [{star_results_count}/{expected_count}]: '{title}' | categoryName: '{category_label}' | Address: '{address[:30]}'")
                            
                            pct = (star_results_count / expected_count * 100)
                            print(f"[{mode_tag}] Tiến trình: {star_results_count} / {expected_count} bản ghi đã quét ({pct:.1f}%)")

                            # ĐÁNH DẤU MỖI KHI ĐẠT BỘI SỐ 25 BẢN GHI (#25, #50, #75...)
                            if star_results_count > 0 and (star_results_count % 25 == 0) and star_results_count != last_milestone:
                                last_milestone = star_results_count
                                print(f"[{mode_tag}] [📍 MỐC {star_results_count} BẢN GHI] Đã lưu xong mốc {star_results_count} bản ghi ➔ Cuộn xuống cuối trang ngay lập tức & Bấm Load More...")
                                
                                try:
                                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                    time.sleep(0.4)
                                except Exception:
                                    pass

                                clicked = trigger_load_more_click(page)
                                if clicked:
                                    print(f"[{mode_tag}] [{star}★] ✓ Đã click 'Load more results' ở cuối trang tại mốc {star_results_count}. Chờ Booking nạp kết quả mới 2.0s...")
                                else:
                                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

                                time.sleep(2.0)

                        except Exception:
                            continue

                    if hit_outside_banner or star_results_count >= expected_count:
                        break

                    # KIỂM TRA THỜI GIAN 30 GIÂY KHÔNG CÓ BẢN GHI MỚI ➔ CHUYỂN FILTER
                    elapsed_no_new = time.time() - last_new_record_time
                    if elapsed_no_new >= 30.0:
                        print(f"[{mode_tag}] [!] Đã quá 30 giây ({elapsed_no_new:.1f}s) không có bản ghi mới nào cho hạng {star} sao. Tự động chuyển sang hạng sao tiếp theo!")
                        break

                    # Cuộn xuống cuối trang và nhấp nút "Load more results"
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(0.4)

                    clicked = trigger_load_more_click(page)
                    if clicked:
                        print(f"[{mode_tag}] [{star}★] ✓ Đã click nút 'Load more results' ở cuối trang. Chờ Booking nạp kết quả 2.0s...")
                        time.sleep(2.0)
                    else:
                        time.sleep(1.0)

                print(f"[{mode_tag}] [*] Đã hoàn thành STAGE 1 cho hạng {star} sao ({star_results_count}/{expected_count} chỗ nghỉ).")
                toggle_star_filter(page, star=star, enable=False, mode_tag=mode_tag)

            # =========================================================================
            # STAGE 2: BÓC TÁCH CHI TIẾT (TITLE, CATEGORYNAME, ADDRESS) PLAYWRIGHT CHROMIUM
            # =========================================================================
            print(f"\n==================================================")
            print(f"[{mode_tag}] [*] CHUYỂN SANG STAGE 2: BÓC TÁCH CHI TIẾT 100% PLAYWRIGHT CHROMIUM...")
            print(f"==================================================")

            all_records_to_enrich = []
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                        if isinstance(raw, list):
                            all_records_to_enrich = raw
                except Exception:
                    pass

            total_enrich = len(all_records_to_enrich)
            print(f"[{mode_tag}] [STAGE 2 Playwright] Đang bóc tách chi tiết cho {total_enrich} bản ghi trong '{output_file}'...")

            for idx, record_item in enumerate(all_records_to_enrich):
                url = record_item.get("url", "")
                if not url:
                    continue

                try:
                    details = extract_detail_page(page, url)
                    if details:
                        if details.get("title") and details["title"].strip():
                            record_item["title"] = details["title"].strip()

                        if details.get("address") and details["address"].strip():
                            record_item["address"] = details["address"].strip()

                        # Gắn cờ hậu tố (#can-ho) khi extract_detail_page phát hiện thẻ rating-squares (đánh giá chất lượng căn hộ)
                        if details.get("is_apartment"):
                            t_curr = record_item.get("title", "")
                            if "(#can-ho)" not in t_curr:
                                record_item["title"] = f"{t_curr} (#can-ho)".strip()

                        record_item["totalScore"] = ""  # Đảm bảo rỗng 100%

                        safe_save_record(output_file, record_item)
                        print(f"[{mode_tag}] [Stage 2 Detail {idx + 1}/{total_enrich}] ✓ '{record_item.get('title')}' | categoryName: '{record_item.get('categoryName')}' | Addr: '{record_item.get('address')[:45]}'")
                except Exception as e:
                    print(f"[{mode_tag}] [Stage 2 Detail {idx + 1}/{total_enrich}] [!] Bỏ qua bản ghi do lỗi điều hướng: {e}")

        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                if os.path.exists(worker_profile_dir):
                    shutil.rmtree(worker_profile_dir, ignore_errors=True)
            except Exception:
                pass

            print(f"[{mode_tag}] HOÀN THÀNH TOÀN BỘ BỐC TÁCH BOOKING.COM! Dữ liệu đã lưu trọn vẹn vào '{output_file}'.")

if __name__ == "__main__":
    dest = CONFIG.get("target_province", "Ho Chi Minh City")
    out_file = CONFIG.get("output_file", "hotels.json")

    for arg in sys.argv[1:]:
        if arg.endswith(".json"):
            out_file = arg
        else:
            dest = arg

    run_booking_harvester(dest, out_file)
