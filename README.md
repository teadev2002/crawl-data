# 🚀 HỆ THỐNG CÀO & PHÂN TÍCH DỮ LIỆU ĐA NỀN TẢNG (MAPS, EMAIL, CATEGORY, STAR HARVESTER)

Hệ thống tự động hóa cào, thu thập, bóc tách và phục hồi dữ liệu thông tin doanh nghiệp, khách sạn và dịch vụ lưu trú quy mô lớn với giao diện Web Dashboard quản lý thời gian thực (Real-Time Live Dashboard).

---

## 📌 MỤC LỤC
1. [Tổng Quan Kiến Trúc & Công Nghệ](#-tổng-quan-kiến-trúc--công-nghệ)
2. [Chi Tiết Các Chức Năng Chính](#-chi-tiết-các-chức-năng-chính)
   - [Tool 1: Cào Dữ Liệu Google Maps Đa Luồng](#tool-1-cào-dữ-liệu-google-maps-đa-luồng-map_scraperpy)
   - [Tool 2: Quét Tìm Email Doanh Nghiệp](#tool-2-quét-tìm-email-doanh-nghiệp-email_harvesterpy)
   - [Tool 3: Dò Tìm Phân Loại CategoryName](#tool-3-dò-tìm-phân-loại-categoryname-category_repairerpy)
   - [Tool 4: Sửa & Khôi Phục Bản Ghi Lỗi N/A](#tool-4-sửa--khôi-phục-bản-ghi-lỗi-na-info_repairerpy)
   - [Tool 5: Tìm Số Sao Khách Sạn Waterfall 3 Nền Tảng](#tool-5-tìm-số-sao-khách-sạn-waterfall-3-nền-tảng-star_harvesterpy)
3. [Luồng Sử Dụng Cho Từng Chức Năng (User Flows)](#-luồng-sử-dụng-cho-từng-chức-năng-user-flows)
4. [Giao Diện Quản Lý Web Dashboard](#-giao-diện-quản-lý-web-dashboard)
5. [Hướng Dẫn Cài Đặt & Vận Hành](#-hướng-dẫn-cài-đặt--vận-hành)
6. [Cấu Trúc Dữ Liệu Tiêu Chuẩn (JSON Output)](#-cấu-trúc-dữ-liệu-tiêu-chuẩn-json-output)

---


## 💡 CHI TIẾT CÁC CHỨC NĂNG CHÍNH

### Tool 1: Cào Dữ Liệu Google Maps Đa Luồng (`map_scraper.py`)
* **Chạy Đa Luồng Song Song Flex:** Cho phép người dùng tùy chọn radio chạy **3 Luồng**, **4 Luồng** hoặc **5 Luồng** song song (`3way`, `4way`, `5way`).
* **Chia Phân Đoạn Toán Học $X$-Way:** Tự động phân chia danh sách hàng ngàn từ khóa dán trong cấu hình theo công thức floor-division, đảm bảo **0% trùng lặp** và **0% bỏ sót**.
* **Bộ Lọc Tọa Độ Tỉnh/Thành (`target_province`):** Tích hợp tọa độ Bounding Box (`PROVINCE_BOUNDS_MAP`) của 34 tỉnh/thành phố Việt Nam, tự động loại bỏ các địa điểm nằm ngoài vùng địa lý mong muốn.
* **Tối Ưu Tốc Độ Siêu Tốc (Asset Blocking):** Chặn tải hình ảnh, font chữ, media nặng qua Playwright Route Interception, giảm 70% băng thông và tăng tốc cào gấp 3 lần.
* **Cơ Chế Chỉ Tiêu Tối Đa `max_results`:** Tất cả các luồng tự động kiểm tra tổng số bản ghi đĩa và dừng ngay lập tức khi đạt đủ chỉ tiêu.

---

### Tool 2: Quét Tìm Email Doanh Nghiệp (`email_harvester.py`)
* **Chạy 2 Luồng Song Song (TOP & BOTTOM):** Phân chia danh sách các bản ghi chưa có email thành 2 nửa và quét đồng thời.
* **Đa Nguồn Quét Email:** Quét từ kết quả Google Search, trang chủ Website của cơ sở, trang Contact/Giới thiệu, và trang Facebook About.
* **Bóc Tách Regex Tiêu Chuẩn:** Nhận diện email qua thẻ `mailto:` và chuỗi regex tiêu chuẩn RFC 5322, tự động loại bỏ email rác/placeholder.

---

### Tool 3: Dò Tìm Phân Loại CategoryName (`category_repairer.py`)
* **Phục Hồi CategoryName Rỗng/N/A:** Dò tìm ngành nghề chính xác của cơ sở (ví dụ: `Hotel`, `Resort`, `Restaurant`, `Repair Shop`...).
* **Phân Tích Đa Nguồn:** Tra cứu tên cơ sở, trang web, và danh mục dịch vụ trên Google Maps/Search để cập nhật trường `"categoryName"`.

---

### Tool 6: Khôi Phục & Sửa Lỗi Lệch Dòng Title & URL (`mismatch_repairer.py`)
* **Thuật Toán Swapping Tức Thì (< 1s):** Giải mã tên cơ sở ẩn trong đường link `url` (unquote), tạo Bảng tra cứu đối chiếu trong bộ nhớ (In-Memory Lookup Map) và tráo trả dữ liệu `url`, `address`, `phone`, `categoryName`, `totalScore` về đúng vị trí hàng Tên cơ sở (`title`).
* **Bảo Tồn 100% Dữ Liệu Gốc:** Khôi phục nhanh chóng các file JSON bị tráo dòng/cột do thao tác trên Excel mà không cần cào lại trình duyệt.

---

### Tool 7: Cào Dữ Liệu Booking.com Trực Tiếp (Stage 1) (`booking_harvester.py`)
* **Cào Trực Tiếp Booking.com Theo Hạng Sao:** Lựa chọn địa điểm (ví dụ: *Ho Chi Minh City*), áp dụng bộ lọc `Hotels` và quét vòng lặp từ **5★ ➔ 4★ ➔ 3★ ➔ 2★ ➔ 1★**.
* **Lazy Loading & Nạp Nút:** Tự động cuộn trang và nhấp nút `"Load more results"` đến khi nạp hết toàn bộ danh sách khách sạn.
* **Bóc Tách Chi Tiết Trang Khách Sạn:** Thu thập Tên cơ sở (`pp-header__title`), Địa chỉ chuẩn (`b99b6ef58f...`), Số sao chính xác (`rating-stars` / đếm thẻ `e03979cfad`) và lưu đè đĩa nguyên tử Real-Time!

---

### Tool 8: AI Checking (Google Gemini API) (`ai_checking.py`)
* **Truy Vấn AI Đa Tầng (`google-genai` / `gemini-3.5-flash`):** Sử dụng Gemini API tự động tạo câu lệnh tìm kiếm Google Maps tối ưu từ Tên + Địa chỉ Booking kèm từ khóa `"map"`.
* **Thẩm Định Điểm Trùng Khớp ($\ge 70\%$):** Gọi Gemini AI so sánh độ tương đồng Tên và Địa chỉ giữa Booking.com và kết quả Google Maps candidate.
* **Cập Nhật Link Maps Vào Trường `url` & Bảo Tồn Source:** Khi Match Score $\ge 70\%$, hệ thống lưu link Google Maps vừa tìm được vào trường `url`, điền SĐT (`phone`), Rating (`totalScore`), Website, Facebook và nối nguồn Booking vào trường `source`!

---

### Tool 5: Tìm Số Sao Khách Sạn Waterfall 3 Nền Tảng (`star_harvester.py`)
* **Quy Trình Waterfall 3 Lớp:**
  1. Thử cào trên **Booking.com**
  2. Nếu không tìm thấy $\rightarrow$ Thử sang **Agoda.com**
  3. Nếu vẫn không thấy $\rightarrow$ Thử tiếp **Traveloka.com**
  *(Lấy được số sao ở bất kỳ nền tảng nào sẽ chốt kết quả ngay và chuyển sang khách sạn tiếp theo).*
* **Tùy Chọn Đa Luồng (2, 3, 4 Luồng):** Tự động phân chia danh sách chưa có sao theo radio chọn số luồng trên UI (`star_2way`, `star_3way`, `star_4way`).
* **Lọc Link Cụ Thể "Link 1 vs Link 2" (`is_specific_hotel_url`):** Tự động phát hiện và bỏ qua các đường link dẫn về trang danh sách thành phố chung (`booking.com/city/...`), tự động thử Link 2 để chọn đúng trang chi tiết khách sạn.
* **Đối Chiếu Tỉnh/Thành Chuẩn Hóa Không Dấu (`strip_accents` & `is_province_matched`):** Bóc tách địa chỉ hiển thị trên trang khách sạn, bỏ dấu tiếng Việt (Unicode NFD) để đối chiếu Tỉnh/Thành. **Nếu địa chỉ trên trang sai Tỉnh/Thành $\rightarrow$ hủy kết quả ngay lập tức** để tránh lấy nhầm số sao của khách sạn cùng tên ở tỉnh khác.
* **Nối Chuỗi Trường Nguồn `source` Bằng Dấu ` | `:**
  - `categoryName`: `"2-star hotel"`
  - `stars`: `"2-star hotel"`
  - `source`: `"Facebook About: https://... | Agoda: https://www.agoda.com/vi-vn/..."` *(Cộng dồn các nguồn linh hoạt).*
* **Bộ Tìm Kiếm Đa Engine Chống CAPTCHA:** Google Search $\rightarrow$ Bing Search $\rightarrow$ DuckDuckGo.
* **Tự Động Xóa Cache Sau Khi Hoàn Thành:** Tự động giải phóng hoàn toàn thư mục `browser_profile_pX` sau khi dừng hoặc hoàn thành nhiệm vụ.

---

## 🔄 LUỒNG SỬ DỤNG CHO TỪNG CHỨC NĂNG (USER FLOWS)

### 🔴 User Flow 1: Cấu Hình Hệ Thống & Chuẩn Bị Tìm Kiếm (Tab Config)
```
[Mở Dashboard] ➔ [Chọn Tab 'Cấu hình'] ➔ [Dán Danh Sách Từ Khóa (Search Queries)]
                                                    │
[Lưu Cấu Hình] ◄─ [Đặt Tên File Output (hotels.json)] ◄─ [Chọn Tỉnh/Thành Mục Tiêu]
```
1. Người dùng mở trang Web Dashboard tại `http://localhost:8000`.
2. Chuyển sang tab **"Cấu hình Hệ thống"** (`Tab Config`).
3. Dán danh sách từ khóa tìm kiếm (mỗi từ khóa 1 dòng, ví dụ: danh sách tên con đường trong các phường/xã).
4. Chọn **Tỉnh/Thành phố mục tiêu** từ menu 34 Tỉnh/Thành để kích hoạt bộ lọc địa lý chuẩn xác.
5. Đặt tên file xuất dữ liệu (`hotels.json`).
6. Nhấn nút **"Lưu Cấu hình"**.

---

### 🟢 User Flow 2: Cào Dữ Liệu Google Maps Đa Luồng (`map_scraper.py`)
```
[Chọn Radio: 3 / 4 / 5 Luồng] ➔ [Nhập max_results] ➔ [Bấm '🚀 Chạy X Luồng (Song song)']
                                                                  │
[Tự Động Dừng Khi Xong/Đủ Max] ◄─ [Cập Nhật Progress & Logs] ◄─ [5 Trình Duyệt Bật Giãn Cách 0.8s]
```
1. Tại Tab **Dashboard**, di chuyển đến thẻ **Tool 1: Cào Dữ Liệu Google Maps**.
2. Chọn số luồng cào song song bằng nút Radio: **3 Luồng**, **4 Luồng** hoặc **5 Luồng**.
3. Nhập số kết quả tối đa cần cào vào ô `max_results` (mặc định 100/200/1000).
4. Nhấn nút **`🚀 Chạy X Luồng (Song song)`**.
5. Quan sát các cửa sổ trình duyệt khởi chạy lần lượt (giãn cách 0.8s), log Real-Time chạy liên tục trên Live Console và thanh tiến trình nhảy con số thực tế.
6. Khi hoàn thành hoặc đủ chỉ tiêu `max_results`, hệ thống thông báo hoàn thành và tự động đóng trình duyệt.

---

### 🟡 User Flow 3: Quét Tìm Email Doanh Nghiệp (`email_harvester.py`)
```
[File Output Đã Có Data] ➔ [Thẻ Tool 2: Quét Email] ➔ [Bấm '📧 Quét Email (2 Luồng)']
                                                                  │
[Cập Nhật Email & Icon Thẻ Email] ◄─ [Quét Google/Web/Facebook] ◄─ [2 Luồng TOP & BOTTOM Khởi Chạy]
```
1. Đảm bảo file JSON làm việc (`hotels.json`) đã có dữ liệu địa điểm từ bước cào Google Maps.
2. Tại thẻ **Tool 2: Quét Email Doanh Nghiệp**, bấm nút **`📧 Quét Email (2 Luồng)`**.
3. Hệ thống kích hoạt 2 luồng song song (TOP & BOTTOM) tự động quét các bản ghi chưa có email.
4. Trình duyệt mở Google Search, trang chủ Website của cơ sở, trang Giới thiệu/Contact và trang Facebook About để bóc tách email.
5. Dữ liệu Email bổ sung Real-Time vào file JSON, thẻ **"Đã có Email"** trên ô thống kê tăng dần.

---

### 🔵 User Flow 4: Dò Tìm Phân Loại CategoryName (`category_repairer.py`)
```
[Thẻ Tool 3: Dò Category] ➔ [Bấm '🏷️ Dò Category (2 Luồng)'] ➔ [2 Luồng Song Song Khởi Chạy]
                                                                        │
[Cập Nhật CategoryName Chuẩn] ◄─ [Lưu Atomic Write Real-Time] ◄─ [Dò Tìm Tên/Web/Search]
```
1. Tại thẻ **Tool 3: Dò CategoryName**, bấm nút **`🏷️ Dò Category (2 Luồng)`**.
2. Hệ thống quét rà soát các bản ghi bị rỗng hoặc `"N/A"` ở trường `categoryName`.
3. Dò tìm ngành nghề thực tế (như `Hotel`, `Resort`, `Restaurant`...) và lưu đè vào file JSON.

---

### 🟣 User Flow 5: Sửa & Khôi Phục Bản Ghi Lỗi N/A (`info_repairer.py`)
```
[Thẻ Tool 4: Sửa Lỗi N/A] ➔ [Bấm '🔧 Sửa dữ liệu N/A'] ➔ [Rà Soát Bản Ghi Khuyết SĐT/Địa Chỉ]
                                                                   │
[Bản Ghi Đầy Đủ 100%] ◄─ [Khôi Phục SĐT & Địa Chỉ Chuẩn] ◄─ [Truy Vấn Lại Trang Chi Tiết]
```
1. Tại thẻ **Tool 4: Sửa bản ghi lỗi N/A**, bấm nút **`🔧 Sửa dữ liệu N/A`**.
2. Hệ thống tìm các bản ghi thiếu SĐT hoặc Địa chỉ.
3. Mở lại trang truy vấn chi tiết để điền bổ sung thông tin chính xác.

---

### 🧡 User Flow 6: Tìm Số Sao Khách Sạn Waterfall 3 Nền Tảng (`star_harvester.py`)
```
[Chọn Radio: 2 / 3 / 4 Luồng] ➔ [Bấm '🚀 Chạy X Luồng (Booking & Agoda)']
                                                 │
[Tự Động Xóa Profile Cache Tạm] ◄─ [Thử Waterfall: Booking ➔ Agoda ➔ Traveloka]
              │                                  │
              └─── [Ajax Polling 3s Nhảy Thống Kê 1-5★] ◄─ [Lưu Nguồn `source` Nối ` | `]
```
1. Tại thẻ **Tool 5: Tìm số sao Booking & Agoda**, tích chọn số luồng: **2 Luồng**, **3 Luồng** hoặc **4 Luồng**.
2. Nhấn nút **`🚀 Chạy X Luồng (Booking & Agoda)`**.
3. Các luồng Playwright bật lên song song với bộ Profile cách ly (`browser_profile_pX`).
4. Hệ thống thực thi thử cào theo mô hình Waterfall 3 lớp: **Booking.com $\rightarrow$ Agoda.com $\rightarrow$ Traveloka.com**.
5. Bóc tách số sao, lọc bỏ trang danh sách thành phố chung, đối chiếu Tỉnh/Thành không dấu chuẩn xác.
6. Nối chuỗi nguồn vào trường `source` (`Facebook About: ... | Agoda: https://...`).
7. Thẻ thống kê thứ 5 **"Khách sạn Có Sao"** và 5 nhãn hạng sao (`1★` đến `5★`) ở góc trên màn hình tự động nhảy số Real-Time qua Ajax Polling (3 giây/lần).
8. Ngay khi cào xong, hệ thống tự động dọn dẹp sạch sẽ 100% các thư mục cache đệm tạm (`browser_profile*`).

---

### 📊 User Flow 7: Khám Phá & Xuất Dữ Liệu (Tab Data Explorer)
```
[Chọn Tab 'Khám Phá Dữ Liệu'] ➔ [Tìm Kiếm / Lọc Theo Category] ➔ [Duyệt Bảng Phân Trang]
                                                                        │
[Tải Xuất File Data] ◄─ [Chọn Nút: Xuất CSV / Excel / Tải JSON] ◄───────┘
```
1. Người dùng chọn tab **"Khám phá & Xuất Dữ liệu"** (`Tab Data`).
2. Gõ từ khóa tìm kiếm trên thanh tìm kiếm hoặc lọc theo ngành nghề Category.
3. Duyệt danh sách trực quan qua bảng phân trang 50 bản ghi/trang.
4. Bấm nút **Xuất CSV**, **Xuất Excel**, hoặc **Tải file JSON** để tải tệp kết quả về máy tính.

---

## 📊 GIAO DIỆN QUẢN LÝ WEB DASHBOARD

1. **Hàng 5 Thẻ Thống Kê Tổng Quan (Top Dashboard Grid):**
   - **Tổng số Địa điểm:** Số lượng bản ghi hiện có trong tệp JSON.
   - **Đã có Email:** Số lượng cơ sở đã thu thập được Email.
   - **Đã có Category:** Số lượng bản ghi có phân loại ngành nghề.
   - **Số Điện Thoại:** Số lượng bản ghi có SĐT liên hệ.
   - **Khách sạn Có Sao:** Tổng số địa điểm có số sao kèm 5 nhãn pill phân loại chi tiết: `1★: X`, `2★: Y`, `3★: Z`, `4★: W`, `5★: V`.
2. **Thanh Tiến Trình Real-Time & Cập Nhật Tự Động Qua Ajax:**
   - **Tỉ lệ quét thực tế:** Hiển thị `SỐ BẢN GHI ĐÃ QUÉT / TỔNG BẢN GHI FILE OUTPUT` (Ví dụ: `85 / 200 bản ghi đã quét (42.5%)`).
   - **Ajax Polling 3 giây/lần:** Các con số thống kê và thanh tiến trình tự động nhảy Real-Time mà người dùng **không cần bấm F5 làm mới trang**.
3. **Tab Cấu Hình Hệ Thống (Config Manager):**
   - Quản lý danh sách từ khóa tìm kiếm dán hàng ngàn dòng.
   - Chọn Tỉnh/Thành phố mục tiêu (34 Tỉnh/Thành).
   - Đặt tên file xuất dữ liệu (`hotels.json`).
4. **Tab Khám Phá & Xuất Dữ Liệu (Data Explorer):**
   - Bảng tra cứu dữ liệu phân trang, hỗ trợ tìm kiếm từ khóa và lọc theo ngành nghề.
   - Xuất dữ liệu sang file CSV / Excel / JSON.

---

## ⚡ HƯỚNG DẪN CÀI ĐẶT & VẬN HÀNH

### 1. Yêu cầu môi trường
- Python 3.10 trở lên.
- Trình duyệt Google Chrome hoặc Microsoft Edge.

### 2. Cài đặt các thư viện phụ thuộc
Mở CMD hoặc PowerShell tại thư mục dự án và chạy:

```powershell
# Tạo và kích hoạt môi trường ảo Python
python -m venv .venv
.\.venv\Scripts\activate

# Cài đặt các thư viện Python cần thiết
pip install fastapi uvicorn playwright selenium

# Tải trình duyệt Chromium cho Playwright
playwright install chromium
```

### 3. Khởi chạy hệ thống
Chạy lệnh khởi động Uvicorn Server:

```powershell
python server.py
```

Mở trình duyệt web và truy cập địa chỉ:
👉 **`http://localhost:8000`**

---

## 📄 CẤU TRÚC DỮ LIỆU TIÊU CHUẨN (JSON OUTPUT)

Mỗi bản ghi được lưu trữ theo cấu trúc chuẩn 12+ trường dữ liệu:

```json
[
  {
    "stt": 1,
    "title": "CT Morning Hotel",
    "email": "info@ctmorning.com",
    "phone": "+84971714174",
    "address": "81 Lý Hồng Thanh, Cái Khế, Cần Thơ, Vietnam",
    "url": "https://www.google.com/maps/place/CT+Morning+Hotel/...",
    "totalScore": "4.7",
    "website": "https://www.ctmorning.com/",
    "facebook": "https://www.facebook.com/ctmorninghotel/",
    "categoryName": "2-star hotel",
    "source": "Facebook About: https://www.facebook.com/ctmorninghotel/about | Agoda: https://www.agoda.com/vi-vn/ct-morning-hotel/hotel/can-tho-vn.html",
    "isFlag": true,
    "stars": "2-star hotel"
  }
]
```

---

*Hệ thống được phát triển và tối ưu bởi **Antigravity AI Team**.*
