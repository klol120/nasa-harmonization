import { useEffect, useState } from "react";
import { REGION_INFO } from "../config";
import { type BBox, type DatasetMeta, MONTH_ABBR, ym, ymMonth, ymYear } from "../data/contract";
import type { KeyEvent } from "../lib/analytics";
import { type Area, areaFromBBox, bboxIntersects, ringAreaKm2 } from "../lib/geo";
import type { DrawMode, LayerState } from "./MapView";

export function Section({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section className="panel">
      <header className="panel-head">
        <h2>{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------------------

interface AreaProps {
  meta: DatasetMeta;
  /** The "everything" area: the region outline when there is one. */
  whole: Area;
  area: Area;
  cellCount: number;
  onArea: (a: Area) => void;
  drawMode: DrawMode;
  setDrawMode: (m: DrawMode) => void;
  excludePersistent: boolean;
  onExcludePersistent: (v: boolean) => void;
}

export function AreaPanel({ meta, whole, area, cellCount, onArea, drawMode, setDrawMode, excludePersistent, onExcludePersistent }: AreaProps) {
  const [tab, setTab] = useState<"bbox" | "point">("bbox");
  const [bbox, setBbox] = useState<string[]>(area.bbox.map((v) => v.toFixed(3)));
  const [pt, setPt] = useState({ lat: "", lon: "", km: "25" });
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => setBbox(area.bbox.map((v) => v.toFixed(3))), [area]);

  const presets = REGION_INFO[meta.id]?.presets ?? [];
  const outside = !bboxIntersects(area.bbox, meta.bbox);

  const applyBbox = () => {
    const v = bbox.map(Number) as BBox;
    if (v.some((x) => !Number.isFinite(x))) return setErr("Enter four numbers.");
    if (v[0] >= v[2] || v[1] >= v[3]) return setErr("West must be < East and South < North.");
    if (v[1] < -90 || v[3] > 90 || v[0] < -180 || v[2] > 180) return setErr("Out of lat/lon range.");
    setErr(null);
    onArea(areaFromBBox("Custom bounds", v));
  };
  const applyPoint = () => {
    const lat = Number(pt.lat);
    const lon = Number(pt.lon);
    const km = Number(pt.km);
    if (![lat, lon, km].every(Number.isFinite) || km <= 0) return setErr("Enter latitude, longitude and a radius in km.");
    if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return setErr("Out of lat/lon range.");
    setErr(null);
    const dLat = km / 111.32;
    const dLon = km / (111.32 * Math.cos((lat * Math.PI) / 180));
    onArea(areaFromBBox(`${km} km around ${lat.toFixed(2)}, ${lon.toFixed(2)}`, [lon - dLon, lat - dLat, lon + dLon, lat + dLat]));
  };

  return (
    <Section title="Area of interest">
      <div className="area-card">
        <div className="area-name">{area.name}</div>
        <div className="area-meta">
          {area.kind === "polygon" ? "Polygon" : "Box"} · {Math.round(ringAreaKm2(area.ring)).toLocaleString()} km² · {cellCount} grid cells
        </div>
        {outside && <div className="warn">This area is outside the loaded dataset ({meta.name}). Nothing to show.</div>}
        {!outside && cellCount === 0 && <div className="warn">No grid cells of this dataset fall in this area.</div>}
      </div>

      {!!meta.n_persistent_cells && (
        <label className="toggle">
          <input type="checkbox" checked={excludePersistent} onChange={(e) => onExcludePersistent(e.target.checked)} />
          <span className="toggle-ui" aria-hidden />
          <span className="toggle-text">
            Hide industrial &amp; waste-burning sites
            <small>{meta.n_persistent_cells} cells with persistent non-wildfire heat; totals and anomalies are recomputed without them</small>
          </span>
        </label>
      )}

      <div className="chips" role="list">
        <button role="listitem" className={`chip${area.name === whole.name ? " is-on" : ""}`} onClick={() => onArea(whole)}>
          {whole.name}
        </button>
        {presets.map((p) => (
          <button key={p.name} role="listitem" className={`chip${area.name === p.name ? " is-on" : ""}`} onClick={() => onArea(areaFromBBox(p.name, p.bbox))}>
            {p.name}
          </button>
        ))}
      </div>

      <div className="draw-row">
        <button className={`btn btn-ghost${drawMode === "rect" ? " is-on" : ""}`} onClick={() => setDrawMode(drawMode === "rect" ? "none" : "rect")}>
          Draw box
        </button>
        <button className={`btn btn-ghost${drawMode === "poly" ? " is-on" : ""}`} onClick={() => setDrawMode(drawMode === "poly" ? "none" : "poly")}>
          Draw polygon
        </button>
      </div>

      <div className="seg seg-sm seg-full" role="tablist">
        <button role="tab" aria-selected={tab === "bbox"} className={tab === "bbox" ? "is-on" : ""} onClick={() => setTab("bbox")}>
          Bounds
        </button>
        <button role="tab" aria-selected={tab === "point"} className={tab === "point" ? "is-on" : ""} onClick={() => setTab("point")}>
          Point + radius
        </button>
      </div>

      {tab === "bbox" ? (
        <form
          className="coord-grid"
          onSubmit={(e) => {
            e.preventDefault();
            applyBbox();
          }}
        >
          {["West", "South", "East", "North"].map((label, k) => (
            <label key={label} className="field">
              <span>{label}</span>
              <input inputMode="decimal" value={bbox[k]} onChange={(e) => setBbox(bbox.map((v, j) => (j === k ? e.target.value : v)))} />
            </label>
          ))}
          <button className="btn btn-primary span-2" type="submit">
            Apply bounds
          </button>
        </form>
      ) : (
        <form
          className="coord-grid"
          onSubmit={(e) => {
            e.preventDefault();
            applyPoint();
          }}
        >
          <label className="field">
            <span>Latitude</span>
            <input inputMode="decimal" placeholder="33.89" value={pt.lat} onChange={(e) => setPt({ ...pt, lat: e.target.value })} />
          </label>
          <label className="field">
            <span>Longitude</span>
            <input inputMode="decimal" placeholder="35.50" value={pt.lon} onChange={(e) => setPt({ ...pt, lon: e.target.value })} />
          </label>
          <label className="field span-2">
            <span>Radius (km)</span>
            <input inputMode="decimal" value={pt.km} onChange={(e) => setPt({ ...pt, km: e.target.value })} />
          </label>
          <button className="btn btn-primary span-2" type="submit">
            Apply
          </button>
        </form>
      )}
      {err && <div className="warn">{err}</div>}
    </Section>
  );
}

// ---------------------------------------------------------------------------

interface DateProps {
  meta: DatasetMeta;
  range: [number, number];
  onRange: (r: [number, number]) => void;
  bounds: [number, number];
}

export function DatePanel({ range, onRange, bounds }: DateProps) {
  const years: number[] = [];
  for (let y = ymYear(bounds[0]); y <= ymYear(bounds[1]); y++) years.push(y);
  const clamp = (i: number) => Math.max(bounds[0], Math.min(bounds[1], i));
  const set = (from: number, to: number) => {
    const a = clamp(from);
    const b = clamp(to);
    onRange(a <= b ? [a, b] : [b, a]);
  };
  const lastY = ymYear(bounds[1]);
  const quick: [string, number, number][] = [
    ["All", bounds[0], bounds[1]],
    ["Last 10 yrs", ym(lastY - 9, 1), bounds[1]],
    ["Modelled (pre-2012)", bounds[0], ym(2011, 12)],
    ["Observed (2012–)", ym(2012, 1), bounds[1]],
  ];

  const Picker = ({ value, onChange, label }: { value: number; onChange: (i: number) => void; label: string }) => (
    <div className="ym-picker">
      <span className="field-label">{label}</span>
      <div className="ym-inputs">
        <select aria-label={`${label} month`} value={ymMonth(value)} onChange={(e) => onChange(ym(ymYear(value), Number(e.target.value)))}>
          {MONTH_ABBR.map((m, k) => (
            <option key={m} value={k + 1}>
              {m}
            </option>
          ))}
        </select>
        <select aria-label={`${label} year`} value={ymYear(value)} onChange={(e) => onChange(ym(Number(e.target.value), ymMonth(value)))}>
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </div>
    </div>
  );

  return (
    <Section title="Date range">
      <div className="ym-row">
        <Picker label="From" value={range[0]} onChange={(i) => set(i, range[1])} />
        <span className="ym-arrow" aria-hidden>→</span>
        <Picker label="To" value={range[1]} onChange={(i) => set(range[0], i)} />
      </div>
      <div className="chips">
        {quick.map(([label, a, b]) => (
          <button key={label} className={`chip${range[0] === clamp(a) && range[1] === clamp(b) ? " is-on" : ""}`} onClick={() => set(a, b)}>
            {label}
          </button>
        ))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------------------

/** Switches for slower machines: stop the animations, or hide the fire data and keep only the map. */
export function PerformancePanel(p: { animations: boolean; onAnimations: (on: boolean) => void; showData: boolean; onShowData: (on: boolean) => void }) {
  const Row = ({ on, set, label, hint }: { on: boolean; set: (v: boolean) => void; label: string; hint: string }) => (
    <label className="toggle">
      <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked)} />
      <span className="toggle-ui" aria-hidden />
      <span className="toggle-text">
        {label}
        <small>{hint}</small>
      </span>
    </label>
  );
  return (
    <Section title="Performance">
      <Row on={p.animations} set={p.onAnimations} label="Animations" hint="Sparks, camera orbit, moving pillars, glows and fades" />
      <Row on={p.showData} set={p.onShowData} label="Fire cells on the map" hint="Turn off to see the map only" />
      {(!p.animations || !p.showData) && <p className="muted small">Still slow? Press the 3D button on the map to go flat, and pick "Dark map" under Map layers.</p>}
    </Section>
  );
}

export function LayersPanel({ layers, setLayers, detections }: { layers: LayerState; setLayers: (l: LayerState) => void; detections: boolean }) {
  const all: { key: Exclude<keyof LayerState, "basemap">; label: string; hint: string }[] = [
    { key: "glow", label: "Fire glow", hint: "Activity as glowing points" },
    { key: "cells", label: "Grid cells", hint: "Activity per grid cell" },
    { key: "heat", label: "Heat surface", hint: "Smoothed density" },
    { key: "hotspots", label: "Hotspot points", hint: "Raw detections, selected month" },
    { key: "mask", label: "Dim outside area", hint: "" },
    { key: "extent", label: "Dataset extent", hint: "" },
  ];
  // Individual detections exist only for loaded FIRMS files.
  const rows = all.filter((r) => r.key !== "hotspots" || detections);
  return (
    <Section title="Map layers">
      <div className="seg seg-sm seg-full" role="radiogroup" aria-label="Basemap">
        {(["dark", "satellite"] as const).map((b) => (
          <button key={b} role="radio" aria-checked={layers.basemap === b} className={layers.basemap === b ? "is-on" : ""} onClick={() => setLayers({ ...layers, basemap: b })}>
            {b === "dark" ? "Dark map" : "Satellite"}
          </button>
        ))}
      </div>
      <ul className="layers">
        {rows.map((r) => {
          const l = layers[r.key] as { on: boolean; opacity?: number };
          return (
            <li key={r.key}>
              <label className="toggle">
                <input type="checkbox" checked={l.on} onChange={(e) => setLayers({ ...layers, [r.key]: { ...l, on: e.target.checked } })} />
                <span className="toggle-ui" aria-hidden />
                <span className="toggle-text">
                  {r.label}
                  {r.hint && <small>{r.hint}</small>}
                </span>
              </label>
              {l.opacity !== undefined && (
                <input
                  type="range"
                  className="opacity"
                  min={0.1}
                  max={1}
                  step={0.05}
                  value={l.opacity}
                  disabled={!l.on}
                  aria-label={`${r.label} opacity`}
                  onChange={(e) => setLayers({ ...layers, [r.key]: { ...l, opacity: Number(e.target.value) } })}
                />
              )}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

// ---------------------------------------------------------------------------

export function EventsPanel({ events, documented, onJump, activeId }: { events: KeyEvent[]; documented: KeyEvent[]; onJump: (e: KeyEvent) => void; activeId?: string }) {
  return (
    <>
      {documented.length > 0 && (
        <Section title="Documented fires">
          <ul className="events">
            {documented.map((e) => (
              <li key={e.id}>
                <button className={`event tone-event${activeId === e.id ? " is-active" : ""}`} onClick={() => onJump(e)}>
                  <svg className="event-flame" viewBox="0 0 16 16" aria-hidden>
                    <path d="M8 1.5c.6 2.3 3.8 3.7 3.8 7.3A3.8 3.8 0 0 1 8 12.6a3.8 3.8 0 0 1-3.8-3.8c0-1.6.8-2.6 1.5-3.4.2 1 .7 1.8 1.4 2.1C7 5.6 6.9 3.4 8 1.5z" />
                  </svg>
                  <span className="event-text">
                    <b>{e.label}</b>
                    <small>{e.detail}</small>
                    {activeId === e.id && e.note && <span className="event-note">{e.note}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Section>
      )}
    <Section title="In the numbers">
      {events.length === 0 ? (
        <p className="muted small">Nothing notable in this selection.</p>
      ) : (
        <ul className="events">
          {events.map((e) => (
            <li key={e.id}>
              <button className={`event tone-${e.tone}`} onClick={() => onJump(e)} disabled={e.i === undefined}>
                <span className="event-dot" aria-hidden />
                <span className="event-text">
                  <b>{e.label}</b>
                  <small>{e.detail}</small>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Section>
    </>
  );
}
