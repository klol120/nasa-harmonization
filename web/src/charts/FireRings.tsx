import { useEffect, useMemo, useRef, useState } from "react";
import { MONTH_ABBR, ym } from "../data/contract";
import { type AnomalyCell, fmt, fmtPct } from "../lib/analytics";
import { INFERNO, interpolateRamp } from "../lib/colors";
import { reducedMotion } from "../lib/motion";

interface Props {
  cells: AnomalyCell[];
  unit: string;
  selected: number;
  onSelect: (i: number) => void;
  /** Documented events by month index. */
  events?: Map<number, string>;
  /** Year a new sensor starts (drawn as a dashed ring). */
  markerYear?: number;
  markerLabel?: string;
}

interface Target {
  years: number[];
  /** Colour position 0..1 per month index (NaN = no coverage). */
  t: Map<number, number>;
  /** Share of the radial space per year (sums to 1). */
  share: Map<number, number>;
}

const TAU = Math.PI * 2;
const GAP = 0.012; // radians between months
const ease = (x: number) => 1 - (1 - x) ** 3;

/**
 * The fire record read like a tree: every ring is a year (oldest at the core),
 * a thicker ring is a year with more fire, and the 12 sectors are the months.
 * Values tween when the sensor or area changes, so a sensor jump is visible as the rings swelling.
 */
