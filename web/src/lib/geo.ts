import type { BBox } from "../data/contract";

export type Ring = [number, number][]; // [lon, lat]

export interface Area {
  name: string;
  kind: "bbox" | "polygon";
  bbox: BBox;
  ring: Ring; // closed or open; always present (bbox areas get their 4 corners)
}

export const bboxRing = ([w, s, e, n]: BBox): Ring => [
  [w, s],
  [e, s],
  [e, n],
  [w, n],
];

export function areaFromBBox(name: string, bbox: BBox): Area {
  const [w, s, e, n] = bbox;
  const norm: BBox = [Math.min(w, e), Math.min(s, n), Math.max(w, e), Math.max(s, n)];
  return { name, kind: "bbox", bbox: norm, ring: bboxRing(norm) };
}

export function areaFromRing(name: string, ring: Ring): Area {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return { name, kind: "polygon", bbox: [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)], ring };
}

export function pointInArea(lon: number, lat: number, a: Area) {
  const [w, s, e, n] = a.bbox;
  if (lon < w || lon > e || lat < s || lat > n) return false;
  if (a.kind === "bbox") return true;
  // Ray casting.
  let inside = false;
  const r = a.ring;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i];
    const [xj, yj] = r[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export const bboxIntersects = (a: BBox, b: BBox) => a[0] <= b[2] && a[2] >= b[0] && a[1] <= b[3] && a[3] >= b[1];

/** Approximate area in km² (spherical, fine for UI copy). */
export function ringAreaKm2(ring: Ring) {
  const R = 6371;
  let sum = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % ring.length];
    sum += ((x2 - x1) * Math.PI) / 180 * (2 + Math.sin((y1 * Math.PI) / 180) + Math.sin((y2 * Math.PI) / 180));
  }
  return Math.abs((sum * R * R) / 2);
}

