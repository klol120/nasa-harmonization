import { useEffect } from "react";
import { type DatasetMeta, MONTH_ABBR, SENSOR_LABEL, type Sensor } from "../data/contract";
import { fmt } from "../lib/analytics";

interface Props {
  open: boolean;
  onClose: () => void;
  meta: DatasetMeta;
  sourceLabel: string;
}

/** Methods & limitations: what the numbers mean, how they were made, where they break. */
export function MethodsDrawer({ open, onClose, meta, sourceLabel }: Props) {
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);

  const maxK = Math.max(1, ...meta.calibration.map((c) => c.k));
  const v = meta.validation;

  return (
    <>
      <div className={`scrim${open ? " is-open" : ""}`} onClick={onClose} aria-hidden />
      <aside className={`drawer${open ? " is-open" : ""}`} aria-hidden={!open} aria-label="Methods and limitations">
        <header className="drawer-head">
          <div>
            <span className="eyebrow">Methods &amp; limitations</span>
            <h2>How the harmonized record is built</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="drawer-body">
          <h3>Dataset</h3>
          <dl className="kv">
            <dt>Source</dt>
            <dd>{sourceLabel}</dd>
            <dt>Extent</dt>
            <dd>{meta.bbox.map((x) => x.toFixed(2)).join(", ")} (W, S, E, N)</dd>
            <dt>Grid</dt>
            <dd>{meta.grid_deg}° cells</dd>
            <dt>Coverage</dt>
            <dd>
              {Object.entries(meta.sensor_start).map(([s, start]) => (
                <span key={s} className="kv-line">
                  {SENSOR_LABEL[s as Sensor] ?? s}: from {start}
                </span>
              ))}
              <span className="kv-line">Through {meta.last_month}{meta.last_complete_month !== meta.last_month ? ` (medians and trends through ${meta.last_complete_month})` : ""}</span>
              {meta.generated_at && <span className="kv-line">Export generated {meta.generated_at.replace("T", " ").replace("Z", " UTC")}</span>}
            </dd>
            <dt>Unit</dt>
            <dd>{meta.harmonized_unit ?? "Fire-days"}</dd>
            {meta.n_cells !== undefined && (
              <>
                <dt>Cells</dt>
                <dd>
                  {meta.n_cells.toLocaleString()}
                  {meta.n_persistent_cells ? ` (${meta.n_persistent_cells} with persistent industrial or waste-burning sources)` : ""}
                </dd>
              </>
            )}
          </dl>

          <h3>Pipeline</h3>
          <ol className="steps">
            <li>
              <b>Clean each sensor separately.</b> Keep vegetation fires, drop low-confidence detections and duplicates, and flag cells with persistent
              industrial or waste-burning heat.
            </li>
            <li>
              <b>Grid and count fire-days.</b> Snap detections to a global {meta.grid_deg}° grid. A cell counts once per UTC day per sensor, so the unit
              measures burning activity, not how many pixels one fire lights up.
            </li>
            <li>
              <b>Calibrate on the overlap.</b> In the years both sensors flew ({meta.splice_date?.slice(0, 4) ?? "2012"} onward), fit how many VIIRS fire-days correspond to one MODIS
              fire-day, month by month
              {meta.calibration_strategy ? <> (strategy <code>{meta.calibration_strategy}</code>)</> : null}.
            </li>
            <li>
              <b>Splice.</b> From {meta.splice_date ?? "2012-01-20"} the record is observed VIIRS. Before that it is MODIS converted to <b>VIIRS-equivalent</b> fire-days, with a
              90% uncertainty band. Those months are labelled as modelled estimates everywhere in the app.
            </li>
            {meta.viirs_switch_date && meta.continuation && (
              <li>
                <b>Continue with NOAA-20.</b> VIIRS on S-NPP stopped delivering data, so from {meta.viirs_switch_date} the record is VIIRS NOAA-20 calibrated to
                S-NPP units, month by month on {meta.continuation.overlap_years ? `${meta.continuation.overlap_years[0]}–${meta.continuation.overlap_years[1]}` : "the overlap"}
                {meta.continuation.strategy ? <> (strategy <code>{meta.continuation.strategy}</code>)</> : null}: factor{" "}
                {(() => {
                  const cs = meta.continuation.factors.map((f) => f.c);
                  const lo = Math.min(...cs), hi = Math.max(...cs);
                  return cs.length ? (lo === hi ? lo.toFixed(3) : `${lo.toFixed(3)}–${hi.toFixed(3)}`) : "–";
                })()}
                . These months are observations, not estimates; the month tooltip names the satellite.
              </li>
            )}
            <li>
              <b>Anomalies.</b> Each month's z-score compares it with the same calendar month over{" "}
              {meta.baseline_years ? `${meta.baseline_years[0]}–${meta.baseline_years[1]}` : "the baseline years"}. For a drawn area, the server sums the cells first and
              recomputes the z on that sum.
            </li>
          </ol>

          {meta.calibration.length > 0 && (
            <>
              <h3>VIIRS fire-days per MODIS fire-day, by month</h3>
              <div className="kbars" role="table" aria-label="Calibration factor per month">
                {meta.calibration.map((c) => (
                  <div
                    key={c.month}
                    className="kbar"
                    role="row"
                    title={`${MONTH_ABBR[c.month - 1]}: ${c.k.toFixed(2)}${c.k_low !== undefined && c.k_high !== undefined ? ` (90%: ${c.k_low.toFixed(2)}–${c.k_high.toFixed(2)})` : ""}${c.b ? `, plus ${c.b.toFixed(2)}` : ""}`}
                  >
                    <span className="kbar-fill" style={{ height: `${(c.k / maxK) * 100}%` }} />
                    <span className="kbar-val">{c.k.toFixed(1)}</span>
                    <span className="kbar-m">{MONTH_ABBR[c.month - 1][0]}</span>
                  </div>
                ))}
              </div>
              <p className="muted small">
                VIIRS records about {fmt(meta.calibration.reduce((a, c) => a + c.k, 0) / meta.calibration.length, 1)}× the MODIS fire-days on average, which is why raw MODIS has its
                own scale.
              </p>
            </>
          )}

          {v && (
            <>
              <h3>Validation</h3>
              <div className="metrics">
                <div>
                  <span>{v.wape !== undefined ? "WAPE" : "MAPE"}</span>
                  <b>{v.wape !== undefined ? `${v.wape.toFixed(0)}%` : v.mape !== undefined ? `${v.mape}%` : "–"}</b>
                </div>
                <div>
                  <span>Bias</span>
                  <b>{v.bias !== undefined ? `${v.bias > 0 ? "+" : ""}${v.bias.toFixed(1)}%` : "–"}</b>
                </div>
                <div>
                  <span>Held out</span>
                  <b>{v.holdout_years.length ? `${v.holdout_years[0]}–${v.holdout_years[v.holdout_years.length - 1]}` : "–"}</b>
                </div>
              </div>
              <p className="muted small">
                Error of the converted MODIS against real VIIRS in years the calibration never saw. {v.note ?? ""}
              </p>
            </>
          )}

          <h3>Read with care</h3>
          <ul className="caveats">
            {(meta.caveats ?? []).map((c) => (
              <li key={c}>{c}</li>
            ))}
            <li>
              Hatched calendar cells mean <b>no data</b>, not zero fires. Dotted cells are low-confidence estimates.
            </li>
            <li>A partial year, or a month whose data is still arriving, is outlined with a dashed border and left out of medians and trends.</li>
            <li>
              The climatology band is the historical median and spread. It describes what has been typical; it is <b>not a forecast</b>.
            </li>
          </ul>

          {meta.notes && meta.notes.length > 0 && (
            <>
              <h3>Notes from the data</h3>
              <ul className="caveats">
                {meta.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </>
          )}

          <h3>References</h3>
          <ul className="refs">
            <li>Schroeder et al. 2014, RSE: VIIRS 375 m active fire algorithm.</li>
            <li>Csiszar et al. 2014, JGR Atmospheres: VIIRS vs MODIS detections.</li>
            <li>Giglio, Schroeder &amp; Justice 2016: MODIS Collection 6 active fires.</li>
            <li>Li et al. 2018, JGR Atmospheres: VIIRS vs MODIS FRP.</li>
            <li>Data: NASA FIRMS (MODIS C6.1 Terra + Aqua, VIIRS 375 m S-NPP{meta.viirs_switch_date ? " and NOAA-20" : ""}).</li>
          </ul>
        </div>
      </aside>
    </>
  );
}
