import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402


@pytest.fixture
def client():
    app_module.sim.reset()
    app_module.sim.set_config({"speed": 1})
    return app_module.app.test_client()


def test_dashboard_page_served(client):
    assert client.get("/dashboard").status_code == 200


def test_state_has_expected_shape(client):
    s = client.get("/api/state").get_json()
    assert s["data_source"] == "SIMULATION"
    assert len(s["steps"]) == 24 and "tank" in s and "pump" in s and "schedules" in s
    assert s["valves"] == {"A": True, "B": True}


def test_pump_on_off_changes_state(client):
    r = client.post("/api/pump", json={"action": "on"})
    assert r.status_code == 200 and r.get_json()["state"]["pump"]["on"] is True
    assert client.get("/api/state").get_json()["pump"]["desired_state"] == "ON"
    r = client.post("/api/pump", json={"action": "off"})
    assert r.get_json()["state"]["pump"]["on"] is False


def test_bad_inputs_rejected(client):
    assert client.post("/api/pump", json={"action": "boom"}).status_code == 400
    assert client.post("/api/mode", json={"mode": "auto"}).status_code == 400
    assert client.post("/api/estop", json={"engaged": "yes"}).status_code == 400
    assert client.post("/api/config", json={"pump_flow_lpm": -5}).status_code == 400
    assert client.post("/api/refill", json={"liters": "abc"}).status_code == 409


def test_estop_blocks_pump_over_api(client):
    client.post("/api/estop", json={"engaged": True})
    r = client.post("/api/pump", json={"action": "on"})
    assert r.status_code == 409
    assert r.get_json()["state"]["pump"]["on"] is False


def test_schedule_add_toggle_delete(client):
    r = client.post("/api/schedules", json={"start": "10:00", "duration_s": 120})
    assert r.status_code == 200
    scheds = client.get("/api/schedules").get_json()
    new = next(s for s in scheds if s["start"] == "10:00")
    # chồng lấn bị từ chối
    assert client.post("/api/schedules", json={"start": "10:01", "duration_s": 60}).status_code == 409
    r = client.post(f"/api/schedules/{new['id']}", json={"enabled": False})
    assert r.status_code == 200
    r = client.delete(f"/api/schedules/{new['id']}")
    assert r.status_code == 200
    assert client.delete(f"/api/schedules/{new['id']}").status_code == 409


def test_valve_endpoint_and_pump_refused_when_both_closed(client):
    assert client.post("/api/valve", json={"strand": "A", "open": False}).status_code == 200
    assert client.post("/api/valve", json={"strand": "B", "open": False}).status_code == 200
    r = client.post("/api/pump", json={"action": "on"})
    assert r.status_code == 409 and r.get_json()["state"]["pump"]["on"] is False
    assert client.post("/api/valve", json={"strand": "C", "open": True}).status_code == 400
    assert client.post("/api/valve", json={"strand": "A", "open": "x"}).status_code == 400


def test_manual_on_refused_in_timer_mode(client):
    client.post("/api/mode", json={"mode": "timer"})
    assert client.post("/api/pump", json={"action": "on"}).status_code == 409


def test_history_events_and_csv_endpoints(client):
    h = client.get("/api/history?window_s=3600&limit=50").get_json()
    assert h["data_source"] == "SIMULATION" and "points" in h and "clock_start_min" in h
    assert isinstance(client.get("/api/events").get_json(), list)
    r = client.get("/api/export.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "attachment" in r.headers["Content-Disposition"]


def test_run_config_local_vs_host():
    local = app_module.get_run_config({})
    assert local == {"host": "127.0.0.1", "port": 5000, "debug": True}
    host = app_module.get_run_config({"PORT": "10000"})
    assert host == {"host": "0.0.0.0", "port": 10000, "debug": False}   # host công khai: không debug
    assert app_module.get_run_config({"PORT": "10000", "FLASK_DEBUG": "1"})["debug"] is True
    assert app_module.get_run_config({"FLASK_DEBUG": "0"})["debug"] is False
    assert app_module.get_run_config({"PORT": "abc"})["port"] == 5000       # PORT hỏng thì dùng mặc định


def test_chat_without_key_returns_503_not_crash(client, monkeypatch):
    monkeypatch.setattr(app_module, "client", None)
    r = client.post("/chat", json={"message": "xin chào"})
    assert r.status_code == 503
