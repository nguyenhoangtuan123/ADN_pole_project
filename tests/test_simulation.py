import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import simulation as S  # noqa: E402
from simulation import Simulation, STEPS  # noqa: E402


def run(sim, seconds, dt=1.0):
    for _ in range(int(seconds / dt)):
        sim.step(dt)


def to_clock(sim, hhmm):
    """Tua đồng hồ mô phỏng (không bơm) tới giờ hhmm trong ngày 1."""
    h, m = hhmm.split(":")
    target = int(h) * 3600 + int(m) * 60
    start = sim.cfg["clock_start_min"] * 60
    assert target >= start
    sim.time_s = target - start


# ----------------------------------------------------------------- hình học theo bản vẽ
def test_geometry_matches_drawing():
    assert abs(S.SUBSTRATE_L - 2.2275) < 0.01            # 0.486 m² × 110 mm / 24 bậc
    assert abs(S.TANK_AREA_M2 * 0.060 * 1000 - 17.0) < 0.1   # 60 mm ≈ 17 L (tờ 11)
    assert abs(S.TANK_AREA_M2 * 0.100 * 1000 - 28.3) < 0.1   # 100 mm ≈ 28 L
    assert S.step_info("A", 1)["floor_z"] == 385
    assert S.step_info("A", 12)["floor_z"] == 1210
    assert S.step_info("B", 7)["floor_z"] == 835
    assert S.step_info("B", 1)["angle"] == "180–210°"


def test_snapshot_has_24_steps_and_two_strands():
    snap = Simulation().snapshot()
    assert len(snap["steps"]) == 24
    assert {s["strand"] for s in snap["steps"]} == {"A", "B"}
    assert snap["data_source"] == "SIMULATION"
    assert snap["pump"]["device_connected"] is False


# ----------------------------------------------------------------- thủy lực
def test_water_conservation_pump_on_off():
    sim = Simulation()
    sim.command_pump(True)
    run(sim, 200)
    sim.command_pump(False)
    run(sim, 3600)
    assert abs(sim.balance_error_l()) < 1e-9
    assert sim.pumped_l > 0 and sim.recovered_l > 0


def test_conservation_large_step_and_refill():
    sim = Simulation()
    sim.command_pump(True)
    sim.step(300)
    assert sim.refill(5)[0]
    sim.step(300)
    assert abs(sim.balance_error_l()) < 1e-9
    assert sim.added_l > 0


def test_conservation_with_one_valve_closed():
    sim = Simulation()
    sim.set_valve("B", False)
    sim.command_pump(True)
    run(sim, 200)
    assert abs(sim.balance_error_l()) < 1e-9


def test_water_enters_top_step_first_and_cascades_down():
    sim = Simulation()
    sim.command_pump(True)
    run(sim, 3)
    leca = sim.leca_l["A"]
    # bậc 12 (chỉ số 11) đã nhận nước trước; bậc 1 (chỉ số 0) chưa
    assert leca[11] > 0.5 * S.LECA_THRESH_L
    assert sim.flow_in_lpm["A"][11] > 0
    assert sim.flow_in_lpm["A"][0] == 0      # nước chưa xuống tới bậc 1
    assert leca[0] <= 0.5 * S.LECA_THRESH_L  # chỉ có mao dẫn rút bớt, không tăng
    run(sim, 120)
    # sau một lúc nước đã xuống tới bậc 1 và về bể
    assert sim.return_lpm["A"] > 0 and sim.return_lpm["B"] > 0
    assert sim.recovered_l > 0


def test_leca_never_exceeds_threshold_when_door_not_limiting():
    sim = Simulation()
    sim.command_pump(True)
    run(sim, 300)
    for s in S.STRANDS:
        assert max(sim.leca_l[s]) <= S.LECA_THRESH_L + 1e-9


def test_valve_split_and_valve_closed_branch_gets_nothing():
    sim = Simulation()
    sim.set_valve("A", False)
    sim.command_pump(True)
    run(sim, 5)
    assert sim.supply_lpm["A"] == 0
    assert abs(sim.supply_lpm["B"] - sim.cfg["pump_flow_lpm"]) < 1e-6
    sim.set_valve("A", True)
    run(sim, 2)
    assert abs(sim.supply_lpm["A"] - sim.cfg["pump_flow_lpm"] / 2) < 1e-6
    assert abs(sim.supply_lpm["B"] - sim.cfg["pump_flow_lpm"] / 2) < 1e-6


