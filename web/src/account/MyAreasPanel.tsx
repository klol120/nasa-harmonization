import { useCallback, useEffect, useState } from "react";
import { regionInfo } from "../config";
import { type Area, areaFromBBox, areaFromRing } from "../lib/geo";
import { buildHash } from "../lib/urlState";
import { useAuth } from "./AuthContext";
import { type SavedArea, api } from "./client";

const THRESHOLDS = [1, 1.5, 2, 3];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const ymLabel = (ym: string) => `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;

/** Link that opens a saved area in its region (same format as shareable links; App reloads on a link to another region). */
function areaHash(a: SavedArea): string {
  const p = new URLSearchParams({ s: "harmonized", m: "cell_days", n: a.name });
  if (a.kind === "polygon" && a.ring) p.set("p", a.ring.map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(";"));
  else p.set("b", a.bbox.map((v) => v.toFixed(3)).join(","));
  return buildHash("overview", `api:${a.region}`, p);
}

export function toArea(a: SavedArea): Area {
  return a.kind === "polygon" && a.ring ? areaFromRing(a.name, a.ring) : areaFromBBox(a.name, a.bbox);
}

function StatusChip({ a }: { a: SavedArea }) {
  const s = a.status;
  if (!s) return <span className="area-status muted">No data yet</span>;
  const z = s.anomaly_z;
  const tone = z === null ? "" : z >= 2 ? " is-hot" : z >= 1 ? " is-warm" : z <= -1 ? " is-cool" : "";
  return (
    <span className={`area-status${tone}`} title={s.is_estimate ? "Modelled estimate (not detections)" : "Satellite detections"}>
      {ymLabel(s.ym)}
      {s.partial_month ? " (so far)" : ""} · {s.harmonized.toFixed(s.harmonized < 10 ? 1 : 0)} fire-days
      {z !== null && ` · z ${z >= 0 ? "+" : "−"}${Math.abs(z).toFixed(1)}`}
    </span>
  );
}

interface Props {
  /** Region id of the dashboard (e.g. "lebanon"). */
  region: string;
  area: Area;
  isWhole: boolean;
  excludePersistent: boolean;
  onOpen: (a: Area) => void;
  onFlash: (msg: string) => void;
}

/** "My areas" sidebar panel: save the current area, reopen saved ones, switch fire alerts on or off. */
export function MyAreasPanel({ region, area, isWhole, excludePersistent, onOpen, onFlash }: Props) {
  const { me, requestSignIn, refresh } = useAuth();
  const [areas, setAreas] = useState<SavedArea[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!me) return setAreas(null);
    api.areas().then(setAreas, (e: Error) => setError(e.message));
  }, [me]);
  useEffect(load, [load]);

  const saved = areas?.find((a) => a.region === region && a.name === area.name);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const name = isWhole ? `All of ${regionInfo(region).name}` : area.name;
      const a = await api.saveArea({
        region,
        name,
        kind: area.kind,
        bbox: area.bbox,
        ring: area.kind === "polygon" ? area.ring : null,
        exclude_persistent: excludePersistent,
      });
      setAreas((xs) => [a, ...(xs ?? [])]);
      refresh();
      onFlash(`Saved “${name}”`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const patch = async (a: SavedArea, p: Parameters<typeof api.updateArea>[1], msg?: string) => {
    try {
      const next = await api.updateArea(a.id, p);
      setAreas((xs) => xs?.map((x) => (x.id === a.id ? next : x)) ?? null);
      if (msg) onFlash(msg);
    } catch (e) {
      onFlash((e as Error).message);
    }
  };

  const remove = async (a: SavedArea) => {
    try {
      await api.deleteArea(a.id);
      setAreas((xs) => xs?.filter((x) => x.id !== a.id) ?? null);
      refresh();
      onFlash(`Removed “${a.name}”`);
    } catch (e) {
      onFlash((e as Error).message);
    }
  };

  const open = (a: SavedArea) => {
    if (a.region === region) onOpen(toArea(a));
    else window.location.hash = areaHash(a);
  };

  return (
    <section className="panel my-areas" id="my-areas">
      <header className="panel-head">
        <h2>My areas</h2>
        {me && areas && <span className="muted small">{areas.length} saved</span>}
      </header>

      {!me ? (
        <div className="my-areas-cta">
          <p className="small muted">Save areas you care about and get an email when burning there is unusually high. Optional and free.</p>
          <button className="btn" onClick={() => requestSignIn("Sign in to save this area and get fire alerts for it.")}>
            Sign in to save areas
          </button>
        </div>
      ) : (
        <>
          {saved ? (
            <p className="small muted">✓ “{saved.name}” is saved.</p>
          ) : (
            <button className="btn btn-primary" disabled={busy} onClick={save}>
              {busy ? "Saving…" : `Save “${isWhole ? `All of ${regionInfo(region).name}` : area.name}”`}
            </button>
          )}
          {error && <p className="warn">{error}</p>}
          {areas === null ? (
            <p className="small muted">Loading…</p>
          ) : areas.length === 0 ? (
            <p className="small muted">No saved areas yet. Pick an area (preset, box or polygon) and save it.</p>
          ) : (
            <ul className="area-list">
              {areas.map((a) => (
                <li key={a.id} className={`area-item${a.region === region && a.name === area.name ? " is-current" : ""}`}>
                  <div className="area-item-top">
                    <button className="area-open" onClick={() => open(a)} title="Open this area">
                      <b>{a.name}</b>
                      {a.region !== region && <small> · {regionInfo(a.region).name}</small>}
                    </button>
                    <button className="icon-btn" onClick={() => remove(a)} aria-label={`Remove ${a.name}`} title="Remove">
                      ✕
                    </button>
                  </div>
                  <StatusChip a={a} />
                  <div className="area-alert">
                    <label className="toggle toggle-sm">
                      <input
                        type="checkbox"
                        checked={a.alert_enabled}
                        onChange={(e) =>
                          patch(a, { alert_enabled: e.target.checked }, e.target.checked ? `Alerts on for “${a.name}”` : `Alerts off for “${a.name}”`)
                        }
                      />
                      <span className="toggle-ui" aria-hidden />
                      <span className="toggle-text">Email me when unusual</span>
                    </label>
                    {a.alert_enabled && (
                      <select
                        className="alert-z"
                        value={a.alert_z}
                        onChange={(e) => patch(a, { alert_z: Number(e.target.value) })}
                        aria-label="Alert threshold"
                        title="How unusual a month must be (anomaly z-score) before you get an email"
                      >
                        {THRESHOLDS.map((t) => (
                          <option key={t} value={t}>
                            z ≥ {t}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
