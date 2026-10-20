/* Macro Terminal front end. Plain JavaScript, no libraries; data comes from data.js (window.TERMINAL). */
(function () {
  "use strict";
  const D = window.TERMINAL || {};
  const $ = (s) => document.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; };
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  const TABS = ["macro", "gp", "fa", "risk", "brief", "ask", "news", "status"];
  const TAB_ALIASES = { MACRO: "macro", ECO: "macro", GP: "gp", PRICE: "gp", CHART: "gp", FA: "fa", FUND: "fa", RISK: "risk", RV: "risk", BRIEF: "brief", AI: "brief", ASK: "ask", Q: "ask", NEWS: "news", NL: "news", STATUS: "status", DATA: "status" };
  const watch = D.watchlist || [];
  const byTicker = Object.fromEntries(watch.map((w) => [w.ticker, w]));
  const state = { tab: "macro", ticker: "PETR4", range: 252, riskRegion: "BR" };

  try {
    const saved = JSON.parse(localStorage.getItem("mtrm") || "{}");
    if (TABS.includes(saved.tab)) state.tab = saved.tab;
    if (byTicker[saved.ticker]) state.ticker = saved.ticker;
  } catch (e) { /* storage unavailable: defaults */ }
  // a link like index.html#fa/VALE3 opens that function and security
  const [hTab, hTicker] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (TABS.includes(hTab)) state.tab = hTab;
  if (hTicker && byTicker[hTicker.toUpperCase()]) state.ticker = hTicker.toUpperCase();

  // ---------------------------------------------------------------- formatting
  const fmt = (v, nd = 2) => (v == null || Number.isNaN(v) ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: nd, maximumFractionDigits: nd }));
  const sgn = (v, nd = 2, suf = "") => (v == null ? "—" : (v > 0 ? "+" : "") + fmt(v, nd) + suf);
  const cls = (v) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
  const big = (v) => { if (v == null) return "—"; const a = Math.abs(v); if (a >= 1e9) return fmt(v / 1e9, 2) + "B"; if (a >= 1e6) return fmt(v / 1e6, 2) + "M"; if (a >= 1e3) return fmt(v / 1e3, 1) + "K"; return fmt(v, 0); };

  function spark(values, w = 90, h = 18) {
    const v = (values || []).filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), r = hi - lo || 1;
    const pts = v.map((x, i) => `${(i / (v.length - 1)) * (w - 2) + 1},${h - 1 - ((x - lo) / r) * (h - 2)}`).join(" ");
    const col = v[v.length - 1] >= v[0] ? css("--amber") : css("--orange");
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><polyline fill="none" stroke="${col}" stroke-width="1.2" points="${pts}"/></svg>`;
  }

  // ---------------------------------------------------------------- canvas helpers
  function setupCanvas(canvas, height) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || canvas.parentElement.clientWidth;
    canvas.width = Math.max(1, Math.floor(w * dpr));
    canvas.height = Math.floor(height * dpr);
    canvas.style.height = height + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = "10px " + css("--mono");
    return { ctx, w, h: height };
  }

  function niceTicks(lo, hi, n) {
    const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return out;
  }

  // ---------------------------------------------------------------- header, lists, footer
  function renderHeader() {
    $("#asof").textContent = D.as_of ? "PX AS OF " + D.as_of : "";
    const st = Object.values(D.status || {});
    const bad = st.filter((s) => s.status !== "live").length;
    const h = $("#health");
    h.textContent = bad ? bad + " STALE" : "ALL LIVE";
    h.className = "pill " + (bad ? "warn" : "ok");
    h.title = "Data status — see the STATUS tab";
    h.style.cursor = "pointer";
    h.onclick = () => go({ tab: "status" });
    const tick = () => { const d = new Date(); $("#clock").textContent = d.toLocaleTimeString("en-GB", { hour12: false }); };
    tick(); setInterval(tick, 1000);
  }

  function renderWatchlist() {
    const box = $("#watchlist");
    box.innerHTML = "";
    const groups = [["BR", "BRAZIL · B3"], ["US", "UNITED STATES"], ["IDX", "INDICES"], ["FX", "CURRENCY"]];
    for (const [region, label] of groups) {
      const rows = watch.filter((w) => w.region === region);
      if (!rows.length) continue;
      box.appendChild(el("div", "wl-group", label));
      for (const w of rows) {
        const r = el("div", "wl-row" + (w.ticker === state.ticker ? " sel" : ""));
        r.title = `${w.name} · last ${w.date || "n/a"}`;
        r.innerHTML = `<span class="mark">${w.ticker === state.ticker ? "▸" : ""}</span>` +
          `<span class="tk">${esc(w.ticker)}${w.stale ? ' <span class="stale">STALE</span>' : ""}</span>` +
          `<span class="px num">${fmt(w.last, w.region === "FX" ? 4 : 2)}</span>` +
          `<span class="num ${cls(w.chg_pct)}">${sgn(w.chg_pct, 2, "%")}</span>`;
        r.onclick = () => go({ ticker: w.ticker });
        box.appendChild(r);
      }
    }
    const p = (D.status || {}).prices;
    $("#watch-note").innerHTML = p ? `Daily closes · ${esc(p.source)}<br>Fetched ${esc((p.fetched_at || "").replace("T", " ").slice(0, 16))} UTC` : "";
  }

  function renderFilings() {
    const box = $("#filings");
    box.innerHTML = "";
    const all = D.filings || [];
    const isBR = (byTicker[state.ticker] || {}).region === "BR";
    const mine = isBR ? all.filter((f) => f.ticker === state.ticker) : [];
    const list = (mine.length ? mine.concat(all.filter((f) => f.ticker !== state.ticker)) : all).slice(0, 60);
    if (!list.length) { box.innerHTML = '<div class="view dim">No filings in cache.</div>'; return; }
    for (const f of list) {
      const a = el("a", "filing" + (f.ticker === state.ticker ? " hl" : ""));
      a.href = f.link || "#"; a.target = "_blank"; a.rel = "noopener";
      a.title = `${f.category_en}: ${f.subject}`;
      a.innerHTML = `<span class="fd">${esc(f.date)}</span><span class="ft">${esc(f.ticker)}</span><span class="fc">${esc(f.category)}</span><span class="fs">${esc(f.subject || f.category_en)}</span>`;
      box.appendChild(a);
    }
  }

  function renderAlerts() {
    const al = D.alerts || [];
    const bar = $("#alertbar");
    if (!al.length) { bar.innerHTML = ""; return; }
    bar.innerHTML = `<span class="lab">ALERTS ${al.length}</span>` + al.map((a) => `<span class="a ${a.level}" title="Rule: ${esc(a.rule)}"><b>${esc(a.code)}</b> ${esc(a.text)}</span>`).join('<span class="sep">|</span>');
    bar.onclick = () => go({ tab: "macro" });
  }

  function renderFooter() {
    const st = D.status || {};
    const parts = [`<span><b>SOURCES</b> BCB SGS · Focus · FRED · Yahoo Finance · CVM</span>`];
    for (const [k, s] of Object.entries(st)) parts.push(`<span>${esc(k.toUpperCase())} <span class="${s.status === "live" ? "up" : "orange"}">${esc(s.status.toUpperCase())}</span></span>`);
    parts.push(`<span>BUILT ${esc((D.generated_at || "").replace("T", " ").slice(0, 16))} UTC</span>`);
    parts.push(`<span>Public data, not investment advice</span>`);
    $("#status-line").innerHTML = parts.join("");
  }

  // ---------------------------------------------------------------- MACRO
  function macroTable(rows) {
    if (!rows || !rows.length) return '<div class="dim">No data in cache.</div>';
    let h = '<table class="t"><thead><tr><th>Indicator</th><th class="num">Last</th><th class="num">Chg</th><th>Date</th><th class="trend">Trend</th></tr></thead><tbody>';
    for (const r of rows) {
      h += `<tr title="${esc(r.source || "")} · ${esc(r.unit)}"><td class="lbl">${esc(r.label)}</td><td class="num">${fmt(r.last)}</td>` +
        `<td class="num ${cls(r.chg)}">${r.chg == null ? "" : sgn(r.chg)}</td><td class="dim">${esc(r.date)}</td><td class="trend">${spark(r.spark, 64)}</td></tr>`;
    }
    return h + "</tbody></table>";
  }

  function viewMacro(v) {
    const m = D.macro || {};
    let h = "";
    const b = D.brief;
    if (b && b.brief) h += `<div class="teaser" id="teaser"><span class="k">AI BRIEF</span>${esc(b.brief.headline)} <span class="dim">· ${esc(b.date)} ▸ 5 BRIEF</span></div>`;
    const al = D.alerts || [];
    if (al.length) h += `<div class="sec-h">ALERTS <span class="dim">rule-based, no AI</span></div><ul class="issues alert-list">${al.map((a) => `<li class="${a.level}" title="Rule: ${esc(a.rule)}"><b>${esc(a.code)}</b> ${esc(a.text)}</li>`).join("")}</ul>`;
    h += '<div class="grid2"><div><div class="sec-h">BRAZIL <span class="dim">BCB SGS</span></div>' + macroTable(m.br) +
      '</div><div><div class="sec-h">UNITED STATES <span class="dim">FRED</span></div>' + macroTable(m.us) + "</div></div>";
    const f = m.focus || [];
    h += `<div class="sec-h">FOCUS SURVEY · MARKET EXPECTATIONS <span class="dim">median, all respondents · ${esc((f[0] || {}).date || "")}</span></div>`;
    if (f.length) {
      h += '<table class="t"><thead><tr><th>Indicator</th><th>Year</th><th class="num">Median</th><th class="num">4w ago</th><th class="num">Chg</th><th class="num">Resp.</th></tr></thead><tbody>';
      for (const r of f) h += `<tr><td class="lbl">${esc(r.label)}</td><td>${r.year}</td><td class="num">${fmt(r.median)}</td><td class="num dim">${fmt(r.median_4w_ago)}</td><td class="num ${cls(r.chg_4w)}">${sgn(r.chg_4w)}</td><td class="num dim">${r.respondents == null ? "—" : r.respondents}</td></tr>`;
      h += "</tbody></table>";
    } else h += '<div class="dim">No Focus data in cache.</div>';
    h += '<div class="note">Chg = change from the previous observation (pp for rates). Daily series show month-end points in the trend line. Real rate = Selic target minus IPCA 12m, both at their latest values.</div>';
    v.innerHTML = h;
    const t = $("#teaser"); if (t) t.onclick = () => go({ tab: "brief" });
  }

  // ---------------------------------------------------------------- GP (price chart)
  function viewGP(v) {
    const c = (D.charts || {})[state.ticker];
    const w = byTicker[state.ticker] || {};
    if (!c) { v.innerHTML = '<div class="dim">No price history in cache for this security.</div>'; return; }
    const nd = w.region === "FX" ? 4 : 2;
    v.innerHTML =
      `<div class="quote"><div class="big">${fmt(w.last, nd)}</div><div class="${cls(w.chg_pct)}">${sgn(w.chg, nd)} (${sgn(w.chg_pct, 2, "%")})</div>` +
      `<div class="kv"><span>52W HIGH</span>${fmt(c.hi52, nd)}</div><div class="kv"><span>52W LOW</span>${fmt(c.lo52, nd)}</div>` +
      `<div class="kv"><span>AVG VOL 20D</span>${big(c.avg_vol_20)}</div><div class="kv"><span>LAST</span>${esc(w.date || "")}</div>` +
      `<div class="ranges" id="ranges">${[["1M", 21], ["3M", 63], ["6M", 126], ["1Y", 252]].map(([l, n]) => `<button data-n="${n}" class="${state.range === n ? "on" : ""}">${l}</button>`).join("")}</div></div>` +
      `<div class="legend"><span><i style="background:${css("--amber")}"></i>CLOSE</span><span><i style="background:${css("--up")}"></i>MA20</span><span><i style="background:${css("--cyan")}"></i>MA50</span><span><i style="background:${css("--white")}"></i>MA200</span></div>` +
      `<div class="chart-wrap"><canvas id="px"></canvas><canvas id="vol"></canvas><div class="tip" id="tip"></div></div>` +
      `<div class="note">Daily closes adjusted for dividends and splits (Yahoo Finance). Moving averages over trading days.</div>`;
    document.querySelectorAll("#ranges button").forEach((b) => (b.onclick = () => { state.range = +b.dataset.n; render(); }));
    drawPrice(c);
  }

  function drawPrice(c) {
    const n = Math.min(state.range, c.dates.length);
    const s = c.dates.length - n;
    const sl = (a) => a.slice(s);
    const dates = sl(c.dates), close = sl(c.close), vol = sl(c.volume);
    const lines = [[sl(c.ma200), css("--white"), 1], [sl(c.ma50), css("--cyan"), 1], [sl(c.ma20), css("--up"), 1], [close, css("--amber"), 1.6]];
    const pxH = Math.max(220, Math.min(420, window.innerHeight * 0.45));
    const { ctx, w, h } = setupCanvas($("#px"), pxH);
    const pad = { l: 8, r: 58, t: 8, b: 18 };
    const vals = lines.flatMap((l) => l[0]).filter((x) => x != null);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const m = (hi - lo) * 0.06 || 1; lo -= m; hi += m;
    const X = (i) => pad.l + (i / Math.max(1, n - 1)) * (w - pad.l - pad.r);
    const Y = (y) => pad.t + (1 - (y - lo) / (hi - lo)) * (h - pad.t - pad.b);
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#1d1606"; ctx.fillStyle = css("--dim"); ctx.lineWidth = 1;
    for (const t of niceTicks(lo, hi, 5)) { const y = Math.round(Y(t)) + 0.5; ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke(); ctx.fillText(fmt(t, t < 10 ? 2 : 0), w - pad.r + 6, y + 3); }
    const step = Math.max(1, Math.round(n / Math.max(2, Math.min(6, Math.floor((w - pad.l - pad.r) / 75)))));
    for (let i = 0; i < n; i += step) if (X(i) <= w - pad.r - 50) ctx.fillText(dates[i].slice(2), X(i), h - 4);
    // area under the close
    const g = ctx.createLinearGradient(0, pad.t, 0, h - pad.b);
    g.addColorStop(0, "rgba(255,181,46,0.25)"); g.addColorStop(1, "rgba(255,181,46,0)");
    ctx.beginPath(); close.forEach((y, i) => (i ? ctx.lineTo(X(i), Y(y)) : ctx.moveTo(X(i), Y(y))));
    ctx.lineTo(X(n - 1), h - pad.b); ctx.lineTo(X(0), h - pad.b); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
    for (const [arr, col, lw] of lines) {
      ctx.beginPath(); ctx.strokeStyle = col; ctx.lineWidth = lw; let started = false;
      arr.forEach((y, i) => { if (y == null) { started = false; return; } if (!started) { ctx.moveTo(X(i), Y(y)); started = true; } else ctx.lineTo(X(i), Y(y)); });
      ctx.stroke();
    }
    // last price tag
    const ly = Y(close[n - 1]);
    ctx.fillStyle = css("--amber"); ctx.fillRect(w - pad.r + 2, ly - 7, pad.r - 4, 14);
    ctx.fillStyle = "#000"; ctx.fillText(fmt(close[n - 1], close[n - 1] < 10 ? 3 : 2), w - pad.r + 5, ly + 3);

    // volume
    const vc = setupCanvas($("#vol"), 70);
    const vmax = Math.max(1, ...vol);
    vc.ctx.fillStyle = "#000"; vc.ctx.fillRect(0, 0, vc.w, vc.h);
    const bw = Math.max(1, (w - pad.l - pad.r) / n - 1);
    vol.forEach((x, i) => {
      const up = i === 0 || close[i] >= close[i - 1];
      vc.ctx.fillStyle = up ? "rgba(255,181,46,0.55)" : "rgba(251,139,30,0.35)";
      const bh = (x / vmax) * (vc.h - 14);
      vc.ctx.fillRect(X(i) - bw / 2, vc.h - bh, bw, bh);
    });
    vc.ctx.fillStyle = css("--dim"); vc.ctx.fillText("VOLUME  max " + big(vmax), pad.l, 10);

    // crosshair tooltip
    const cv = $("#px"), tip = $("#tip");
    const move = (ev) => {
      const r = cv.getBoundingClientRect();
      const px = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - pad.l) / (w - pad.l - pad.r)) * (n - 1))));
      tip.style.display = "block";
      tip.innerHTML = `${dates[i]} · <span class="amber">${fmt(close[i], close[i] < 10 ? 3 : 2)}</span> · vol ${big(vol[i])}`;
      tip.style.left = Math.min(X(i) + 8, w - 200) + "px"; tip.style.top = "6px";
    };
    cv.onmousemove = move; cv.ontouchstart = move; cv.ontouchmove = move;
    cv.onmouseleave = () => (tip.style.display = "none");
  }

  // ---------------------------------------------------------------- FA (fundamentals)
  function viewFA(v) {
    const f = (D.fundamentals || {})[state.ticker];
    const avail = Object.keys(D.fundamentals || {});
    if (!f) {
      const why = (D.no_fundamentals || []).includes(state.ticker) ? "Banks file a different income statement layout (no net revenue line); not covered."
        : "Fundamentals come from CVM filings, so they cover Brazilian listed companies only.";
      v.innerHTML = `<div class="dim">${esc(state.ticker)}: ${why}</div><div class="sec-h">AVAILABLE</div><div class="seg">${avail.map((t) => `<button data-t="${t}">${t}</button>`).join("")}</div>`;
      document.querySelectorAll(".seg button").forEach((b) => (b.onclick = () => go({ ticker: b.dataset.t })));
      return;
    }
    const labels = { revenue: "Net revenue", gross_profit: "Gross profit", ebit: "EBIT", net_income: "Net income", gross_margin: "Gross margin %", ebit_margin: "EBIT margin %", net_margin: "Net margin %" };
    let h = `<div class="sec-h">${esc(state.ticker)} INCOME STATEMENT · QUARTERLY <span class="dim">${esc(f.unit)} · consolidated · CVM ITR/DFP</span></div>`;
    h += '<div style="overflow-x:auto"><table class="t"><thead><tr><th></th>' + f.periods.map((p) => `<th class="num">${p}</th>`).join("") + "</tr></thead><tbody>";
    for (const [k, lab] of Object.entries(labels)) {
      const pct = k.endsWith("margin");
      h += `<tr><td class="lbl">${lab}</td>` + f.rows[k].map((x) => `<td class="num ${x != null && x < 0 ? "down" : ""}">${fmt(x, pct ? 1 : 0)}</td>`).join("") + "</tr>";
    }
    h += "</tbody></table></div>";
    h += `<div class="legend" style="margin-top:12px"><span><i style="background:${css("--orange")}"></i>NET REVENUE</span><span><i style="background:${css("--cyan")}"></i>NET INCOME</span></div><canvas id="bars"></canvas>`;
    h += '<div class="note">Q4 is not filed as a quarter: Q4 = annual (DFP) minus nine months year-to-date (ITR Q3). Values as filed (latest version).</div>';
    v.innerHTML = h;
    drawBars(f);
  }

  function drawBars(f) {
    const { ctx, w, h } = setupCanvas($("#bars"), 220);
    const a = f.rows.revenue, b = f.rows.net_income, n = f.periods.length;
    const vals = a.concat(b).filter((x) => x != null);
    const hi = Math.max(0, ...vals), lo = Math.min(0, ...vals);
    const pad = { l: 8, r: 64, t: 8, b: 18 };
    const Y = (y) => pad.t + (1 - (y - lo) / (hi - lo || 1)) * (h - pad.t - pad.b);
    ctx.fillStyle = "#000"; ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "#1d1606"; ctx.fillStyle = css("--dim");
    for (const t of niceTicks(lo, hi, 4)) { const y = Math.round(Y(t)) + 0.5; ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke(); ctx.fillText(Math.abs(t) < 1e-9 ? "0" : big(t * 1e6).replace(/\.\d+/, ""), w - pad.r + 6, y + 3); }
    const slot = (w - pad.l - pad.r) / n, bw = Math.min(28, slot * 0.32);
    for (let i = 0; i < n; i++) {
      const x0 = pad.l + i * slot + slot / 2;
      [[a[i], css("--orange"), -bw - 1], [b[i], css("--cyan"), 1]].forEach(([val, col, dx]) => {
        if (val == null) return;
        ctx.fillStyle = col; const y0 = Y(0), y1 = Y(val);
        ctx.fillRect(x0 + dx, Math.min(y0, y1), bw, Math.abs(y1 - y0));
      });
      ctx.fillStyle = css("--dim"); ctx.fillText(f.periods[i], x0 - 18, h - 4);
    }
  }

  // ---------------------------------------------------------------- RISK
  function heatColor(x) {
    if (x == null) return "#111";
    if (x >= 0) { const a = 0.15 + 0.85 * x; return `rgba(35,209,96,${a.toFixed(2)})`; }
    const a = 0.15 + 0.85 * -x; return `rgba(255,77,77,${a.toFixed(2)})`;
  }

  function viewRisk(v) {
    const region = (byTicker[state.ticker] || {}).region;
    if (region === "BR" || region === "US") state.riskRegion = region;
    const R = (D.risk || {})[state.riskRegion];
    if (!R) { v.innerHTML = '<div class="dim">No risk data in cache.</div>'; return; }
    let h = `<div class="sec-h">RISK METRICS · ${state.riskRegion === "BR" ? "BRAZIL vs IBOVESPA" : "US vs S&amp;P 500"} <span class="seg">${["BR", "US"].map((r) => `<button data-r="${r}" class="${r === state.riskRegion ? "on" : ""}">${r}</button>`).join("")}</span></div>`;
    h += `<div class="note" style="margin:0 0 6px">Trailing ${R.rows[0] ? R.rows[0].obs : "—"} daily returns · ${esc(R.window)} · risk-free = ${esc(R.rf_label)} ${fmt(R.rf)}%</div>`;
    h += '<table class="t"><thead><tr><th>Ticker</th><th class="num">Vol (ann.)</th><th class="num">Beta</th><th class="num">Max DD</th><th class="num">Sharpe</th><th class="num">1Y ret</th></tr></thead><tbody>';
    for (const r of R.rows) h += `<tr class="${r.ticker === state.ticker ? "sel" : ""}"><td class="lbl">${r.ticker === state.ticker ? "▸ " : ""}${esc(r.ticker)}</td><td class="num">${fmt(r.vol, 1)}%</td><td class="num">${fmt(r.beta)}</td><td class="num down">${fmt(r.mdd, 1)}%</td><td class="num ${cls(r.sharpe)}">${fmt(r.sharpe)}</td><td class="num ${cls(r.ret_1y)}">${sgn(r.ret_1y, 1, "%")}</td></tr>`;
    h += "</tbody></table>";
    const c = R.corr;
    h += `<div class="sec-h">CORRELATION OF DAILY RETURNS <span class="dim">${esc(R.window)}</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th></th>${c.tickers.map((t) => `<th>${esc(t)}</th>`).join("")}</tr></thead><tbody>`;
    c.tickers.forEach((a, i) => { h += `<tr><td class="lbl">${esc(a)}</td>` + c.matrix[i].map((x) => `<td class="c" style="background:${heatColor(x)};color:${x != null && Math.abs(x) >= 0.55 ? "#000" : "#e9e9e9"}">${x == null ? "—" : fmt(x)}</td>`).join("") + "</tr>"; });
    h += "</tbody></table></div>";
    h += '<div class="note">Vol = std. dev. × √252. Beta = cov(stock, index) / var(index). Max DD = worst fall from a running peak. Sharpe = (mean daily return × 252 − risk-free) / vol. Each market uses its own trading calendar.</div>';
    v.innerHTML = h;
    document.querySelectorAll(".seg button").forEach((b) => (b.onclick = () => { state.riskRegion = b.dataset.r; const first = (D.risk[b.dataset.r].rows[0] || {}).ticker; go({ ticker: first || state.ticker }); }));
  }

  // ---------------------------------------------------------------- BRIEF
  function viewBrief(v) {
    const b = D.brief;
    if (!b || !b.brief) { v.innerHTML = '<div class="dim">No AI brief yet. Run <code>python -m macro_terminal brief</code>.</div>'; return; }
    const x = b.brief, m = b.meta || {};
    let h = `<div class="sec-h">AI BRIEF · ${esc(b.date)} <span class="dim">${esc(m.mode === "live" ? "written today by the API" : "recorded answer (" + (m.recorded_at || "").slice(0, 10) + ")")}</span></div>`;
    h += `<div class="headline">${esc(x.headline)}</div><ol class="points">${x.points.map((p) => `<li>${esc(p)}</li>`).join("")}</ol>`;
    h += `<div class="sec-h">RISKS TO WATCH</div><ul class="risks">${x.risks.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
    if (x.data_caveats && x.data_caveats.length) h += `<div class="sec-h">DATA CAVEATS</div><ul class="issues">${x.data_caveats.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
    h += `<div class="meta"><div><span>MODEL</span>${esc(m.model || "")}</div><div><span>MODE</span>${esc(m.mode || "")}</div>` +
      `<div><span>NUMBER CHECK</span>${esc(m.number_check || "")}</div><div><span>TOKENS IN / OUT</span>${m.input_tokens == null ? "—" : m.input_tokens + " / " + m.output_tokens}</div>` +
      `<div><span>EST. COST</span>${m.cost_usd == null ? "—" : "US$ " + Number(m.cost_usd).toFixed(5)}</div><div><span>INPUT</span>${esc(m.input_hash || "")}</div></div>`;
    h += '<div class="note">The model only writes the text. Every number in it must exist in the day\'s input data; the program checks this and retries once if not. Not investment advice.</div>';
    v.innerHTML = h;
  }

  // ---------------------------------------------------------------- ASK
  const LIVE = /^(localhost|127\.0\.0\.1)$/.test(location.hostname);

  function qaBlock(x) {
    const cites = (x.series_used || []).map((c) => `<span title="${esc(c.source)}">${esc(c.label)}</span>`).join("");
    const m = x.meta || {};
    return `<div class="qa"><div class="q">${esc(x.question)}</div><div class="a">${esc(x.answer)}</div>` +
      `<div class="cites">${x.cannot_answer ? '<b class="orange">NOT IN THE DATA</b> ' : ""}SERIES USED: ${cites || "—"}</div>` +
      `<div class="cites">numbers checked: ${esc(x.number_check || "")} · ${esc(m.mode || "")} ${esc((m.recorded_at || "").slice(0, 10))}${x.as_of ? " · data as of " + esc(x.as_of) : ""}${x.stale_reason ? " · not refreshed on the last run" : ""}</div></div>`;
  }

  function viewAsk(v) {
    const A = D.ask || {};
    let h = "";
    if (LIVE) {
      h += `<form class="askform" id="askform"><input id="askq" maxlength="300" placeholder="Ask about today's data, e.g. did the real rate go up this month?"><button>ASK</button></form><div id="asklive"></div>`;
    }
    h += `<div class="sec-h">${LIVE ? "PRESET QUESTIONS" : "PRESET QUESTIONS · ANSWERED ON THE LAST SCHEDULED RUN"} <span class="dim">${esc(A.model || "")}</span></div>`;
    h += (A.items || []).map(qaBlock).join("") || '<div class="dim">No answers yet. Run <code>python -m macro_terminal ask</code>.</div>';
    h += `<div class="note">The model answers from a small JSON context built by the code (recent points of each series). It must cite the series it used (a closed list in the schema) and every number in its answer must exist in that context; otherwise it is asked once more, then the answer is dropped.${LIVE ? "" : " Live questions run on the author's machine: <code>python -m macro_terminal serve</code>."}</div>`;
    v.innerHTML = h;
    if (LIVE) {
      $("#askform").onsubmit = async (e) => {
        e.preventDefault();
        const q = $("#askq").value.trim(); if (q.length < 3) return;
        const out = $("#asklive"); out.innerHTML = '<div class="dim">asking...</div>';
        try {
          const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }) });
          const x = await r.json();
          out.innerHTML = x.error ? `<div class="down">${esc(x.error)}</div>` : qaBlock(x) + `<div class="note">${x.meta.api_calls} API call(s) · ~US$ ${Number(x.meta.cost_usd || 0).toFixed(5)}</div>`;
        } catch (err) { out.innerHTML = '<div class="down">No local server. Start it with <code>python -m macro_terminal serve</code>.</div>'; }
      };
    }
  }

  // ---------------------------------------------------------------- NEWS
  function viewNews(v) {
    const eds = D.newsletters || [];
    if (!eds.length) { v.innerHTML = '<div class="dim">No editions yet. Run <code>python -m macro_terminal newsletter</code>.</div>'; return; }
    let h = `<div class="sec-h">EDITIONS <span class="dim">one edition per week · AI brief + 3 charts + the week's numbers</span></div>`;
    h += eds.map((x) => `<div class="ed"><span class="amber">${esc(x.week)}</span><span>${esc(x.headline)}</span><span><a href="${esc(x.html)}" target="_blank" rel="noopener">HTML</a> · <a href="${esc(x.md)}" target="_blank" rel="noopener">MD</a></span></div>`).join("");
    h += `<iframe class="newsframe" src="${esc(eds[0].html)}" title="Latest edition"></iframe>`;
    v.innerHTML = h;
  }

  // ---------------------------------------------------------------- STATUS
  function viewStatus(v) {
    const st = D.status || {};
    let h = '<div class="sec-h">DATA STATUS <span class="dim">a failed source keeps its last good copy and shows STALE</span></div>';
    h += '<div style="overflow-x:auto"><table class="t"><thead><tr><th>Dataset</th><th>Status</th><th>Source</th><th>Last obs.</th><th class="num">Rows</th><th>Fetched (UTC)</th><th>Checks</th></tr></thead><tbody>';
    for (const [k, s] of Object.entries(st)) {
      const iss = (s.issues || []).map((i) => `<li class="${i.level}">${esc(i.level.toUpperCase())}: ${esc(i.msg)}</li>`).join("");
      h += `<tr><td class="lbl">${esc(k)}</td><td><span class="badge ${esc(s.status)}">${esc(s.status.toUpperCase())}</span></td><td>${esc(s.source)}</td><td class="dim">${esc(s.last_date || "—")}</td><td class="num">${s.rows == null ? "—" : s.rows}</td>` +
        `<td class="dim">${esc((s.fetched_at || "never").replace("T", " ").slice(0, 16))}</td><td>${s.error ? `<div class="down">${esc(s.error)}</div>` : ""}${iss ? `<ul class="issues">${iss}</ul>` : '<span class="up">all passed</span>'}</td></tr>`;
    }
    h += "</tbody></table></div>";
    h += '<div class="sec-h">CHECKS RUN ON EVERY DOWNLOAD</div><ul class="issues">' +
      "<li>Missing values: share of empty observations per series (above 20% rejects the download).</li>" +
      "<li>Dates: unreadable or future dates dropped (the Selic target series is published up to the next meeting); duplicates dropped; last observation older than the series frequency allows is flagged.</li>" +
      "<li>Units: every series has a plausible range (e.g. Selic 0–60% p.a., USD/BRL 1–15); a value outside it rejects the download (a unit or scale change at the source).</li>" +
      "<li>Prices: positive closes, non-negative volume, high ≥ low, daily moves above 40% flagged, tickers missing from the download kept from cache.</li>" +
      "<li>Fundamentals: revenue must sit between BRL 100 million and BRL 1 trillion per quarter (catches a thousands-vs-units scale error).</li></ul>";
    v.innerHTML = h;
  }

  // ---------------------------------------------------------------- router
  const VIEWS = { macro: viewMacro, gp: viewGP, fa: viewFA, risk: viewRisk, brief: viewBrief, ask: viewAsk, news: viewNews, status: viewStatus };
  const TITLES = { macro: () => "MACRO MONITOR · BRAZIL / US", gp: () => `${state.ticker} · ${(byTicker[state.ticker] || {}).name || ""} · PRICE`, fa: () => `${state.ticker} · FUNDAMENTALS`, risk: () => "RISK · VOLATILITY, BETA, DRAWDOWN, SHARPE", brief: () => "AI BRIEF · MACRO AND MARKETS", ask: () => "ASK · QUESTIONS ON TODAY'S DATA", news: () => "WEEKLY NEWSLETTER · ARCHIVE", status: () => "DATA STATUS · CHECKS AND CACHE" };

  function render() {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === state.tab));
    $("#cmd-sec").textContent = state.ticker;
    $("#main-title").innerHTML = `<span>${esc(TITLES[state.tab]())}</span><span class="dim">${esc(state.tab.toUpperCase())} &lt;GO&gt;</span>`;
    renderWatchlist();
    renderFilings();
    VIEWS[state.tab]($("#view"));
    try { history.replaceState(null, "", "#" + state.tab + "/" + state.ticker); } catch (e) { /* file:// in some browsers */ }
    try { localStorage.setItem("mtrm", JSON.stringify({ tab: state.tab, ticker: state.ticker })); } catch (e) { /* ignore */ }
  }

  function go(change) {
    Object.assign(state, change);
    if (change.ticker && !change.tab && state.tab === "macro") state.tab = "gp";
    render();
  }

  function command(text) {
    const words = text.trim().toUpperCase().split(/\s+/).filter((w) => w && w !== "GO" && w !== "<GO>");
    const change = {};
    for (const w of words) {
      if (byTicker[w]) change.ticker = w;
      else if (TAB_ALIASES[w]) change.tab = TAB_ALIASES[w];
      else if (/^[1-8]$/.test(w)) change.tab = TABS[+w - 1];
    }
    if (!Object.keys(change).length) { $("#cmd-input").value = ""; $("#cmd-input").placeholder = `Unknown: ${text}. Try PETR4 GP, VALE3 FA, RISK`; return; }
    go(change);
  }

  $("#cmd").addEventListener("submit", (e) => { e.preventDefault(); command($("#cmd-input").value); $("#cmd-input").value = ""; });
  document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => go({ tab: b.dataset.tab })));
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    if (/^[1-8]$/.test(e.key)) go({ tab: TABS[+e.key - 1] });
    else if (e.key === "/" || (e.key.length === 1 && /[a-z]/i.test(e.key) && !e.ctrlKey && !e.metaKey)) { $("#cmd-input").focus(); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const i = watch.findIndex((w) => w.ticker === state.ticker);
      const j = (i + (e.key === "ArrowDown" ? 1 : -1) + watch.length) % watch.length;
      e.preventDefault(); go({ ticker: watch[j].ticker });
    }
  });
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(render, 150); });

  renderHeader();
  renderAlerts();
  renderFooter();
  render();
})();
