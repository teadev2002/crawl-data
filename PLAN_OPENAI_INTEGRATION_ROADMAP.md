# 📌 KẾ HOẠCH NÂNG CẤP HỆ THỐNG: TÍCH HỢP CHATGPT API (OPENAI) & HỢP NHẤT DỮ LIỆU ĐA NỀN TẢNG

Tài liệu ghi nhớ kế hoạch chiến lược mở rộng hệ thống: Kết hợp cào dữ liệu từ **Website Trung Gian** + **Google Maps** + **ChatGPT API (`gpt-4o-mini`)** để đạt độ chính xác tối đa (98% - 99%).

---

 MỤC TIÊU chức năng AI Checking

 Bổ sung nguồn dữ liệu: Lấy danh sách tên cơ sở + địa chỉ gốc từ file output viết thành search query như đang chat box với AI "title + address + url map" để AI trả lời rồi lấy url map AI phản hồi vào link map đó kiểm tra xem đúng tên cơ sở ( title ) và địa chỉ ( address) không, nếu đúng trên 70% thì lấy thêm field phone, điền vào field phone và link trên google map và điền vào field url, nếu dưới 70% so với dữ liệu đang tìm thì giữ nguyên record và next qua record khác. Đối với 1 happy case sau khi tìm kiếm sẽ có response:
{
    "stt": 155,
    "title": "Vsana Vu Son Hotel",
    "email": "",
    "phone": "0913796386",
    "address": "Hồ Xuân Hương, Sầm Sơn, Việt Nam",
    "url": "https://www.google.com/maps/place/Kh%C3%A1ch+s%E1%BA%A1n+V%C5%A9+S%C6%A1n/@19.7557868,105.9131843,825m/data=!3m2!1e3!4b1!4m6!3m5!1s0x313650e6aaaaaaab:0x83b4d3183c44390b!8m2!3d19.7557868!4d105.9131843!16s%2Fg%2F11c5sskgqz?entry=ttu&g_ep=EgoyMDI2MDgwNS4xIKXMDSoASAFQAw%3D%3D",
    "totalScore": "",
    "website": "",
    "facebook": "",
    "categoryName": "3-star hotel",
    "source": "Booking: https://www.booking.com/hotel/vn/vsana-vu-son.vi.html?aid=304142&label=gen173nr-10CAQoggJCEXNlYXJjaF90aGFuaCBow7NhSCpYBGj0AYgBAZgBM7gBF8gBDNgBA-gBAfgBAYgCAagCAbgC9qTn0wbAAgHSAiQ4NDk3YmMzNy0wOGM1LTQyOTktOTdmMi02MzVkNzQ4Y2RjZTbYAgHgAgE&ucfs=1&arphpl=1&group_adults=2&req_adults=2&no_rooms=1&group_children=0&req_children=0&hpos=14&hapos=64&sr_order=popularity&nflt=class%3D3&srpvid=915c5efbc785149c&srepoch=1786368667&from=searchresults",
    "isFlag": false
  }

đối với worst case thì response sẽ là:
{
    "stt": 155,
    "title": "Vsana Vu Son Hotel",
    "email": "",
    "phone": "",
    "address": "Hồ Xuân Hương, Sầm Sơn, Việt Nam",
    "url": "https://www.booking.com/hotel/vn/vsana-vu-son.vi.html?aid=304142&label=gen173nr-10CAQoggJCEXNlYXJjaF90aGFuaCBow7NhSCpYBGj0AYgBAZgBM7gBF8gBDNgBA-gBAfgBAYgCAagCAbgC9qTn0wbAAgHSAiQ4NDk3YmMzNy0wOGM1LTQyOTktOTdmMi02MzVkNzQ4Y2RjZTbYAgHgAgE&ucfs=1&arphpl=1&group_adults=2&req_adults=2&no_rooms=1&group_children=0&req_children=0&hpos=14&hapos=64&sr_order=popularity&nflt=class%3D3&srpvid=915c5efbc785149c&srepoch=1786368667&from=searchresults",
    "totalScore": "",
    "website": "",
    "facebook": "",
    "categoryName": "3-star hotel",
    "source": "Booking: https://www.booking.com/hotel/vn/vsana-vu-son.vi.html?aid=304142&label=gen173nr-10CAQoggJCEXNlYXJjaF90aGFuaCBow7NhSCpYBGj0AYgBAZgBM7gBF8gBDNgBA-gBAfgBAYgCAagCAbgC9qTn0wbAAgHSAiQ4NDk3YmMzNy0wOGM1LTQyOTktOTdmMi02MzVkNzQ4Y2RjZTbYAgHgAgE&ucfs=1&arphpl=1&group_adults=2&req_adults=2&no_rooms=1&group_children=0&req_children=0&hpos=14&hapos=64&sr_order=popularity&nflt=class%3D3&srpvid=915c5efbc785149c&srepoch=1786368667&from=searchresults",
    "isFlag": false
  }
 tự động sửa lỗi chính tả/viết tắt 
---

## 🏗️ 2. KIẾN TRÚC LUỒNG XỬ LÝ 4 GIAI ĐOẠN (DATA PIPELINE)