def test_soil_moisture_rises_with_watering_and_bounded():
    sim = Simulation()
    before = sim.avg_vwc()
    sim.command_pump(True)
    run(sim, 300)
    sim.command_pump(False)
    run(sim, 3600)
    assert sim.avg_vwc() > before
    for s in S.STRANDS:
        assert all(0 <= sim.vwc_pct(s, i) <= S.SOIL_SAT_FRAC * 100 + 1e-6 for i in range(STEPS))
    assert sim.tank_l >= 0


def test_soil_dries_without_watering():
    sim = Simulation()
    sim.step(48 * 3600)
    assert sim.avg_vwc() < sim.cfg["soil_initial_frac"] * 100
    assert sim.total_lost_l() > 0


# ----------------------------------------------------------------- an toàn
def test_pump_cuts_when_tank_low():
    sim = Simulation(config={"tank_initial_l": 4.5, "max_run_s": 3600})
    assert sim.command_pump(True)[0]
    run(sim, 600)
    assert sim.pump_on is False
    assert any(a["code"] == "tank_low" for a in sim.snapshot()["alerts"])


def test_cannot_start_when_tank_low():
    sim = Simulation(config={"tank_initial_l": 3.0})
    ok, _ = sim.command_pump(True)
    assert not ok and sim.pump_on is False


def test_cannot_start_with_both_valves_closed():
    sim = Simulation()
    sim.set_valve("A", False)
    sim.set_valve("B", False)
    assert not sim.command_pump(True)[0]
    assert any(a["code"] == "valves_closed" for a in sim.snapshot()["alerts"])


def test_closing_both_valves_trips_pump():
    sim = Simulation()
    sim.command_pump(True)
    run(sim, 5)
    sim.set_valve("A", False)
    sim.set_valve("B", False)
    run(sim, 2)
    assert sim.pump_on is False


def test_max_continuous_run_stops_pump():
    sim = Simulation()
    sim.schedules.clear()
    assert sim.set_config({"max_run_s": 30})[0]
    sim.command_pump(True)
    run(sim, 60)
    assert sim.pump_on is False
    assert sim.total_run_s <= 31


def test_emergency_stop_latches():
    sim = Simulation()
    sim.command_pump(True)
    sim.set_estop(True)
    assert sim.pump_on is False
    assert not sim.command_pump(True)[0]
    sim.set_mode("timer")
    to_clock(sim, "06:30")
    run(sim, 20)
    assert sim.pump_on is False
    sim.set_estop(False)
    assert sim.pump_on is False


def test_manual_on_refused_in_timer_mode():
    sim = Simulation()
    sim.set_mode("timer")
    assert not sim.command_pump(True)[0]


def test_mode_switch_turns_pump_off():
    sim = Simulation()
    sim.command_pump(True)
    sim.set_mode("timer")
    assert sim.pump_on is False


# ----------------------------------------------------------------- hẹn giờ
def test_timer_runs_exactly_in_window():
    sim = Simulation()
    sim.schedules.clear()
    assert sim.add_schedule("07:00", 120)[0]
    sim.set_mode("timer")
    to_clock(sim, "06:59")
    run(sim, 30)
    assert sim.pump_on is False
    run(sim, 40)
    assert sim.pump_on is True and sim.run_source == "timer"
    run(sim, 100)
    assert sim.pump_on is True
    run(sim, 30)
    assert sim.pump_on is False
    assert 118 <= sim.total_run_s <= 122
    assert abs(sim.balance_error_l()) < 1e-9


def test_disabled_schedule_does_not_run():
    sim = Simulation()
    sim.schedules.clear()
    sim.add_schedule("07:00", 60)
    sid = sim.schedules[0]["id"]
    assert sim.set_schedule_enabled(sid, False)[0]
    sim.set_mode("timer")
    to_clock(sim, "07:00")
    run(sim, 30)
    assert sim.pump_on is False


