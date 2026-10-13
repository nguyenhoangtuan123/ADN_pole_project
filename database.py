"""Lưu dữ liệu vận hành (SQLite) cho Trụ ADN Digital Twin.

Mọi bản ghi đều mang nhãn nguồn dữ liệu (cột `source`). Ở DEMO MODE nguồn luôn là
'SIMULATION': đây là số liệu mô phỏng, không phải số đo thực tế.

Mỗi lần mô phỏng được đặt lại (reset) bắt đầu một "lượt chạy" (run) mới để các chuỗi dữ liệu
không bị trộn lẫn.
"""
import csv
import io
import os
import sqlite3
import threading
import time
from datetime import datetime

SAMPLE_EVERY_SIM_S = 60.0     # lấy mẫu ít nhất mỗi 60 giây mô phỏng
SAMPLE_EVERY_REAL_S = 10.0    # và ít nhất mỗi 10 giây thực (để biểu đồ có số liệu khi chạy ×1)
MAX_SAMPLES = 100_000         # giữ tối đa chừng này mẫu mới nhất
PRUNE_EVERY = 500             # số lần ghi giữa hai lần dọn dẹp

SAMPLE_COLUMNS = [
    "t", "day", "hhmm", "pump_on", "mode", "pump_flow_lpm", "return_lpm", "tank_l",
    "tank_level_mm", "avg_vwc", "vwc_a", "vwc_b", "pumped_l", "recovered_l", "lost_l",
    "energy_wh", "source",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    t REAL NOT NULL,
    day INTEGER, hhmm TEXT, pump_on INTEGER, mode TEXT,
    pump_flow_lpm REAL, return_lpm REAL, tank_l REAL, tank_level_mm REAL,
    avg_vwc REAL, vwc_a REAL, vwc_b REAL,
    pumped_l REAL, recovered_l REAL, lost_l REAL, energy_wh REAL,
    source TEXT NOT NULL DEFAULT 'SIMULATION'
);
CREATE INDEX IF NOT EXISTS idx_samples_run ON samples(run_id, id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    t REAL NOT NULL,
    level TEXT NOT NULL,
    msg TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'SIMULATION'
);
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, id);
"""


class Recorder:
    def __init__(self, path):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()
        self._sim_run = None      # run_id của Simulation đang được ghi
        self._db_run = None       # id dòng trong bảng runs tương ứng
        self._last_t = None
        self._last_real = 0.0
        self._last_pump = None
        self._writes = 0

    # ------------------------------------------------------------------ gắn vào mô phỏng
    def attach(self, sim):
        """Nối vào Simulation: ghi sự kiện bền vững và bù các sự kiện đã có."""
        with self._lock:
            self._ensure_run(sim.run_id)
            sim.on_event = self.event
            for entry in list(sim.events):
                self._insert_event(entry)

    def _ensure_run(self, sim_run_id):
        if sim_run_id != self._sim_run:
            cur = self._db.execute(
                "INSERT INTO runs(started_at) VALUES (?)", (datetime.now().isoformat(timespec="seconds"),)
            )
            self._db.commit()
            self._sim_run = sim_run_id
            self._db_run = cur.lastrowid
            self._last_t = None
            self._last_pump = None

    def _insert_event(self, entry):
        self._db.execute(
            "INSERT INTO events(run_id, t, level, msg, created_at) VALUES (?,?,?,?,?)",
            (self._db_run, entry["t"], entry["level"], entry["msg"],
             datetime.now().isoformat(timespec="seconds")),
        )
        self._db.commit()

    def event(self, sim_run_id, entry):
        with self._lock:
            self._ensure_run(sim_run_id)
            self._insert_event(entry)

    # ------------------------------------------------------------------ lấy mẫu
    def tick(self, sim):
        """Gọi sau mỗi bước mô phỏng; tự quyết định có ghi mẫu hay không."""
        s = sim.sample()
        with self._lock:
            self._ensure_run(s["run_id"])
            now = time.monotonic()
            first = self._last_t is None
            edge = self._last_pump is not None and s["pump_on"] != self._last_pump
            due = (not first) and (
                s["t"] - self._last_t >= SAMPLE_EVERY_SIM_S
                or (s["t"] > self._last_t and now - self._last_real >= SAMPLE_EVERY_REAL_S)
            )
            if first or edge or due:
                self._insert_sample(s)
                self._last_t = s["t"]
                self._last_real = now
            self._last_pump = s["pump_on"]

    def _insert_sample(self, s):
        cols = [c for c in SAMPLE_COLUMNS if c != "source"]
        self._db.execute(
            f"INSERT INTO samples(run_id, {', '.join(cols)}) VALUES (?, {', '.join('?' * len(cols))})",
            [self._db_run] + [s[c] for c in cols],
        )
        self._db.commit()
        self._writes += 1
        if self._writes % PRUNE_EVERY == 0:
            self._db.execute(
                "DELETE FROM samples WHERE id < (SELECT MAX(id) FROM samples) - ?", (MAX_SAMPLES,)
            )
            self._db.commit()

    # ------------------------------------------------------------------ truy vấn
    def history(self, window_s=None, limit=400):
        """Mẫu của lượt chạy hiện tại, thu gọn còn tối đa `limit` điểm (giữ điểm đầu, cuối và các điểm bật/tắt bơm)."""
        limit = max(10, min(int(limit), 5000))
        with self._lock:
            if self._db_run is None:
                return {"run_id": None, "count": 0, "points": []}
            rows = self._db.execute(
                "SELECT * FROM samples WHERE run_id=? ORDER BY id", (self._db_run,)
            ).fetchall()
        total = len(rows)
        if window_s and rows:
            t_max = rows[-1]["t"]
            rows = [r for r in rows if r["t"] >= t_max - window_s]
        n = len(rows)
        if n > limit:
            stride = -(-n // limit)
            kept = []
            for i, r in enumerate(rows):
                edge = i > 0 and r["pump_on"] != rows[i - 1]["pump_on"]
                prev_edge = i + 1 < n and rows[i + 1]["pump_on"] != r["pump_on"]
                if i % stride == 0 or i == n - 1 or edge or prev_edge:
                    kept.append(r)
            rows = kept
        return {
            "run_id": self._db_run,
            "total": total,
            "count": len(rows),
            "points": [dict(r) for r in rows],
        }

    def events(self, limit=200):
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            if self._db_run is None:
                return []
            rows = self._db.execute(
                "SELECT t, level, msg, created_at, source FROM events WHERE run_id=? ORDER BY id DESC LIMIT ?",
                (self._db_run, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def export_csv(self, all_runs=False):
        """Trả về nội dung CSV (UTF-8 có BOM để Excel đọc đúng) của các mẫu."""
        with self._lock:
            if all_runs:
                rows = self._db.execute("SELECT * FROM samples ORDER BY id").fetchall()
            else:
                rows = self._db.execute(
                    "SELECT * FROM samples WHERE run_id=? ORDER BY id", (self._db_run,)
                ).fetchall()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["run_id"] + SAMPLE_COLUMNS)
        for r in rows:
            w.writerow([r["run_id"]] + [round(r[c], 4) if isinstance(r[c], float) else r[c] for c in SAMPLE_COLUMNS])
        return "﻿" + buf.getvalue()

    def close(self):
        with self._lock:
            self._db.close()
