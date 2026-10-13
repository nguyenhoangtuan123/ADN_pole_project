import os
import threading
import time

from flask import Flask, Response, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

from database import Recorder
from simulation import Simulation

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("ADN_DB_PATH", os.path.join(BASE_DIR, "database", "tru_adn.db"))

app = Flask(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Không có API key thì chatbot tắt, phần mô phỏng bơm vẫn chạy bình thường.
client = genai.Client(api_key=API_KEY) if API_KEY else None
if client is None:
    print("Cảnh báo: chưa có GEMINI_API_KEY trong .env, chatbot sẽ không hoạt động.")

# ---------------------------------------------------------------------------
# Mô phỏng Trụ ADN (DEMO MODE)
# ---------------------------------------------------------------------------
sim = Simulation()
recorder = Recorder(DB_PATH)
recorder.attach(sim)
TICK_REAL_S = 0.5


def simulation_loop():
    last = time.monotonic()
    while True:
        time.sleep(TICK_REAL_S)
        now = time.monotonic()
        real_dt = now - last
        last = now
        sim.step(real_dt * sim.cfg["speed"])
        try:
            recorder.tick(sim)
        except Exception as error:  # lỗi ghi dữ liệu không được làm dừng mô phỏng
            print("Lỗi ghi cơ sở dữ liệu:", repr(error))


def start_simulation_thread():
    threading.Thread(target=simulation_loop, daemon=True).start()


def api_result(result):
    ok, message = result
    return jsonify({"ok": ok, "message": message, "state": sim.snapshot()}), (200 if ok else 409)


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.get("/api/state")
def api_state():
    return jsonify(sim.snapshot())


@app.post("/api/pump")
def api_pump():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("on", "off"):
        return jsonify({"ok": False, "message": "action phải là 'on' hoặc 'off'."}), 400
    return api_result(sim.command_pump(action == "on", source="dashboard"))


@app.post("/api/valve")
def api_valve():
    data = request.get_json(silent=True) or {}
    strand, is_open = data.get("strand"), data.get("open")
    if strand not in ("A", "B") or not isinstance(is_open, bool):
        return jsonify({"ok": False, "message": "Cần strand = 'A'|'B' và open = true/false."}), 400
    return api_result(sim.set_valve(strand, is_open))


@app.post("/api/mode")
def api_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode")
    if mode not in ("manual", "timer"):
        return jsonify({"ok": False, "message": "mode phải là 'manual' hoặc 'timer'."}), 400
    return api_result(sim.set_mode(mode))


@app.route("/api/schedules", methods=["GET", "POST"])
def api_schedules():
    if request.method == "GET":
        return jsonify(sim.snapshot()["schedules"])
    data = request.get_json(silent=True) or {}
    return api_result(sim.add_schedule(data.get("start"), data.get("duration_s")))


@app.delete("/api/schedules/<int:sched_id>")
def api_schedule_delete(sched_id):
    return api_result(sim.delete_schedule(sched_id))


@app.post("/api/schedules/<int:sched_id>")
def api_schedule_update(sched_id):
    data = request.get_json(silent=True) or {}
    return api_result(sim.set_schedule_enabled(sched_id, data.get("enabled")))


@app.post("/api/estop")
def api_estop():
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get("engaged"), bool):
        return jsonify({"ok": False, "message": "engaged phải là true/false."}), 400
    return api_result(sim.set_estop(data["engaged"]))


@app.post("/api/refill")
def api_refill():
    data = request.get_json(silent=True) or {}
    return api_result(sim.refill(data.get("liters")))


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify(sim.snapshot()["config"])
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "message": "Body phải là JSON object."}), 400
    ok, message = sim.set_config(data)
    return jsonify({"ok": ok, "message": message, "state": sim.snapshot()}), (200 if ok else 400)


@app.get("/api/history")
def api_history():
    window_s = request.args.get("window_s", type=float)
    limit = request.args.get("limit", default=400, type=int)
    data = recorder.history(window_s=window_s, limit=limit)
    data["clock_start_min"] = sim.cfg["clock_start_min"]
    data["data_source"] = "SIMULATION"
    return jsonify(data)


@app.get("/api/events")
def api_events():
    return jsonify(recorder.events(limit=request.args.get("limit", default=200, type=int)))


@app.get("/api/export.csv")
def api_export_csv():
    all_runs = request.args.get("run") == "all"
    return Response(
        recorder.export_csv(all_runs=all_runs),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=tru_adn_mo_phong.csv"},
    )


@app.post("/api/reset")
def api_reset():
    sim.reset()
    return jsonify({"ok": True, "message": "Đã đặt lại mô phỏng.", "state": sim.snapshot()})


