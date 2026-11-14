/**
 * User-controlled animation switch (saved in the browser), on top of the system
 * "reduce motion" preference. CSS reads it from <html data-motion="on|off">.
 */
const KEY = "wel3a.animations";
const CELLS_KEY = "wel3a.fireCells";

const read = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // storage blocked: fall back to defaults
  }
};
const save = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore: the setting just won't persist
  }
};

export const animationsEnabled = () => read(KEY) !== "off";
export function setAnimations(on: boolean) {
  save(KEY, on ? "on" : "off");
  document.documentElement.dataset.motion = on ? "on" : "off";
}

export const fireCellsEnabled = () => read(CELLS_KEY) !== "off";
export const setFireCells = (on: boolean) => save(CELLS_KEY, on ? "on" : "off");

/** True when animations should not run: switched off in the app, or the system asks for reduced motion. */
export const reducedMotion = () =>
  document.documentElement.dataset.motion === "off" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Apply the saved choice before the first paint.
document.documentElement.dataset.motion = animationsEnabled() ? "on" : "off";
