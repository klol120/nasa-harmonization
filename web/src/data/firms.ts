import type { CellMonthlyRow, HotspotRow, Sensor } from "./contract";

/**
 * Raw NASA FIRMS hotspot files (archive or API CSV) → contract rows.
 * This applies the brief's cleaning filters and the cell-day unit, but NOT the
 * calibration: it yields modis_raw / viirs_raw only. Harmonized rows come from the engine.
 */

export const isFirmsHeader = (header: string[]) => {
  const h = new Set(header.map((x) => x.toLowerCase()));
  return h.has("latitude") && h.has("longitude") && h.has("acq_date");
};

export interface FirmsResult {
  rows: CellMonthlyRow[];
  hotspots: HotspotRow[];
  warnings: string[];
}

export function aggregateFirms(records: Record<string, string>[], gridDeg = 0.1): FirmsResult {
  const warnings: string[] = [];
  const lower = (r: Record<string, string>) => Object.fromEntries(Object.entries(r).map(([k, v]) => [k.toLowerCase(), v]));
  const cells = new Map<string, CellMonthlyRow>();
  const cellDays = new Set<string>();
  const hotspots: HotspotRow[] = [];
  let dropped = { type: 0, confidence: 0, bad: 0 };

  for (const raw of records) {
    const r = lower(raw);
    const lat = Number(r.latitude);
    const lon = Number(r.longitude);
    const date = r.acq_date ?? "";
    const [y, m] = date.split("-").map(Number);
    if (![lat, lon, y, m].every(Number.isFinite)) {
      dropped.bad++;
      continue;
    }
    // Vegetation fires only (archive files carry `type`; API NRT files do not).
    if (r.type !== undefined && r.type !== "" && r.type !== "0") {
      dropped.type++;
      continue;
    }
    const conf = (r.confidence ?? "").trim().toLowerCase();
    const numeric = conf !== "" && !Number.isNaN(Number(conf));
    const instrument = (r.instrument ?? "").toUpperCase() || (numeric || r.brightness !== undefined ? "MODIS" : "VIIRS");
    const sensor: Sensor = instrument.startsWith("MODIS") ? "modis_raw" : "viirs_raw";
    // Confidence filters from the brief: MODIS ≥ 30, VIIRS nominal + high.
    if (sensor === "modis_raw" && numeric && Number(conf) < 30) {
      dropped.confidence++;
      continue;
    }
    if (sensor === "viirs_raw" && (conf === "l" || conf === "low")) {
      dropped.confidence++;
      continue;
    }

    // Epsilon keeps points on a grid line (33.8 / 0.1 = 337.999…) in the right cell.
    const clat = +(Math.floor(lat / gridDeg + 1e-9) * gridDeg + gridDeg / 2).toFixed(4);
    const clon = +(Math.floor(lon / gridDeg + 1e-9) * gridDeg + gridDeg / 2).toFixed(4);
    const cell_id = `${clat.toFixed(3)}_${clon.toFixed(3)}`;
    const key = `${cell_id}|${y}|${m}|${sensor}`;
    const row = cells.get(key) ?? { cell_id, lat: clat, lon: clon, year: y, month: m, sensor, cell_days: 0, fire_count: 0, sum_frp: 0 };
    const frp = Number(r.frp);
    row.fire_count += 1;
    row.sum_frp += Number.isFinite(frp) ? frp : 0;
    // A cell counts once per day per sensor.
    const dayKey = `${cell_id}|${date}|${sensor}`;
    if (!cellDays.has(dayKey)) {
      cellDays.add(dayKey);
      row.cell_days += 1;
    }
    cells.set(key, row);

    hotspots.push({
      latitude: lat,
      longitude: lon,
      acq_date: date,
      acq_time: String(r.acq_time ?? "").padStart(4, "0"), // FIRMS drops leading zeros ("52" = 00:52)
      satellite: r.satellite ?? "",
      instrument: sensor === "modis_raw" ? "MODIS" : "VIIRS",
      confidence: r.confidence ?? "",
      frp: Number.isFinite(frp) ? frp : 0,
      daynight: (r.daynight === "N" ? "N" : "D") as "D" | "N",
      type: Number(r.type ?? 0) || 0,
      scan: r.scan !== undefined && r.scan !== "" && Number.isFinite(Number(r.scan)) ? Number(r.scan) : undefined,
      track: r.track !== undefined && r.track !== "" && Number.isFinite(Number(r.track)) ? Number(r.track) : undefined,
    });
  }

  if (dropped.type) warnings.push(`${dropped.type.toLocaleString()} non-vegetation detections removed (type ≠ 0).`);
  if (dropped.confidence) warnings.push(`${dropped.confidence.toLocaleString()} low-confidence detections removed (MODIS < 30, VIIRS low).`);
  if (dropped.bad) warnings.push(`${dropped.bad.toLocaleString()} rows without valid coordinates or date skipped.`);
  warnings.push("Raw FIRMS file: MODIS and VIIRS are shown separately. The Harmonized view needs the harmonization engine output.");
  const rows = [...cells.values()].map((r) => ({ ...r, sum_frp: +r.sum_frp.toFixed(2) }));
  return { rows, hotspots, warnings };
}
