(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const REFRESH_MS = 3000;
  const H = 210, M = { l: 46, r: 16, t: 12, b: 26 };

  // Mỗi biểu đồ chỉ có một trục y (không dùng hai trục). Hai đại lượng khác thang đo nằm ở hai biểu đồ riêng.
  const CHARTS = [
    {
      id: "moisture", title: "Độ ẩm giá thể theo thời gian",
      sub: "Trung bình mỗi sợi, % thể tích giá thể (ước tính của mô hình, không phải cảm biến). Hai đường trùng nhau khi cả hai van cùng mở.",
      series: [
        { key: "vwc_a", name: "Sợi A", color: "var(--series-1)" },
        { key: "vwc_b", name: "Sợi B", color: "var(--series-2)" },
      ],
      minSpan: 4, fmt: (v) => v.toFixed(1) + " %", tickFmt: (v, d) => v.toFixed(d),
    },
    {
      id: "flow", title: "Lưu lượng nước",
      sub: "L/phút: nước bơm lên trụ và nước hồi về bể",
      series: [
        { key: "pump_flow_lpm", name: "Bơm đưa lên", color: "var(--series-1)" },
        { key: "return_lpm", name: "Hồi về bể", color: "var(--series-2)" },
      ],
      step: true, zero: true, minSpan: 1, fmt: (v) => v.toFixed(2) + " L/phút", tickFmt: (v, d) => v.toFixed(d),
    },
    {
      id: "tank", title: "Mực nước trong bể",
      sub: "Lít (mức thường khoảng 17 L, tối đa khoảng 28 L theo bản vẽ)",
      series: [{ key: "tank_l", name: "Nước trong bể", color: "var(--series-1)" }],
      area: true, minSpan: 3, fmt: (v) => v.toFixed(1) + " L", tickFmt: (v, d) => v.toFixed(d),
    },
    {
      id: "pump", title: "Trạng thái bơm",
      sub: "BẬT / TẮT theo từng thời điểm lấy mẫu",
      series: [{ key: "pump_on", name: "Bơm", color: "var(--series-1)" }],
      step: true, area: true, fixed: [0, 1.2], ticks: [0, 1],
      fmt: (v) => (v >= 0.5 ? "BẬT" : "TẮT"), tickFmt: (v) => (v >= 0.5 ? "BẬT" : "TẮT"),
    },
    {
      id: "energy", title: "Điện năng ước tính (tích lũy)",
      sub: "Wh, tính từ công suất bơm giả định × thời gian bơm",
      series: [{ key: "energy_wh", name: "Điện năng", color: "var(--series-1)" }],
      area: true, zero: true, minSpan: 0.5, fmt: (v) => v.toFixed(2) + " Wh", tickFmt: (v, d) => v.toFixed(d),
    },
  ];

  const state = { windowS: 7200, data: null, charts: {} };

  const el = (tag, attrs, text) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const html = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };

  function niceTicks(min, max, count) {
    const span = max - min || 1;
    const raw = span / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
    const lo = Math.floor(min / step + 1e-9) * step;
    const hi = Math.ceil(max / step - 1e-9) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
    const decimals = step >= 1 ? 0 : Math.min(3, Math.ceil(-Math.log10(step)));
    return { ticks, lo: ticks[0], hi: ticks[ticks.length - 1], decimals };
  }

  function clockLabel(t, startMin, withDay) {
    const abs = startMin * 60 + t;
    const day = Math.floor(abs / 86400) + 1;
    const m = Math.floor((abs % 86400) / 60);
    const hh = String(Math.floor(m / 60)).padStart(2, "0"), mm = String(m % 60).padStart(2, "0");
    return withDay ? `Ngày ${day} · ${hh}:${mm}` : `${hh}:${mm}`;
  }

  // ---------------------------------------------------------------- dựng khung các thẻ biểu đồ
  function buildCards() {
    const grid = document.getElementById("chart-grid");
    grid.innerHTML = "";
    CHARTS.forEach((c) => {
      const card = html("div", "chart-card");
      card.appendChild(html("h3", "", c.title));
      card.appendChild(html("p", "sub", c.sub));
      if (c.series.length >= 2) {
        const lg = html("div", "legend");
        c.series.forEach((s) => {
          const item = html("span", "");
          const key = html("span", "key");
          key.style.background = s.color;
          item.append(key, document.createTextNode(s.name));
          lg.appendChild(item);
        });
        card.appendChild(lg);
      }
      const wrap = html("div", "plot-wrap");
      card.appendChild(wrap);
      const det = document.createElement("details");
      det.appendChild(html("summary", "", "Xem dạng bảng"));
      const scroll = html("div", "table-scroll");
      det.appendChild(scroll);
      card.appendChild(det);
      grid.appendChild(card);
      state.charts[c.id] = { cfg: c, card, wrap, scroll, idx: null };
      new ResizeObserver(() => draw(c.id)).observe(wrap);
    });
  }

  // ---------------------------------------------------------------- vẽ một biểu đồ
  function draw(id) {
    const ch = state.charts[id];
    const data = state.data;
    if (!ch) return;
    const c = ch.cfg;
    const w = Math.max(280, Math.floor(ch.wrap.clientWidth || 420));
    ch.wrap.innerHTML = "";
    if (!data || data.points.length < 2) {
      ch.wrap.appendChild(html("div", "plot-empty", "Chưa đủ dữ liệu. Hãy để mô phỏng chạy một lúc hoặc tăng tốc độ."));
      ch.scroll.innerHTML = "";
      return;
    }
    const pts = data.points;
    const startMin = data.clock_start_min;
    const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
    const spanDays = (startMin * 60 + t1) / 86400 - (startMin * 60 + t0) / 86400;
    const withDay = Math.floor((startMin * 60 + t1) / 86400) !== Math.floor((startMin * 60 + t0) / 86400) || spanDays > 1;

    // miền y
    let ticks, lo, hi, dec = 0;
    if (c.fixed) {
      lo = c.fixed[0]; hi = c.fixed[1]; ticks = c.ticks;
    } else {
      let mn = Infinity, mx = -Infinity;
      pts.forEach((p) => c.series.forEach((s) => { mn = Math.min(mn, p[s.key]); mx = Math.max(mx, p[s.key]); }));
      if (c.zero) mn = Math.min(0, mn);
      if (mx - mn < c.minSpan) { const mid = (mx + mn) / 2; mn = c.zero ? mn : mid - c.minSpan / 2; mx = Math.max(mx, mn + c.minSpan); }
      const nt = niceTicks(mn, mx, 4);
      ticks = nt.ticks; lo = nt.lo; hi = nt.hi; dec = nt.decimals;
    }
    const iw = w - M.l - M.r, ih = H - M.t - M.b;
    const xs = (t) => M.l + (t1 === t0 ? 0 : ((t - t0) / (t1 - t0)) * iw);
    const ys = (v) => M.t + ih - ((v - lo) / (hi - lo)) * ih;

    const svg = el("svg", {
      viewBox: `0 0 ${w} ${H}`, role: "img", tabindex: "0",
      "aria-label": `${c.title}. Dùng phím mũi tên trái phải để xem từng điểm.`,
    });

    // lưới ngang mảnh, đặc, nhạt
    ticks.forEach((v) => {
      svg.appendChild(el("line", { class: v === lo ? "vz-axis" : "vz-grid", x1: M.l, x2: w - M.r, y1: ys(v), y2: ys(v) }));
      svg.appendChild(el("text", { class: "vz-tick", x: M.l - 8, y: ys(v) + 4, "text-anchor": "end" }, c.tickFmt(v, dec)));
    });

    // nhãn trục x
    const nx = Math.max(2, Math.min(5, Math.floor(iw / 90)));
    for (let i = 0; i <= nx; i++) {
      const t = t0 + ((t1 - t0) * i) / nx;
      const anchor = i === 0 ? "start" : i === nx ? "end" : "middle";
      svg.appendChild(el("text", { class: "vz-tick", x: xs(t), y: H - 6, "text-anchor": anchor }, clockLabel(t, startMin, withDay && nx <= 3)));
    }

    // đường dữ liệu (độ dày 2 px) + vùng tô 10% khi chỉ có một chuỗi
    const pathFor = (key) => {
      let d = "";
      pts.forEach((p, i) => {
        const x = xs(p.t), y = ys(p[key]);
        if (i === 0) d += `M${x.toFixed(1)} ${y.toFixed(1)}`;
        else if (c.step) d += `H${x.toFixed(1)}V${y.toFixed(1)}`;
        else d += `L${x.toFixed(1)} ${y.toFixed(1)}`;
      });
      return d;
    };
    c.series.forEach((s) => {
      const d = pathFor(s.key);
      if (c.area && c.series.length === 1) {
        const a = el("path", { d: `${d}L${xs(t1).toFixed(1)} ${ys(lo)}L${xs(t0).toFixed(1)} ${ys(lo)}Z`, fill: s.color, opacity: "0.1" });
        svg.appendChild(a);
      }
      const line = el("path", { class: "vz-line", d, stroke: s.color });
      svg.appendChild(line);
      // chấm cuối: r = 4.5, viền 2 px màu nền
      const last = pts[pts.length - 1];
      svg.appendChild(el("circle", { cx: xs(last.t), cy: ys(last[s.key]), r: 4.5, fill: s.color, stroke: "var(--viz-surface)", "stroke-width": 2 }));
    });

    // lớp tương tác: crosshair bắt vào điểm gần nhất
    const cross = el("line", { class: "vz-cross", y1: M.t, y2: M.t + ih, visibility: "hidden" });
    const dots = c.series.map((s) => el("circle", { r: 4.5, fill: s.color, stroke: "var(--viz-surface)", "stroke-width": 2, visibility: "hidden" }));
    svg.appendChild(cross);
    dots.forEach((d) => svg.appendChild(d));
    const hit = el("rect", { x: M.l, y: M.t, width: iw, height: ih, fill: "transparent" });
    svg.appendChild(hit);
    ch.wrap.appendChild(svg);

    const tip = html("div", "vz-tip");
    tip.hidden = true;
    ch.wrap.appendChild(tip);

    const nearest = (px) => {
      let best = 0, bd = Infinity;
      pts.forEach((p, i) => { const dd = Math.abs(xs(p.t) - px); if (dd < bd) { bd = dd; best = i; } });
      return best;
    };
    const show = (i) => {
      ch.idx = i;
      const p = pts[i], x = xs(p.t);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.setAttribute("visibility", "visible");
      c.series.forEach((s, k) => {
        dots[k].setAttribute("cx", x); dots[k].setAttribute("cy", ys(p[s.key])); dots[k].setAttribute("visibility", "visible");
      });
      tip.innerHTML = "";
      tip.appendChild(html("div", "tip-time", clockLabel(p.t, startMin, true)));
      c.series.forEach((s) => {
        const row = html("div", "tip-row");
        const key = html("span", "tip-key");
        key.style.background = s.color;
        row.append(key, html("span", "tip-val", c.fmt(p[s.key])), html("span", "tip-name", s.name));
        tip.appendChild(row);
      });
      tip.hidden = false;
      const tw = tip.offsetWidth;
      let left = x + 12;
      if (left + tw > w - 4) left = x - tw - 12;
      tip.style.left = Math.max(4, left) + "px";
      tip.style.top = (M.t + 4) + "px";
    };
    const hide = () => {
      cross.setAttribute("visibility", "hidden");
      dots.forEach((d) => d.setAttribute("visibility", "hidden"));
      tip.hidden = true;
    };
    const toX = (ev) => {
      const r = svg.getBoundingClientRect();
      return ((ev.clientX - r.left) / r.width) * w;
    };
    hit.addEventListener("pointermove", (ev) => show(nearest(toX(ev))));
    hit.addEventListener("pointerleave", hide);
    svg.addEventListener("focus", () => show(ch.idx === null ? pts.length - 1 : Math.min(ch.idx, pts.length - 1)));
    svg.addEventListener("blur", hide);
    svg.addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      ev.preventDefault();
      const cur = ch.idx === null ? pts.length - 1 : ch.idx;
      show(Math.max(0, Math.min(pts.length - 1, cur + (ev.key === "ArrowRight" ? 1 : -1))));
    });

    // dạng bảng: mọi giá trị đều đọc được mà không cần di chuột
    ch.scroll.innerHTML = "";
    const table = document.createElement("table");
    const thead = document.createElement("tr");
    thead.appendChild(html("th", "", "Thời điểm"));
    c.series.forEach((s) => thead.appendChild(html("th", "", s.name)));
    table.appendChild(thead);
    pts.slice(-40).reverse().forEach((p) => {
      const tr = document.createElement("tr");
      tr.appendChild(html("td", "", clockLabel(p.t, startMin, true)));
      c.series.forEach((s) => tr.appendChild(html("td", "", c.fmt(p[s.key]))));
      table.appendChild(tr);
    });
    ch.scroll.appendChild(table);
  }

  function drawAll() { CHARTS.forEach((c) => draw(c.id)); }

  // ---------------------------------------------------------------- lấy dữ liệu
  let fetching = false;
  async function refresh() {
    if (fetching) return;
    fetching = true;
    Object.values(state.charts).forEach((c) => c.card.classList.add("loading"));
    try {
      const q = state.windowS ? `window_s=${state.windowS}&` : "";
      const res = await fetch(`/api/history?${q}limit=300`);
      if (res.ok) {
        state.data = await res.json();
        drawAll();
      }
    } catch (err) {
      /* giữ nguyên hình cũ khi mất kết nối */
    } finally {
      Object.values(state.charts).forEach((c) => c.card.classList.remove("loading"));
      fetching = false;
    }
  }

  // bộ lọc khoảng thời gian: một hàng phía trên, áp dụng cho mọi biểu đồ
  document.querySelectorAll(".filter-row .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.windowS = Number(btn.dataset.window);
      document.querySelectorAll(".filter-row .chip").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      refresh();
    });
  });

  buildCards();
  refresh();
  setInterval(refresh, REFRESH_MS);
  window.AdnCharts = { refresh };
})();
