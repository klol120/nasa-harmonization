import { useEffect, useMemo, useRef, useState } from "react";
import { MONTH_ABBR, ymMonth, ymYear } from "../data/contract";
import { type MonthPoint, fmt } from "../lib/analytics";

interface Props {
  series: MonthPoint[];
  selected: number;
  onSelect: (i: number) => void;
  windowMode: "month" | "year" | "range";
  setWindowMode: (m: "month" | "year" | "range") => void;
  unit: string;
}

/** Month scrubber with a sparkline of the series behind it and a play button. */
export function Timeline({ series, selected, onSelect, windowMode, setWindowMode, unit }: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const first = series[0]?.i ?? 0;
  const last = series[series.length - 1]?.i ?? 0;
  const selRef = useRef(selected);
  selRef.current = selected;

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

  const path = useMemo(() => {
    const vals = series.map((p) => p.value ?? 0);
    const max = Math.max(1, ...vals);
    const n = Math.max(1, series.length - 1);
    return vals.map((v, k) => `${k === 0 ? "M" : "L"}${((k / n) * 1000).toFixed(1)},${(40 - (Math.sqrt(v) / Math.sqrt(max)) * 38).toFixed(1)}`).join(" ");
  }, [series]);

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
          <span>{cur?.value === null ? "no coverage" : `${fmt(cur?.value)} ${unit}${cur?.partial ? " · partial" : ""}`}</span>
        </div>
        <button className="chip" onClick={() => setSpeed(speed >= 4 ? 1 : speed * 2)} title="Playback speed">
          {speed}×
        </button>
        <div className="seg seg-sm" role="radiogroup" aria-label="Map time window">
          {(["month", "year", "range"] as const).map((m) => (
            <button key={m} role="radio" aria-checked={windowMode === m} className={windowMode === m ? "is-on" : ""} onClick={() => setWindowMode(m)}>
              {m === "month" ? "Month" : m === "year" ? "Year" : "Whole range"}
            </button>
          ))}
        </div>
      </div>
      <div className="timeline-track">
        <svg className="spark" viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden>
          <path d={`${path} L1000,40 L0,40 Z`} className="spark-area" />
          <path d={path} className="spark-line" />
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
          aria-valuetext={`${MONTH_ABBR[ymMonth(selected) - 1]} ${ymYear(selected)}`}
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
