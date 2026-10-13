"""Mô hình mô phỏng dòng nước tuần hoàn của Trụ ADN Ø600 (DEMO MODE).

Theo bộ bản vẽ "TRỤ ADN Ø600 – BẢN THIẾT KẾ" (ADN-600-01…16, 16 tờ):
- 2 sợi xoắn A và B lệch nhau 180°, mỗi sợi 12 bậc (A1–A12, B1–B12), tổng 24 bậc.
- Sàn bậc k: Z = 385 + 75·(k−1) mm; bậc 12 cao nhất, bậc 1 thấp nhất.
- Bơm 12V/USB (100–200 L/h) trong bể → ống mềm trong trụ → chữ T ở Z1440 → 2 nhánh có
  van riêng (Van A, Van B) → đầu phễu bậc 12 của mỗi sợi.
- Trong mỗi bậc, nước nằm ở lớp LECA (sâu 18 mm). Phần nước vượt ngưỡng +18 mm chảy qua
  "cửa nước" ống Ø16 xuống LECA bậc dưới (bậc k → bậc k−1). Bậc 1 xả qua ống hồi Ø16 về bể.
  Đất hút nước từ LECA lên (mao dẫn qua vải địa); cây hút nước từ đất.
- Hộc giun (2 ngăn) độc lập, không trao đổi nước với các bậc nên không có trong mô hình nước.

Toàn bộ số liệu hình học lấy từ bản vẽ. Các hệ số vật lý (độ rỗng LECA, độ ẩm bão hòa của
giá thể, tốc độ mao dẫn, lượng cây dùng nước, lưu lượng thực tế của bơm…) là GIẢ ĐỊNH, chưa
hiệu chỉnh bằng thực nghiệm; được đánh dấu ASSUMPTION bên dưới.

Quy ước: lít (L), giây mô phỏng (s). Độ ẩm bậc (%) = nước trong giá thể / thể tích giá thể
(ước tính của mô hình, không phải số đo cảm biến). Nước không tự sinh ra:
bể + lớp LECA + giá thể + tổng nước mất = nước ban đầu + nước bổ sung.
"""
import math
import re
import threading
from collections import deque

STEPS = 12                # số bậc mỗi sợi
STRANDS = ("A", "B")
DAY_S = 86400

# ---------------------------------------------------------------- hình học (theo bản vẽ)
STEP_AREA_M2 = 0.486 / 24          # tờ 15: diện tích 0.486 m² cho 24 bậc
SUBSTRATE_DEPTH_M = 0.110          # tờ 06: giá thể 110 mm
LECA_DEPTH_M = 0.030               # tờ 06: LECA 30 mm
LECA_WATER_DEPTH_M = 0.018         # tờ 06/07: nước sâu 18 mm, ngưỡng +18
TANK_AREA_M2 = math.pi * 0.30 ** 2  # tờ 11: bể Ø600 (chưa trừ trụ, thành, bơm)
TANK_NORMAL_L = 17.0               # tờ 11: mức thường 60 mm ≈ 17 L
TANK_MAX_L = 28.0                  # tờ 11: mức tối đa 100 mm ≈ 28 L (trước khi trừ thành bể, trụ, đế, bơm)

SUBSTRATE_L = STEP_AREA_M2 * SUBSTRATE_DEPTH_M * 1000.0   # ≈ 2.23 L giá thể mỗi bậc

# ---------------------------------------------------------------- giả định (ASSUMPTION)
LECA_POROSITY = 0.40        # ASSUMPTION: phần thể tích LECA chứa được nước
SOIL_SAT_FRAC = 0.60        # ASSUMPTION: độ ẩm thể tích bão hòa của giá thể
WICK_TARGET_FRAC = 0.45     # ASSUMPTION: độ ẩm thể tích mà mao dẫn kéo đất lên tới

LECA_THRESH_L = STEP_AREA_M2 * LECA_WATER_DEPTH_M * 1000.0 * LECA_POROSITY   # nước ở ngưỡng +18
LECA_MAX_L = STEP_AREA_M2 * LECA_DEPTH_M * 1000.0 * LECA_POROSITY            # LECA đầy (30 mm)
SOIL_SAT_L = SOIL_SAT_FRAC * SUBSTRATE_L
SOIL_TARGET_L = WICK_TARGET_FRAC * SUBSTRATE_L

