"use strict";

/* Deterministic, dependency-free port of ears.py for static hosting. */
(function (root) {
  const CAP = 100;
  const DAY = 86400000;
  const MAX_DAYS = 50000;
  const METHODS = ["C1", "C2", "C3"];

  function parseCsv(text) {
    if (typeof text !== "string" || !text.trim()) throw new Error("Paste or upload a CSV containing date,count.");
    const records = [];
    let row = [], cell = "", quoted = false;
    text = text.replace(/^\uFEFF/, "");
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
        else if (ch === '"') quoted = false;
        else cell += ch;
      } else if (ch === '"' && cell.length === 0) {
        quoted = true;
      } else if (ch === ",") {
        row.push(cell); cell = "";
      } else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(cell); cell = "";
        if (row.some(value => value.trim() !== "")) records.push(row);
        row = [];
      } else {
        if (ch === '"') throw new Error("Invalid CSV quoting.");
        cell += ch;
      }
    }
    if (quoted) throw new Error("Unterminated quoted CSV field.");
    row.push(cell);
    if (row.some(value => value.trim() !== "")) records.push(row);
    if (records.length < 2) throw new Error("CSV must contain a header and at least one data row.");
    const headers = records.shift().map(s => s.trim().toLowerCase());
    const di = headers.indexOf("date"), ci = headers.indexOf("count");
    if (di < 0 || ci < 0) throw new Error("CSV requires date and count columns.");
    const seen = new Map();
    for (let i = 0; i < records.length; i++) {
      const row = records[i];
      if (row.length !== headers.length) throw new Error("Column mismatch at data row " + (i + 2) + ".");
      const date = row[di].trim(), raw = row[ci].trim();
      const time = parseIsoDay(date);
      if (time === null) throw new Error("Invalid ISO date at data row " + (i + 2) + ": " + date);
      if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
        throw new Error("Counts must be nonnegative whole numbers (row " + (i + 2) + ").");
      }
      if (seen.has(time)) throw new Error("Duplicate date: " + date);
      seen.set(time, Number(raw));
    }
    const ordered = Array.from(seen.keys()).sort((a, b) => a - b);
    const days = (ordered[ordered.length - 1] - ordered[0]) / DAY + 1;
    if (days > MAX_DAYS) throw new Error("Date range exceeds " + MAX_DAYS + " days.");
    const series = [];
    let missing = 0;
    for (let t = ordered[0]; t <= ordered[ordered.length - 1]; t += DAY) {
      if (!seen.has(t)) missing++;
      series.push({ date: new Date(t).toISOString().slice(0, 10), count: seen.get(t) ?? 0, time: t });
    }
    return { series, missing };
  }

  function parseIsoDay(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const time = Date.parse(value + "T00:00:00Z");
    if (!Number.isFinite(time)) return null;
    return new Date(time).toISOString().slice(0, 10) === value ? time : null;
  }

  function detect(series, options) {
    const window = Number(options.window), gap = Number(options.gap), threshold = Number(options.threshold);
    const c3Threshold = options.c3Threshold === undefined ? 2 : Number(options.c3Threshold);
    const dowAdjust = Boolean(options.dowAdjust);
    if (!Number.isInteger(window) || window < 2 || !Number.isInteger(gap) || gap < 0
        || !Number.isFinite(threshold) || threshold < 0 || threshold >= CAP
        || !Number.isFinite(c3Threshold) || c3Threshold < 0 || c3Threshold >= CAP * 3) {
      throw new Error("Use a baseline window of at least 2, a nonnegative integer gap, a C1/C2 threshold below 100 and a C3 threshold below 300.");
    }
    if (!Array.isArray(series) || !series.length) throw new Error("No surveillance records.");
    for (let i = 0; i < series.length; i++) {
      if (parseIsoDay(series[i].date) === null || !Number.isSafeInteger(series[i].count) || series[i].count < 0)
        throw new Error("Invalid count or date at position " + (i + 1) + ".");
      if (i > 0 && parseIsoDay(series[i].date) - parseIsoDay(series[i - 1].date) !== DAY)
        throw new Error("The date series must be daily, sorted and gap-free.");
    }
    const weekdays = series.map(x => new Date(x.date + "T00:00:00Z").getUTCDay());
    function statistic(t, guard) {
      const lo = t - guard - window, hi = t - guard;
      if (lo < 0) return null;
      const baseline = [];
      for (let j = lo; j < hi; j++) {
        if (!dowAdjust || weekdays[j] === weekdays[t]) baseline.push(series[j].count);
      }
      if (baseline.length < 2) return null;
      const avg = baseline.reduce((a, b) => a + b, 0) / baseline.length;
      const variance = baseline.reduce((a, b) => a + (b - avg) ** 2, 0) / (baseline.length - 1);
      const sd = Math.sqrt(variance);
      return sd === 0 ? (series[t].count <= avg ? 0 : CAP) : (series[t].count - avg) / sd;
    }
    const rows = series.map((item, t) => ({
      date: item.date, count: item.count, C1: statistic(t, 0), C2: statistic(t, gap),
      C3: null, alert_C1: false, alert_C2: false, alert_C3: false
    }));
    for (let t = 0; t < rows.length; t++) {
      if (t >= 2 && rows[t].C2 !== null && rows[t - 1].C2 !== null && rows[t - 2].C2 !== null)
        rows[t].C3 = computeC3([rows[t].C2, rows[t - 1].C2, rows[t - 2].C2]);
      for (const m of METHODS) rows[t]["alert_" + m] = rows[t][m] !== null && rows[t][m] > (m === "C3" ? c3Threshold : threshold);
    }
    return rows;
  }

  function computeC3(values) {
    if (values.length !== 3 || values.some(value => value === null || !Number.isFinite(value))) return null;
    return values.reduce((total, value) => total + Math.max(0, value - 1), 0);
  }

  function csvExport(rows) {
    const cols = ["date", "count", "C1", "C2", "C3", "alert_C1", "alert_C2", "alert_C3"];
    return cols.join(",") + "\n" + rows.map(r =>
      cols.map(k => r[k] === null ? "" : String(r[k])).join(",")
    ).join("\n") + "\n";
  }

  const api = { parseCsv, parseIsoDay, detect, computeC3, csvExport };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (!root.document) return;

  const doc = root.document;
  const el = id => doc.getElementById(id);
  let rows = [];
  function setStatus(message, failed = false) {
    el("status").textContent = message;
    el("status").classList.toggle("error", failed);
  }
  function download(name, content) {
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
    const a = doc.createElement("a");
    a.href = url; a.download = name;
    doc.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }
  function drawChart(rows) {
    const svg = el("chart"), ns = "http://www.w3.org/2000/svg";
    svg.replaceChildren();
    if (!rows.length) return;
    const width = 1000, height = 240, padX = 22, padY = 18;
    const max = Math.max(1, ...rows.map(r => r.count));
    const x = i => padX + i * (width - padX * 2) / Math.max(1, rows.length - 1);
    const y = v => height - padY - v / max * (height - 2 * padY);
    const element = (tag, attrs) => {
      const node = doc.createElementNS(ns, tag);
      for (const [key, val] of Object.entries(attrs)) node.setAttribute(key, String(val));
      svg.appendChild(node);
      return node;
    };
    for (let i = 0; i <= 4; i++) element("line", {
      x1: padX, x2: width - padX, y1: y(max * i / 4), y2: y(max * i / 4),
      stroke: "#334155", "stroke-width": 1
    });
    element("polyline", {
      points: rows.map((r, i) => x(i) + "," + y(r.count)).join(" "),
      fill: "none", stroke: "#38bdf8", "stroke-width": 2.5, "stroke-linejoin": "round"
    });
    rows.forEach((r, i) => {
      if (METHODS.some(m => r["alert_" + m])) {
        const circle = element("circle", { cx: x(i), cy: y(r.count), r: 4.7, fill: "#f87171" });
        const label = doc.createElementNS(ns, "title");
        label.textContent = r.date + ": " + r.count + " (" + METHODS.filter(m => r["alert_" + m]).join(", ") + ")";
        circle.appendChild(label);
      }
    });
    el("chart-desc").textContent = "Daily observed counts from " + rows[0].date + " to " +
      rows[rows.length - 1].date + ". Red dots indicate an alert from at least one EARS method.";
  }
  function render(rows, missing) {
    el("results").hidden = false;
    el("n-days").textContent = rows.length.toLocaleString();
    el("n-missing").textContent = missing.toLocaleString();
    for (const m of METHODS) el("n-" + m).textContent = rows.filter(r => r["alert_" + m]).length.toLocaleString();
    drawChart(rows);
    const body = el("alerts-body");
    body.replaceChildren();
    const alerts = rows.filter(r => METHODS.some(m => r["alert_" + m]));
    const limit = 300;
    for (const r of alerts.slice(0, limit)) {
      const tr = doc.createElement("tr");
      const values = [r.date, r.count, ...METHODS.map(m => r["alert_" + m] ? "Alert" : "—")];
      for (const value of values) {
        const cell = doc.createElement("td"); cell.textContent = value;
        tr.appendChild(cell);
      }
      body.appendChild(tr);
    }
    el("no-alerts").hidden = alerts.length !== 0;
    el("table-note").textContent = alerts.length > limit
      ? "Showing first " + limit + " of " + alerts.length + " alert days; download CSV for all records."
      : alerts.length + " day(s) flagged by one or more methods.";
    el("download-all").disabled = false;
    el("download-alerts").disabled = alerts.length === 0;
  }
  function example() {
    const records = ["date,count"];
    const start = Date.UTC(2026, 0, 1);
    for (let i = 0; i < 35; i++) {
      const date = new Date(start + i * DAY).toISOString().slice(0, 10);
      records.push(date + "," + ((i === 22 || i === 23 || i === 29) ? 31 : (9 + i % 4)));
    }
    return records.join("\n") + "\n";
  }
  el("csv-text").addEventListener("input", () => { if (el("csv-text").value.trim()) el("file").value = ""; });
  el("file").addEventListener("change", () => { if (el("file").files.length) el("csv-text").value = ""; });
  el("sample").addEventListener("click", () => {
    el("csv-text").value = example(); el("file").value = ""; setStatus("Sample data loaded.");
  });
  el("run").addEventListener("click", async () => {
    el("run").disabled = true;
    try {
      const f = el("file").files[0];
      if (f && f.size > 2_000_000) throw new Error("CSV file exceeds the 2 MB limit.");
      const text = f ? await f.text() : el("csv-text").value;
      const parsed = parseCsv(text);
      if (!el("gap").value.trim() || !el("threshold").value.trim() || !el("c3-threshold").value.trim()) {
        throw new Error("Enter a gap and both alert thresholds.");
      }
      rows = detect(parsed.series, {
        window: el("window").value, gap: el("gap").value,
        threshold: el("threshold").value, c3Threshold: el("c3-threshold").value,
        dowAdjust: el("dow").checked
      });
      render(rows, parsed.missing);
      setStatus("Analysis completed locally. No records were uploaded.");
    } catch (err) {
      rows = []; el("results").hidden = true;
      setStatus(err.message || "Analysis failed.", true);
    } finally { el("run").disabled = false; }
  });
  el("download-all").addEventListener("click", () => download("ears-results.csv", csvExport(rows)));
  el("download-alerts").addEventListener("click", () => download("ears-alerts.csv",
    csvExport(rows.filter(r => METHODS.some(m => r["alert_" + m])))));
})(typeof window === "undefined" ? globalThis : window);
