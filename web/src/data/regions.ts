import { feature } from "topojson-client";
import type { BBox } from "./contract";

/**
 * Country outlines for the world view and region borders. They come from Natural Earth 1:50m
 * (world-atlas), loaded lazily so the first paint stays light.
 */
export type Ring = [number, number][]; // [lon, lat]

export interface Country {
  id: string; // "country:<iso numeric>"
  name: string;
  bbox: BBox;
  /** Main polygons (outer rings only), largest first; tiny far-away islands are dropped. */
  outline: Ring[];
  /** Every polygon's outer ring, for drawing the full border. */
  allRings: Ring[];
}

let cache: Promise<Country[]> | null = null;

export function loadCountries(): Promise<Country[]> {
  cache ??= import("world-atlas/countries-50m.json").then((mod) => {
    const topo = (mod as any).default ?? mod;
    const fc = feature(topo, topo.objects.countries) as unknown as GeoJSON.FeatureCollection;
    const out: Country[] = [];
    for (const f of fc.features) {
      if (!f.geometry || !f.properties?.name || f.id === undefined) continue;
      const polys: Ring[] =
        f.geometry.type === "Polygon"
          ? [f.geometry.coordinates[0] as Ring]
          : f.geometry.type === "MultiPolygon"
            ? f.geometry.coordinates.map((p) => p[0] as Ring)
            : [];
      if (!polys.length) continue;
      polys.sort((a, b) => ringArea(b) - ringArea(a));
      // Keep parts that matter (drops tiny far-away islands that would blow up the bbox).
      const main = polys.filter((p, k) => k === 0 || ringArea(p) > ringArea(polys[0]) * 0.08);
      out.push({ id: `country:${String(f.id).padStart(3, "0")}`, name: f.properties.name, bbox: ringsBBox(main), outline: main, allRings: polys });
    }
    return out.sort((a, b) => a.name.localeCompare(b.name));
  });
  return cache;
}

/** Full border of a country by its name (as written in the export's meta.countries). */
export async function countryOutline(name: string): Promise<Ring[] | undefined> {
  const c = (await loadCountries()).find((x) => x.name.toLowerCase() === name.toLowerCase());
  return c?.allRings;
}

export function ringArea(r: Ring) {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] + r[i][0]) * (r[j][1] - r[i][1]);
  return Math.abs(a / 2);
}

export function ringsBBox(rings: Ring[]): BBox {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const r of rings)
    for (const [x, y] of r) {
      w = Math.min(w, x); e = Math.max(e, x);
      s = Math.min(s, y); n = Math.max(n, y);
    }
  return [w, s, e, n];
}