```
[BƯỚC 1: CÀO TRANG TRUNG GIAN]
       │ ➔ Thu thập: Tên cơ sở thô + Địa chỉ thô
       ▼
[BƯỚC 2: CHATGPT AI CHUẨN HÓA & TẠO QUERY]
       │ ➔ Xử lý viết tắt (KS ➔ Khách sạn), phân rã Tỉnh/Thành
       │ ➔ Tạo câu lệnh tìm kiếm Google Maps tối ưu
       ▼
[BƯỚC 3: CÀO ĐỐI CHIẾU GOOGLE MAPS]
       │ ➔ Truy vấn Google Maps cào bổ sung: SĐT, Web, FB, Rating, Maps URL
       ▼
[BƯỚC 4: CHATGPT AI THẨM ĐỊNH & HỢP NHẤT MASTER DATA]
       │ ➔ Chấm điểm độ tin cậy trùng khớp (Confidence Score %)
       │ ➔ Lọc bỏ 100% email/rác hệ thống
       ▼
[BỘ DỮ LIỆU ĐẦY ĐỦ 100% CHÍNH XÁC]
```

---

## 🛠️ 3. CHI TIẾT TỪNG GIAI ĐOẠN THỰC THI

### Giai Đoạn 1: Cào Dữ Liệu Gốc Trang Trung Gian (`site_harvester.py`)
- Viết module cào dữ liệu danh sách cơ sở từ website trung gian mục tiêu.
- Trích xuất 2 trường cốt lõi: `Tên cơ sở thô` và `Địa chỉ thô`.

### Giai Đoạn 2: AI Chuẩn Hóa & Tạo Từ Khóa (`ai_enricher.py`)
- Gửi `Tên thô` + `Địa chỉ thô` qua **ChatGPT API (`gpt-4o-mini`)** them từ keyword "map".
- AI phân tích và trả về định dạng JSON:
  - `clean_title`: Tên đã sửa chính tả và giải mã từ viết tắt (`KS` ➔ `Khách sạn`, `DNTN` ➔ `Doanh nghiệp tư nhân`).
  - `clean_province`: Tỉnh/Thành phố chuẩn.
  - `search_query`: Từ khóa tối ưu nhất để cào Google Maps.

### Giai Đoạn 3: Cào Bổ Sung Chi Tiết Từ Google Maps (`map_scraper.py`)
- Sử dụng `search_query` từ Giai Đoạn 2 để chạy module `map_scraper.py`.
- Thu thập đầy đủ các trường: `phone`, `address`, `url`, `totalScore`, `website`, `facebook`, `categoryName`.

### Giai Đoạn 4: AI Thẩm Định Trùng Khớp & Hợp Nhất (`ai_matcher.py`)
- Gửi Bản ghi A (Trang trung gian) + Bản ghi B (Google Maps) cho ChatGPT API.
- Prompt AI đánh giá 2 bản ghi có cùng mô tả 1 địa điểm thực tế hay không.
- AI trả về kết quả JSON Structured Output:
  - `is_same_place`: True / False.
  - `confidence`: % độ tin cậy (ví dụ: 95%).
  - `master_record`: Bản ghi đã gộp thông tin hoàn chỉnh nhất.

---

## 💰 4. DỰ TÍNH CHI PHÍ & HIỆU NĂNG OPERATIONAL

| Tiêu chí | Thông số kỹ thuật |
| :--- | :--- |
| **Model AI Khuyên Dùng** | `gpt-4o-mini` (Bản API siêu nhẹ, hỗ trợ JSON Structured Outputs) |
| **Chi Phí API** | ~$0.15 / 1.000.000 Tokens |
| **Ước Tính Chi Phí Thực Tế** | 10.000 địa điểm tốn khoảng **0.3$ - 0.5$ USD** (~8.000 - 12.000 VNĐ) |
| **Tốc Độ Xử Lý** | ~0.2s - 0.5s / bản ghi (hỗ trợ Async/Await gọi song song) |
| **Độ Chính Xác** | Đạt **98% - 99%**, loại bỏ 100% email/rác hệ thống |

---

## 📝 5. DANH SÁCH CÔNG VIỆC CẦN LÀM KHI BẮT ĐẦU (CHECKLIST FOR LATER)

- [ ] **Bước 1:** Đăng ký OpenAI API Key (`OPENAI_API_KEY`) tại `platform.openai.com`.
- [ ] **Bước 2:** Xác định Website Trung Gian mục tiêu & cấu trúc dữ liệu cần cào.
- [ ] **Bước 3:** Viết script cào dữ liệu gốc trang trung gian.
- [ ] **Bước 4:** Tạo module `ai_enricher.py` kết hợp thư viện `openai` Async Client.
- [ ] **Bước 5:** Tích hợp nút bấm kích hoạt AI vào Web Dashboard (`server.py` & `static/app.js`).

---

*Tài liệu kế hoạch được lưu trữ tự động tại tệp: `PLAN_OPENAI_INTEGRATION_ROADMAP.md`.*