@app.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}

    message = data.get("message", "")
    history = data.get("history", [])

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Vui lòng nhập câu hỏi."}), 400

    if len(message) > 4000:
        return jsonify({"error": "Câu hỏi quá dài."}), 400

    if not isinstance(history, list):
        return jsonify({"error": "Lịch sử không hợp lệ."}), 400

    if client is None:
        return jsonify({"error": "Chưa cấu hình GEMINI_API_KEY nên chatbot đang tắt."}), 503

    contents = []

    # Chỉ lấy 20 tin nhắn gần nhất
    for item in history[-20:]:
        if not isinstance(item, dict):
            continue

        role = item.get("role")
        text = item.get("text")

        if role not in ("user", "model"):
            continue

        if not isinstance(text, str) or not text.strip():
            continue

        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=text[:4000])]
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=message)]
        )
    )

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=(
                """
                Bạn là AgriBot, một trợ lý AI chuyên tư vấn về
                nông nghiệp, cây trồng và kỹ thuật canh tác tại Việt Nam.

                VAI TRÒ:
                - Cung cấp kiến thức về các loại cây trồng.
                - Hướng dẫn trồng, chăm sóc và thu hoạch cây.
                - Hỗ trợ nhận biết các vấn đề về sâu bệnh.
                - Tư vấn tưới nước, dinh dưỡng và phân bón.
                - Giải thích kỹ thuật canh tác dễ hiểu cho nông dân.

                NGUYÊN TẮC TRẢ LỜI:

                1. Trả lời bằng tiếng Việt, rõ ràng, dễ hiểu.
                2. Ưu tiên hướng dẫn thực tế, phù hợp điều kiện Việt Nam.
                3. Không tự bịa thông tin khi thiếu dữ liệu.
                4. Nếu chưa biết loại cây, độ tuổi cây hoặc triệu chứng,
                hãy hỏi thêm thông tin trước khi tư vấn cụ thể.
                5. Khi đánh giá sâu bệnh, hãy nêu các nguyên nhân
                có thể xảy ra, không khẳng định khi chưa đủ bằng chứng.
                6. Hướng dẫn cách kiểm tra để phân biệt các nguyên nhân.
                7. Ưu tiên biện pháp phòng ngừa, canh tác an toàn và
                quản lý dịch hại tổng hợp (IPM).
                8. Không đề xuất tùy tiện tên thuốc, liều lượng hoặc
                cách pha thuốc bảo vệ thực vật.
                9. Nếu đề cập thuốc bảo vệ thực vật, cần lưu ý kiểm tra
                sản phẩm được phép sử dụng tại Việt Nam, nhãn thuốc,
                đối tượng cây trồng, thời gian cách ly và hướng dẫn an toàn.
                10. Nếu vấn đề nghiêm trọng hoặc không thể xác định,
                    khuyến nghị liên hệ cán bộ bảo vệ thực vật tại địa phương.

                CÁCH TRÌNH BÀY:
                - Giải thích vấn đề.
                - Nêu nguyên nhân có thể xảy ra.
                - Đưa ra các bước xử lý phù hợp.
                - Hướng dẫn phòng ngừa.
                - Hỏi thêm thông tin nếu cần.

                MỤC TIÊU:
                Giúp người dùng chăm sóc cây trồng hiệu quả,
                an toàn, tiết kiệm chi phí và bảo vệ môi trường.
                """
                ),
                temperature=0.3
            )
        )

        answer = response.text or "Không có nội dung trả lời."
        return jsonify({"reply": answer})

    except Exception as error:
        print("Gemini API error:", repr(error))
        return jsonify({
            "error": "Không thể gọi Gemini API. Kiểm tra API key, model và quota."
        }), 502


def get_run_config(environ):
    """Cấu hình chạy `python app.py`.

    - Trên máy bạn (không có biến PORT): chỉ nghe 127.0.0.1:5000 và bật debug để tự nạp lại code.
    - Trên host như Render/Railway (host đặt biến PORT): nghe 0.0.0.0:$PORT và TẮT debug,
      vì trình gỡ lỗi Werkzeug trên máy chủ công khai là lỗ hổng bảo mật.
    Đặt FLASK_DEBUG=1 hoặc 0 để ép bật/tắt debug.
    """
    on_host = "PORT" in environ
    try:
        port = int(environ.get("PORT", "5000"))
    except ValueError:
        port = 5000
    debug = environ.get("FLASK_DEBUG", "0" if on_host else "1") == "1"
    return {"host": "0.0.0.0" if on_host else "127.0.0.1", "port": port, "debug": debug}


if __name__ == "__main__":
    cfg = get_run_config(os.environ)
    # Debug bật thì Flask khởi động 2 tiến trình; chỉ chạy luồng mô phỏng ở tiến trình con.
    # Debug tắt thì chỉ có một tiến trình nên chạy luồng ngay.
    if not cfg["debug"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_simulation_thread()
    app.run(host=cfg["host"], port=cfg["port"], debug=cfg["debug"])
else:
    # Được nạp bởi máy chủ WSGI (gunicorn): chạy luồng mô phỏng, nhớ dùng đúng 1 worker.
    start_simulation_thread()
