import { useEffect, useRef, useState } from "react";
import type { GeoJSONSource } from "maplibre-gl";
import { FALLBACK_STYLE, SATELLITE_SOURCE, TERRAIN_SOURCE, loadStyle, maplibregl } from "../lib/maplibre";
import type { BBox, HotspotRow } from "../data/contract";
import { fmt, robustMax } from "../lib/analytics";
import { INFERNO } from "../lib/colors";
import { type Area, type Ring, areaFromBBox, areaFromRing, bboxRing } from "../lib/geo";
import { reducedMotion } from "../lib/motion";

export type DrawMode = "none" | "rect" | "poly";

export interface LayerState {
  basemap: "dark" | "satellite";
  glow: { on: boolean; opacity: number };
  cells: { on: boolean; opacity: number };
  heat: { on: boolean; opacity: number };
  hotspots: { on: boolean; opacity: number };
  extent: { on: boolean };
  mask: { on: boolean };
}

interface Props {
  area: Area;
  extent: BBox;
  gridDeg: number;
  cells: Map<string, { lat: number; lon: number; value: number }>;
  /** Fixed value that maps to the top of the scale (shared by every window of the range). Omitted: scale to the current window. */
  scaleMax?: number;
  hotspots: HotspotRow[];
  /** Region border (outer rings), drawn with a soft glow. */
  outline?: Ring[];
  /** The area is the whole region: its border already shows it, so skip the area line. */
  areaIsRegion?: boolean;
  /** A place to zoom to and mark (e.g. a documented fire); key changes re-trigger it. */
  focus?: { lat: number; lon: number; radius: number; key: string } | null;
  layers: LayerState;
  /** False hides every fire layer so only the map shows (lighter on slow machines). */
  showData: boolean;
  /** False stops sparks, the camera orbit and tweens. */
  animate: boolean;
  /** "grid" = the dataset's analysis grid, "1km" = detections re-gridded at ~1 km. */
  resolution: "grid" | "1km";
  onResolution: (r: "grid" | "1km") => void;
  /** Individual detections are available (loaded FIRMS files); otherwise the 1 km view is hidden. */
  detections: boolean;
  gridLabel: string;
  /** Extra line under the legend (what the cells mean). */
  note?: string;
  unit: string;
  windowLabel: string;
  drawMode: DrawMode;
  setDrawMode: (m: DrawMode) => void;
  onArea: (a: Area) => void;
  fitKey: string;
  mapRef?: React.MutableRefObject<maplibregl.Map | null>;
}


const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });
const poly = (ring: Ring, props: Record<string, unknown> = {}): GeoJSON.Feature => ({
  type: "Feature",
  properties: props,
  geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] },
});

const rampExpr = (): any[] => {
  const stops: (number | string)[] = [];
  INFERNO.forEach((c, k) => stops.push(k / (INFERNO.length - 1), c));
  return ["interpolate", ["linear"], ["get", "t"], ...stops];
};

/** Circle radius (px) equal to factor x one grid cell at the current zoom (Web Mercator, 512 px tiles). */
function cellRadius(gridDeg: number, factor: unknown): any {
  const px0 = (gridDeg * 512) / 360; // cell width in px at zoom 0
  return ["interpolate", ["exponential", 2], ["zoom"], 0, ["*", px0, factor], 22, ["*", px0 * 2 ** 22, factor]];
}

/** Tallest pillar, in grid-cell widths. */
const PILLAR_HEIGHT = 1.7;

/** Cells below this share of the scale keep their ground tile but get no column (stubs only add clutter). */
const PILLAR_MIN_T = 0.1;

/** Glowing cap on each column, as a share of the tallest column's height (thinner on short columns). */
const CAP_FRAC = 0.05;

/** Sides of the column polygon: enough to read as round, few enough to stay cheap while tweening. */
const COLUMN_SIDES = 16;

/** Mixes a hex colour towards warm white by k (0..1). */
function lighten(hex: string, k: number) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const to = [255, 243, 196];
  return `rgb(${[r, g, b].map((c, i) => Math.round(c + (to[i] - c) * k)).join(",")})`;
}

/**
 * The colour ramp brightened towards white-hot, for the column caps and the hovered column.
 * k0 at the cool end, k1 at the hot end: quiet cells get a subtle lid, the hottest a white-hot tip.
 */
const hotRampExpr = (k0: number, k1 = k0): any[] => {
  const stops: (number | string)[] = [];
  INFERNO.forEach((c, i) => {
    const x = i / (INFERNO.length - 1);
    stops.push(x, lighten(c, k0 + (k1 - k0) * x));
  });
  return ["interpolate", ["linear"], ["get", "t"], ...stops];
};

/** A round column footprint, corrected for latitude so it looks circular on the Mercator map. */
function column(lon: number, lat: number, r: number, maxLon: number, props: Record<string, unknown>): GeoJSON.Feature {
  const rLon = Math.min(r / Math.cos((lat * Math.PI) / 180), maxLon);
  const ring: Ring = [];
  for (let i = 0; i < COLUMN_SIDES; i++) {
    const a = (i / COLUMN_SIDES) * 2 * Math.PI;
    ring.push([lon + Math.cos(a) * rLon, lat + Math.sin(a) * r]);
  }
  return poly(ring, props);
}

interface LiveCell {
  lat: number;
  lon: number;
  value: number;
  t: number;
}

/** Vertical stretch of the terrain in 3D, so relief reads at country scale. */
const TERRAIN_EXAGGERATION = 2.2;

