import { type DatasetMeta, MONTH_ABBR, SENSOR_LABEL, type Sensor } from "../data/contract";
import { fmt } from "../lib/analytics";
import { PageHead } from "./Blocks";

interface Props {
  meta: DatasetMeta;
  sourceLabel: string;
}

/** Methods & limitations: what the numbers mean, how they were made, where they break. */
export function MethodsPage({ meta, sourceLabel }: Props) {
  const maxK = Math.max(1, ...meta.calibration.map((c) => c.k));
  const v = meta.validation;

  return (
    <article className="methods" aria-label="Methods and limitations">
      <PageHead
        eyebrow={`Methods & limitations · ${meta.name}`}
        title="How the harmonized record is built"
        lede="What the numbers mean, how two satellites become one consistent record, and where that record should be read with care."
      />

      <div className="methods-grid">
        <section className="card methods-card methods-main">
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

        </section>

        <div className="methods-side">
          <section className="card methods-card">
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

          </section>
          <section className="card methods-card">
          <h3>Read with care</h3>
          <ul className="caveats">
            {(meta.caveats ?? []).map((c) => (
              <li key={c}>{c}</li>
            ))}
            <li>
              Hatched calendar cells mean <b>no data</b>, not zero fires. Dotted cells are low-confidence estimates.
            </li>
            <li>A partial year is outlined with a dashed border and left out of medians and trends.</li>
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
            <li>Data: NASA FIRMS (MODIS C6.1 Terra + Aqua, VIIRS 375 m S-NPP).</li>
          </ul>
          </section>
        </div>
      </div>
    </article>
  );
}