# Cấu hình mặc định. Các khóa trong CONFIG_LIMITS chỉnh được lúc chạy.
DEFAULT_CONFIG = {
    "tank_initial_l": TANK_NORMAL_L,
    "soil_initial_frac": 0.35,       # ASSUMPTION: độ ẩm thể tích ban đầu của giá thể
    "pump_flow_lpm": 2.0,            # ASSUMPTION: 120 L/h (bản vẽ: bơm 100–200 L/h, Hmax ≥ 2 m, cần nâng ~1,4 m)
    "pump_power_w": 6.0,             # ASSUMPTION: bơm 12V cỡ nhỏ
    "min_tank_l": 4.0,               # ASSUMPTION: dưới mức này rọ hút bơm có thể hở
    "max_run_s": 600.0,              # giới hạn bơm liên tục (bản vẽ: 3–5 phút/lần)
    "door_max_lpm": 4.0,             # ASSUMPTION: lưu lượng tối đa qua ống cửa nước Ø16
    "wick_tau_s": 600.0,             # ASSUMPTION: hằng số thời gian mao dẫn LECA → giá thể
    "et_lph": 0.004,                 # ASSUMPTION: cây dùng nước + bay hơi mỗi bậc khi đất bão hòa (L/giờ)
    "tank_evap_lph": 0.002,          # ASSUMPTION: bể có nắp che kín
    "speed": 1.0,
    "clock_start_min": 360,          # giờ mô phỏng bắt đầu lúc 06:00
}

CONFIG_LIMITS = {
    "pump_flow_lpm": (0.5, 3.5),
    "pump_power_w": (1.0, 100.0),
    "min_tank_l": (0.0, 10.0),
    "max_run_s": (10.0, 3600.0),
    "door_max_lpm": (0.2, 10.0),
    "wick_tau_s": (30.0, 7200.0),
    "et_lph": (0.0, 0.05),
    "tank_evap_lph": (0.0, 0.5),
    "speed": (1.0, 600.0),
}

DEFAULT_SCHEDULES = [(6 * 60 + 30, 300.0), (17 * 60, 300.0)]  # 06:30 và 17:00, 5 phút (bản vẽ: 2–3 lần/ngày)
MAX_SCHEDULES = 8
MIN_SCHEDULE_S = 10.0
MAX_SUBSTEP_S = 1.0
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fmt_hhmm(minute_of_day):
    m = int(minute_of_day) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def step_info(strand, k):
    """Thông tin hình học của bậc (strand 'A'|'B', k = 1…12) theo tờ 14."""
    floor_z = 385 + 75 * (k - 1)
    start_deg = (0 if strand == "A" else 180) + 30 * (k - 1)
    return {
        "id": f"{strand}{k}",
        "strand": strand,
        "k": k,
        "angle": f"{start_deg}–{start_deg + 30}°",
        "floor_z": floor_z,
        "soil_z": floor_z + 140,
    }


