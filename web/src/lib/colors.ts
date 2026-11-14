import type { Sensor } from "../data/contract";

/** Inferno (perceptually uniform, colour-blind safe), dropping the near-black end so low values read on a dark UI. */
export const INFERNO = ["#1f0c48", "#420a68", "#6a176e", "#932667", "#bc3754", "#dd513a", "#f37819", "#fca50a", "#f6d746", "#fcffa4"];

/** Diverging blue ↔ red for anomalies (RdBu family, colour-blind safe), neutral matched to the card surface. */
export const DIVERGING = ["#2166ac", "#4393c3", "#92c5de", "#2a3140", "#f4a582", "#d6604d", "#b2182b"];

/** Okabe–Ito picks for the sensors; harmonized is the bright "truth" line. */
export const SENSOR_COLOR: Record<Sensor, string> = {
  modis_raw: "#E69F00",
  viirs_raw: "#56B4E9",
  harmonized: "#F2EDE4",
};

export const UI = {
  text: "#e8ebf2",
  muted: "#8c94a8",
  faint: "#5a6276",
  grid: "#232a38",
  surface: "#131824",
  accent: "#3d7bff",
  noData: "#1a1f2b",
};

export function interpolateRamp(ramp: string[], t: number) {
  const x = Math.min(1, Math.max(0, t)) * (ramp.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = hex(ramp[i]);
  const b = hex(ramp[Math.min(ramp.length - 1, i + 1)]);
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`;
}

const hex = (h: string) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
