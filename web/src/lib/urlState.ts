import { METRICS, type Metric, SENSORS, type Sensor, parseYm, ymKey } from "../data/contract";
import { type Area, type Ring, areaFromBBox, areaFromRing } from "./geo";

/** Pages of the site. "explore" is the world globe; the others show one region. */
export const PAGES = ["explore", "overview", "calendar", "trends", "forecast", "weather", "methods"] as const;
export type Page = (typeof PAGES)[number];
const isPage = (p: string | null | undefined): p is Page => !!p && (PAGES as readonly string[]).includes(p);

/**
 * View state and the URL.
 *
 * The address bar shows only the page and the region: #/calendar/lebanon (the world map is #/).
 * The rest of the view (sensor, metric, area, date range, month) is kept with the browser history
 * entry, so refresh and back/forward still restore it, and is put in the link only when sharing:
 *   #/calendar/lebanon?s=harmonized&m=cell_days&a=all&r=2000-11,2026-11&t=2026-10
 * Links in the old format (#pg=calendar&src=api:lebanon&...) still open.
 */
export interface UrlState {
  page?: Page;
  source?: string;
  sensor?: Sensor;
  metric?: Metric;
  area?: Area;
  /** True when the area is the whole region (kept short in the link: a=all). */
  areaAll?: boolean;
  range?: [number, number];
  selected?: number;
}

interface Parsed {
  page?: Page;
  source?: string;
  /** The view details (s, m, a, n, b, p, r, t). Empty in a short link. */
  details: URLSearchParams;
}

/** What this app keeps with each history entry: the view details of that entry. */
interface HistoryState {
  firecal: { source: string; details: string };
}

/** "api:lebanon" is shown as "lebanon"; any other source id is kept whole. */
const sourceToPath = (source: string) => (source.startsWith("api:") ? source.slice(4) : source);
const pathToSource = (seg: string) => (seg.includes(":") ? seg : `api:${seg}`);

function parse(hash: string): Parsed {
  const h = hash.replace(/^#/, "");
  if (h.startsWith("/")) {
    const [path, query = ""] = h.slice(1).split("?", 2);
    const [pg, region] = path.split("/").map((x) => decodeURIComponent(x));
    return { page: isPage(pg) ? pg : undefined, source: region ? pathToSource(region) : undefined, details: new URLSearchParams(query) };
  }
  // Old format: everything in one query.
  const p = new URLSearchParams(h);
  const pg = p.get("pg");
  const source = p.get("src") ?? undefined;
  p.delete("pg");
  p.delete("src");
  return { page: isPage(pg) ? pg : undefined, source, details: p };
}

/** A link in the current format. Without details it is the short form shown in the address bar. */
export function buildHash(page: Page, source: string | undefined, details?: URLSearchParams | string) {
  const q = details ? details.toString() : "";
  if (!source) return page === "explore" ? "#/" : `#/${page}`;
  if (page === "explore" && !q) return "#/";
  return `#/${page}/${encodeURIComponent(sourceToPath(source))}${q ? `?${q}` : ""}`;
}

const savedState = (): HistoryState["firecal"] | undefined => (history.state as Partial<HistoryState> | null)?.firecal;

let reloading = false;
/** The current view as a full link (page, region and details), as this app last wrote it. */
let current: Parsed = parse(window.location.hash);

export function readHash(): UrlState {
  const parsed = parse(window.location.hash);
  // A short link: take the details kept with this history entry (refresh, back/forward).
  const saved = savedState();
  if (![...parsed.details.keys()].length && saved && (!parsed.source || parsed.source === saved.source)) {
    parsed.source = saved.source;
    parsed.details = new URLSearchParams(saved.details);
  }
  current = parsed;
  const p = parsed.details;
  const out: UrlState = {};
  try {
    if (parsed.page) out.page = parsed.page;
    if (parsed.source) out.source = parsed.source;
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
    // Malformed link: ignore and use defaults.
  }
  return out;
}

function entry(page: Page): [HistoryState | null, string] {
  const state = current.source ? { firecal: { source: current.source, details: current.details.toString() } } : null;
  return [state, buildHash(page, current.source)];
}

export function writeHash(s: Required<Omit<UrlState, "areaAll">> & { areaAll: boolean }) {
  const p = new URLSearchParams();
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
  if (reloading) return; // a pasted or edited link is being applied; don't overwrite it
  current = { page: s.page, source: s.source, details: p };
  const [state, short] = entry(s.page);
  history.replaceState(state, "", short);
}

/** The full link to another page of the current view (for nav hrefs, so they can be opened in a new tab). */
export function pageHref(page: Page) {
  return buildHash(page, current.source, current.details);
}

/** The full link to exactly this view, for sharing. */
export function shareUrl() {
  return `${window.location.href.split("#")[0]}${buildHash(current.page ?? "explore", current.source, current.details)}`;
}

/** Moves to another page as a new history entry, so Back returns to the previous page. */
export function pushPage(page: Page) {
  current = { ...current, page };
  const [state, short] = entry(page);
  if (short !== window.location.hash) history.pushState(state, "", short);
}

/**
 * Back/forward between pages, or a link that only changes the page, switches the page in place.
 * A link to another region or another view (pasted, edited, or opened from "My areas") reloads,
 * so the new view state is applied from scratch.
 * Our own writes use replaceState/pushState and fire no event.
 */
export function watchHash(onPage: (p: Page) => void) {
  const onChange = () => {
    const next = parse(window.location.hash);
    const saved = savedState();
    if (!next.source && saved) next.source = saved.source;
    const hasDetails = [...next.details.keys()].length > 0;
    const sameView =
      !next.source || (next.source === current.source && (!hasDetails || next.details.toString() === current.details.toString()));
    if (sameView) {
      current = { ...current, page: next.page ?? (next.source ? "overview" : "explore") };
      onPage(current.page!);
      return;
    }
    reloading = true;
    window.location.reload();
  };
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}
