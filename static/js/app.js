(function () {
  "use strict";

  const POLL_MS = 1000;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const STEPS = 12;
  const ROW_Y0 = 100, ROW_STEP = 56, STEP_H = 40, STEP_W = 200;
  const COL_X = { A: 150, B: 410 };
  const DOOR_X = { A: 162, B: 598 };     // vị trí ống cửa nước Ø16 (mép ngoài mỗi sợi)
  const DROP_X = { A: 250, B: 510 };     // điểm nước từ chữ T rơi vào bậc 12
  const TANK_TOP = 846, TANK_H = 110;
  const EPS = 0.01;

  let lastState = null;
  let selectedId = "A12";
  let built = false;
  const stepEls = {};   // id → { grp, soil, leca, label }
  const pipeEls = {};   // tên đường nước → phần tử

  const $ = (id) => document.getElementById(id);

  function svgEl(name, attrs, text) {
    const el = document.createElementNS(SVG_NS, name);
    for (const k in attrs) el.setAttribute(k, attrs[k]);
    if (text !== undefined) el.textContent = text;
    return el;
  }

  const rowY = (k) => ROW_Y0 + (STEPS - k) * ROW_STEP;   // bậc 12 ở trên cùng, bậc 1 ở dưới cùng

  // ---------------------------------------------------------------- dựng SVG
  function build() {
    const pipes = $("pipes"), stepsG = $("steps"), valves = $("valves");

    ["A", "B"].forEach((s) => {
      // nhánh từ chữ T xuống phễu bậc 12 (có van riêng)
      pipeEls["supply" + s] = pipes.appendChild(svgEl("path", {
        class: "water-seg", d: `M380 52 H${DROP_X[s]} V${rowY(12) + 20}`,
      }));
      // cửa nước Ø16: bậc k+1 → bậc k
      for (let k = STEPS - 1; k >= 1; k--) {
        pipeEls[`door${s}${k}`] = pipes.appendChild(svgEl("path", {
          class: "water-seg", d: `M${DOOR_X[s]} ${rowY(k + 1) + 34} V${rowY(k) + 34}`,
        }));
      }
      // bậc 1 xả qua ống hồi Ø16 về bể
      pipeEls["return" + s] = pipes.appendChild(svgEl("path", {
        class: "water-seg", d: `M${DOOR_X[s]} ${rowY(1) + 34} V${TANK_TOP + 6}`,
      }));

      // ký hiệu van
      const vx = (380 + DROP_X[s]) / 2;
      const v = svgEl("g", { class: "valve", id: `valve-ico-${s}` });
      v.appendChild(svgEl("rect", { x: vx - 12, y: 40, width: 24, height: 24, rx: 5 }));
      v.appendChild(svgEl("text", { x: vx, y: 57, "text-anchor": "middle" }, s));
      valves.appendChild(v);
      pipeEls["valve" + s] = v;
    });

    ["A", "B"].forEach((s) => {
      for (let k = STEPS; k >= 1; k--) {
        const id = `${s}${k}`, x = COL_X[s], y = rowY(k);
        const grp = svgEl("g", { class: "step", tabindex: "0", role: "button", "aria-label": `Bậc ${id}` });
        grp.appendChild(svgEl("rect", { class: "box", x, y, width: STEP_W, height: STEP_H, rx: 7 }));
        const soil = svgEl("rect", { class: "soil", x: x + 3, y: y + STEP_H - 3, width: STEP_W - 6, height: 0 });
        const leca = svgEl("rect", { class: "leca", x: x + 3, y: y + STEP_H - 8, width: STEP_W - 6, height: 5, rx: 2 });
        grp.append(soil, leca);
        // cây con: hình hai lá của bộ nhận diện
        grp.appendChild(svgEl("path", {
          class: "plant", d: "M0 0 C-9 -4 -10 -14 -2 -20 C4 -14 3 -5 0 0Z M0 0 C1 -8 6 -14 13 -15 C13 -6 8 -1 0 0Z",
          transform: `translate(${x + 100} ${y + 1})`,
        }));
        const label = svgEl("text", { class: "lbl", x: x + STEP_W / 2, y: y + 23, "text-anchor": "middle" }, id);
        grp.appendChild(label);
        const z = 385 + 75 * (k - 1);
        grp.appendChild(svgEl("text", {
          class: "svg-tiny", x: s === "A" ? x - 6 : x + STEP_W + 6, y: y + 24,
          "text-anchor": s === "A" ? "end" : "start",
        }, `Z${z}`));
        grp.addEventListener("click", () => select(id));
        grp.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(id); }
        });
        stepsG.appendChild(grp);
        stepEls[id] = { grp, soil, leca, label };
      }
    });
    built = true;
    select(selectedId);
  }

  function select(id) {
    selectedId = id;
    Object.keys(stepEls).forEach((k) => stepEls[k].grp.classList.toggle("selected", k === id));
    if (lastState) renderDetail(lastState);
  }

  // ---------------------------------------------------------------- hiển thị
  function fmtDur(s) {
    s = Math.floor(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const mm = String(m).padStart(2, "0"), ss = String(sec).padStart(2, "0");
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  }

  function fmtDurText(s) {
    return s >= 60 ? `${(s / 60).toFixed(s % 60 ? 1 : 0)} phút` : `${s} giây`;
  }

  function renderDetail(st) {
    const box = $("step-detail");
    const t = st.steps.find((x) => x.id === selectedId);
    if (!t) return;
    box.innerHTML = "";
    const h = document.createElement("h2");
    h.textContent = `Bậc ${t.id} (góc ${t.angle})`;
    box.appendChild(h);
    const rows = [
      ["Cao độ sàn / mặt đất", `Z${t.floor_z} / Z${t.soil_z} mm`],
      ["Độ ẩm giá thể (ước tính)", `${t.vwc_pct.toFixed(1)} %`],
      ["Nước trong giá thể", `${t.soil_l.toFixed(3)} / ${t.soil_capacity_l.toFixed(2)} L`],
      ["Mực nước LECA (ngưỡng 18 mm)", `${t.leca_level_mm.toFixed(1)} mm (${t.leca_l.toFixed(3)} L)`],
      ["Nước đang chảy vào bậc", `${(t.inflow_lpm * 60).toFixed(0)} L/giờ`],
      ["Nước đã mất (cây + bay hơi)", `${t.lost_l.toFixed(4)} L`],
    ];
    const table = document.createElement("table");
    rows.forEach(([k, v]) => {
      const tr = document.createElement("tr");
      const a = document.createElement("td"); a.textContent = k;
      const b = document.createElement("td"); b.textContent = v;
      tr.append(a, b);
      table.appendChild(tr);
    });
    box.appendChild(table);
    const note = document.createElement("p");
    note.className = "muted small";
    note.textContent = "Độ ẩm % = nước trong giá thể / thể tích giá thể 110 mm. Là ước tính của mô hình, không phải cảm biến thật.";
    box.appendChild(note);
  }

  function renderSchedules(st) {
    const ul = $("schedules");
    ul.innerHTML = "";
    if (!st.schedules.length) {
      const li = document.createElement("li");
      li.className = "muted small";
      li.textContent = "Chưa có lịch nào.";
      ul.appendChild(li);
    }
    st.schedules.forEach((s) => {
      const li = document.createElement("li");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = s.enabled;
      cb.setAttribute("aria-label", `Bật lịch ${s.start}`);
      cb.addEventListener("change", () => api(`/api/schedules/${s.id}`, { enabled: cb.checked }));
      const txt = document.createElement("span");
      txt.className = "sched-txt";
      txt.textContent = `${s.start} · ${fmtDurText(s.duration_s)}`;
      const del = document.createElement("button");
      del.type = "button";
      del.className = "btn btn-small";
      del.textContent = "Xóa";
      del.addEventListener("click", () => api(`/api/schedules/${s.id}`, undefined, "DELETE"));
      li.append(cb, txt, del);
      ul.appendChild(li);
    });
    const nx = st.next_schedule;
    $("next-sched").textContent = nx
      ? `Lịch kế tiếp: ${nx.start} (còn ${fmtDur(nx.in_s)} giờ mô phỏng). Chỉ chạy khi chọn chế độ Hẹn giờ.`
      : "Không có lịch nào đang bật.";
  }

  function render(st) {
    lastState = st;
    const p = st.pump;
    if (!built) build();

    // --- bậc: độ ẩm giá thể (nền xanh nhạt) + mực nước LECA (dải xanh đậm ở đáy)
    st.steps.forEach((t) => {
      const el = stepEls[t.id];
      const frac = Math.min(1, t.soil_l / t.soil_capacity_l);
      const h = (STEP_H - 6) * frac;
      const y = rowY(t.k);
      el.soil.setAttribute("height", h);
      el.soil.setAttribute("y", y + STEP_H - 3 - h);
      const lecaFill = Math.min(1, t.leca_l / st.geometry.leca_max_l);
      el.leca.setAttribute("height", Math.max(1, 6 * lecaFill));
      el.leca.setAttribute("y", y + STEP_H - 3 - Math.max(1, 6 * lecaFill));
      el.label.textContent = `${t.id} · ${t.vwc_pct.toFixed(0)}%`;
    });

    // --- bể
    const tankH = TANK_H * st.tank.pct / 100;
    $("tank-water").setAttribute("height", tankH);
    $("tank-water").setAttribute("y", TANK_TOP + TANK_H - 2 - tankH);
    const normY = TANK_TOP + TANK_H - 2 - TANK_H * st.tank.normal_l / st.tank.capacity_l;
    $("tank-normal").setAttribute("y1", normY);
    $("tank-normal").setAttribute("y2", normY);
    $("tank-text").textContent = `${st.tank.water_l.toFixed(1)} L · ${st.tank.level_mm.toFixed(0)} mm`;

    // --- đường nước: bể → ống mềm → T → van → bậc 12 → … → bậc 1 → hồi → bể
    $("hose").classList.toggle("active", p.flow_lpm > EPS);
    $("pump-body").classList.toggle("on", p.on);
    ["A", "B"].forEach((s) => {
      const open = st.valves[s];
      pipeEls["valve" + s].classList.toggle("closed", !open);
      pipeEls["supply" + s].classList.toggle("active", st.strands[s].supply_lpm > EPS);
      const inflow = {};
      st.steps.filter((t) => t.strand === s).forEach((t) => { inflow[t.k] = t.inflow_lpm; });
      for (let k = 1; k <= STEPS - 1; k++) {
        pipeEls[`door${s}${k}`].classList.toggle("active", inflow[k] > EPS);
      }
      pipeEls["return" + s].classList.toggle("active", st.strands[s].return_lpm > EPS);
      $("valve-" + s).checked = open;
    });

    // --- số liệu tổng quan
    const sp = $("s-pump");
    sp.textContent = p.estop ? "DỪNG KHẨN CẤP" : (p.on ? (p.source === "timer" ? "ĐANG BƠM (hẹn giờ)" : "ĐANG BƠM") : "TẮT");
    sp.className = "v " + (p.on ? "on" : "off");
    $("s-mode").textContent = p.mode === "timer" ? "Hẹn giờ" : "Thủ công";
    $("s-tank").textContent = `${st.tank.water_l.toFixed(1)} L (${st.tank.pct.toFixed(0)}%)`;
    $("s-avg").textContent = `${st.avg_moisture.toFixed(1)} %`;
    $("s-pumped").textContent = `${st.totals.pumped_l.toFixed(1)} L`;
    $("s-recovered").textContent = `${st.totals.recovered_l.toFixed(1)} L`;
    $("s-lost").textContent = `${st.totals.lost_l.toFixed(3)} L`;
    $("s-energy").textContent = `${st.totals.energy_wh.toFixed(2)} Wh`;
    $("s-runtime").textContent = fmtDur(p.total_run_s);
    $("s-clock").textContent = `${st.clock.hhmm} (ngày ${st.clock.day}, ×${st.speed})`;
    $("s-device").textContent = p.device_connected ? "đã kết nối" : "chưa kết nối (DEMO MODE)";
    $("s-desired").textContent = p.desired_state;
    $("s-reported").textContent = p.reported_state + (p.device_connected ? "" : " (mô phỏng)");
    $("s-balance").textContent = st.totals.balance_error_l.toExponential(1);

    const al = $("alerts");
    al.innerHTML = "";
    st.alerts.forEach((a) => {
      const d = document.createElement("div");
      d.className = "alert " + a.level;
      d.textContent = a.msg;
      al.appendChild(d);
    });

    $("btn-estop").textContent = p.estop ? "NHẢ DỪNG KHẨN CẤP" : "DỪNG KHẨN CẤP";
    $("btn-estop").classList.toggle("engaged", p.estop);
    document.querySelectorAll('input[name="mode"]').forEach((r) => { r.checked = r.value === p.mode; });
    if (document.activeElement !== $("speed-select")) $("speed-select").value = String(st.speed);
    document.querySelectorAll("#config-form input").forEach((inp) => {
      if (document.activeElement !== inp && st.config[inp.name] !== undefined) inp.value = st.config[inp.name];
    });

    renderSchedules(st);

    const ev = $("events");
    ev.innerHTML = "";
    st.events.slice().reverse().forEach((e) => {
      const li = document.createElement("li");
      li.className = e.level;
      const t = document.createElement("span");
      t.className = "t";
      t.textContent = "T+" + fmtDur(e.t);
      li.appendChild(t);
      li.appendChild(document.createTextNode(e.msg));
      ev.appendChild(li);
    });

    renderDetail(st);
  }

  // ---------------------------------------------------------------- gọi API
  let toastTimer = null;
  function toast(msg, isError) {
    const el = $("toast");
    el.textContent = msg;
    el.className = "toast" + (isError ? " error" : "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
  }

  async function api(path, body, method) {
    try {
      const res = await fetch(path, {
        method: method || (body === undefined ? "GET" : "POST"),
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (data.state) render(data.state);
      if (data.message && (method || body !== undefined)) toast(data.message, !data.ok);
      return data;
    } catch (err) {
      toast("Không kết nối được máy chủ Flask.", true);
      return null;
    }
  }

  async function poll() {
    try {
      const res = await fetch("/api/state");
      if (!res.ok) throw new Error(res.status);
      render(await res.json());
    } catch (err) {
      toast("Mất kết nối với máy chủ Flask.", true);
    }
  }

  // ---------------------------------------------------------------- sự kiện
  $("btn-on").addEventListener("click", () => api("/api/pump", { action: "on" }));
  $("btn-off").addEventListener("click", () => api("/api/pump", { action: "off" }));
  $("btn-estop").addEventListener("click", () => {
    api("/api/estop", { engaged: lastState ? !lastState.pump.estop : true });
  });
  document.querySelectorAll('input[name="mode"]').forEach((r) => {
    r.addEventListener("change", () => api("/api/mode", { mode: r.value }));
  });
  ["A", "B"].forEach((s) => {
    $("valve-" + s).addEventListener("change", (e) => api("/api/valve", { strand: s, open: e.target.checked }));
  });
  $("speed-select").addEventListener("change", (e) => api("/api/config", { speed: Number(e.target.value) }));
  $("btn-refill").addEventListener("click", () => api("/api/refill", { liters: 3 }));
  $("btn-reset").addEventListener("click", () => {
    if (confirm("Đặt lại toàn bộ mô phỏng (kể cả lịch hẹn giờ và van) về trạng thái ban đầu?")) api("/api/reset", {});
  });
  $("config-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const body = {};
    document.querySelectorAll("#config-form input").forEach((inp) => {
      if (inp.value !== "") body[inp.name] = Number(inp.value);
    });
    api("/api/config", body);
  });
  $("sched-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const f = e.target;
    api("/api/schedules", { start: f.start.value, duration_s: Math.round(Number(f.minutes.value) * 60) });
  });

  // ---------------------------------------------------------------- khởi chạy
  poll();
  setInterval(poll, POLL_MS);
})();