/** Zoom at which detections switch from dots to their true pixel footprints. */
const FOOTPRINT_ZOOM = 10;

/**
 * Pixel footprint of a detection: scan (across-track) x track (along-track) km around the
 * pixel centre. Drawn axis-aligned; the real pixel is rotated by the orbit (~8° off north).
 */
function footprint(h: HotspotRow): GeoJSON.Feature {
  const scan = h.scan ?? (h.instrument === "MODIS" ? 1 : 0.375);
  const track = h.track ?? (h.instrument === "MODIS" ? 1 : 0.375);
  const dLon = scan / 2 / (111.32 * Math.cos((h.latitude * Math.PI) / 180));
  const dLat = track / 2 / 110.57;
  const [x, y] = [h.longitude, h.latitude];
  return poly(
    [
      [x - dLon, y - dLat],
      [x + dLon, y - dLat],
      [x + dLon, y + dLat],
      [x - dLon, y + dLat],
    ],
    {
      instrument: h.instrument,
      satellite: h.satellite,
      date: h.acq_date,
      time: h.acq_time,
      frp: h.frp,
      confidence: h.confidence,
      scan: scan.toFixed(2),
      track: track.toFixed(2),
      lat: y,
      lon: x,
    },
  );
}

export function MapView(props: Props) {
  const { area, extent, gridDeg, cells, scaleMax, hotspots, outline, areaIsRegion, focus, layers, showData, animate, resolution, onResolution, detections, gridLabel, note, unit, windowLabel, drawMode, setDrawMode, onArea, fitKey, mapRef } = props;
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [basemap, setBasemap] = useState(true);
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  /** Legend scale: the value at the top of the ramp, whether some cells exceed it, and whether it is shared across the range. */
  const [scale, setScale] = useState({ max: 0, clipped: false, fixed: false });
  const [zoom, setZoom] = useState(0);
  const [mode3d, setMode3d] = useState(true);
  const [orbit, setOrbit] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const [panelsHidden, setPanelsHidden] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  /** The element that goes full screen: the whole stage (map + timeline) when there is one. */
  const stageEl = () => (wrap.current?.closest(".stage") as HTMLElement | null) ?? wrap.current;

  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement !== null && document.fullscreenElement === stageEl());
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = () => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void stageEl()?.requestFullscreen?.().catch(() => {});
  };
  // The floating panels live outside this component, so the switch is a class on the stage.
  useEffect(() => {
    stageEl()?.classList.toggle("panels-hidden", panelsHidden);
  }, [panelsHidden]);
  const fx = useRef<HTMLCanvasElement>(null);
  /** What the map shows right now (tweened), plus derived values the ember loop reads. */
  const live = useRef({
    shown: new Map<string, LiveCell>(),
    rise: 0,
    emitters: [] as LiveCell[],
    mode3d: true,
    gridDeg,
    embers: true,
    first3d: true,
    /** Rank of each cell by value in the current window (1 = most active), for the hover readout. */
    rank: new Map<string, number>(),
  });
  live.current.mode3d = mode3d;
  live.current.gridDeg = gridDeg;
  live.current.embers = layers.glow.on && showData && animate;
  const drawRef = useRef({ mode: drawMode, start: null as maplibregl.LngLat | null, verts: [] as [number, number][] });
  drawRef.current.mode = drawMode;
  const cbRef = useRef({ onArea, setDrawMode });
  cbRef.current = { onArea, setDrawMode };

  // --- init -------------------------------------------------------------
  useEffect(() => {
    let disposed = false;
    setReady(false);
    loadStyle().then((style) => {
      if (disposed) return;
      setBasemap(style.layers.length > FALLBACK_STYLE.layers.length);
      const m = new maplibregl.Map({
        container: el.current!,
        style,
        bounds: [
          [area.bbox[0], area.bbox[1]],
          [area.bbox[2], area.bbox[3]],
        ],
        fitBoundsOptions: { padding: 40 },
        attributionControl: { compact: true },
        canvasContextAttributes: { preserveDrawingBuffer: true }, // for PNG export
        dragRotate: false,
        pitchWithRotate: false,
        // The map sits in a scrolling dashboard: zoom needs Ctrl/⌘ + scroll so the page still scrolls.
        cooperativeGestures: true,
      });
      m.touchZoomRotate.disableRotation();
      m.on("zoomend", () => setZoom(m.getZoom()));
      m.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), "bottom-right");
      // Any hands-on camera move ends the automatic orbit.
      for (const ev of ["mousedown", "touchstart", "wheel"] as const) m.on(ev, () => setOrbit(false));
      m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
      map.current = m;
      if (mapRef) mapRef.current = m;
      if (import.meta.env.DEV) (window as any).__map = m;

      m.on("load", () => {
        const firstSymbol = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
        const empty = fc([]);
        for (const id of ["cells", "heat", "hotspots", "aoi", "mask", "extent", "draft", "outline", "footprints"]) m.addSource(id, { type: "geojson", data: empty });
        // Columns are keyed by cell id so the hovered one can be lit through feature state.
        m.addSource("pillars", { type: "geojson", data: empty, promoteId: "id" });
        m.addSource("sat", SATELLITE_SOURCE);
        // Elevation: one source lifts the ground in 3D, a second one shades the slopes.
        m.addSource("dem", TERRAIN_SOURCE);
        m.addSource("dem-shade", TERRAIN_SOURCE);
        m.addLayer({ id: "sat", type: "raster", source: "sat", layout: { visibility: "none" }, paint: { "raster-saturation": -0.35, "raster-brightness-max": 0.75 } }, firstSymbol);

        m.addLayer(
          { id: "heat", type: "heatmap", source: "heat", paint: {
            "heatmap-weight": ["get", "t"],
            "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 5, 0.8, 10, 2],
            "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 5, 10, 8, 26, 11, 60],
            "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.15, INFERNO[1], 0.35, INFERNO[3], 0.55, INFERNO[5], 0.75, INFERNO[7], 1, INFERNO[9]],
          } },
          firstSymbol,
        );
        m.addLayer(
          { id: "cells", type: "fill", source: "cells", paint: { "fill-color": rampExpr() as any, "fill-opacity": 0.8, "fill-outline-color": "rgba(0,0,0,0.25)" } },
          firstSymbol,
        );
        m.addLayer(
          {
            id: "hillshade",
            type: "hillshade",
            source: "dem-shade",
            layout: { visibility: "none" },
            paint: {
              "hillshade-exaggeration": 0.55,
              "hillshade-shadow-color": "#02040a",
              "hillshade-highlight-color": "rgba(255, 236, 200, 0.5)",
              "hillshade-accent-color": "#0b1220",
              "hillshade-illumination-direction": 315,
            },
          },
          "heat",
        );
        // 3D mode: every active cell becomes a round column whose height and colour follow the same
        // scale as the legend. The body stops where a thin white-hot cap takes over (no overlap, so
        // no z-fighting); heights are set with the grid in the data effect.
        const hovered = ["boolean", ["feature-state", "hover"], false];
        m.addLayer({
          id: "cells-3d",
          type: "fill-extrusion",
          source: "pillars",
          layout: { visibility: "none" },
          paint: {
            "fill-extrusion-color": ["case", hovered, hotRampExpr(0.45), rampExpr()] as any,
            "fill-extrusion-height": 0,
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.95,
            "fill-extrusion-vertical-gradient": true,
          },
        });
        m.addLayer({
          id: "cells-3d-cap",
          type: "fill-extrusion",
          source: "pillars",
          layout: { visibility: "none" },
          paint: {
            "fill-extrusion-color": ["case", hovered, "#ffffff", hotRampExpr(0.2, 0.75)] as any,
            "fill-extrusion-height": 0,
            "fill-extrusion-base": 0,
            "fill-extrusion-opacity": 0.95,
            "fill-extrusion-vertical-gradient": false,
          },
        });
        m.setLight({ anchor: "viewport", color: "#fff1dd", intensity: 0.45, position: [1.4, 215, 35] });
        // Mask sits above the data so everything outside the area is dimmed.
        m.addLayer({ id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#05070c", "fill-opacity": 0.55 } }, firstSymbol);
        // Glowing fire points: a blurred halo plus a bright core, both coloured by intensity.
        m.addLayer(
          {
            id: "glow",
            type: "circle",
            source: "heat",
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, ["*", 9, ["+", 0.4, ["get", "t"]]], 9, ["*", 30, ["+", 0.4, ["get", "t"]]]],
              "circle-color": rampExpr() as any,
              "circle-blur": 1,
              "circle-opacity": 0.75,
            },
          },
          firstSymbol,
        );
        m.addLayer(
          {
            id: "glow-core",
            type: "circle",
            source: "heat",
            filter: [">", ["get", "t"], 0.25],
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, ["*", 2.2, ["get", "t"]], 9, ["*", 6, ["get", "t"]]],
              "circle-color": "#fff3c4",
              "circle-blur": 0.4,
              "circle-opacity": ["*", 0.9, ["get", "t"]],
            },
          },
          firstSymbol,
        );
        m.addLayer({ id: "outline-glow", type: "line", source: "outline", paint: { "line-color": "#fca50a", "line-width": 7, "line-blur": 7, "line-opacity": 0.35 } });
        m.addLayer({ id: "outline-line", type: "line", source: "outline", paint: { "line-color": "#ffe1b0", "line-width": 1.3, "line-opacity": 0.9 } });
        m.addLayer({ id: "cells-hover", type: "line", source: "cells", paint: { "line-color": "#ffffff", "line-width": 1.5 }, filter: ["==", ["get", "id"], ""] });
        m.addLayer({
          id: "hotspots",
          type: "circle",
          source: "hotspots",
          maxzoom: FOOTPRINT_ZOOM,
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 1.6, 10, 4],
            "circle-color": ["match", ["get", "instrument"], "MODIS", "#E69F00", "#56B4E9"],
            "circle-stroke-color": "#0b0f17",
            "circle-stroke-width": 0.5,
          },
        });
        // Each detection drawn as its real pixel (scan x track km), once zoomed in far enough to see it.
        m.addLayer({
          id: "footprints",
          type: "fill",
          source: "footprints",
          minzoom: FOOTPRINT_ZOOM,
          paint: {
            "fill-color": ["match", ["get", "instrument"], "MODIS", "#E69F00", "#56B4E9"],
            "fill-opacity": [
              "*",
              ["match", ["get", "instrument"], "MODIS", 0.6, 1],
              ["interpolate", ["linear"], ["ln", ["+", 1, ["get", "frp"]]], 0, 0.3, 5, 0.8],
            ],
          },
        });
        m.addLayer({
          id: "footprints-line",
          type: "line",
          source: "footprints",
          minzoom: FOOTPRINT_ZOOM + 1,
          paint: { "line-color": ["match", ["get", "instrument"], "MODIS", "#ffcf6b", "#a9dcff"], "line-width": 0.8, "line-opacity": 0.9 },
        });
        m.addLayer({ id: "extent", type: "line", source: "extent", paint: { "line-color": "#6b7690", "line-width": 1, "line-dasharray": [3, 3] } });
        m.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#3d7bff", "line-width": 2 } });
        m.addLayer({ id: "draft-fill", type: "fill", source: "draft", paint: { "fill-color": "#3d7bff", "fill-opacity": 0.12 }, filter: ["==", ["geometry-type"], "Polygon"] });
        m.addLayer({ id: "draft-line", type: "line", source: "draft", paint: { "line-color": "#8fb0ff", "line-width": 1.5, "line-dasharray": [2, 1.5] } });
        m.addLayer({ id: "draft-pts", type: "circle", source: "draft", paint: { "circle-radius": 4, "circle-color": "#ffffff", "circle-stroke-color": "#3d7bff", "circle-stroke-width": 2 }, filter: ["==", ["geometry-type"], "Point"] });
        setReady(true);
      });

      // Hover readout on cells.
      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "cell-pop", offset: 10 });
      let hoverCol: string | null = null;
      const lightColumn = (id: string | null) => {
        if (id === hoverCol) return;
        if (hoverCol !== null) m.setFeatureState({ source: "pillars", id: hoverCol }, { hover: false });
        if (id !== null) m.setFeatureState({ source: "pillars", id }, { hover: true });
        hoverCol = id;
      };
      const cellHtml = (id: string, value: number, unit: string) => {
        const rank = live.current.rank.get(id);
        const of = live.current.rank.size;
        return `<b>${fmt(value)}</b> ${unit}${rank ? `<br/>#${rank} of ${of.toLocaleString()} active cells` : ""}<br/><span>cell ${id}</span>`;
      };
      m.on("mousemove", (e) => {
        setCursor([e.lngLat.lng, e.lngLat.lat]);
        if (drawRef.current.mode !== "none" || !m.getLayer("cells")) return;
        // In 3D the pointer is usually on a column, not over its ground cell: test the columns first.
        const col = m.getLayoutProperty("cells-3d", "visibility") !== "none" ? m.queryRenderedFeatures(e.point, { layers: ["cells-3d-cap", "cells-3d"] })[0] : undefined;
        if (col) {
          const p = col.properties as any;
          lightColumn(p.id);
          m.setFilter("cells-hover", ["==", ["get", "id"], ""]);
          popup.setLngLat(e.lngLat).setHTML(cellHtml(p.id, p.value, p.unit)).addTo(m);
          return;
        }
        lightColumn(null);
        const fp = m.getLayoutProperty("footprints", "visibility") !== "none" ? m.queryRenderedFeatures(e.point, { layers: ["footprints"] })[0] : undefined;
        if (fp) {
          const q = fp.properties as any;
          m.setFilter("cells-hover", ["==", ["get", "id"], ""]);
          popup
            .setLngLat(e.lngLat)
            .setHTML(
              `<b>${q.instrument}</b> · ${q.satellite} · ${q.date} ${q.time.slice(0, 2)}:${q.time.slice(2)} UTC<br/>FRP <b>${fmt(q.frp)} MW</b> · confidence ${q.confidence}<br/><span>pixel ${q.scan} × ${q.track} km · centre ${(+q.lat).toFixed(4)}, ${(+q.lon).toFixed(4)}</span>`,
            )
            .addTo(m);
          return;
        }
        const f = m.queryRenderedFeatures(e.point, { layers: ["cells"] })[0];
        if (!f) {
          popup.remove();
          m.setFilter("cells-hover", ["==", ["get", "id"], ""]);
          return;
        }
        const p = f.properties as any;
        m.setFilter("cells-hover", ["==", ["get", "id"], p.id]);
        popup.setLngLat(e.lngLat).setHTML(cellHtml(p.id, p.value, p.unit)).addTo(m);
      });
      m.on("mouseout", () => {
        lightColumn(null);
        popup.remove();
        setCursor(null);
      });
    });
    return () => {
      disposed = true;
      map.current?.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- drawing ------------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const draft = m.getSource("draft") as GeoJSONSource;
    const d = drawRef.current;
    d.start = null;
    d.verts = [];
    draft.setData(fc([]));
    m.getCanvas().style.cursor = drawMode === "none" ? "" : "crosshair";
    if (drawMode === "none") {
      m.dragPan.enable();
      m.doubleClickZoom.enable();
      return;
    }
    m.doubleClickZoom.disable();
    if (drawMode === "rect") m.dragPan.disable();

    const rectRing = (a: maplibregl.LngLat, b: maplibregl.LngLat): Ring => bboxRing([Math.min(a.lng, b.lng), Math.min(a.lat, b.lat), Math.max(a.lng, b.lng), Math.max(a.lat, b.lat)]);
    const finishPoly = () => {
      // A double-click also fires two clicks; drop the near-duplicate vertices they add.
      const verts = d.verts.filter((v, k) => k === 0 || Math.hypot(v[0] - d.verts[k - 1][0], v[1] - d.verts[k - 1][1]) > 1e-4);
      if (verts.length >= 3) cbRef.current.onArea(areaFromRing("Drawn polygon", verts));
      cbRef.current.setDrawMode("none");
    };

    const down = (e: maplibregl.MapMouseEvent) => {
      if (drawMode === "rect") d.start = e.lngLat;
    };
    const move = (e: maplibregl.MapMouseEvent) => {
      if (drawMode === "rect" && d.start) draft.setData(fc([poly(rectRing(d.start, e.lngLat))]));
      if (drawMode === "poly" && d.verts.length) {
        const pts = [...d.verts, [e.lngLat.lng, e.lngLat.lat] as [number, number]];
        draft.setData(
          fc([
            pts.length >= 3 ? poly(pts) : { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: pts } },
            ...d.verts.map((v) => ({ type: "Feature", properties: {}, geometry: { type: "Point", coordinates: v } }) as GeoJSON.Feature),
          ]),
        );
      }
    };
    const up = (e: maplibregl.MapMouseEvent) => {
      if (drawMode !== "rect" || !d.start) return;
      const a = d.start;
      d.start = null;
      if (Math.abs(a.lng - e.lngLat.lng) < 1e-3 || Math.abs(a.lat - e.lngLat.lat) < 1e-3) return;
      cbRef.current.onArea(areaFromBBox("Drawn rectangle", [a.lng, a.lat, e.lngLat.lng, e.lngLat.lat]));
      cbRef.current.setDrawMode("none");
    };
    const click = (e: maplibregl.MapMouseEvent) => {
      if (drawMode !== "poly") return;
      // Clicking near the first vertex closes the ring.
      if (d.verts.length >= 3) {
        const p0 = m.project(d.verts[0] as [number, number]);
        if (Math.hypot(p0.x - e.point.x, p0.y - e.point.y) < 10) return finishPoly();
      }
      d.verts.push([e.lngLat.lng, e.lngLat.lat]);
      move(e);
    };
    const dbl = (e: maplibregl.MapMouseEvent) => {
      if (drawMode !== "poly") return;
      e.preventDefault();
      finishPoly();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") cbRef.current.setDrawMode("none");
      if (e.key === "Enter" && drawMode === "poly") finishPoly();
    };
    m.on("mousedown", down);
    m.on("mousemove", move);
    m.on("mouseup", up);
    m.on("click", click);
    m.on("dblclick", dbl);
    window.addEventListener("keydown", key);
    return () => {
      m.off("mousedown", down);
      m.off("mousemove", move);
      m.off("mouseup", up);
      m.off("click", click);
      m.off("dblclick", dbl);
      window.removeEventListener("keydown", key);
    };
  }, [drawMode, ready]);

  // --- data -------------------------------------------------------------
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    // One scale for colour and height: t = sqrt(value / top), clamped. The top is the range-wide
    // value from App when there is one, else this window's 98th percentile (never one outlier).
    let mx = 0;
    cells.forEach((c) => (mx = Math.max(mx, c.value)));
    const top = scaleMax && scaleMax > 0 ? scaleMax : robustMax([...cells.values()].map((c) => c.value));
    setScale({ max: top, clipped: mx > top * 1.0001, fixed: !!scaleMax });
    const target = new Map<string, LiveCell>();
    cells.forEach((c, id) => {
      if (c.value > 0) target.set(id, { lat: c.lat, lon: c.lon, value: c.value, t: top > 0 ? Math.sqrt(Math.min(1, c.value / top)) : 0 });
    });
    live.current.rank = new Map(
      [...target.entries()]
        .sort((a, b) => b[1].value - a[1].value)
        .map(([id], k) => [id, k + 1]),
    );

    const h = gridDeg / 2;
    // Columns are slimmer than their cell so the terrain stays visible between them.
    const pr = h * (gridDeg >= 0.05 ? 0.44 : 0.85);
    const paint = (state: Map<string, LiveCell>, rise: number) => {
      const feats: GeoJSON.Feature[] = [];
      const pts: GeoJSON.Feature[] = [];
      const pillars: GeoJSON.Feature[] = [];
      state.forEach((c, id) => {
        if (c.t <= 0.004) return;
        feats.push(poly(bboxRing([c.lon - h, c.lat - h, c.lon + h, c.lat + h]), { id, value: c.value, t: c.t, unit }));
        pts.push({ type: "Feature", properties: { t: c.t }, geometry: { type: "Point", coordinates: [c.lon, c.lat] } });
        if (rise > 0.001 && c.t >= PILLAR_MIN_T) pillars.push(column(c.lon, c.lat, pr, h * 0.95, { id, value: c.value, unit, t: c.t, h: c.t * rise }));
      });
      (m.getSource("cells") as GeoJSONSource).setData(fc(feats));
      (m.getSource("heat") as GeoJSONSource).setData(fc(pts));
      (m.getSource("pillars") as GeoJSONSource).setData(fc(pillars));
      live.current.shown = state;
      live.current.rise = rise;
      live.current.emitters = [...state.values()].filter((c) => c.t > 0.35).sort((a, b) => b.t - a.t).slice(0, 60);
    };

    // Tween from what is on screen to the new values: pillars rise and fall as time plays.
    const from = live.current.shown;
    const riseFrom = live.current.rise;
    const riseTo = mode3d ? 1 : 0;
    const ids = new Set([...from.keys(), ...target.keys()]);
    const reduce = reducedMotion();
    let raf = 0;
    let settle = 0;
    if (reduce || ids.size > 1600 || (from.size === 0 && riseFrom === riseTo)) paint(target, riseTo);
    else {
      const start = performance.now();
      const dur = riseFrom !== riseTo ? 1500 : 600;
      const tick = (now: number) => {
        const x = Math.min(1, (now - start) / dur);
        const k = 1 - (1 - x) ** 3;
        if (x >= 1) return paint(target, riseTo);
        const state = new Map<string, LiveCell>();
        ids.forEach((id) => {
          const a = from.get(id);
          const b = target.get(id);
          const ref = (b ?? a)!;
          state.set(id, { lat: ref.lat, lon: ref.lon, value: b?.value ?? 0, t: (a?.t ?? 0) + ((b?.t ?? 0) - (a?.t ?? 0)) * k });
        });
        paint(state, riseFrom + (riseTo - riseFrom) * k);
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
      // Background tabs get no animation frames: land on the final state anyway.
      settle = window.setTimeout(() => paint(target, riseTo), dur + 700);
    }
    // Glow sized to the grid cell at every zoom, so 11 km and 1 km grids both read correctly.
    m.setPaintProperty("glow", "circle-radius", cellRadius(gridDeg, ["+", 0.45, ["*", 0.55, ["get", "t"]]]));
    m.setPaintProperty("glow-core", "circle-radius", cellRadius(gridDeg, ["*", 0.16, ["get", "t"]]));
    // Heights in metres: the tallest column is PILLAR_HEIGHT cell widths. The cap is the top slice
    // (CAP_FRAC of the tallest, at most 30% of a short column) and the body stops beneath it.
    const K = gridDeg * 111_000 * PILLAR_HEIGHT;
    const H = ["*", ["get", "h"], K];
    const capBase = ["-", H, ["min", K * CAP_FRAC, ["*", ["get", "h"], K * 0.3]]];
    m.setPaintProperty("cells-3d", "fill-extrusion-height", capBase);
    m.setPaintProperty("cells-3d-cap", "fill-extrusion-base", capBase);
    m.setPaintProperty("cells-3d-cap", "fill-extrusion-height", H);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cells, scaleMax, gridDeg, unit, ready, mode3d]);

  // Embers: sparks drifting up from the hottest cells (from the pillar tops in 3D).
  useEffect(() => {
    const m = map.current;
    const c = fx.current;
    if (!m || !c || !ready) return;
    if (!animate || reducedMotion()) {
      c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
      return;
    }
    const g = c.getContext("2d")!;
    type P = { x: number; y: number; vx: number; vy: number; life: number; ttl: number; s: number; seed: number };
    let parts: P[] = [];
    let last = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = c.clientWidth;
      const hgt = c.clientHeight;
      if (c.width !== Math.round(w * dpr) || c.height !== Math.round(hgt * dpr)) {
        c.width = Math.round(w * dpr);
        c.height = Math.round(hgt * dpr);
      }
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, hgt);
      const L = live.current;
      if (L.embers && parts.length < 420) {
        const zoom = m.getZoom();
        const pitch = (m.getPitch() * Math.PI) / 180;
        for (const e of L.emitters) {
          if (Math.random() > e.t * e.t * 9 * dt) continue;
          const p = m.project([e.lon, e.lat]);
          if (p.x < -20 || p.x > w + 20 || p.y < -20 || p.y > hgt + 20) continue;
          const mpp = (40075016.686 * Math.cos((e.lat * Math.PI) / 180)) / (512 * 2 ** zoom);
          const cellPx = (L.gridDeg * 111_000) / mpp;
          const top = L.mode3d && e.t >= PILLAR_MIN_T ? ((e.t * L.rise * L.gridDeg * 111_000 * PILLAR_HEIGHT) / mpp) * Math.sin(pitch) : 0;
          parts.push({
            x: p.x + (Math.random() - 0.5) * cellPx * 0.4,
            y: p.y - top,
            vx: (Math.random() - 0.5) * 10,
            vy: -(14 + Math.random() * 34),
            life: 0,
            ttl: 1.1 + Math.random() * 1.9,
            s: 0.7 + Math.random() * 1.5 * e.t,
            seed: Math.random() * 6.28,
          });
        }
      }
      g.globalCompositeOperation = "lighter";
      parts = parts.filter((p) => (p.life += dt) < p.ttl);
      for (const p of parts) {
        p.x += (p.vx + Math.sin(now / 420 + p.seed) * 9) * dt;
        p.y += p.vy * dt;
        const a = 1 - p.life / p.ttl;
        g.fillStyle = a > 0.62 ? "#fff3c4" : a > 0.32 ? "#fca50a" : "#dd513a";
        g.globalAlpha = a * 0.16;
        g.beginPath();
        g.arc(p.x, p.y, p.s * 3.4, 0, 6.2832);
        g.fill();
        g.globalAlpha = a * 0.95;
        g.beginPath();
        g.arc(p.x, p.y, p.s, 0, 6.2832);
        g.fill();
      }
      g.globalAlpha = 1;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready, animate]);

  // Slow orbit around the area while in 3D, until the user takes the camera.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !mode3d || !orbit || !animate || reducedMotion()) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      raf = requestAnimationFrame(tick);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!m.isEasing()) m.setBearing(m.getBearing() + 2.6 * dt);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [mode3d, orbit, ready, animate]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("hotspots") as GeoJSONSource).setData(
      fc(hotspots.map((h) => ({ type: "Feature", properties: { instrument: h.instrument, frp: h.frp }, geometry: { type: "Point", coordinates: [h.longitude, h.latitude] } }))),
    );
    // MODIS first so the finer VIIRS pixels draw on top of the larger MODIS ones.
    const ordered = [...hotspots].sort((p, q) => (p.instrument === q.instrument ? 0 : p.instrument === "MODIS" ? -1 : 1));
    (m.getSource("footprints") as GeoJSONSource).setData(fc(ordered.map(footprint)));
  }, [hotspots, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !focus) return;
    const r = Math.max(focus.radius * 1.8, gridDeg * 2);
    m.fitBounds(
      [
        [focus.lon - r, focus.lat - r],
        [focus.lon + r, focus.lat + r],
      ],
      { padding: 40, duration: 1200, maxZoom: 10 },
    );
    const node = document.createElement("div");
    node.className = "pulse pulse-focus";
    node.innerHTML = `<span class="pulse-ring"></span><span class="pulse-ring pulse-ring-2"></span><span class="pulse-dot"></span>`;
    const marker = new maplibregl.Marker({ element: node }).setLngLat([focus.lon, focus.lat]).addTo(m);
    return () => {
      marker.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.key, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("outline") as GeoJSONSource).setData(fc((outline ?? []).map((r) => poly(r))));
  }, [outline, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("aoi") as GeoJSONSource).setData(fc(areaIsRegion && outline?.length ? [] : [poly(area.ring)]));
    (m.getSource("extent") as GeoJSONSource).setData(fc([poly(bboxRing(extent))]));
    const world: Ring = [[-180, -85], [180, -85], [180, 85], [-180, 85]];
    (m.getSource("mask") as GeoJSONSource).setData(
      fc([{ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...world, world[0]], [...area.ring, area.ring[0]].reverse()] } }]),
    );
  }, [area, extent, areaIsRegion, outline, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.fitBounds(
      [
        [area.bbox[0], area.bbox[1]],
        [area.bbox[2], area.bbox[3]],
      ],
      { padding: 48, duration: 700, maxZoom: 10 },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const vis = (id: string, on: boolean) => m.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    vis("sat", layers.basemap === "satellite");
    vis("glow", layers.glow.on && showData);
    vis("glow-core", layers.glow.on && !mode3d && showData);
    vis("cells-3d", mode3d && showData);
    vis("cells-3d-cap", mode3d && showData);
    vis("hillshade", mode3d);
    m.setPaintProperty("glow", "circle-opacity", 0.75 * layers.glow.opacity);
    vis("cells", layers.cells.on && showData);
    vis("cells-hover", layers.cells.on && !mode3d && showData);
    vis("heat", layers.heat.on && showData);
    vis("hotspots", layers.hotspots.on && showData);
    vis("footprints", layers.hotspots.on && showData);
    vis("footprints-line", layers.hotspots.on && showData);
    vis("extent", layers.extent.on);
    vis("mask", layers.mask.on);
    m.setPaintProperty("cells", "fill-opacity", mode3d ? Math.min(0.28, layers.cells.opacity) : layers.cells.opacity);
    m.setPaintProperty("heat", "heatmap-opacity", layers.heat.opacity);
    m.setPaintProperty("hotspots", "circle-opacity", layers.hotspots.opacity);
  }, [layers, mode3d, showData, ready]);

  // Tilt the camera in and out of 3D.
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    if (mode3d) {
      m.dragRotate.enable();
      m.touchZoomRotate.enableRotation();
      // Real relief under the map: mountains rise, valleys sink, and haze adds distance.
      m.setMaxPitch(78);
      m.setTerrain({ source: "dem", exaggeration: TERRAIN_EXAGGERATION });
      m.setSky({
        "sky-color": "#070b16",
        "horizon-color": "#2a2233",
        "fog-color": "#0b0f1a",
        "sky-horizon-blend": 0.6,
        "horizon-fog-blend": 0.7,
        "fog-ground-blend": 0.25,
      });
      // The first tilt is a slow swoop down from the top-down view.
      m.easeTo({ pitch: 60, bearing: -24, zoom: m.getZoom() + 0.15, duration: reducedMotion() ? 0 : live.current.first3d ? 3200 : 1200 });
      live.current.first3d = false;
    } else {
      m.setTerrain(null);
      m.dragRotate.disable();
      m.touchZoomRotate.disableRotation();
      if (m.getPitch() !== 0 || m.getBearing() !== 0) m.easeTo({ pitch: 0, bearing: 0, zoom: m.getZoom() - 0.15, duration: 800 });
    }
  }, [mode3d, ready]);

  return (
    <div className="map-wrap" ref={wrap}>
      <div ref={el} className="map" />
      <canvas ref={fx} className="map-fx" aria-hidden />
      <div className="map-tools" role="toolbar" aria-label="Area drawing tools">
        <button className={`tool${drawMode === "rect" ? " is-on" : ""}`} onClick={() => setDrawMode(drawMode === "rect" ? "none" : "rect")} title="Draw a rectangle (drag)">
          <svg viewBox="0 0 20 20" aria-hidden><rect x="3.5" y="5.5" width="13" height="9" rx="1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="2.5 1.8" /></svg>
          <span>Rectangle</span>
        </button>
        <button className={`tool${drawMode === "poly" ? " is-on" : ""}`} onClick={() => setDrawMode(drawMode === "poly" ? "none" : "poly")} title="Draw a polygon (click points, double-click to finish)">
          <svg viewBox="0 0 20 20" aria-hidden><path d="M4 14 L7 4 L16 7 L14 16 Z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" /></svg>
          <span>Polygon</span>
        </button>
        <button
          className="tool"
          title="Zoom to the selected area"
          onClick={() =>
            map.current?.fitBounds(
              [
                [area.bbox[0], area.bbox[1]],
                [area.bbox[2], area.bbox[3]],
              ],
              { padding: 48, duration: 600, maxZoom: 10 },
            )
          }
        >
          <svg viewBox="0 0 20 20" aria-hidden><path d="M3 7V3h4M13 3h4v4M17 13v4h-4M7 17H3v-4" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
          <span>Fit area</span>
        </button>
        <button className={`tool tool-3d${mode3d ? " is-on" : ""}`} onClick={() => setMode3d(!mode3d)} aria-pressed={mode3d} title="3D: real terrain plus fire columns (right-drag or Ctrl+drag to rotate and tilt)">
          <svg viewBox="0 0 20 20" aria-hidden>
            <path d="M10 2.5 16.5 6v8L10 17.5 3.5 14V6z M10 10l6.5-4M10 10 3.5 6M10 10v7.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
          </svg>
          <span>3D</span>
        </button>
        {mode3d && (
          <button className={`tool${orbit ? " is-on" : ""}`} onClick={() => setOrbit(!orbit)} aria-pressed={orbit} title="Slowly orbit the camera around the area">
            <svg viewBox="0 0 20 20" aria-hidden>
              <ellipse cx="10" cy="10" rx="7.5" ry="3.4" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <circle cx="10" cy="10" r="2" fill="currentColor" />
            </svg>
            <span>Orbit</span>
          </button>
        )}
        <button className={`tool${panelsHidden ? " is-on" : ""}`} onClick={() => setPanelsHidden(!panelsHidden)} aria-pressed={panelsHidden} title={panelsHidden ? "Show the panels again" : "Hide the panels and legend: map only"}>
          <svg viewBox="0 0 20 20" aria-hidden>
            {panelsHidden ? (
              <path d="M2.5 10s2.8-5 7.5-5 7.5 5 7.5 5-2.8 5-7.5 5-7.5-5-7.5-5z M10 7.6a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8z M3.5 16.5l13-13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <path d="M2.5 10s2.8-5 7.5-5 7.5 5 7.5 5-2.8 5-7.5 5-7.5-5-7.5-5z M10 7.6a2.4 2.4 0 1 0 0 4.8 2.4 2.4 0 0 0 0-4.8z" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
            )}
          </svg>
          <span>{panelsHidden ? "Show panels" : "Hide panels"}</span>
        </button>
        <button className={`tool${fullscreen ? " is-on" : ""}`} onClick={toggleFullscreen} aria-pressed={fullscreen} title={fullscreen ? "Exit full screen (Esc)" : "Full screen"}>
          <svg viewBox="0 0 20 20" aria-hidden>
            {fullscreen ? (
              <path d="M7.5 3v4.5H3M12.5 3v4.5H17M7.5 17v-4.5H3M12.5 17v-4.5H17" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <path d="M3 7.5V3h4.5M17 7.5V3h-4.5M3 12.5V17h4.5M17 12.5V17h-4.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            )}
          </svg>
          <span>{fullscreen ? "Exit full screen" : "Full screen"}</span>
        </button>
        {detections ? (
          <div className="seg seg-sm map-res" role="radiogroup" aria-label="Map resolution" title="Map cell size">
            <button role="radio" aria-checked={resolution === "grid"} className={resolution === "grid" ? "is-on" : ""} onClick={() => onResolution("grid")}>
              {gridLabel}
            </button>
            <button role="radio" aria-checked={resolution === "1km"} className={resolution === "1km" ? "is-on" : ""} onClick={() => onResolution("1km")}>
              1 km
            </button>
          </div>
        ) : (
          <span className="map-res map-res-label" title="Analysis grid">
            {gridLabel}
          </span>
        )}
      </div>
      {drawMode !== "none" && (
        <div className="map-hint">
          {drawMode === "rect" ? "Drag on the map to draw a rectangle" : "Click to add points · double-click or Enter to finish"} · Esc to cancel
        </div>
      )}
      {!showData && <div className="map-offline">Fire cells hidden: map only</div>}
      <div className="map-legend" hidden={!showData}>
        <div className="map-legend-title">
          {windowLabel} · {unit} per cell
        </div>
        <div className="ramp" style={{ background: `linear-gradient(90deg, ${INFERNO.join(",")})` }} />
        <div className="ramp-labels">
          <span>0</span>
          <span>{fmt(scale.max / 4)}</span>
          <span>
            {scale.clipped ? "≥ " : ""}
            {fmt(scale.max)}
          </span>
        </div>
        <div className="map-legend-hint">
          {mode3d ? "Colour and column height: square-root scale" : "Square-root scale"}
          {scale.fixed ? ", fixed across the selected years" : ", scaled to this window"}
          {scale.clipped ? `. Cells above ${fmt(scale.max)} are drawn at the top` : ""}
        </div>
        {detections && layers.hotspots.on && (
          <div className="ramp-labels dots">
            <span><i style={{ background: "#E69F00" }} /> MODIS</span>
            <span><i style={{ background: "#56B4E9" }} /> VIIRS</span>
          </div>
        )}
        {note && <div className="map-legend-hint">{note}</div>}
        {detections && layers.hotspots.on && (
          <div className="map-legend-hint">{zoom >= FOOTPRINT_ZOOM ? "Squares = real pixel size (MODIS ≈ 1 km, VIIRS ≈ 375 m)" : "Zoom in to see each detection at its real pixel size"}</div>
        )}
      </div>
      {cursor && (
        <div className="map-coords">
          {cursor[1].toFixed(3)}°, {cursor[0].toFixed(3)}°
        </div>
      )}
      {!basemap && <div className="map-offline">Basemap offline: showing data only</div>}
    </div>
  );
}
