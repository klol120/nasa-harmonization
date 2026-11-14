import { METRICS, type Metric, SENSORS, type Sensor, parseYm, ymKey } from "../data/contract";
import { type Area, type Ring, areaFromBBox, areaFromRing } from "./geo";

/** Shareable view state in the URL hash, e.g. #src=api:lebanon&s=harmonized&b=35.4,33.5,35.7,33.8&r=2000-11,2026-11 */
export interface UrlState {
  source?: string;
  sensor?: Sensor;
  metric?: Metric;
  area?: Area;
  /** True when the area is the whole region (kept short in the URL: a=all). */
  areaAll?: boolean;
  range?: [number, number];
  selected?: number;
}

let reloading = false;

export function readHash(): UrlState {
  const p = new URLSearchParams(window.location.hash.slice(1));
  const out: UrlState = {};
  try {
    if (p.get("src")) out.source = p.get("src")!;
    const s = p.get("s") as Sensor;
    if (SENSORS.includes(s)) out.sensor = s;
    const m = p.get("m") as Metric;
    if (METRICS.includes(m)) out.metric = m;
    const name = p.get("n") ?? "Shared area";
    const b = p.get("b")?.split(",").map(Number);
    if (b && b.length === 4 && b.every(Number.isFinite)) out.area = areaFromBBox(name, b as [number, number, number, number]);
    const poly = p.get("p")?.split(";").map((pt) => pt.split(",").map(Number) as [number, number]);
    if (poly && poly.length >= 3 && poly.every((pt) => pt.length === 2 && pt.every(Number.isFinite))) out.area = areaFromRing(name, poly as Ring);
    const r = p.get("r")?.split(",");
    if (r?.length === 2 && r.every((x) => /^\d{4}-\d{2}$/.test(x))) out.range = [parseYm(r[0]), parseYm(r[1])];
    if (p.get("a") === "all") {
      out.area = undefined;
      out.areaAll = true;
    }
    const t = p.get("t");
    if (t && /^\d{4}-\d{2}$/.test(t)) out.selected = parseYm(t);
  } catch {
    // Malformed hash: ignore and use defaults.
  }
  return out;
}

export function writeHash(s: Required<Omit<UrlState, "areaAll">> & { areaAll: boolean }) {
  const p = new URLSearchParams();
  p.set("src", s.source);
  p.set("s", s.sensor);
  p.set("m", s.metric);
  if (s.areaAll) p.set("a", "all");
  else {
    p.set("n", s.area.name);
    if (s.area.kind === "polygon") p.set("p", s.area.ring.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(";"));
    else p.set("b", s.area.bbox.map((v) => v.toFixed(3)).join(","));
  }
  p.set("r", `${ymKey(s.range[0])},${ymKey(s.range[1])}`);
  p.set("t", ymKey(s.selected));
  if (reloading) return; // a hand-edited URL is being applied; don't overwrite it
  const next = `#${p.toString()}`;
  if (next !== window.location.hash) history.replaceState(null, "", next);
}

/** Reload when someone edits or pastes a different hash by hand (our own writes use replaceState and fire no event). */
export function reloadOnManualHashChange() {
  const onChange = () => {
    reloading = true;
    window.location.reload();
  };
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