export function FireRings({ cells, unit, selected, onSelect, events, markerYear, markerLabel }: Props) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  const byIndex = useMemo(() => new Map(cells.map((c) => [c.i, c])), [cells]);

  const target = useMemo<Target>(() => {
    const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b);
    const max = Math.max(1e-9, ...cells.map((c) => c.value ?? 0));
    const t = new Map<number, number>();
    const totals = new Map<number, number>();
    for (const c of cells) {
      t.set(c.i, c.value === null ? NaN : Math.sqrt(c.value / max));
      totals.set(c.year, (totals.get(c.year) ?? 0) + (c.value ?? 0));
    }
    const sum = [...totals.values()].reduce((a, b) => a + b, 0);
    const share = new Map<number, number>();
    // 35% of the space is shared equally so quiet years stay readable; the rest follows the year's activity.
    for (const y of years) share.set(y, 0.35 / years.length + (sum > 0 ? (0.65 * (totals.get(y) ?? 0)) / sum : 0.65 / years.length));
    return { years, t, share };
  }, [cells]);

  // What is on screen right now (tweened towards `target`).
  const shown = useRef<Target | null>(null);
  const anim = useRef<{ from: Target; start: number } | null>(null);
  const raf = useRef(0);
  const state = useRef({ selected, hover, events, markerYear, markerLabel });
  state.current = { selected, hover, events, markerYear, markerLabel };

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setSize(Math.round(Math.min(e.contentRect.width, 620))));
    ro.observe(wrap.current!);
    return () => ro.disconnect();
  }, []);

  /** Ring geometry for a given state: inner/outer radius per year. */
  const radii = (s: Target, R: number, r0: number) => {
    const out = new Map<number, [number, number]>();
    let r = r0;
    for (const y of s.years) {
      const w = (s.share.get(y) ?? 0) * (R - r0);
      out.set(y, [r, r + w]);
      r += w;
    }
    return out;
  };

  const geom = () => {
    const R = size / 2 - 24;
    return { R, r0: R * 0.27, cx: size / 2, cy: size / 2 };
  };

  const draw = (s: Target) => {
    const c = canvas.current;
    if (!c || size <= 0) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (c.width !== size * dpr) {
      c.width = size * dpr;
      c.height = size * dpr;
    }
    const g = c.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size, size);
    const { R, r0, cx, cy } = geom();
    const rr = radii(s, R, r0);
    const st = state.current;
    const hasData = (y: number) => {
      for (let m = 1; m <= 12; m++) {
        const v = s.t.get(ym(y, m));
        if (v !== undefined && !Number.isNaN(v)) return true;
      }
      return false;
    };
    const firstData = s.years.find(hasData);
    const showMarker = !!st.markerYear && rr.has(st.markerYear) && firstData !== undefined && firstData < st.markerYear;

    const wedge = (year: number, month: number, pad = 0.6) => {
      const [ri, ro] = rr.get(year)!;
      const a0 = -Math.PI / 2 + ((month - 1) / 12) * TAU + GAP;
      const a1 = -Math.PI / 2 + (month / 12) * TAU - GAP;
      const inner = ri + Math.min(pad, (ro - ri) / 4);
      g.beginPath();
      g.arc(cx, cy, Math.max(ro - Math.min(pad, (ro - ri) / 4), inner), a0, a1);
      g.arc(cx, cy, inner, a1, a0, true);
      g.closePath();
    };

    // Pass 1: bloom from the hot months. Pass 2: the crisp rings.
    for (const pass of [0, 1]) {
      g.save();
      if (pass === 0) {
        g.filter = `blur(${Math.max(6, size / 60)}px)`;
        g.globalCompositeOperation = "lighter";
      }
      for (const y of s.years)
        for (let m = 1; m <= 12; m++) {
          const t = s.t.get(ym(y, m));
          if (t === undefined) continue;
          if (Number.isNaN(t)) {
            if (pass === 1) {
              wedge(y, m);
              g.fillStyle = "rgba(255,255,255,0.035)";
              g.fill();
            }
            continue;
          }
          if (pass === 0 && t < 0.45) continue;
          wedge(y, m);
          g.globalAlpha = pass === 0 ? Math.min(0.9, (t - 0.35) * 1.2) : 1;
          g.fillStyle = interpolateRamp(INFERNO, t);
          g.fill();
        }
      g.restore();
    }

    // Sensor-change ring.
    if (showMarker) {
      const r = rr.get(st.markerYear!)![0];
      g.save();
      g.setLineDash([3, 4]);
      g.strokeStyle = "rgba(170,205,255,0.75)";
      g.lineWidth = 1;
      g.beginPath();
      g.arc(cx, cy, r, 0, TAU);
      g.stroke();
      g.restore();
    }

    // Documented events: a white ember on the month.
    st.events?.forEach((_, i) => {
      const y = Math.floor(i / 12);
      const m = (i % 12) + 1;
      if (!rr.has(y)) return;
      const [ri, ro] = rr.get(y)!;
      const a = -Math.PI / 2 + ((m - 0.5) / 12) * TAU;
      const r = (ri + ro) / 2;
      g.beginPath();
      g.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, Math.max(1.6, Math.min(3, (ro - ri) / 3)), 0, TAU);
      g.fillStyle = "#fff";
      g.fill();
      g.lineWidth = 1.2;
      g.strokeStyle = "#f37819";
      g.stroke();
    });

    // Hover and selection outlines.
    const outline = (i: number, colour: string, width: number, glow: number) => {
      const y = Math.floor(i / 12);
      if (!rr.has(y)) return;
      g.save();
      wedge(y, (i % 12) + 1, 0);
      g.shadowColor = "rgba(255,255,255,0.9)";
      g.shadowBlur = glow;
      g.lineWidth = width;
      g.strokeStyle = colour;
      g.stroke();
      g.restore();
    };
    if (st.hover !== null && st.hover !== st.selected) outline(st.hover, "rgba(255,255,255,0.75)", 1.2, 0);
    outline(st.selected, "#ffffff", 2, 10);

    // Month labels and a few year ticks along the January edge.
    g.fillStyle = "#8c94a8";
    g.font = "500 10.5px 'IBM Plex Sans', system-ui, sans-serif";
    g.textAlign = "center";
    g.textBaseline = "middle";
    MONTH_ABBR.forEach((label, k) => {
      const a = -Math.PI / 2 + ((k + 0.5) / 12) * TAU;
      g.fillText(label, cx + Math.cos(a) * (R + 13), cy + Math.sin(a) * (R + 13));
    });
    g.font = "500 9px 'IBM Plex Mono', ui-monospace, monospace";
    g.textAlign = "right";
    let lastY = -99;
    for (const y of s.years) {
      const first = y === firstData;
      const last = y === s.years[s.years.length - 1];
      if (!hasData(y) || (!first && !last && y % 5 !== 0)) continue;
      const [ri, ro] = rr.get(y)!;
      const mid = (ri + ro) / 2;
      if (Math.abs(mid - lastY) < 11) continue;
      lastY = mid;
      g.fillStyle = "rgba(10,13,20,0.7)";
      g.fillRect(cx - 27, cy - mid - 5.5, 25, 11);
      g.fillStyle = "#c3c9d6";
      g.fillText(String(y), cx - 3, cy - mid);
    }
    if (showMarker && st.markerLabel) {
      const r = rr.get(st.markerYear!)![0];
      const a = -Math.PI / 2 + (10.5 / 12) * TAU;
      g.font = "600 9.5px 'IBM Plex Sans', system-ui, sans-serif";
      g.textAlign = "center";
      g.fillStyle = "rgba(10,13,20,0.75)";
      const w = g.measureText(st.markerLabel).width + 8;
      g.fillRect(cx + Math.cos(a) * r - w / 2, cy + Math.sin(a) * r - 7, w, 14);
      g.fillStyle = "#a9dcff";
      g.fillText(st.markerLabel, cx + Math.cos(a) * r, cy + Math.sin(a) * r);
    }
  };

  // Tween towards the new target whenever the data changes.
  useEffect(() => {
    if (size <= 0) return;
    const reduce = reducedMotion();
    const from = shown.current;
    if (!from || reduce) {
      shown.current = target;
      draw(target);
      return;
    }
    anim.current = { from, start: performance.now() };
    const tick = (now: number) => {
      const a = anim.current;
      if (!a) return;
      const k = ease(Math.min(1, (now - a.start) / 900));
      const mix = (x: number | undefined, y: number | undefined) => {
        if (y === undefined || Number.isNaN(y)) return y ?? NaN;
        const s0 = x === undefined || Number.isNaN(x) ? 0 : x;
        return s0 + (y - s0) * k;
      };
      const t = new Map<number, number>();
      target.t.forEach((v, i) => t.set(i, mix(a.from.t.get(i), v)));
      const share = new Map<number, number>();
      let sum = 0;
      for (const y of target.years) {
        const v = mix(a.from.share.get(y), target.share.get(y)) || 0;
        share.set(y, v);
        sum += v;
      }
      for (const y of target.years) share.set(y, share.get(y)! / (sum || 1));
      const cur = { years: target.years, t, share };
      shown.current = cur;
      draw(cur);
      if (k < 1) raf.current = requestAnimationFrame(tick);
      else {
        shown.current = target;
        anim.current = null;
      }
    };
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(tick);
    // Background tabs get no animation frames: land on the final state anyway.
    const settle = window.setTimeout(() => {
      if (anim.current) {
        anim.current = null;
        shown.current = target;
        draw(target);
      }
    }, 1400);
    return () => {
      cancelAnimationFrame(raf.current);
      window.clearTimeout(settle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, size]);

  // Selection, hover and annotations only need a redraw.
  useEffect(() => {
    if (shown.current && !anim.current) draw(shown.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, hover, events, markerYear, markerLabel]);

  const hit = (e: React.MouseEvent) => {
    const s = shown.current;
    if (!s) return null;
    const rect = canvas.current!.getBoundingClientRect();
    const { R, r0, cx, cy } = geom();
    const x = e.clientX - rect.left - cx;
    const y = e.clientY - rect.top - cy;
    const r = Math.hypot(x, y);
    if (r < r0 || r > R) return null;
    const month = Math.floor((((Math.atan2(y, x) + Math.PI / 2 + TAU) % TAU) / TAU) * 12) + 1;
    for (const [year, [ri, ro]] of radii(s, R, r0)) if (r >= ri && r < ro) return byIndex.has(ym(year, month)) ? ym(year, month) : null;
    return null;
  };

  const focus = byIndex.get(hover ?? selected) ?? byIndex.get(selected);
  const { r0 } = geom();
  const glow = focus && focus.value !== null ? interpolateRamp(INFERNO, shown.current?.t.get(focus.i) || target.t.get(focus.i) || 0) : "#2a3140";

  return (
    <div className="rings" ref={wrap}>
      <div
        className="rings-stage"
        style={{ width: size || undefined, height: size || undefined }}
        tabIndex={0}
        role="application"
        aria-label={`Fire rings: ${target.years.length} years of monthly fire activity. Arrow keys move the selected month.`}
        onKeyDown={(e) => {
          const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : e.key === "ArrowUp" ? 12 : e.key === "ArrowDown" ? -12 : 0;
          if (!d || !byIndex.has(selected + d)) return;
          e.preventDefault();
          onSelect(selected + d);
        }}
      >
        <canvas
          ref={canvas}
          style={{ width: size, height: size }}
          onMouseMove={(e) => setHover(hit(e))}
          onMouseLeave={() => setHover(null)}
          onClick={(e) => {
            const i = hit(e);
            if (i !== null) onSelect(i);
          }}
        />
        {focus && size > 0 && (
          <div className="rings-core" style={{ width: r0 * 2 - 10, height: r0 * 2 - 10, ["--ember" as string]: glow }}>
            <span className="rings-core-date">
              {MONTH_ABBR[focus.month - 1]} {focus.year}
            </span>
            {focus.value === null ? (
              <span className="rings-core-sub">no coverage</span>
            ) : (
              <>
                <span className="rings-core-value">{fmt(focus.value)}</span>
                <span className="rings-core-sub">{unit}</span>
                {focus.pct !== null && <span className={`rings-core-pct ${focus.pct >= 30 ? "tone-warm" : focus.pct <= -30 ? "tone-cool" : ""}`}>{fmtPct(focus.pct)} vs normal</span>}
              </>
            )}
            {events?.get(focus.i) && <span className="rings-core-event">{events.get(focus.i)}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
