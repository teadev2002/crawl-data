# HƯỚNG DẪN SỬ DỤNG NHANH CÔNG CỤ CÀO GOOGLE MAPS & EMAIL

---

## 🛠️ Bước 1: Thiết lập (Chỉ làm 1 lần duy nhất)
Click đúp chuột vào file **`setup.bat`** để chương trình tự động cài đặt môi trường và trình duyệt.

---

## ⚙️ Bước 2: Chỉnh sửa Cấu hình (Mở file `config.json`)
Mở file **`config.json`** bằng Notepad để chỉnh sửa thông tin theo ý bạn:

* **`search_queries`**: Nhập danh sách từ khóa khu vực cần cào (ví dụ: `["khách sạn Tây Ninh", "khách sạn Hòa Thành"]`).
* **`output_file`**: Tên file JSON lưu kết quả đầu ra (ví dụ: `hotels-TayNinh.json`). Cả 2 tool sẽ tự động đọc/ghi chung vào file này.
* **`max_results`**: Số lượng kết quả tối đa muốn cào.
* **`USE_MY_CHROME_PROFILE`**: Đổi thành `true` nếu muốn dùng Chrome cá nhân của bạn (Lưu ý: Phải tắt hẳn trình duyệt Chrome trước khi chạy).

---

## 🚀 Bước 3: Khởi chạy

### 1. Cào địa điểm mới (Chạy file `run.bat`)
Click đúp file **`run.bat`** để bắt đầu cào thông tin địa điểm (Tên, SĐT, Địa chỉ, Website, Điểm số) theo từ khóa trong `config.json`.

### 2. Cào bổ sung Email (Có 2 chế độ chọn)

* **Chế độ 1 luồng truyền thống (Chạy file `run_email_harvester.bat`):**
  Click đúp file **`run_email_harvester.bat`** để chạy tuần tự từ trên xuống dưới.
  
* **Chế độ 2 luồng song song - Tăng tốc gấp đôi (Khuyên dùng):**
  Click đúp đồng thời **cả 2 file** sau đây:
  1. **`run_email_harvester_top.bat`** (Quét từ đầu danh sách xuống)
  2. **`run_email_harvester_bottom.bat`** (Quét từ cuối danh sách lên)
  
  *(Hai màn hình đen CMD sẽ hiện ra chạy song song. Hai luồng sẽ tự động điều phối để không cào trùng nhau, khi gặp nhau ở giữa danh sách sẽ tự dừng lại và tự động gộp kết quả gỡ bỏ file tạm).*
