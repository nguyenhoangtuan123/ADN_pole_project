# Máy bơm thật qua MQTT

## Luồng hoạt động

Trình duyệt tại `/pump` kết nối WebSocket TLS trực tiếp tới EMQX để gửi lệnh và nhận trạng thái. ESP32 kết nối broker bằng MQTT/TLS, điều khiển relay GPIO 23. Flask chỉ render trang và chuyển cấu hình từ biến môi trường; tính năng này độc lập với mô phỏng.

## Topic

| Topic | Hướng | Payload | QoS/retain |
|---|---|---|---|
| `adn/pump/cmd` | Web → ESP32 | `ON` / `OFF` | QoS 1, không retain |
| `adn/pump/status` | ESP32 → Web | `ON` / `OFF` | QoS 1, retain; gửi khi đổi trạng thái và mỗi 10 giây |
| `adn/pump/online` | ESP32 → Web | `online` / `offline` | retain; Last Will là `offline` |

## Nạp firmware

1. Trong Arduino IDE, chọn bo ESP32 phù hợp và cài thư viện **PubSubClient** (Nick O'Leary) và **WiFiManager** (tzapu). `WiFi.h` và `WiFiClientSecure.h` đi cùng ESP32 Arduino core.
2. Tạo `secrets.h` từ `firmware/pump_mqtt/secrets.h.example`, chỉ điền thông tin MQTT của user ESP32; không đưa file bí mật lên Git. **WiFi không nằm trong file này.**
3. Mở `firmware/pump_mqtt/pump_mqtt.ino`, chọn cổng/bo rồi nạp. Bơm khởi động ở trạng thái tắt. Bản thi dùng `setInsecure()`; triển khai thực tế nên xác minh chứng thư bằng `setCACert()`.

### Cấu hình WiFi bằng điện thoại

- Khi chưa có WiFi đã lưu (hoặc không kết nối được), ESP32 phát WiFi **`ADN-Pump-Setup`**. Kết nối bằng điện thoại, trang cấu hình tự mở (nếu không, vào `192.168.4.1`), chọn WiFi và nhập mật khẩu. ESP32 lưu lại và tự kết nối các lần sau.
- Đổi nhà/nơi thi: **giữ nút BOOT (GPIO 0) 3 giây** để xóa WiFi đã lưu và mở lại trang cấu hình. Mất WiFi hơn 2 phút thì ESP32 cũng tự mở lại trang này.
- Trang cấu hình mở tối đa 3 phút rồi dừng; trong lúc này bơm luôn ở trạng thái tắt.
- Khi đi thi, nếu mạng nơi thi bắt đăng nhập qua trang web, hãy phát hotspot từ điện thoại và cấu hình ESP32 vào hotspot đó.

Firmware giới hạn thời gian chạy 5 phút và tắt bơm nếu WiFi/MQTT mất quá 30 giây. Cần kiểm tra relay thực tế tương thích mức kích hoạt HIGH trên GPIO 23.

## Chạy thử trên localhost

1. Cài Python theo phiên bản dự án hỗ trợ, mở terminal tại thư mục dự án và cài dependencies: `python -m pip install -r requirements.txt`.
2. Tạo `.env` từ `.env.example`, rồi điền `MQTT_WS_URL`, `MQTT_WEB_USER`, `MQTT_WEB_PASS` cùng các biến Gemini nếu cần chatbot. Không chia sẻ `.env` hoặc đưa lên Git.
3. Khởi động Flask: `python app.py`. Mở `http://127.0.0.1:5000/pump` để vào tab máy bơm thật; trang dashboard mô phỏng vẫn ở `http://127.0.0.1:5000/dashboard`.
4. Máy tính cần truy cập được broker qua WebSocket TLS. Nếu chưa cấu hình MQTT, trang vẫn mở được và báo “Chưa cấu hình MQTT”, nhưng không thể điều khiển bơm.

## Cấu hình Vercel

Trong Project Settings → Environment Variables, đặt `MQTT_WS_URL`, `MQTT_WEB_USER`, `MQTT_WEB_PASS`. URL WebSocket là `wss://w1130619.ala.asia-southeast1.emqxsl.com:8084/mqtt`; web chỉ cần quyền client phù hợp với ACL bên dưới. Sau khi đổi biến, triển khai lại ứng dụng. `.env.example` liệt kê tên biến môi trường dùng trong dự án; không dùng thông tin thật trong tệp này.

## ACL EMQX

Tạo user web chỉ được subscribe `adn/pump/status` và `adn/pump/online`, publish `adn/pump/cmd`. User ESP32 chỉ được subscribe `adn/pump/cmd`, publish `adn/pump/status` và `adn/pump/online`.

Để thử thủ công, mở EMQX Dashboard → **Diagnose → WebSocket Client**, kết nối vào WebSocket endpoint, đăng nhập bằng user phù hợp rồi subscribe/publish các topic ở bảng trên. Dùng payload `ON`/`OFF` cho lệnh và quan sát status/online.
