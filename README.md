# Tháp ADN – AgriBot

Ứng dụng web giới thiệu và mô phỏng hệ thống trồng cây tháp ADN. Dự án kết hợp giao diện giám sát, mô hình vận hành bơm và van, lịch tưới, lưu lịch sử hoạt động, cùng chatbot hỗ trợ hỏi đáp về chăm sóc cây. Firmware ESP32 và trang điều khiển bơm thật qua MQTT được cung cấp riêng.

> **Lưu ý:** Bảng điều khiển `/dashboard` chạy ở chế độ mô phỏng (DEMO MODE); các số liệu và thông số sinh trưởng chưa được hiệu chỉnh bằng thực nghiệm. Trang `/pump` điều khiển phần cứng thật khi ESP32 và MQTT được cấu hình đầy đủ.

## Tính năng

- Trang AgriBot giới thiệu hệ thống và cung cấp chatbot AI (Gemini) khi có API key.
- Dashboard theo dõi trạng thái bơm, van, mực nước, lưu lượng và các chỉ số mô phỏng.
- Điều khiển bơm, van A/B, chế độ thủ công hoặc hẹn giờ; thêm, sửa và xóa lịch tưới.
- Ghi sự kiện và dữ liệu theo thời gian vào SQLite; xem lịch sử, biểu đồ và tải CSV.
- Trang `/pump` gửi lệnh tới bơm thật qua MQTT WebSocket TLS.
- Firmware ESP32 điều khiển relay, hỗ trợ cấu hình Wi-Fi và có giới hạn thời gian chạy cùng cơ chế tắt an toàn khi mất kết nối.

## Công nghệ

- Python, Flask và SQLite
- HTML, CSS, JavaScript
- Google Gemini API cho chatbot
- ESP32 Arduino, MQTT/TLS và EMQX cho bơm thật

## Yêu cầu

- Python 3.13 (phiên bản đã được dùng để chạy và kiểm thử dự án)
- Pip
- API key Gemini nếu muốn bật chatbot
- Cấu hình broker MQTT và phần cứng ESP32 nếu muốn điều khiển bơm thật

## Cài đặt và chạy

```bash
python -m venv .venv
```

Kích hoạt môi trường ảo, sau đó cài thư viện và chạy ứng dụng:

```bash
python -m pip install -r requirements.txt
python app.py
```

Mở các địa chỉ sau trong trình duyệt:

- `http://127.0.0.1:5000/` — AgriBot
- `http://127.0.0.1:5000/dashboard` — giám sát và mô phỏng
- `http://127.0.0.1:5000/pump` — điều khiển bơm thật qua MQTT

Ứng dụng chạy được mà không cần Gemini key hoặc MQTT; những tính năng tương ứng sẽ không hoạt động cho đến khi cấu hình.

## Cấu hình môi trường

Tạo tệp `.env` tại thư mục gốc dựa trên các tên biến dưới đây. Không đưa thông tin bí mật lên Git.

| Biến | Mục đích |
|---|---|
| `GEMINI_API_KEY` | Bật chatbot Gemini; bỏ trống thì chatbot tắt |
| `GEMINI_MODEL` | Tùy chọn tên model Gemini; mặc định `gemini-2.5-flash-lite` |
| `ADN_DB_PATH` | Tùy chọn đường dẫn tệp SQLite; mặc định là `database/tru_adn.db` (trên Vercel dùng `/tmp/tru_adn.db`) |
| `MQTT_WS_URL` | URL WebSocket TLS của broker MQTT |
| `MQTT_WEB_USER` | Tài khoản MQTT dùng từ trình duyệt |
| `MQTT_WEB_PASS` | Mật khẩu tài khoản MQTT dùng từ trình duyệt |

Ví dụ cấu hình MQTT và hướng dẫn broker có trong [PUMP_README.md](PUMP_README.md). Trên Vercel, đặt các biến môi trường trong phần cài đặt dự án và triển khai lại sau khi thay đổi. Lưu ý dữ liệu ghi tại `/tmp` trên Vercel là tạm thời.

## Firmware bơm thật

Firmware ở `firmware/pump_mqtt/pump_mqtt.ino`. Mở bằng Arduino IDE, cài thư viện PubSubClient và WiFiManager, rồi tạo `firmware/pump_mqtt/secrets.h` từ tệp mẫu nếu có để điền thông tin MQTT cho ESP32. Tệp bí mật không được chia sẻ hoặc commit.

Firmware điều khiển relay GPIO 23; kiểm tra relay thực tế tương thích mức kích hoạt trước khi sử dụng. Bơm tự tắt sau 5 phút chạy liên tục và khi mất Wi-Fi/MQTT quá 30 giây. Xem [PUMP_README.md](PUMP_README.md) để biết cách cấu hình Wi-Fi, topic MQTT và chạy trang điều khiển.

## API mô phỏng

Các endpoint chính gồm:

| Phương thức | Đường dẫn | Chức năng |
|---|---|---|
| `GET` | `/api/state` | Lấy trạng thái mô phỏng hiện tại |
| `POST` | `/api/pump` | Bật hoặc tắt bơm mô phỏng |
| `POST` | `/api/valve` | Mở hoặc đóng van A/B |
| `POST` | `/api/mode` | Chọn chế độ thủ công hoặc hẹn giờ |
| `GET`, `POST` | `/api/schedules` | Xem hoặc thêm lịch tưới |
| `GET` | `/api/history` | Lấy dữ liệu lịch sử |
| `GET` | `/api/events` | Lấy nhật ký sự kiện |
| `GET` | `/api/export.csv` | Tải dữ liệu CSV |
| `POST` | `/api/reset` | Đặt lại mô phỏng |

## Cấu trúc dự án

```text
├── app.py                  # Ứng dụng Flask và các API
├── simulation.py           # Mô hình mô phỏng trụ ADN
├── database.py             # Lưu lịch sử và sự kiện SQLite
├── firmware/pump_mqtt/     # Firmware ESP32 cho bơm thật
├── templates/              # Các trang giao diện
├── static/                 # CSS, JavaScript, hình ảnh
├── tests/                  # Bộ kiểm thử dự án
├── PUMP_README.md           # Hướng dẫn chi tiết MQTT và firmware
└── requirements.txt        # Thư viện Python
```

## Triển khai

Ứng dụng có thể chạy trên máy cá nhân hoặc nền tảng hỗ trợ Python. Trên Linux, có thể dùng Gunicorn với một worker vì mô phỏng lưu trạng thái trong bộ nhớ:

```bash
gunicorn app:app --workers 1 --threads 4
```

## Giới hạn mô hình

Độ rỗng LECA, độ ẩm bão hòa của giá thể, tốc độ mao dẫn, lượng nước cây sử dụng và lưu lượng bơm trong mô phỏng là các giả định, chưa được hiệu chỉnh bằng thực nghiệm. Không dùng kết quả mô phỏng làm thông số vận hành thực tế nếu chưa kiểm chứng hệ thống.
