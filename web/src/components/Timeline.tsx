import { useEffect, useMemo, useRef, useState } from "react";
import { MONTH_ABBR, ymMonth, ymYear } from "../data/contract";
import { type MonthPoint, fmt } from "../lib/analytics";

interface Props {
  series: MonthPoint[];
  selected: number;
  onSelect: (i: number) => void;
  windowMode: "month" | "year" | "range";
  unit: string;
}

/** Month scrubber with a sparkline of the series behind it and a play button. */
/** The map's Month/Year/All window is set in the top bar, next to the month arrows. */
export function Timeline({ series, selected, onSelect, windowMode, unit }: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const first = series[0]?.i ?? 0;
  const last = series[series.length - 1]?.i ?? 0;
  const selRef = useRef(selected);
  selRef.current = selected;
  const track = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = track.current;
    if (!el || last <= first) return;
    let distance = 0;
    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey || (!event.shiftKey && Math.abs(event.deltaX) <= Math.abs(event.deltaY))) return;
      const delta = event.deltaX || event.deltaY;
      if (!delta) return;
      event.preventDefault();
      if (Math.sign(distance) !== Math.sign(delta)) distance = 0;
      distance += delta * (event.deltaMode ? 35 : 1);
      const months = Math.trunc(distance / 35);
      if (!months) return;
      distance -= months * 35;
      const next = Math.max(first, Math.min(last, selRef.current + months));
      selRef.current = next;
      onSelect(next);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [first, last, onSelect]);

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      const next = selRef.current + 1;
      if (next > last) {
        setPlaying(false);
        return;
      }
      onSelect(next);
    }, 450 / speed);
    return () => clearInterval(t);
  }, [playing, speed, last, onSelect]);

  const forecastStart = series.find((p) => p.forecast)?.i;
  const paths = useMemo(() => {
    const max = Math.sqrt(Math.max(1, ...series.map((p) => p.value ?? 0)));
    const width = Math.max(1, last - first);
    const points = series.map((p) => `${((p.i - first) / width) * 1000},${40 - (Math.sqrt(p.value ?? 0) / max) * 38}`);
    const split = series.findIndex((p) => p.forecast);
    const observed = split < 0 ? points : points.slice(0, split);
    const projected = split < 0 ? [] : points.slice(Math.max(0, split - 1));
    return {
      observed: observed.length ? `M${observed.join(" L")}` : "",
      projected: projected.length ? `M${projected.join(" L")}` : "",
      observedEnd: ((series[Math.max(0, observed.length - 1)]?.i ?? first) - first) * 1000 / width,
    };
  }, [series, first, last]);

  const years = useMemo(() => {
    const ys = [...new Set(series.map((p) => p.year))];
    const step = ys.length > 20 ? 5 : ys.length > 10 ? 2 : 1;
    return ys.filter((y) => y % step === 0);
  }, [series]);

  const pos = (i: number) => (last > first ? ((i - first) / (last - first)) * 100 : 0);
  const cur = series.find((p) => p.i === selected);

  return (
    <div className="timeline">
      <div className="timeline-controls">
        <button
          className="play"
          onClick={() => {
            if (!playing && selected >= last) onSelect(first);
            setPlaying(!playing);
          }}
          aria-label={playing ? "Pause" : "Play through months"}
        >
          {playing ? (
            <svg viewBox="0 0 16 16" aria-hidden><rect x="3.5" y="3" width="3" height="10" rx="0.5" /><rect x="9.5" y="3" width="3" height="10" rx="0.5" /></svg>
          ) : (
            <svg viewBox="0 0 16 16" aria-hidden><path d="M4.5 2.8v10.4L13 8z" /></svg>
          )}
        </button>
        <div className="timeline-now">
          <strong>
            {MONTH_ABBR[ymMonth(selected) - 1]} {ymYear(selected)}
          </strong>
          <span className={cur?.forecast ? "time-forecast-label" : undefined}>{cur?.value == null ? "no coverage" : `${fmt(cur.value)} ${unit}${cur.forecast ? " · forecast" : cur.partialMonth ? " · partial month" : cur.partial ? " · partial" : ""}`}</span>
        </div>
        <button className="chip" onClick={() => setSpeed(speed >= 4 ? 1 : speed * 2)} title="Playback speed">
          {speed}×
        </button>
      </div>
      <div className="timeline-track" ref={track}>
        {forecastStart !== undefined && <div className="timeline-outlook" style={{ left: `${pos(forecastStart - 0.5)}%` }} aria-hidden />}
        <svg className="spark" viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden>
          {paths.observed && <path d={`${paths.observed} L${paths.observedEnd},40 L0,40 Z`} className="spark-area" />}
          <path d={paths.observed} className="spark-line" />
          {paths.projected && <path d={paths.projected} className="spark-outlook" />}
        </svg>
        {windowMode === "year" && (
          <div
            className="timeline-window"
            style={{ left: `${pos(Math.max(first, ymYear(selected) * 12))}%`, width: `${pos(Math.min(last, ymYear(selected) * 12 + 11)) - pos(Math.max(first, ymYear(selected) * 12))}%` }}
          />
        )}
        <input
          type="range"
          min={first}
          max={last}
          value={selected}
          onChange={(e) => onSelect(Number(e.target.value))}
          aria-label="Selected month"
          aria-valuetext={`${MONTH_ABBR[ymMonth(selected) - 1]} ${ymYear(selected)}${cur?.forecast ? ", forecast" : ""}`}
        />
        <div className="timeline-years" aria-hidden>
          {years.map((y) => (
            <span key={y} style={{ left: `${pos(Math.max(first, y * 12))}%` }}>
              {y}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