class Simulation:
    def __init__(self, config=None):
        self._lock = threading.RLock()
        self.cfg = dict(DEFAULT_CONFIG)
        if config:
            self.cfg.update(config)
        self.events = deque(maxlen=100)
        self.run_id = 0          # tăng mỗi lần reset: mỗi lượt chạy là một chuỗi dữ liệu riêng
        self.on_event = None     # hook ghi nhật ký bền vững: on_event(run_id, entry)
        self.reset()

    # ------------------------------------------------------------------ trạng thái
    def reset(self):
        with self._lock:
            c = self.cfg
            self.run_id += 1
            self.time_s = 0.0
            self.tank_l = min(c["tank_initial_l"], TANK_MAX_L)
            # trạng thái mỗi sợi: danh sách theo chỉ số i = k−1 (i=0 là bậc 1, i=11 là bậc 12)
            self.soil_l = {s: [c["soil_initial_frac"] * SUBSTRATE_L] * STEPS for s in STRANDS}
            self.leca_l = {s: [0.5 * LECA_THRESH_L] * STEPS for s in STRANDS}
            for s in STRANDS:
                self.soil_l[s] = list(self.soil_l[s])
                self.leca_l[s] = list(self.leca_l[s])
            self.lost_l = {s: [0.0] * STEPS for s in STRANDS}
            self.flow_in_lpm = {s: [0.0] * STEPS for s in STRANDS}
            self.supply_lpm = {s: 0.0 for s in STRANDS}
            self.return_lpm = {s: 0.0 for s in STRANDS}
            self.valve_open = {s: True for s in STRANDS}
            self.tank_lost_l = 0.0
            self.initial_l = self._inventory()
            self.added_l = 0.0
            self.pumped_l = 0.0
            self.recovered_l = 0.0
            self.energy_wh = 0.0
            self.pump_on = False
            self.run_source = None       # "manual" | "timer" | None
            self.run_s = 0.0
            self.total_run_s = 0.0
            self.mode = "manual"
            self.estop = False
            self.suppress_key = None
            self.timer_key = None
            self.flow_pump_lpm = 0.0
            self.schedules = []
            self._next_sched_id = 1
            for start_min, dur in DEFAULT_SCHEDULES:
                self.schedules.append(
                    {"id": self._next_sched_id, "start_min": start_min, "duration_s": dur, "enabled": True}
                )
                self._next_sched_id += 1
            self.events.clear()
            self._log("info", "Khởi tạo mô phỏng (DEMO MODE, dữ liệu mô phỏng).")

    def _inventory(self):
        return self.tank_l + sum(sum(self.soil_l[s]) + sum(self.leca_l[s]) for s in STRANDS)

    def _log(self, level, msg):
        entry = {"t": round(self.time_s, 1), "level": level, "msg": msg}
        self.events.append(entry)
        if self.on_event:
            self.on_event(self.run_id, entry)

    def sample(self):
        """Bản ghi gọn để lưu vào cơ sở dữ liệu (không dựng toàn bộ snapshot)."""
        with self._lock:
            clk = self.clock()
            return {
                "run_id": self.run_id,
                "t": self.time_s,
                "day": clk["day"],
                "hhmm": clk["hhmm"],
                "pump_on": 1 if self.pump_on else 0,
                "mode": self.mode,
                "pump_flow_lpm": self.flow_pump_lpm,
                "return_lpm": sum(self.return_lpm.values()),
                "tank_l": self.tank_l,
                "tank_level_mm": self.tank_l / TANK_AREA_M2,
                "avg_vwc": self.avg_vwc(),
                "vwc_a": self.avg_vwc("A"),
                "vwc_b": self.avg_vwc("B"),
                "pumped_l": self.pumped_l,
                "recovered_l": self.recovered_l,
                "lost_l": self.total_lost_l(),
                "energy_wh": self.energy_wh,
            }

    # ------------------------------------------------------------------ đồng hồ & độ ẩm
    def _abs_s(self):
        return self.cfg["clock_start_min"] * 60 + self.time_s

    def clock(self):
        a = self._abs_s()
        return {"day": int(a // DAY_S) + 1, "hhmm": fmt_hhmm((a % DAY_S) / 60.0)}

    def vwc_pct(self, strand, i):
        return self.soil_l[strand][i] / SUBSTRATE_L * 100.0

    def avg_vwc(self, strand=None):
        strands = (strand,) if strand else STRANDS
        vals = [self.vwc_pct(s, i) for s in strands for i in range(STEPS)]
        return sum(vals) / len(vals)

    def n_valves_open(self):
        return sum(1 for s in STRANDS if self.valve_open[s])

    # ------------------------------------------------------------------ lệnh bơm / van / chế độ
    def command_pump(self, on, source="user"):
        """Trả về (ok, message). Lệnh BẬT chỉ hợp lệ ở chế độ thủ công."""
        with self._lock:
            if not on:
                if self.pump_on:
                    self._pump_off(f"Tắt bơm ({source}). Chạy {self.run_s:.0f}s.", "info")
                return True, "Đã tắt bơm."
            if self.estop:
                return False, "Đang dừng khẩn cấp. Hãy nhả dừng khẩn cấp trước."
            if self.mode != "manual":
                return False, "Đang ở chế độ hẹn giờ. Chuyển sang thủ công để bật bơm."
            if self.n_valves_open() == 0:
                return False, "Cả Van A và Van B đang đóng: bơm sẽ bị bí đầu ra. Hãy mở ít nhất một van."
            if self.tank_l <= self.cfg["min_tank_l"]:
                self._log("warn", "Từ chối bật bơm: bể quá thấp.")
                return False, "Bể quá thấp, không thể bật bơm. Hãy bổ sung nước."
            if not self.pump_on:
                self._pump_on("manual", f"Bật bơm ({source}).")
            return True, "Đã bật bơm."

    def _pump_on(self, source, msg):
        self.pump_on = True
        self.run_source = source
        self.run_s = 0.0
        self._log("info", msg)

    def _pump_off(self, msg, level):
        self.pump_on = False
        self.run_source = None
        self._log(level, msg)

    def set_valve(self, strand, is_open):
        with self._lock:
            if strand not in STRANDS:
                return False, "Van phải là 'A' hoặc 'B'."
            if not isinstance(is_open, bool):
                return False, "open phải là true/false."
            if self.valve_open[strand] != is_open:
                self.valve_open[strand] = is_open
                self._log("info", f"{'Mở' if is_open else 'Đóng'} Van {strand}.")
            return True, f"Van {strand} đã {'mở' if is_open else 'đóng'}."

    def set_mode(self, mode):
        with self._lock:
            if mode not in ("manual", "timer"):
                return False, "Chế độ không hợp lệ."
            if mode != self.mode:
                if self.pump_on:
                    self._pump_off("Tắt bơm do đổi chế độ.", "info")
                self.mode = mode
                self.suppress_key = None
                self._log("info", f"Chuyển chế độ: {'hẹn giờ' if mode == 'timer' else 'thủ công'}.")
            return True, "Đã đổi chế độ."

    def set_estop(self, engaged):
        with self._lock:
            engaged = bool(engaged)
            if engaged and not self.estop:
                self.estop = True
                if self.pump_on:
                    self._pump_off("DỪNG KHẨN CẤP: đã ngắt bơm.", "alarm")
                else:
                    self._log("alarm", "DỪNG KHẨN CẤP đã được kích hoạt.")
            elif not engaged and self.estop:
                self.estop = False
                self._log("info", "Đã nhả dừng khẩn cấp. Bơm vẫn TẮT.")
            return True, "Đã cập nhật dừng khẩn cấp."

    def refill(self, liters):
        with self._lock:
            if not _is_number(liters) or liters <= 0:
                return False, "Lượng nước bổ sung không hợp lệ."
            added = min(float(liters), TANK_MAX_L - self.tank_l)
            if added <= 0:
                return False, "Bể đã đầy (mức tối đa ≈ 28 L)."
            self.tank_l += added
            self.added_l += added
            self._log("info", f"Bổ sung {added:.1f} L vào bể.")
            return True, f"Đã bổ sung {added:.1f} L."

    # ------------------------------------------------------------------ cấu hình
    def set_config(self, updates):
        with self._lock:
            if not isinstance(updates, dict) or not updates:
                return False, "Không có cấu hình để cập nhật."
            merged = {}
            for key, val in updates.items():
                if key not in CONFIG_LIMITS:
                    return False, f"Không được phép chỉnh '{key}'."
                if not _is_number(val):
                    return False, f"Giá trị '{key}' phải là số."
                lo, hi = CONFIG_LIMITS[key]
                if not lo <= val <= hi:
                    return False, f"'{key}' phải nằm trong khoảng {lo} – {hi}."
                merged[key] = float(val)
            new_max = merged.get("max_run_s", self.cfg["max_run_s"])
            longest = max((s["duration_s"] for s in self.schedules), default=0.0)
            if new_max < longest:
                return False, (f"'max_run_s' không được nhỏ hơn thời lượng lịch dài nhất ({longest:.0f}s). "
                               "Hãy sửa lịch trước.")
            self.cfg.update(merged)
            self._log("info", "Cập nhật cấu hình: " + ", ".join(f"{k}={v:g}" for k, v in merged.items()))
            return True, "Đã lưu cấu hình."

    # ------------------------------------------------------------------ lịch hẹn giờ
    @staticmethod
    def _overlap(a_start_min, a_dur, b_start_min, b_dur):
        a, b = a_start_min * 60, b_start_min * 60
        return (b - a) % DAY_S < a_dur or (a - b) % DAY_S < b_dur

    def add_schedule(self, start, duration_s):
        """start dạng 'HH:MM'. Từ chối lịch trùng/chồng lấn với lịch có sẵn."""
        with self._lock:
            if not isinstance(start, str) or not TIME_RE.match(start):
                return False, "Giờ bắt đầu phải có dạng HH:MM (00:00–23:59)."
            if not _is_number(duration_s):
                return False, "Thời lượng phải là số giây."
            if not MIN_SCHEDULE_S <= duration_s <= self.cfg["max_run_s"]:
                return False, (f"Thời lượng phải trong khoảng {MIN_SCHEDULE_S:g} – "
                               f"{self.cfg['max_run_s']:g} giây (giới hạn bơm liên tục).")
            if len(self.schedules) >= MAX_SCHEDULES:
                return False, f"Tối đa {MAX_SCHEDULES} lịch."
            h, m = start.split(":")
            start_min = int(h) * 60 + int(m)
            for s in self.schedules:
                if self._overlap(start_min, float(duration_s), s["start_min"], s["duration_s"]):
                    return False, f"Lịch trùng/chồng lấn với lịch {fmt_hhmm(s['start_min'])}."
            sched = {"id": self._next_sched_id, "start_min": start_min,
                     "duration_s": float(duration_s), "enabled": True}
            self._next_sched_id += 1
            self.schedules.append(sched)
            self.schedules.sort(key=lambda s: s["start_min"])
            self._log("info", f"Thêm lịch {start}, {duration_s:g}s.")
            return True, "Đã thêm lịch."

    def delete_schedule(self, sched_id):
        with self._lock:
            for s in self.schedules:
                if s["id"] == sched_id:
                    self.schedules.remove(s)
                    self._log("info", f"Xóa lịch {fmt_hhmm(s['start_min'])}.")
                    return True, "Đã xóa lịch."
            return False, "Không tìm thấy lịch."

    def set_schedule_enabled(self, sched_id, enabled):
        with self._lock:
            if not isinstance(enabled, bool):
                return False, "enabled phải là true/false."
            for s in self.schedules:
                if s["id"] == sched_id:
                    s["enabled"] = enabled
                    self._log("info", f"{'Bật' if enabled else 'Tắt'} lịch {fmt_hhmm(s['start_min'])}.")
                    return True, "Đã cập nhật lịch."
            return False, "Không tìm thấy lịch."

    def _active_window(self):
        a = self._abs_s()
        for s in self.schedules:
            if not s["enabled"]:
                continue
            since_start = (a - s["start_min"] * 60) % DAY_S
            if since_start < s["duration_s"]:
                return (s["id"], a - since_start)
        return None

    def next_schedule(self):
        a = self._abs_s()
        best = None
        for s in self.schedules:
            if not s["enabled"]:
                continue
            wait = (s["start_min"] * 60 - a) % DAY_S
            if best is None or wait < best[1]:
                best = (fmt_hhmm(s["start_min"]), wait)
        return best

    # ------------------------------------------------------------------ vòng mô phỏng
    def step(self, dt):
        """Tiến mô phỏng dt giây (chia thành bước con ≤ MAX_SUBSTEP_S)."""
        with self._lock:
            remaining = float(dt)
            while remaining > 1e-9:
                d = min(MAX_SUBSTEP_S, remaining)
                self._control(d)
                self._hydraulics(d)
                self.time_s += d
                remaining -= d

    def _control(self, dt):
        c = self.cfg
        if self.estop:
            if self.pump_on:
                self._pump_off("Dừng khẩn cấp: ngắt bơm.", "alarm")
            return

        if self.pump_on:
            self.run_s += dt
            self.total_run_s += dt
            tripped = None
            if self.tank_l <= c["min_tank_l"]:
                tripped = "Bể cạn: tự ngắt bơm để bảo vệ."
            elif self.n_valves_open() == 0:
                tripped = "Cả hai van đều đóng: tự ngắt bơm (bí đầu ra)."
            elif self.run_s >= c["max_run_s"]:
                tripped = f"Bơm chạy liên tục quá {c['max_run_s']:.0f}s: tự ngắt."
            if tripped:
                if self.run_source == "timer":
                    self.suppress_key = self.timer_key
                self._pump_off(tripped, "alarm")

        if self.mode == "timer":
            key = self._active_window()
            if self.pump_on and self.run_source == "timer" and key != self.timer_key:
                self._pump_off("Hết giờ tưới theo lịch: tắt bơm.", "info")
            elif (
                not self.pump_on
                and key is not None
                and key != self.suppress_key
                and self.tank_l > c["min_tank_l"]
                and self.n_valves_open() > 0
            ):
                self.timer_key = key
                self._pump_on("timer", "Đến giờ tưới theo lịch: bật bơm.")

    def _hydraulics(self, dt):
        c = self.cfg
        dt_min = dt / 60.0
        dt_h = dt / 3600.0
        wick = 1.0 - math.exp(-dt / c["wick_tau_s"])

        # 1. Bơm hút từ bể, chia đều cho các nhánh có van mở
        pumped = 0.0
        n_open = self.n_valves_open()
        if self.pump_on and n_open > 0:
            pumped = min(c["pump_flow_lpm"] * dt_min, self.tank_l)
            self.tank_l -= pumped
            self.pumped_l += pumped
            self.energy_wh += c["pump_power_w"] * dt_h
        self.flow_pump_lpm = pumped / dt_min

        # 2. Mỗi sợi: nước vào LECA bậc 12 rồi chảy xuống bậc 1 qua các cửa nước
        for s in STRANDS:
            inflow = pumped / n_open if (self.valve_open[s] and n_open) else 0.0
            self.supply_lpm[s] = inflow / dt_min
            soil, leca = self.soil_l[s], self.leca_l[s]
            for i in range(STEPS - 1, -1, -1):
                self.flow_in_lpm[s][i] = inflow / dt_min
                leca[i] += inflow
                # giá thể hút nước từ LECA lên (mao dẫn qua vải địa)
                want = max(0.0, SOIL_TARGET_L - soil[i])
                take = min(leca[i], want * wick)
                leca[i] -= take
                soil[i] += take
                # nước vượt ngưỡng +18 chảy qua cửa nước xuống bậc dưới
                door = min(max(0.0, leca[i] - LECA_THRESH_L), c["door_max_lpm"] * dt_min)
                leca[i] -= door
                # khe tràn dự phòng nếu LECA đầy
                over = max(0.0, leca[i] - LECA_MAX_L)
                leca[i] -= over
                inflow = door + over
            # bậc 1 xả qua ống hồi Ø16 về bể
            self.tank_l += inflow
            self.recovered_l += inflow
            self.return_lpm[s] = inflow / dt_min

        # 3. Nước mất: cây dùng + bay hơi (giá thể), bay hơi bể
        for s in STRANDS:
            for i in range(STEPS):
                loss = c["et_lph"] * (self.soil_l[s][i] / SOIL_SAT_L) * dt_h
                loss = min(loss, self.soil_l[s][i])
                self.soil_l[s][i] -= loss
                self.lost_l[s][i] += loss
        tank_loss = min(c["tank_evap_lph"] * dt_h, self.tank_l)
        self.tank_l -= tank_loss
        self.tank_lost_l += tank_loss

    # ------------------------------------------------------------------ xuất dữ liệu
    def total_lost_l(self):
        return sum(sum(self.lost_l[s]) for s in STRANDS) + self.tank_lost_l

    def balance_error_l(self):
        """Sai lệch bảo toàn nước; phải ≈ 0."""
        return self._inventory() + self.total_lost_l() - (self.initial_l + self.added_l)

    def snapshot(self):
        with self._lock:
            c = self.cfg
            alerts = []
            if self.estop:
                alerts.append({"code": "estop", "level": "alarm", "msg": "Đang dừng khẩn cấp."})
            if self.tank_l <= c["min_tank_l"]:
                alerts.append({"code": "tank_low", "level": "alarm", "msg": "Bể nước quá thấp."})
            if self.n_valves_open() == 0:
                alerts.append({"code": "valves_closed", "level": "warn",
                               "msg": "Cả Van A và Van B đều đóng: bơm sẽ không chạy."})
            if self.mode == "timer" and not any(s["enabled"] for s in self.schedules):
                alerts.append({"code": "no_schedule", "level": "warn",
                               "msg": "Chế độ hẹn giờ nhưng chưa có lịch nào được bật."})
            state = "ON" if self.pump_on else "OFF"
            nxt = self.next_schedule()
            steps = []
            for s in STRANDS:
                for i in range(STEPS):
                    steps.append({
                        **step_info(s, i + 1),
                        "vwc_pct": round(self.vwc_pct(s, i), 1),
                        "soil_l": round(self.soil_l[s][i], 4),
                        "soil_capacity_l": round(SOIL_SAT_L, 3),
                        "leca_l": round(self.leca_l[s][i], 4),
                        "leca_level_mm": round(self.leca_l[s][i] / (STEP_AREA_M2 * LECA_POROSITY), 1),
                        "inflow_lpm": round(self.flow_in_lpm[s][i], 3),
                        "lost_l": round(self.lost_l[s][i], 4),
                    })
            return {
                "data_source": "SIMULATION",
                "run_mode": "DEMO",
                "time_s": round(self.time_s, 1),
                "clock": self.clock(),
                "speed": c["speed"],
                "pump": {
                    "on": self.pump_on,
                    "desired_state": state,
                    # DEMO MODE: chưa có ESP32 nên reported_state chính là trạng thái mô phỏng
                    "reported_state": state,
                    "device_connected": False,
                    "mode": self.mode,
                    "source": self.run_source,
                    "estop": self.estop,
                    "run_s": round(self.run_s, 1),
                    "total_run_s": round(self.total_run_s, 1),
                    "flow_lpm": round(self.flow_pump_lpm, 3),
                },
                "valves": {s: self.valve_open[s] for s in STRANDS},
                "strands": {
                    s: {
                        "supply_lpm": round(self.supply_lpm[s], 3),
                        "return_lpm": round(self.return_lpm[s], 3),
                        "avg_vwc": round(self.avg_vwc(s), 1),
                    }
                    for s in STRANDS
                },
                "tank": {
                    "water_l": round(self.tank_l, 2),
                    "capacity_l": TANK_MAX_L,
                    "normal_l": TANK_NORMAL_L,
                    "level_mm": round(self.tank_l / TANK_AREA_M2, 1),  # 1 L trên 1 m² = 1 mm
                    "pct": round(self.tank_l / TANK_MAX_L * 100.0, 1),
                    "return_lpm": round(sum(self.return_lpm.values()), 3),
                },
                "steps": steps,
                "avg_moisture": round(self.avg_vwc(), 1),
                "schedules": [
                    {"id": s["id"], "start": fmt_hhmm(s["start_min"]),
                     "duration_s": s["duration_s"], "enabled": s["enabled"]}
                    for s in self.schedules
                ],
                "next_schedule": ({"start": nxt[0], "in_s": round(nxt[1])} if nxt else None),
                "totals": {
                    "initial_l": round(self.initial_l, 2),
                    "added_l": round(self.added_l, 2),
                    "pumped_l": round(self.pumped_l, 2),
                    "recovered_l": round(self.recovered_l, 2),
                    "lost_l": round(self.total_lost_l(), 3),
                    "energy_wh": round(self.energy_wh, 3),
                    "balance_error_l": round(self.balance_error_l(), 9),
                },
                "config": {k: c[k] for k in CONFIG_LIMITS},
                "geometry": {
                    "step_area_m2": round(STEP_AREA_M2, 5),
                    "substrate_l": round(SUBSTRATE_L, 3),
                    "leca_threshold_l": round(LECA_THRESH_L, 4),
                    "leca_max_l": round(LECA_MAX_L, 4),
                },
                "alerts": alerts,
                "events": list(self.events)[-30:],
            }
