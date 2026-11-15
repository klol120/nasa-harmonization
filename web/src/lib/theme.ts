import { useEffect, useState } from "react";
import { DIVERGING, SENSOR_COLOR, UI } from "./colors";

/** Light or dark interface. */
export type Theme = "light" | "dark";
/** What the person picked: a fixed appearance, or follow the system ("auto"). Saved in the browser. */
export type ThemeChoice = Theme | "auto";

const KEY = "wel3a.theme";

const DARK_UI = { ...UI };
const LIGHT_UI: typeof UI = {
  text: "#1d1d1f",
  muted: "#6e6e73",
  faint: "#aeaeb2",
  grid: "rgba(60,60,67,0.12)",
  surface: "#f7f7f9",
  accent: "#ff9500",
  noData: "rgba(120,120,128,0.1)",
  hatch: "rgba(60,60,67,0.22)",
  hl: "#1d1d1f",
  hlBar: "#6a176e",
  wash: "rgba(60,60,67,0.05)",
  barNeutral: "rgba(29,29,31,0.28)",
  marker: "rgba(0,113,227,0.75)",
  markerText: "#0071e3",
  fireText: "#c93400",
  tooltipBg: "rgba(255,255,255,0.86)",
  tooltipBorder: "rgba(0,0,0,0.08)",
  tooltipShadow: "rgba(0,0,0,.12)",
};
/** Harmonized is the "truth" line: near-white on dark, near-black on light. */
const HARMONIZED = { dark: "#F5F5F7", light: "#1d1d1f" };
/** The diverging scale's midpoint sits close to the glass it is drawn on. */
const NEUTRAL = { dark: "#3a3a3e", light: "#e8e8ed" };

const read = () => {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
};

const media = () => window.matchMedia?.("(prefers-color-scheme: light)");
const systemTheme = (): Theme => (media()?.matches ? "light" : "dark");
export const currentTheme = (): Theme => read() ?? systemTheme();

function apply(t: Theme) {
  Object.assign(UI, t === "light" ? LIGHT_UI : DARK_UI);
  SENSOR_COLOR.harmonized = HARMONIZED[t];
  DIVERGING[3] = NEUTRAL[t];
  const root = document.documentElement;
  root.dataset.theme = t;
  root.style.colorScheme = t;
}

const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

/** Fixes the appearance, or ("auto") hands it back to the system setting. */
export function setTheme(c: ThemeChoice) {
  try {
    if (c === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, c);
  } catch {
    // storage blocked: the choice lasts for this visit only
  }
  apply(c === "auto" ? systemTheme() : c);
  notify();
}

/** Current theme and the person's choice, re-rendering when either changes (switch or system setting). */
export function useTheme(): [Theme, (c: ThemeChoice) => void, ThemeChoice] {
  const [, bump] = useState(0);
  useEffect(() => {
    const l = () => bump((n) => n + 1);
    listeners.add(l);
    const mq = media();
    const onSystem = () => {
      if (read()) return; // an explicit choice wins over the system
      apply(systemTheme());
      notify();
    };
    mq?.addEventListener?.("change", onSystem);
    return () => {
      listeners.delete(l);
      mq?.removeEventListener?.("change", onSystem);
    };
  }, []);
  return [currentTheme(), setTheme, read() ?? "auto"];
}

// Apply before the first paint.
apply(currentTheme());
