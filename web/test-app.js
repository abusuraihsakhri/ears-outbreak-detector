"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { parseCsv, parseIsoDay, detect, csvExport } = require("./app.js");

function sample(counts) {
  const start = Date.UTC(2026, 0, 1), day = 86400000;
  return counts.map((count, i) => ({
    date: new Date(start + i * day).toISOString().slice(0, 10), count
  }));
}

test("C1 spike over flat 7-day baseline is flagged", () => {
  const rows = detect(sample([10,10,10,10,10,10,10,30]), {window:7,gap:2,threshold:3});
  assert.equal(rows.at(-1).C1, 100);
  assert.equal(rows.at(-1).alert_C1, true);
  assert.equal(rows.at(-1).C2, null);
});

test("C1 sample standard deviation matches hand-computed statistic", () => {
  const baseline = [8,10,12,9,11,10,9], avg = baseline.reduce((a,b) => a+b)/7;
  const sd = Math.sqrt(baseline.reduce((a,b) => a+(b-avg)**2,0)/6);
  const rows = detect(sample([...baseline,20]), {window:7,gap:0,threshold:3});
  assert.ok(Math.abs(rows.at(-1).C1 - ((20-avg)/sd)) < 1e-10);
});

test("C2 excludes the two guard-band days", () => {
  const rows = detect(sample([10,10,10,10,10,10,10,50,50,12]), {window:7,gap:2,threshold:3});
  assert.equal(rows.at(-1).C2, 100);
  assert.equal(rows.at(-1).alert_C2, true);
  assert.equal(rows.at(-1).alert_C1, false);
});

test("C3 combines current and preceding two C2 values", () => {
  const rows = detect(sample([10,10,10,10,10,10,10,10,10,20,20,20]), {window:7,gap:2,threshold:3});
  assert.equal(rows[9].C3, null);
  assert.equal(rows[11].C3, [9,10,11].reduce((total,i) => total + Math.max(0, rows[i].C2 - 1), 0));
});

test("positive C2 deviations are not cancelled by negative C2", () => {
  const vals = [5, -10, 5];
  assert.equal(vals.reduce((s,v) => s + Math.max(0,v - 1), 0), 8);
});

test("calendar gaps are filled with zeros", () => {
  const data = parseCsv("date,count\n2026-01-01,5\n2026-01-04,7\n");
  assert.equal(data.missing, 2);
  assert.deepEqual(data.series.map(x=>x.count), [5,0,0,7]);
});

test("supports quoted CSV and CRLF", () => {
  const data = parseCsv("date,count,note\r\n2026-01-01,5,\"noted, here\"\r\n");
  assert.equal(data.series[0].count, 5);
});

test("rejects invalid calendar dates, duplicate dates and invalid counts", () => {
  assert.equal(parseIsoDay("2026-02-30"), null);
  assert.throws(()=>parseCsv("date,count\n2026-01-01,2\n2026-01-01,3"), /Duplicate/);
  for (const value of ["-1","1.5","NaN","Infinity","","=2+3"]) {
    assert.throws(()=>parseCsv("date,count\n2026-01-01," + value), /Counts|Column/);
  }
});

test("rejects negative guard bands and invalid thresholds", () => {
  for (const option of [{window:7,gap:-1,threshold:3}, {window:7,gap:0,threshold:Infinity},
                        {window:7,gap:0,threshold:100}, {window:1,gap:0,threshold:3}]) {
    assert.throws(()=>detect(sample([10,10,10]),option), /window|threshold/);
  }
});

test("weekday adjustment has insufficient data for a 7-day window", () => {
  const rows = detect(sample(Array(20).fill(10)), {window:7,gap:2,threshold:3,dowAdjust:true});
  assert.ok(rows.every(row => row.C1 === null && row.C2 === null));
});

test("CSV export includes all scores and alert columns", () => {
  const rows = detect(sample([1,1,1,1,1,1,1,15]), {window:7,gap:0,threshold:3});
  const output = csvExport(rows);
  assert.match(output, /^date,count,C1,C2,C3,alert_C1,alert_C2,alert_C3\n/);
  assert.match(output, /2026-01-08,15,100,100,,true,true,false/);
});
