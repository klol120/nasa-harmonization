import { useEffect, useRef, useState } from "react";
import { type LiveStatus, getLive } from "../data/api";

const POLL_MS = 30_000;

/** "3 min ago" from an ISO time. */
function ago(iso: string | null, now: number): string {
  if (!iso) return "never";
  const s = Math.max(0, Math.round((now - Date.parse(iso)) / 1000));
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

const dayLabel = (d: string | null) => (d ? new Date(`${d}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" }) : "–");

interface Props {
  region: string;
  demo: boolean;
  onDemo: (on: boolean) => void;
  /** The region's live months changed on the server: reload them. `fromYear` = first year holding live months. */
  onChange: (fromYear: number | undefined) => void;
}

/**
 * Shows that the latest months come from the live pipeline (NASA FIRMS near-real-time detections) and
 * keeps them fresh: it asks the server every 30 s whether they changed and reloads them when they did.
 */
export function LiveBadge({ region, demo, onDemo, onChange }: Props) {
  const [st, setSt] = useState<LiveStatus | null>(null);
  const [now, setNow] = useState(Date.now());
  const [open, setOpen] = useState(false);
  const [pulse, setPulse] = useState(false);
  const seen = useRef<string | null | undefined>(undefined);
  const changed = useRef(onChange);
  changed.current = onChange;

  useEffect(() => {
    setSt(null);
    seen.current = undefined;
    const ctl = new AbortController();
    const tick = () => {
      if (document.hidden) return;
      getLive(region, demo, ctl.signal)
        .then((s) => {
          setSt(s);
          setNow(Date.now());
          if (seen.current !== undefined && s.version !== seen.current) {
            changed.current(s.first_month ? Number(s.first_month.slice(0, 4)) : undefined);
            setPulse(true);
            window.setTimeout(() => setPulse(false), 2400);
          }
          seen.current = s.version;
        })
        .catch(() => {});
    };
    tick();
    const id = window.setInterval(tick, POLL_MS);
    document.addEventListener("visibilitychange", tick);
    return () => {
      ctl.abort();
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [region, demo]);

  if (!st || (!st.enabled && !st.demo_available)) return null;
  const last = st.months[st.months.length - 1];

  return (
    <div className={`live${pulse ? " is-fresh" : ""}${st.demo ? " is-demo" : ""}`}>
      <button className="live-pill" aria-expanded={open} onClick={() => setOpen(!open)} title="Latest months come from the live pipeline">
        <span className="live-dot" aria-hidden />
        <b>{st.demo ? "Demo replay" : "Live"}</b>
        <span className="live-text">data to {dayLabel(st.through)}</span>
      </button>
      {open && (
        <div className="live-pop" role="dialog" aria-label="Live data">
          <p className="live-pop-title">{st.demo ? "Demo replay (simulated detections)" : "Live from the satellites"}</p>
          <dl>
            <dt>Data through</dt>
            <dd>{dayLabel(st.through)} (UTC)</dd>
            <dt>Last check with NASA</dt>
            <dd>{ago(st.polled_at, now)}</dd>
            <dt>Last detection</dt>
            <dd>{ago(st.last_detection_at, now)}</dd>
            <dt>Received in 24 h</dt>
            <dd>{st.detections_24h.toLocaleString()} detections</dd>
            {last && (
              <>
                <dt>{last.ym} so far</dt>
                <dd>{last.fire_days.toLocaleString()} fire-days</dd>
              </>
            )}
            <dt>Live months</dt>
            <dd>
              {st.first_month} → {st.last_month}
            </dd>
          </dl>
          <p className="live-note">
            {st.source}. New detections arrive within about 3 hours of a satellite pass.
            {" "}Since 3 Nov 2026 the counts come from NOAA-20, calibrated to S-NPP units.
            {st.harmonization.placeholder && " Some months are provisional: this region has no NOAA-20 calibration or source filter yet."}
          </p>
          {st.demo_available && (
            <label className="toggle toggle-sm">
              <input type="checkbox" checked={demo} onChange={(e) => onDemo(e.target.checked)} />
              <span className="toggle-ui" aria-hidden />
              <span className="toggle-text">Show the demo replay (a past outbreak replayed as if live)</span>
            </label>
          )}
        </div>
      )}
    </div>
  );
}
