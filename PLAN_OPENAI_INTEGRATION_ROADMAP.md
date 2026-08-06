# 📌 KẾ HOẠCH NÂNG CẤP HỆ THỐNG: TÍCH HỢP CHATGPT API (OPENAI) & HỢP NHẤT DỮ LIỆU ĐA NỀN TẢNG

Tài liệu ghi nhớ kế hoạch chiến lược mở rộng hệ thống: Kết hợp cào dữ liệu từ **Website Trung Gian** + **Google Maps** + **ChatGPT API (`gpt-4o-mini`)** để đạt độ chính xác tối đa (98% - 99%).

---

## 🎯 1. MỤC TIÊU DỰ ÁN

1. **Bổ sung nguồn dữ liệu:** Lấy danh sách tên cơ sở + địa chỉ gốc từ một trang web trung gian (ví dụ: Trang vàng, danh bạ du lịch, cổng thông tin...).
2. **Đối chiếu & Làm giàu dữ liệu:** Dùng Google Maps để cào bổ sung các trường thông tin bị thiếu: Số điện thoại, Tọa độ GPS, Đánh giá TotalScore, Website chính thức, Trang Facebook, Link Google Maps.
3. **Thẩm định bằng AI (ChatGPT API):** Tự động so sánh bản ghi từ trang trung gian với kết quả Google Maps, tính điểm độ tin cậy trùng khớp ($0-100\%$), tự động sửa lỗi chính tả/viết tắt và gộp thành 1 bản ghi Master chuẩn xác tuyệt đối.

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
- Gửi `Tên thô` + `Địa chỉ thô` qua **ChatGPT API (`gpt-4o-mini`)**.
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
