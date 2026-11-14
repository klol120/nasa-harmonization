import { METRICS, type Metric, SENSORS, type Sensor, parseYm, ymKey } from "../data/contract";
import { type Area, type Ring, areaFromBBox, areaFromRing } from "./geo";

/** Pages of the site. "explore" is the world globe; the others show one region. */
export const PAGES = ["explore", "overview", "calendar", "trends", "weather", "methods"] as const;
export type Page = (typeof PAGES)[number];
const isPage = (p: string | null): p is Page => !!p && (PAGES as readonly string[]).includes(p);

/** Shareable view state in the URL hash, e.g. #pg=calendar&src=api:lebanon&s=harmonized&a=all&r=2000-11,2026-11 */
export interface UrlState {
  page?: Page;
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
/** The hash this app last put in the URL, to tell our own navigation from a hand-edited link. */
let lastWritten = window.location.hash;

export function readHash(): UrlState {
  const p = new URLSearchParams(window.location.hash.slice(1));
  const out: UrlState = {};
  try {
    const pg = p.get("pg");
    if (isPage(pg)) out.page = pg;
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
  p.set("pg", s.page);
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
  lastWritten = next;
  if (next !== window.location.hash) history.replaceState(null, "", next);
}

/** The current link with another page in it (for nav hrefs, so they can be opened in a new tab). */
export function pageHref(page: Page) {
  const p = new URLSearchParams(window.location.hash.slice(1));
  p.set("pg", page);
  return `#${p.toString()}`;
}

/** Moves to another page as a new history entry, so Back returns to the previous page. */
export function pushPage(page: Page) {
  const next = pageHref(page);
  lastWritten = next;
  if (next !== window.location.hash) history.pushState(null, "", next);
}

const withoutPage = (hash: string) => {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  p.delete("pg");
  return p.toString();
};

/**
 * Back/forward between pages switches the page in place. Any other change to the hash (someone
 * pastes or edits a link) reloads, so the new view state is applied from scratch.
 * Our own writes use replaceState/pushState and fire no event.
 */
export function watchHash(onPage: (p: Page) => void) {
  const onChange = () => {
    const hash = window.location.hash;
    const p = new URLSearchParams(hash.slice(1));
    const pg = p.get("pg");
    if (!p.get("src") || withoutPage(hash) === withoutPage(lastWritten)) {
      lastWritten = hash;
      onPage(isPage(pg) ? pg : p.get("src") ? "overview" : "explore");
      return;
    }
    reloading = true;
    window.location.reload();
  };
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
