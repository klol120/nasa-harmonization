import { useEffect, useRef, useState } from "react";
import { METRIC_LABEL, type Metric, SENSOR_LABEL, SENSORS, type Sensor } from "../data/contract";
import type { DataSource } from "../data/sources";
import { SENSOR_COLOR } from "../lib/colors";

export interface ExportAction {
  id: string;
  label: string;
  hint: string;
  run: () => void | Promise<void>;
  disabled?: boolean;
}

interface Props {
  sources: DataSource[];
  sourceId: string;
  onSource: (id: string) => void;
  onImport: () => void;
  sensor: Sensor;
  onSensor: (s: Sensor) => void;
  metric: Metric;
  /** Metrics the current source provides; the picker shows only when there is a choice. */
  metrics: Metric[];
  onMetric: (m: Metric) => void;
  exports: ExportAction[];
  onMethods: () => void;
  onWorld: () => void;
  /** Account control (sign in / avatar menu). */
  account: React.ReactNode;
}

export function TopBar(p: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <img src="./emblem.png" alt="" width={34} height={34} />
        <div>
          <strong>Wel3a</strong>
          <span>Burning Calendar · MODIS + VIIRS</span>
        </div>
      </div>

      <button className="btn btn-ghost world-btn" onClick={p.onWorld} title="Back to the world map">
        <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden>
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M3 10h14M10 3c2.2 2.2 2.2 11.8 0 14M10 3c-2.2 2.2-2.2 11.8 0 14" fill="none" stroke="currentColor" strokeWidth="1.3" />
        </svg>
        World
      </button>

      <div className="topbar-controls">
        <label className="select-wrap" title="Dataset">
          <span className="sr-only">Dataset</span>
          <select
            value={p.sourceId}
            onChange={(e) => (e.target.value === "__import" ? p.onImport() : p.onSource(e.target.value))}
          >
            {p.sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.kind === "upload" ? "File · " : ""}
                {s.label}
              </option>
            ))}
            <option value="__import">Load your own file…</option>
          </select>
        </label>

        <div className="seg sensor-seg" role="radiogroup" aria-label="Sensor">
          {SENSORS.map((s) => (
            <button key={s} role="radio" aria-checked={p.sensor === s} className={p.sensor === s ? "is-on" : ""} onClick={() => p.onSensor(s)}>
              <i style={{ background: SENSOR_COLOR[s] }} aria-hidden />
              {SENSOR_LABEL[s]}
            </button>
          ))}
        </div>

        {p.metrics.length > 1 && (
          <label className="select-wrap" title="Metric">
            <span className="sr-only">Metric</span>
            <select value={p.metric} onChange={(e) => p.onMetric(e.target.value as Metric)}>
              {p.metrics.map((m) => (
                <option key={m} value={m}>
                  {METRIC_LABEL[m]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="topbar-actions">
        <ExportMenu actions={p.exports} />
        <button className="btn btn-ghost" onClick={p.onMethods}>
          Methods
        </button>
        {p.account}
      </div>
    </header>
  );
}

function ExportMenu({ actions }: { actions: ExportAction[] }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="btn btn-primary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
          <path d="M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M3 13h10" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Export
      </button>
      {open && (
        <div className="menu" role="menu">
          {actions.map((a) => (
            <button
              key={a.id}
              role="menuitem"
              disabled={a.disabled || busy !== null}
              onClick={async () => {
                setBusy(a.id);
                try {
                  await a.run();
                } finally {
                  setBusy(null);
                  setOpen(false);
                }
              }}
            >
              <b>{busy === a.id ? "Preparing…" : a.label}</b>
              <small>{a.hint}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
