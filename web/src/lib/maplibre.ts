import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// Vite's dependency pre-bundling rewrites MapLibre's inlined worker so it never answers;
// load the standalone worker file instead (served as-is in dev, emitted as an asset in builds).
import workerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url";

maplibregl.setWorkerUrl(workerUrl);

export { maplibregl };

const STYLE_URLS = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  darkNoLabels: "https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json",
  /** Light street map (Carto Positron) for the light theme. */
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#0b0f17" } }],
};

/** Free, token-less satellite imagery (Esri World Imagery), added as an optional raster layer. */
export const SATELLITE_SOURCE = {
  type: "raster" as const,
  tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
  tileSize: 256,
  maxzoom: 18,
  attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
};

/** NASA Black Marble (VIIRS night lights) from GIBS: token-less, and on-theme for a MODIS/VIIRS app. */
export const NIGHT_LIGHTS_SOURCE = {
  type: "raster" as const,
  tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png"],
  tileSize: 256,
  maxzoom: 8,
  attribution: "Black Marble: NASA Earth Observatory / GIBS",
};

/** NASA Blue Marble (daytime Earth with shaded relief and ocean depth) from GIBS: the globe in light mode. */
export const DAY_EARTH_SOURCE = {
  type: "raster" as const,
  tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg"],
  tileSize: 256,
  maxzoom: 8,
  attribution: "Blue Marble: NASA Earth Observatory / GIBS",
};

/** Free, token-less elevation tiles (Mapzen Terrarium on AWS Open Data) for 3D terrain and hillshading. */
export const TERRAIN_SOURCE = {
  type: "raster-dem" as const,
  tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
  encoding: "terrarium" as const,
  tileSize: 256,
  maxzoom: 13,
  attribution: "Elevation: Mapzen, AWS Open Data",
};

const cache = new Map<string, Promise<StyleSpecification>>();

/** Basemap style, or a plain background when offline so the demo keeps working. */
export function loadStyle(kind: keyof typeof STYLE_URLS = "dark"): Promise<StyleSpecification> {
  if (!cache.has(kind)) {
    cache.set(
      kind,
      (async () => {
        try {
          const ctl = new AbortController();
          const t = setTimeout(() => ctl.abort(), 4000);
          const res = await fetch(STYLE_URLS[kind], { signal: ctl.signal });
          clearTimeout(t);
          if (!res.ok) throw new Error(String(res.status));
          return (await res.json()) as StyleSpecification;
        } catch {
          return FALLBACK_STYLE;
        }
      })(),
    );
  }
  // Each map mutates its style, so hand out a copy.
  return cache.get(kind)!.then((s) => structuredClone(s));
}
