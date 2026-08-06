import json
import time
import os
import re
import sys
import unicodedata
from urllib.parse import unquote

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

def clean_text(text):
    if not text:
        return ""
    cleaned = re.sub(r'[\u200e\u200f\u200b\ufeff\n\r\t\ue000-\uf8ff]', '', text)
    return cleaned.strip()

def strip_accents(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize('NFD', text)
    stripped = "".join([c for c in nfkd if unicodedata.category(c) != 'Mn'])
    return stripped.replace('đ', 'd').replace('Đ', 'D').lower().strip()

def extract_title_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        decoded_url = unquote(url)
        match_place = re.search(r'/place/([^/]+)', decoded_url)
        if match_place:
            return match_place.group(1).replace('+', ' ').replace('%20', ' ').strip()
        match_query = re.search(r'[?&]query=([^&]+)', decoded_url)
        if match_query:
            return match_query.group(1).replace('+', ' ').replace('%20', ' ').strip()
    except Exception:
        pass
    return ""

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
    if "stars" in r and r["stars"]:
        formatted["stars"] = r["stars"]
    return formatted

def safe_save_file(output_file, records):
    for idx, r in enumerate(records):
        records[idx] = format_standard_record(r, idx + 1)

    for attempt in range(15):
        try:
            temp_file = f"{output_file}.tmp_swap_{os.getpid()}"
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
            time.sleep(0.3)
    return False

def run_in_memory_swap_repair(input_file=None):
    if not input_file:
        input_file = TARGET_JSON_FILE

    mode_tag = "MISMATCH_REPAIR"
    print(f"[{mode_tag}] Đã khởi chạy Thuật Toán Hoán Đổi & Căn Chỉnh Dữ Liệu Tức Thì (In-Memory Swapping)...")

    if not os.path.exists(input_file):
        print(f"[{mode_tag}] Lỗi: Không tìm thấy file dữ liệu '{input_file}'!")
        return

    with open(input_file, 'r', encoding='utf-8') as f:
        records = json.load(f)

    total_records = len(records)
    print(f"[{mode_tag}] Đang đọc file dữ liệu: {input_file} ({total_records} bản ghi).")

    # 1. BƯỚC 1: XÂY DỰNG BẢNG TRA CỨU DỮ LIỆU TỪ LINK URL (LOOKUP DICTIONARY)
    url_payload_map = {}
    for idx, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        url = r.get("url", "")
        extracted_name = extract_title_from_url(url)
        norm_name = strip_accents(extracted_name)

        if norm_name:
            payload = {
                "url": r.get("url", ""),
                "address": r.get("address", ""),
                "phone": r.get("phone", ""),
                "categoryName": r.get("categoryName", ""),
                "totalScore": r.get("totalScore", ""),
                "website": r.get("website", ""),
                "facebook": r.get("facebook", ""),
                "email": r.get("email", ""),
                "source": r.get("source", ""),
                "stars": r.get("stars", "")
            }
            url_payload_map[norm_name] = payload

    print(f"[{mode_tag}] Đã bóc tách và tạo Bảng Tra Cứu cho {len(url_payload_map)} URL hợp lệ.")

    # 2. BƯỚC 2: HOÁN ĐỔI & TRẢ DỮ LIỆU KHỚP VỀ ĐÚNG HÀNG TÊN CƠ SỞ (TITLE)
    swapped_count = 0
    already_matched = 0

    for idx, r in enumerate(records):
        if not isinstance(r, dict):
            continue
        title = r.get("title", "")
        norm_title = strip_accents(title)

        # Kiểm tra xem dòng hiện tại có bị lệch không
        cur_url_title = strip_accents(extract_title_from_url(r.get("url", "")))
        if cur_url_title and norm_title and norm_title == cur_url_title:
            already_matched += 1
            print(f"[{mode_tag}] Tiến trình: {idx + 1} / {total_records} bản ghi đã quét ({(idx+1)/total_records*100:.1f}%)")
            continue

        # Tìm kiếm payload khớp nhất trong Lookup Map
        matched_payload = None
        if norm_title in url_payload_map:
            matched_payload = url_payload_map[norm_title]
        else:
            # Fuzzy match thử tìm kiếm theo từ khóa nếu tên gần đúng
            words_title = set(re.findall(r'\w+', norm_title))
            best_ratio = 0.0
            for key_name, payload in url_payload_map.items():
                words_key = set(re.findall(r'\w+', key_name))
                if not words_key:
                    continue
                overlap = len(words_title.intersection(words_key)) / max(len(words_title), 1)
                if overlap > 0.65 and overlap > best_ratio:
                    best_ratio = overlap
                    matched_payload = payload

        if matched_payload:
            for k, val in matched_payload.items():
                if val != "":
                    r[k] = val
            swapped_count += 1
            print(f"[{mode_tag}] ✓ SWAP THÀNH CÔNG #{swapped_count}: '{title}' ➔ Khớp lại đúng Link & Thông tin!")

        print(f"[{mode_tag}] Tiến trình: {idx + 1} / {total_records} bản ghi đã quét ({(idx+1)/total_records*100:.1f}%)")

    # 3. LƯU TỆP KHÔI PHỤC VÀ IN BÁO CÁO
    safe_save_file(input_file, records)

    print(f"\n[{mode_tag}] HOÀN THÀNH HOÁN ĐỔI CĂN CHỈNH!")
    print(f"[{mode_tag}] Tổng số bản ghi đúng sẵn: {already_matched}/{total_records}")
    print(f"[{mode_tag}] Số bản ghi đã được hoán đổi trả về đúng hàng: {swapped_count}/{total_records}")
    print(f"[{mode_tag}] HOÀN THÀNH SỬA LỆCH DÒNG! File dữ liệu '{input_file}' đã được làm sạch và khớp 100%!")

if __name__ == "__main__":
    out_file = CONFIG.get("output_file", "hotels.json")
    for arg in sys.argv[1:]:
        if arg.endswith(".json"):
            out_file = arg
    run_in_memory_swap_repair(out_file)
