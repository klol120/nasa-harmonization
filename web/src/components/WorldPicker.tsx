import { useEffect, useMemo, useRef, useState } from "react";
import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent, SkySpecification } from "maplibre-gl";
import { REGION_INFO, regionInfo } from "../config";
import type { RegionSummary } from "../data/api";
import { type Country, type Ring, loadCountries } from "../data/regions";
import { DAY_EARTH_SOURCE, NIGHT_LIGHTS_SOURCE, loadStyle, maplibregl } from "../lib/maplibre";
import { reducedMotion } from "../lib/motion";
import { type Theme, useTheme } from "../lib/theme";

/**
 * How the globe looks in each theme: Earth at night in deep space (dark), Earth by day under a
 * pale sky (light). land/water tint the basemap that shows while imagery loads or when offline.
 */
const GLOBE: Record<Theme, { land: string; water: string; sky: string; horizon: string; fog: string; border: string; borderServed: string; borderHover: string; borderOpacity: number }> = {
  dark: { land: "#04060c", water: "#060a17", sky: "#0d1f4a", horizon: "#3d7bff", fog: "#0a1430", border: "#9fb4e0", borderServed: "#fcb43a", borderHover: "#e6eeff", borderOpacity: 0.28 },
  light: { land: "#c9d8c0", water: "#7fa9d6", sky: "#9cc7f2", horizon: "#ffffff", fog: "#e4effa", border: "#ffffff", borderServed: "#ff7a00", borderHover: "#ffffff", borderOpacity: 0.5 },
};

const skyFor = (t: Theme): SkySpecification => ({
  "sky-color": GLOBE[t].sky,
  "horizon-color": GLOBE[t].horizon,
  "fog-color": GLOBE[t].fog,
  "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 4.5, 1, 6.5, 0],
});

const borderColor = (t: Theme): ExpressionSpecification => [
  "case",
  ["all", ["boolean", ["feature-state", "hover"], false], ["!=", ["get", "region"], ""]],
  GLOBE[t].borderHover,
  ["!=", ["get", "region"], ""],
  GLOBE[t].borderServed,
  GLOBE[t].border,
];

interface Props {
  /** Regions on the data server; null while loading. */
  regions: RegionSummary[] | null;
  /** Why the region list could not be loaded. */
  error: string | null;
  onRetry: () => void;
  onEnter: (regionId: string) => void;
  /** Region the dashboard last showed, highlighted when coming back. */
  current?: string;
  /** Optional extras shown in the panel (email list) and the top-right corner (account). */
  extras?: React.ReactNode;
  corner?: React.ReactNode;
}

/**
 * Rings that cross the antimeridian (Fiji, Chukotka) jump from +180 to -180, which on a globe
 * draws an edge all the way round the planet. Shift longitudes so the ring stays continuous;
 * rings that genuinely wrap the pole (Antarctica) are left as they are.
 */
function unwrapRing(ring: Ring): Ring {
  let shift = 0;
  const out: Ring = ring.map(([x, y], i) => {
    if (i > 0) {
      const dx = x - ring[i - 1][0];
      if (dx > 180) shift -= 360;
      else if (dx < -180) shift += 360;
    }
    return [x + shift, y];
  });
  return shift === 0 ? out : ring;
}

/** Regions in the order they are presented: configured ones first (Lebanon leads), then the rest by name. */
function ordered(regions: RegionSummary[]) {
  const order = Object.keys(REGION_INFO);
  const rank = (r: RegionSummary) => (order.includes(r.region) ? order.indexOf(r.region) : order.length);
  return [...regions].sort((a, b) => rank(a) - rank(b) || a.region.localeCompare(b.region));
}

/** For each country name, the smallest served region that covers it (Lebanon → "lebanon", Syria → "eastmed"). */
function regionByCountry(regions: RegionSummary[]) {
  const out = new Map<string, string>();
  for (const r of [...regions].sort((a, b) => b.countries.length - a.countries.length)) for (const c of r.countries) out.set(c.toLowerCase(), r.region);
  return out;
}

const markerAt = (r: RegionSummary): [number, number] => regionInfo(r.region).marker ?? [(r.bbox[0] + r.bbox[2]) / 2, (r.bbox[1] + r.bbox[3]) / 2];

