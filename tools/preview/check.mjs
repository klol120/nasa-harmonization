// Node sanity check of the preview helpers against the real exports (contract 0.4):
//   node tools/preview/check.mjs
import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { heatmapGrid, colour, seriesMonthValues, monthLabel, tooltip } from "./lib.js";

const root = new URL("../../data/export/", import.meta.url);
let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"} ${msg}`); if (!ok) failures++; };
const json = (p) => JSON.parse(readFileSync(new URL(p, root), "utf8"));

for (const region of ["lebanon", "greece", "eastmed"]) {
  if (!existsSync(new URL(`${region}/region_monthly.json`, root))) { check(false, `${region}: exports missing`); continue; }
  const rows = json(`${region}/region_monthly.json`);
  const meta = json(`${region}/meta.json`);
  check(meta.contract_version === "0.4", `${region}: contract ${meta.contract_version}`);
  check(rows.every((r) => /^\d{4}-\d{2}$/.test(r.ym)), `${region}: ym on every row`);
  const g = heatmapGrid(rows, "harmonized");
  const nulls = g.cells.filter((c) => c.exists && c.value === null).length;
  check(nulls === rows.filter((r) => !r.data_available).length, `${region}: ${nulls} no-data months render grey`);
  check(colour(null, 1) === "#d0d0d0" && colour(g.max, g.max).startsWith("rgb"), `${region}: colour scale`);
  check(tooltip(rows[0], "harmonized").includes(rows[0].ym), `${region}: tooltip`);
  const est = rows.find((r) => r.is_estimate && r.data_available);
  check(monthLabel(est).includes("MODELLED ESTIMATE"), `${region}: estimate months labelled as modelled`);
  if (!existsSync(new URL(`${region}/cells.geojson`, root))) { console.log(`     ${region}: cells.geojson not present`); continue; }
  const ids = json(`${region}/cells.geojson`).features.map((f) => f.properties.cell_id);
  const doc = json(`${region}/cells_series/2007.json`);
  const v = seriesMonthValues(doc, "2007-09", "h", true, ids);
  check(v.size === ids.length && [...v.values()].every((x) => typeof x === "number"), `${region}: 2007-09 values for all ${ids.length} cells`);
  check(Object.keys(doc.cells).every((k) => ids.includes(k)), `${region}: series cell_ids exist in cells.geojson`);
  const lastNoData = rows.filter((r) => !r.data_available).at(-1);
  const doc26 = json(`${region}/cells_series/${lastNoData.year}.json`);
  const v26 = seriesMonthValues(doc26, lastNoData.ym, "h", false, ids);
  check([...v26.values()].every((x) => x === null), `${region}: ${lastNoData.ym} (no data) is null for every cell`);
}

// series values equal the calendar (Lebanon, one month)
const csv = gunzipSync(readFileSync(new URL("lebanon/calendar.csv.gz", root))).toString("utf8").split("\n");
const head = csv[0].split(",");
const iy = head.indexOf("ym"), ic = head.indexOf("cell_id"), ih = head.indexOf("harmonized");
const fromCal = new Map(csv.slice(1).filter(Boolean).map((l) => l.split(",")).filter((p) => p[iy] === "2007-09")
  .map((p) => [p[ic], p[ih] === "" ? null : Math.round(Number(p[ih]) * 100) / 100]));
const ids = json("lebanon/cells.geojson").features.map((f) => f.properties.cell_id);
const fromSeries = seriesMonthValues(json("lebanon/cells_series/2007.json"), "2007-09", "h", true, ids);
const worst = Math.max(...ids.map((id) => Math.abs((fromSeries.get(id) ?? 0) - (fromCal.get(id) ?? 0))));
check(worst <= 0.01, `lebanon 2007-09: series equals calendar (max diff ${worst.toFixed(3)})`);
process.exit(failures ? 1 : 0);
