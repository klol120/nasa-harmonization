// Export preview: heatmap of region_monthly.json + MapLibre map of cells.geojson.
import { MONTHS, VARIABLES, colour, heatmapGrid, monthLabel, seriesMonthValues, tooltip } from "./lib.js";

const params = new URLSearchParams(location.search);
const state = { region: params.get("region") || "lebanon", field: "harmonized", rows: [], series: new Map(),
  cellIds: [], selected: null, meta: null };
const base = (r) => `../../data/export/${r}/`;
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

async function loadSeries(year) {
  if (!state.series.has(year)) state.series.set(year, getJSON(base(state.region) + `cells_series/${year}.json`));
  return state.series.get(year);
}

function drawHeatmap() {
  const svg = document.getElementById("heatmap");
  const { years, cells, max } = heatmapGrid(state.rows, VARIABLES[state.field].field);
  const cw = 30, ch = 16, left = 44, top = 20;
  svg.setAttribute("width", left + 12 * cw + 10);
  svg.setAttribute("height", top + years.length * ch + 10);
  const ns = "http://www.w3.org/2000/svg";
  svg.innerHTML = `<defs><pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse"
    patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="5" stroke="#000" stroke-width="1.2"
    stroke-opacity="0.55"/></pattern></defs>`;
  MONTHS.forEach((m, i) => {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", left + i * cw + cw / 2); t.setAttribute("y", 14); t.setAttribute("text-anchor", "middle");
    t.textContent = m; svg.appendChild(t);
  });
  years.forEach((y, j) => {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", left - 6); t.setAttribute("y", top + j * ch + ch - 4); t.setAttribute("text-anchor", "end");
    t.textContent = y; svg.appendChild(t);
  });
  for (const c of cells) {
    if (!c.exists) continue;
    const j = years.indexOf(c.year), i = c.month - 1;
    const g = document.createElementNS(ns, "g");
    const r = document.createElementNS(ns, "rect");
    Object.entries({ x: left + i * cw, y: top + j * ch, width: cw - 1, height: ch - 1,
      fill: colour(c.value, max) }).forEach(([k, v]) => r.setAttribute(k, v));
    g.appendChild(r);
    if (c.row.low_confidence) {
      const h = r.cloneNode(); h.setAttribute("fill", "url(#hatch)"); g.appendChild(h);
    }
    if (state.selected === c.row.ym) {
      r.setAttribute("stroke", "#1565c0"); r.setAttribute("stroke-width", 2);
    }
    const title = document.createElementNS(ns, "title");
    title.textContent = tooltip(c.row, VARIABLES[state.field].field);
    g.appendChild(title);
    g.addEventListener("click", () => { state.selected = c.row.ym; drawHeatmap(); colourMap(); });
    svg.appendChild(g);
  }
  document.getElementById("scale").textContent =
    `${VARIABLES[state.field].label}: 0 – ${max.toFixed(0)} per month (sqrt colour scale). ` +
    "Grey = no data. Hatched = low_confidence estimate.";
}

let map;
function initMap(geojson) {
  map = new maplibregl.Map({ container: "map", style: "https://demotiles.maplibre.org/style.json",
    bounds: state.meta.bbox, fitBoundsOptions: { padding: 20 } });
  map.on("load", () => {
    map.addSource("cells", { type: "geojson", data: geojson, promoteId: "cell_id" });
    map.addLayer({ id: "cells-fill", type: "fill", source: "cells",
      paint: { "fill-color": ["coalesce", ["feature-state", "colour"], "#90caf9"], "fill-opacity": 0.75 } });
    map.addLayer({ id: "cells-persistent", type: "line", source: "cells", filter: ["==", ["get", "is_persistent"], true],
      paint: { "line-color": "#d50000", "line-width": 2 } });
    map.on("click", "cells-fill", (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup().setLngLat(e.lngLat)
        .setHTML(`<b>${p.cell_id}</b><br>${p.primary_country}${p.is_persistent ? "<br>persistent source" : ""}`)
        .addTo(map);
    });
    colourMap();
  });
}

async function colourMap() {
  if (!map || !map.getSource("cells")) return;
  const note = document.getElementById("mapnote");
  const banner = document.getElementById("banner");
  const row = state.selected ? state.rows.find((r) => r.ym === state.selected)
    : state.rows.reduce((a, r) => (r.data_available ? r : a), null);
  const doc = await loadSeries(row.year);
  const v = VARIABLES[state.field];
  const vals = seriesMonthValues(doc, row.ym, v.key, row.data_available, state.cellIds);
  const nums = [...vals.values()].filter((x) => x !== null);
  const max = Math.max(1, ...nums);
  for (const [id, x] of vals) map.setFeatureState({ source: "cells", id }, { colour: colour(x, max) });
  banner.textContent = monthLabel(row);
  banner.className = row.is_estimate ? "banner estimate" : "banner";
  note.textContent = `${v.label} per cell, max ${max.toFixed(1)} (own scale per variable and month). ` +
    "Click a heatmap month to change. Red outline = is_persistent.";
}

async function main() {
  document.getElementById("region").value = state.region;
  document.getElementById("region").onchange = (e) => { location.search = `?region=${e.target.value}`; };
  document.querySelectorAll("input[name=var]").forEach((el) => el.addEventListener("change", (e) => {
    state.field = e.target.value; drawHeatmap(); colourMap();
  }));
  const b = base(state.region);
  try {
    [state.rows, state.meta] = await Promise.all([getJSON(b + "region_monthly.json"), getJSON(b + "meta.json")]);
  } catch (err) {
    document.getElementById("status").textContent = `Could not load exports: ${err.message}. ` +
      "Serve the repo root: .venv/bin/python -m http.server 8000, open /tools/preview/";
    return;
  }
  const m = state.meta;
  document.getElementById("status").textContent =
    `${m.region}: ${m.n_cells} cells, ${m.time.first_month} – ${m.time.last_month}, strategy ${m.calibration.strategy}, ` +
    `contract ${m.contract_version}, low_confidence months ${JSON.stringify(m.low_confidence_rule.months)}`;
  drawHeatmap();
  try {
    const geo = await getJSON(b + "cells.geojson");
    state.cellIds = geo.features.map((f) => f.properties.cell_id);
    initMap(geo);
  } catch (err) {
    document.getElementById("mapnote").textContent = `cells.geojson not available: ${err.message}`;
  }
}

main();
