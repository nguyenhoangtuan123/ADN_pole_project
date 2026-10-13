import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database  # noqa: E402
from database import Recorder  # noqa: E402
from simulation import Simulation  # noqa: E402


def make(tmp_path):
    sim = Simulation()
    rec = Recorder(str(tmp_path / "t.db"))
    rec.attach(sim)
    return sim, rec


def drive(sim, rec, seconds, dt=1.0):
    for _ in range(int(seconds / dt)):
        sim.step(dt)
        rec.tick(sim)


def test_samples_recorded_and_labelled_simulation(tmp_path):
    sim, rec = make(tmp_path)
    drive(sim, rec, 300)
    h = rec.history()
    assert h["count"] >= 5
    assert h["points"][0]["source"] == "SIMULATION"
    assert h["points"][0]["t"] <= 1.0   # mẫu đầu ngay sau bước mô phỏng đầu tiên
    ts = [p["t"] for p in h["points"]]
    assert ts == sorted(ts)


def test_pump_edges_are_always_recorded(tmp_path):
    sim, rec = make(tmp_path)
    drive(sim, rec, 5)
    sim.command_pump(True)
    drive(sim, rec, 3)
    sim.command_pump(False)
    drive(sim, rec, 3)
    states = [p["pump_on"] for p in rec.history()["points"]]
    assert 1 in states and states[0] == 0 and states[-1] == 0


def test_reset_starts_a_new_run(tmp_path):
    sim, rec = make(tmp_path)
    drive(sim, rec, 130)
    first = rec.history()
    sim.reset()
    drive(sim, rec, 5)
    second = rec.history()
    assert second["run_id"] != first["run_id"]
    assert second["points"][0]["t"] <= 1.0
    assert second["count"] < first["count"]  # lượt cũ không lẫn vào lượt mới


def test_events_persisted(tmp_path):
    sim, rec = make(tmp_path)
    sim.command_pump(True)
    sim.command_pump(False)
    msgs = [e["msg"] for e in rec.events()]
    assert any("Bật bơm" in m for m in msgs) and any("Tắt bơm" in m for m in msgs)
    assert any("Khởi tạo" in m for m in msgs)  # sự kiện có trước khi gắn cũng được bù vào


def test_history_downsamples_but_keeps_ends_and_edges(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "SAMPLE_EVERY_SIM_S", 1.0)
    sim, rec = make(tmp_path)
    drive(sim, rec, 20)
    sim.command_pump(True)
    drive(sim, rec, 20)
    sim.command_pump(False)
    drive(sim, rec, 200)
    full = rec.history(limit=5000)
    small = rec.history(limit=20)
    assert full["count"] > 100
    assert small["count"] < full["count"]
    assert small["points"][0]["t"] == full["points"][0]["t"]
    assert small["points"][-1]["t"] == full["points"][-1]["t"]
    assert any(p["pump_on"] == 1 for p in small["points"])


def test_history_window(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "SAMPLE_EVERY_SIM_S", 1.0)
    sim, rec = make(tmp_path)
    drive(sim, rec, 300)
    w = rec.history(window_s=60, limit=5000)
    assert all(p["t"] >= w["points"][-1]["t"] - 60 for p in w["points"])
    assert w["count"] < rec.history(limit=5000)["count"]


def test_export_csv(tmp_path):
    sim, rec = make(tmp_path)
    drive(sim, rec, 130)
    text = rec.export_csv()
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[0][0] == "run_id" and "source" in rows[0] and "tank_l" in rows[0]
    assert len(rows) > 2
    assert rows[1][rows[0].index("source")] == "SIMULATION"


def test_prune_keeps_latest(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "SAMPLE_EVERY_SIM_S", 1.0)
    monkeypatch.setattr(database, "MAX_SAMPLES", 50)
    monkeypatch.setattr(database, "PRUNE_EVERY", 10)
    sim, rec = make(tmp_path)
    drive(sim, rec, 300)
    assert rec.history(limit=5000)["total"] <= 60
