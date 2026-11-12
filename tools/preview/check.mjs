// Node sanity check of the preview helpers against the real exports:
//   node tools/preview/check.mjs
import { readFileSync, existsSync } from "node:fs";
import { gunzipSync } from "node:zlib";
import { heatmapGrid, colour, parseCalendarCSV, monthValues, tooltip } from "./lib.js";

const root = new URL("../../data/export/", import.meta.url);
let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"} ${msg}`); if (!ok) failures++; };

for (const region of ["lebanon", "greece", "eastmed"]) {
  const f = new URL(`${region}/region_monthly.json`, root);
  if (!existsSync(f)) { check(false, `${region}: region_monthly.json missing`); continue; }
  const rows = JSON.parse(readFileSync(f, "utf8"));
  const g = heatmapGrid(rows, "harmonized");
  const nulls = g.cells.filter((c) => c.exists && c.value === null).length;
  const lc = rows.filter((r) => r.low_confidence).length;
  check(g.years[0] === 2000 && g.years.at(-1) === 2026, `${region}: years ${g.years[0]}-${g.years.at(-1)}`);
  check(nulls === rows.filter((r) => !r.data_available).length, `${region}: ${nulls} no-data months render grey`);
  check(colour(null, 1) === "#d0d0d0" && colour(g.max, g.max).startsWith("rgb"), `${region}: colour scale`);
  console.log(`     max harmonized ${g.max.toFixed(1)}, low_confidence months ${lc}, rows ${rows.length}`);
  check(tooltip(rows[0], "harmonized").includes("harmonized"), `${region}: tooltip`);
}

const cal = new URL("lebanon/calendar.csv.gz", root);
const rows = parseCalendarCSV(gunzipSync(readFileSync(cal)).toString("utf8"));
check(rows.length === 134706, `lebanon calendar rows ${rows.length}`);
const v = monthValues(rows, 2007, 9, "harmonized");
check(v.size === 429, `lebanon 2007-09 values for ${v.size} cells`);
check(rows.some((r) => r.harmonized === null) && typeof rows[0].is_estimate === "boolean", "nulls and booleans parsed");
const geo = JSON.parse(readFileSync(new URL("lebanon/cells.geojson", root), "utf8"));
const ids = new Set(geo.features.map((f) => f.properties.cell_id));
check([...v.keys()].every((k) => ids.has(k)), "every calendar cell_id has a GeoJSON feature");
process.exit(failures ? 1 : 0);