def test_overlapping_schedules_rejected():
    sim = Simulation()
    sim.schedules.clear()
    assert sim.add_schedule("07:00", 300)[0]
    assert not sim.add_schedule("07:03", 60)[0]
    assert not sim.add_schedule("06:58", 300)[0]
    assert not sim.add_schedule("07:00", 60)[0]
    assert sim.add_schedule("07:05", 60)[0]
    assert len(sim.schedules) == 2


def test_overlap_across_midnight_rejected():
    sim = Simulation()
    sim.schedules.clear()
    sim.set_config({"max_run_s": 3600})
    assert sim.add_schedule("23:50", 1200)[0]
    assert not sim.add_schedule("00:05", 60)[0]
    assert sim.add_schedule("00:30", 60)[0]


def test_schedule_validation():
    sim = Simulation()
    assert not sim.add_schedule("25:00", 60)[0]
    assert not sim.add_schedule("7:00", 60)[0]
    assert not sim.add_schedule("07:00", -5)[0]
    assert not sim.add_schedule("07:00", "abc")[0]
    assert not sim.add_schedule("07:00", sim.cfg["max_run_s"] + 1)[0]
    assert not sim.add_schedule(None, 60)[0]


def test_max_run_cannot_be_below_longest_schedule():
    sim = Simulation()
    assert not sim.set_config({"max_run_s": 20})[0]


def test_timer_trip_does_not_restart_in_same_window():
    sim = Simulation(config={"tank_initial_l": 4.5})
    sim.schedules.clear()
    sim.add_schedule("07:00", 600)
    sim.set_mode("timer")
    to_clock(sim, "07:00")
    run(sim, 300)
    assert sim.pump_on is False
    sim.refill(10)
    run(sim, 100)
    assert sim.pump_on is False


def test_timer_runs_again_next_day():
    sim = Simulation()
    sim.schedules.clear()
    sim.add_schedule("07:00", 60)
    sim.set_mode("timer")
    to_clock(sim, "07:00")
    run(sim, 90)
    assert sim.total_run_s > 0 and sim.pump_on is False
    sim.time_s += 86400 - 90
    run(sim, 30)
    assert sim.pump_on is True


def test_timer_does_not_start_with_valves_closed():
    sim = Simulation()
    sim.schedules.clear()
    sim.add_schedule("07:00", 60)
    sim.set_valve("A", False)
    sim.set_valve("B", False)
    sim.set_mode("timer")
    to_clock(sim, "07:00")
    run(sim, 20)
    assert sim.pump_on is False


def test_next_schedule_reported():
    nxt = Simulation().snapshot()["next_schedule"]
    assert nxt["start"] == "06:30" and nxt["in_s"] == 1800


def test_delete_schedule():
    sim = Simulation()
    sid = sim.schedules[0]["id"]
    assert sim.delete_schedule(sid)[0]
    assert not sim.delete_schedule(sid)[0]


# ----------------------------------------------------------------- cấu hình
def test_config_validation():
    sim = Simulation()
    assert not sim.set_config({"pump_flow_lpm": -1})[0]
    assert not sim.set_config({"pump_flow_lpm": 5})[0]      # vượt 200 L/h của bản vẽ
    assert not sim.set_config({"pump_flow_lpm": "abc"})[0]
    assert not sim.set_config({"pump_flow_lpm": True})[0]
    assert not sim.set_config({"tank_initial_l": 99})[0]    # không được chỉnh lúc chạy
    assert not sim.set_config({"speed": float("nan")})[0]
    assert sim.set_config({"pump_flow_lpm": 3.0, "speed": 60})[0]
    assert sim.cfg["pump_flow_lpm"] == 3.0


def test_valve_validation():
    sim = Simulation()
    assert not sim.set_valve("C", True)[0]
    assert not sim.set_valve("A", "yes")[0]
    assert sim.set_valve("A", False)[0]
    assert sim.valve_open["A"] is False


def test_reset_restores_initial_state():
    sim = Simulation()
    sim.set_valve("A", False)
    sim.command_pump(True)
    run(sim, 100)
    sim.reset()
    assert sim.pump_on is False and sim.time_s == 0 and sim.pumped_l == 0
    assert sim.valve_open == {"A": True, "B": True}
    assert abs(sim.balance_error_l()) < 1e-9
    assert len(sim.schedules) == 2