/**
 * Landing view: a world map where the user picks a region the data server has.
 * Served regions pulse; the countries they cover can be clicked or searched.
 */
export function WorldPicker({ regions, error, onRetry, onEnter, current, extras, corner }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [countries, setCountries] = useState<Country[]>([]);
  const [query, setQuery] = useState("");
  const [hover, setHover] = useState<{ name: string; region?: string; x: number; y: number } | null>(null);
  const [flying, setFlying] = useState<string | null>(null);
  const [active, setActive] = useState(0);
  const enterRef = useRef(onEnter);
  enterRef.current = onEnter;
  const regionsRef = useRef<RegionSummary[]>([]);
  regionsRef.current = regions ?? [];
  const spinRef = useRef(true);
  const pauseRef = useRef(false);
  const resumeRef = useRef<() => void>(() => {});
  const stars = useRef<HTMLCanvasElement>(null);
  const [theme] = useTheme();
  // Read by the one-off globe setup, which must not rebuild when the theme changes.
  const themeRef = useRef(theme);
  themeRef.current = theme;
  /** Basemap layers recoloured per theme (background and water fills). */
  const tintLayers = useRef<{ id: string; prop: "background-color" | "fill-color"; key: "land" | "water" }[]>([]);

  // Starfield behind the globe (seeded, so it is the same every visit).
  useEffect(() => {
    const c = stars.current;
    if (!c) return;
    const draw = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      c.width = c.clientWidth * dpr;
      c.height = c.clientHeight * dpr;
      const g = c.getContext("2d")!;
      let seed = 20261114;
      const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
      const n = Math.round((c.clientWidth * c.clientHeight) / 2600);
      for (let k = 0; k < n; k++) {
        const r = rnd() ** 3 * 1.3 * dpr + 0.25 * dpr;
        g.globalAlpha = 0.25 + rnd() * 0.65;
        g.fillStyle = rnd() < 0.12 ? "#ffd9a8" : rnd() < 0.2 ? "#b9d0ff" : "#ffffff";
        g.beginPath();
        g.arc(rnd() * c.width, rnd() * c.height, r, 0, Math.PI * 2);
        g.fill();
      }
    };
    draw();
    window.addEventListener("resize", draw);
    return () => window.removeEventListener("resize", draw);
  }, []);

  const go = (regionId: string) => {
    if (flying) return;
    const region = regionsRef.current.find((r) => r.region === regionId);
    if (!region) return;
    setFlying(regionInfo(region.region).name);
    const m = map.current;
    if (m) {
      spinRef.current = false;
      m.stop();
      m.fitBounds(
        [
          [region.bbox[0], region.bbox[1]],
          [region.bbox[2], region.bbox[3]],
        ],
        { padding: 80, duration: 2400, maxZoom: 8, essential: true },
      );
      m.once("moveend", () => enterRef.current(region.region));
    } else enterRef.current(region.region);
  };
  const goRef = useRef(go);
  goRef.current = go;

  // ---- the globe (built once; the theme is applied in place below) ------------
  useEffect(() => {
    let disposed = false;
    Promise.all([loadStyle("darkNoLabels"), loadCountries()]).then(([style, cs]) => {
      if (disposed) return;
      setCountries(cs);
      // Basemap land and water take the theme's colours, so the globe never shows Carto's flat grey while imagery loads.
      const look = GLOBE[themeRef.current];
      for (const l of style.layers) {
        if (l.type === "background") {
          l.paint = { ...l.paint, "background-color": look.land };
          tintLayers.current.push({ id: l.id, prop: "background-color", key: "land" });
        } else if (l.type === "fill" && /water|ocean/.test(l.id)) {
          l.paint = { ...l.paint, "fill-color": look.water };
          tintLayers.current.push({ id: l.id, prop: "fill-color", key: "water" });
        }
      }
      const wide = el.current!.clientWidth > 760;
      const h = el.current!.clientHeight;
      const m = new maplibregl.Map({
        container: el.current!,
        style,
        center: [38, 24],
        // Globe diameter is about 512 * 2^zoom / pi px: size it to ~74% of the height (or the free space on phones).
        zoom: Math.log2(((wide ? Math.min(h * 0.72, (el.current!.clientWidth - 440) * 0.78) : h * 0.4) * Math.PI) / 512),
        minZoom: 0.8,
        attributionControl: { compact: true },
        dragRotate: false,
      });
      m.touchZoomRotate.disableRotation();
      map.current = m;
      // Keep the globe in the space the side (desktop) or bottom (phone) panel leaves free.
      m.setPadding(wide ? { left: Math.min(440, el.current!.clientWidth * 0.4), top: 0, right: 0, bottom: 0 } : { left: 0, right: 0, top: 0, bottom: Math.round(h * 0.56) });

      // A globe with a thin atmosphere; MapLibre eases into a flat map as the camera flies in.
      m.on("style.load", () => {
        m.setProjection({ type: "globe" });
        m.setSky(skyFor(themeRef.current));
      });

      // Slow spin until the user takes over (or picks a place).
      const reduce = reducedMotion();
      const spin = () => {
        if (!spinRef.current || pauseRef.current || disposed || reduce) return;
        const c = m.getCenter();
        m.easeTo({ center: [c.lng + 14, c.lat], duration: 7000, easing: (t) => t });
      };
      resumeRef.current = spin;
      m.on("moveend", (e) => {
        if (!(e as { originalEvent?: unknown }).originalEvent) spin();
      });
      for (const ev of ["mousedown", "touchstart", "wheel", "dragstart"] as const)
        m.on(ev, () => {
          spinRef.current = false;
        });

      m.on("load", () => {
        spin();
        // The globe surface: Earth at night (VIIRS Black Marble) in dark mode, Earth by day (Blue Marble)
        // in light mode. Both stay loaded so switching is instant; offline, the tinted basemap shows through.
        const dark = themeRef.current === "dark";
        m.addSource("night", NIGHT_LIGHTS_SOURCE);
        m.addLayer({
          id: "night",
          type: "raster",
          source: "night",
          layout: { visibility: dark ? "visible" : "none" },
          paint: { "raster-contrast": 0.15, "raster-saturation": -0.15, "raster-brightness-min": 0.02, "raster-fade-duration": 400 },
        });
        m.addSource("day", DAY_EARTH_SOURCE);
        m.addLayer({
          id: "day",
          type: "raster",
          source: "day",
          layout: { visibility: dark ? "none" : "visible" },
          paint: { "raster-saturation": 0.05, "raster-contrast": 0.05, "raster-fade-duration": 400 },
        });
        m.addSource("countries", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        const hovered_: ExpressionSpecification = ["boolean", ["feature-state", "hover"], false];
        const served_: ExpressionSpecification = ["!=", ["get", "region"], ""];
        m.addLayer({
          id: "country-fill",
          type: "fill",
          source: "countries",
          paint: {
            "fill-color": ["case", served_, ["case", hovered_, "#fca50a", "#f37819"], "#3d7bff"],
            "fill-opacity": ["case", ["all", hovered_, served_], 0.34, ["==", ["get", "current"], 1], 0.3, served_, 0.2, hovered_, 0.05, 0.01],
          },
        });
        // Soft glow under the outlines of countries the server has data for.
        m.addLayer({
          id: "country-glow",
          type: "line",
          source: "countries",
          filter: served_,
          layout: { "line-join": "round" },
          paint: { "line-color": "#f37819", "line-width": 6, "line-blur": 5, "line-opacity": 0.55 },
        });
        m.addLayer({
          id: "country-line",
          type: "line",
          source: "countries",
          layout: { "line-join": "round" },
          paint: {
            "line-color": borderColor(themeRef.current),
            "line-width": ["case", ["all", hovered_, served_], 1.6, served_, 1.1, 0.5],
            "line-opacity": ["case", hovered_, 1, served_, 0.95, GLOBE[themeRef.current].borderOpacity],
          },
        });

        let hovered: number | null = null;
        m.on("mousemove", "country-fill", (e: MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f) return;
          if (hovered !== null) m.setFeatureState({ source: "countries", id: hovered }, { hover: false });
          hovered = f.id as number;
          m.setFeatureState({ source: "countries", id: hovered }, { hover: true });
          const region = (f.properties as any).region as string;
          m.getCanvas().style.cursor = region ? "pointer" : "";
          if (!pauseRef.current && spinRef.current) {
            pauseRef.current = true;
            m.stop();
          }
          setHover({ name: (f.properties as any).name, region: region || undefined, x: e.point.x, y: e.point.y });
        });
        m.on("mouseleave", "country-fill", () => {
          if (hovered !== null) m.setFeatureState({ source: "countries", id: hovered }, { hover: false });
          hovered = null;
          m.getCanvas().style.cursor = "";
          setHover(null);
          pauseRef.current = false;
          resumeRef.current();
        });
        m.on("click", "country-fill", (e: MapLayerMouseEvent) => {
          const region = (e.features?.[0]?.properties as any)?.region;
          if (region) goRef.current(region);
        });
        setReady(true);
      });
    });
    return () => {
      disposed = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // ---- theme: swap day/night imagery, sky and border colours in place ------------
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const look = GLOBE[theme];
    m.setLayoutProperty("night", "visibility", theme === "dark" ? "visible" : "none");
    m.setLayoutProperty("day", "visibility", theme === "dark" ? "none" : "visible");
    for (const t of tintLayers.current) if (m.getLayer(t.id)) m.setPaintProperty(t.id, t.prop, look[t.key]);
    m.setSky(skyFor(theme));
    m.setPaintProperty("country-line", "line-color", borderColor(theme));
    m.setPaintProperty("country-line", "line-opacity", ["case", ["boolean", ["feature-state", "hover"], false], 1, ["!=", ["get", "region"], ""], 0.95, look.borderOpacity]);
  }, [theme, ready]);

  // ---- served regions: country colouring and pulsing markers -----------------
  useEffect(() => {
    const m = map.current;
    if (!ready || !m || !countries.length) return;
    const byCountry = regionByCountry(regions ?? []);
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: countries.map((c, k) => {
        const region = byCountry.get(c.name.toLowerCase()) ?? "";
        return {
          type: "Feature",
          id: k,
          properties: { name: c.name, region, current: region && region === current ? 1 : 0 },
          geometry: { type: "MultiPolygon", coordinates: c.outline.map((ring) => [unwrapRing(ring)]) },
        };
      }),
    };
    (m.getSource("countries") as GeoJSONSource).setData(fc);

    const markers = ordered(regions ?? []).map((r) => {
      const name = regionInfo(r.region).name;
      const node = document.createElement("button");
      node.className = "pulse";
      node.setAttribute("aria-label", `Open ${name}`);
      node.innerHTML = `<span class="pulse-ring"></span><span class="pulse-dot"></span><span class="pulse-label"></span>`;
      node.querySelector(".pulse-label")!.textContent = name;
      node.addEventListener("click", (ev) => {
        ev.stopPropagation();
        goRef.current(r.region);
      });
      return new maplibregl.Marker({ element: node, opacityWhenCovered: "0" }).setLngLat(markerAt(r)).addTo(m);
    });
    return () => markers.forEach((mk) => mk.remove());
  }, [ready, countries, regions, current]);

  // ---- search: served regions and the countries they cover ------------------
  const searchable = useMemo(() => {
    const out: { label: string; region: string; tag?: string }[] = [];
    for (const r of ordered(regions ?? [])) {
      out.push({ label: regionInfo(r.region).name, region: r.region, tag: "region" });
      for (const c of r.countries) if (c.toLowerCase() !== regionInfo(r.region).name.toLowerCase()) out.push({ label: c, region: r.region, tag: regionInfo(r.region).name });
    }
    return out;
  }, [regions]);
  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return searchable
      .filter((c) => c.label.toLowerCase().includes(q))
      .sort((a, b) => Number(!a.label.toLowerCase().startsWith(q)) - Number(!b.label.toLowerCase().startsWith(q)))
      .slice(0, 7);
  }, [searchable, query]);
  useEffect(() => setActive(0), [query]);

  const list = ordered(regions ?? []);
  const hero = list[0];
  const others = list.slice(1);

  return (
    <div className={`world${flying ? " is-flying" : ""}`}>
      <canvas ref={stars} className="world-stars" aria-hidden />
      <div className="world-glow" aria-hidden />
      <div ref={el} className="world-map" />
      <div className="world-vignette" aria-hidden />

      <aside className="world-panel">
        <div className="world-brand">
          <img src="./emblem.png" alt="" width={44} height={44} />
          <div>
            <strong>Phoenical</strong>
            <span>NASA Space Apps 2026 · Challenge #09</span>
          </div>
        </div>

        <h1>
          25 years of fire.
          <br />
          <em>One consistent record.</em>
        </h1>
        <p className="world-lede">
          MODIS and VIIRS satellite hotspots harmonized into a burning calendar, so a change of satellite never looks like a fire crisis. Pick a place to
          start.
        </p>

        {error ? (
          <div className="world-status">
            <p className="warn">{error}</p>
            <button className="btn btn-primary" onClick={onRetry}>
              Try again
            </button>
          </div>
        ) : !regions ? (
          <div className="world-status">
            <span className="spinner" aria-hidden /> Connecting to the data server…
          </div>
        ) : !regions.length ? (
          <div className="world-status">
            <p className="warn">The data server has no regions loaded yet. Load an export with "python -m firecal_api.cli ingest".</p>
          </div>
        ) : (
          <>
            <div className="world-search">
              <svg viewBox="0 0 20 20" aria-hidden>
                <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
                <path d="M13.2 13.2 17 17" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
              <input
                placeholder="Search a region or country…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") setActive((a) => Math.min(results.length - 1, a + 1));
                  if (e.key === "ArrowUp") setActive((a) => Math.max(0, a - 1));
                  if (e.key === "Enter" && results[active]) go(results[active].region);
                  if (e.key === "Escape") setQuery("");
                }}
                aria-label="Search a region or country"
                aria-autocomplete="list"
              />
              {query.trim() && (
                <ul className="world-results" role="listbox">
                  {results.length ? (
                    results.map((r, k) => (
                      <li key={`${r.region}-${r.label}`} role="option" aria-selected={k === active}>
                        <button className={k === active ? "is-active" : ""} onMouseEnter={() => setActive(k)} onClick={() => go(r.region)}>
                          {r.label}
                          {r.tag && <span className="tag">{r.tag}</span>}
                        </button>
                      </li>
                    ))
                  ) : (
                    <li className="world-results-empty">No data for “{query.trim()}” yet</li>
                  )}
                </ul>
              )}
            </div>

            {hero && (
              <button className="hero-card" onClick={() => go(hero.region)}>
                <span className="eyebrow">Start here</span>
                <span className="hero-card-title">{regionInfo(hero.region).name}</span>
                {regionInfo(hero.region).blurb && <span className="hero-card-blurb">{regionInfo(hero.region).blurb}</span>}
                <span className="hero-card-cta">
                  Open the burning calendar <span aria-hidden>→</span>
                </span>
              </button>
            )}

            {others.length > 0 && (
              <div className="world-others">
                <span className="eyebrow">More regions</span>
                <div className="world-chips">
                  {others.map((r) => (
                    <button key={r.region} className="chip" onClick={() => go(r.region)} title={regionInfo(r.region).blurb}>
                      {regionInfo(r.region).name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {extras}

        <p className="world-foot">
          Or click a highlighted country on the map. Data: NASA FIRMS, harmonized by the Wel3a pipeline. ·{" "}
          <a href="./privacy.html">Privacy</a> · <a href="./terms.html">Terms</a>
        </p>
      </aside>
      {corner && <div className="world-corner">{corner}</div>}

      {hover && !flying && (
        <div className="world-tip" style={{ left: hover.x + 14, top: hover.y + 14 }}>
          {hover.name}
          {!hover.region ? <span className="world-tip-sub"> · no data yet</span> : regionInfo(hover.region).name !== hover.name ? <span className="world-tip-sub"> · {regionInfo(hover.region).name}</span> : null}
        </div>
      )}
      {flying && (
        <div className="world-flying" role="status">
          <span className="spinner" aria-hidden />
          Opening {flying}…
        </div>
      )}
    </div>
  );
}
