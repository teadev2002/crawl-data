# Kế Hoạch Thiết Kế Nâng Cấp: Cào SĐT Từ Gian Hàng Trip.com Thông Qua Google Maps Place URL

Nâng cấp **Bước 2** trong công cụ **Phone Harvester (`phone_harvester.py`)**: Sử dụng trực tiếp đường dẫn Google Maps Place URL (`url`) có sẵn của bản ghi, tự động cuộn tìm mục **"Kết quả bổ sung trên web"** (`h2.QmVJeb`), truy cập đúng liên kết **Trip.com** (`span.QVR4f`), và trích xuất số điện thoại chính xác 100% từ class chuyên dụng `.hotelContact_descriptionInfo-tel__ti6FG` / `.hotelContact_real-tel-text__3lcAp`.

---

## 🔍 QUY TRÌNH BÓC TÁCH SĐT TỪ GOOGLE MAPS ➔ TRIP.COM

```
            [ĐỌC TRƯỜNG `url` GOOGLE MAPS CÓ SẴN TRONG RECORD]
            (VD: https://www.google.com/maps/place/T-Maison+Boutique+Villa...)
                                   │
                                   ▼
             [TRUY CẬP GOOGLE MAPS PLACE URL BẰNG PLAYWRIGHT]
                                   │
                                   ▼
        [ĐỊNH VỊ KHU VỰC: <h2 class="QmVJeb fontTitleSmall">Kết quả bổ sung trên web</h2>]
                                   │
                                   ▼
           [CLICK CHÍNH XÁC VÀO THẺ: <span class="QVR4f fontTitleSmall">Trip.com</span>]
           (Tự động mở Tab mới hoặc chuyển hướng đến trang chi tiết Trip.com)
                                   │
                                   ▼
        [TRUY XUẤT TRANG CHI TIẾT CƠ SỞ TRÊN TRIP.COM]
        Định vị class: `.hotelContact_descriptionInfo-tel__ti6FG`
                   và `.hotelContact_real-tel-text__3lcAp`
        Ví dụ text: "+84-976885077"
                                   │
                                   ▼
        [LỌC VÀ CHUẨN HÓA SỐ ĐIỆN THOẠI VIỆT NAM (VD: 0976885077)]
                                   │
                                   ▼
        [CẬP NHẬT TRƯỜNG PHONE VÀ SOURCE: `phone_trip: https://www.trip.com/...`]
```

---

## Các thay đổi cụ thể trong `phone_harvester.py`

### [MODIFY] [phone_harvester.py](file:///D:/WorkStation/python/phone_harvester.py)

1. **Bổ Sung Hàm `crawl_trip_via_google_maps(page, maps_url)`:**
   - Truy cập `maps_url` (đường dẫn Google Maps place).
   - Chờ phần tử `h2.QmVJeb:has-text("Kết quả bổ sung trên web")` hoặc `h2:has-text("Kết quả bổ sung trên web")`.
   - Tìm thẻ liên kết Trip.com:
     - Biểu thức Selector: `a:has(span.QVR4f:has-text("Trip.com"))` hoặc `a[href*="trip.com"]` trong vùng *Kết quả bổ sung trên web*.
   - Bấm click hoặc lấy `href` của Trip.com:
     - Nếu bấm click mở Tab mới (`popup` page): Tự động lắng nghe sự kiện `expect_page()` để lấy trang tab mới của Trip.com.
   - Trích xuất SĐT trên trang Trip.com:
     ```javascript
     () => {
         const telEl = document.querySelector('.hotelContact_real-tel-text__3lcAp, .hotelContact_descriptionInfo-tel__ti6FG');
         return telEl ? (telEl.innerText || telEl.textContent || '') : '';
     }
     ```
   - Trích xuất và chuẩn hóa SĐT ➔ Trả về `(phone_found, "phone_trip: <Trip_URL>")`.

2. **Nâng Cấp Thứ Tự Quét Trong `harvest_phones`:**
   - **Ưu tiên 1:** Quét qua Facebook / Website chính nếu có.
   - **Ưu tiên 2 (MỚI):** Đọc `url` Google Maps có sẵn ➔ Chạy `crawl_trip_via_google_maps`.
   - **Ưu tiên 3:** Tìm kiếm Facebook qua Search Engines (Google/Bing/DDG).
   - **Ưu tiên 4:** Tìm kiếm trực tiếp Google AI Overview (`div.n6owBd.awi2gc`).

---

## Verification Plan

### Manual Verification
1. Mở Web Dashboard `http://localhost:8000`.
2. Chạy **🚀 Quét & Bổ Sung SĐT (2 Luồng)** với dữ liệu `hotels.json` chứa các URL Google Maps.
3. Quan sát Console Log:
   - Log báo: `[✓] Đã truy cập Trip.com từ Google Maps 'Kết quả bổ sung trên web' -> Tìm thấy SĐT: '0976885077'`.
   - Kiểm tra file `hotels.json`: Trường `phone` được cập nhật và trường `source` ghi vết ` | phone_trip: https://www.trip.com/...`.
