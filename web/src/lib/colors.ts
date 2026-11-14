import type { Sensor } from "../data/contract";

/** Inferno (perceptually uniform, colour-blind safe), dropping the near-black end so low values read on a dark UI. */
export const INFERNO = ["#1f0c48", "#420a68", "#6a176e", "#932667", "#bc3754", "#dd513a", "#f37819", "#fca50a", "#f6d746", "#fcffa4"];

/** Diverging blue ↔ red for anomalies (RdBu family, colour-blind safe), neutral matched to the card surface. */
export const DIVERGING = ["#2166ac", "#4393c3", "#92c5de", "#26262c", "#f4a582", "#d6604d", "#b2182b"];

/** Okabe–Ito picks for the sensors; harmonized is the bright "truth" line. */
export const SENSOR_COLOR: Record<Sensor, string> = {
  modis_raw: "#E69F00",
  viirs_raw: "#56B4E9",
  harmonized: "#F2EDE4",
};

/**
 * Chart colours for the current theme. lib/theme.ts swaps the values in place when the theme
 * changes, and the pages that draw charts remount, so options built from these pick them up.
 */
export const UI = {
  text: "#f5f5f7",
  muted: "#98989d",
  faint: "#636366",
  grid: "rgba(84,84,88,0.42)",
  /** Opaque stand-in for the glass the charts sit on (cell borders, PNG background). */
  surface: "#1d1d21",
  accent: "#ff9f0a",
  noData: "rgba(120,120,128,0.2)",
  /** Stripes of the "no data" hatch. */
  hatch: "rgba(152,152,157,0.4)",
  /** Outline of the selected cell / month. */
  hl: "#ffffff",
  /** Fill of the highlighted bar (selected year). */
  hlBar: "#fcffa4",
  /** Faint wash for bands, empty slots and axis shadows. */
  wash: "rgba(255,255,255,0.05)",
  /** Neutral bar fill (weather months with nothing unusual). */
  barNeutral: "rgba(245,245,247,0.45)",
  /** Sensor-change marker. */
  marker: "rgba(100,210,255,0.8)",
  markerText: "#64d2ff",
  /** Orange text (event labels) readable on the surface. */
  fireText: "#ffb340",
  tooltipBg: "rgba(44,44,48,0.82)",
  tooltipBorder: "rgba(255,255,255,0.14)",
  tooltipShadow: "rgba(0,0,0,.45)",
};

/** Font stack for canvas and chart text: the system UI font (SF Pro on Apple devices), Inter elsewhere. */
export const UI_FONT = `-apple-system, BlinkMacSystemFont, "SF Pro Text", Inter, "Segoe UI", system-ui, sans-serif`;
export const UI_MONO = `ui-monospace, "SF Mono", "Geist Mono", Menlo, Consolas, monospace`;

export function interpolateRamp(ramp: string[], t: number) {
  const x = Math.min(1, Math.max(0, t)) * (ramp.length - 1);
  const i = Math.floor(x);
  const f = x - i;
  const a = hex(ramp[i]);
  const b = hex(ramp[Math.min(ramp.length - 1, i + 1)]);
  return `rgb(${Math.round(a[0] + (b[0] - a[0]) * f)},${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)})`;
}

const hex = (h: string) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
