import { ForecastChart } from "../charts/ForecastChart";
import type { OutlookScore, RegionForecast } from "../data/api";
import { MONTH_ABBR, parseYm, ymMonth, ymYear } from "../data/contract";
import { fmt } from "../lib/analytics";
import { CardHead, Kpi, PageHead, PngButton } from "./Blocks";
import { OUTLOOK_METHOD_LABEL } from "./ForecastMonthReadout";

export type ForecastStatus = "none" | "loading" | "ready" | "unpublished" | "failed";

interface Props {
  eyebrow: string;
  regionName: string;
  status: ForecastStatus;
  forecast: RegionForecast | null;
  /** Recent observed months, only when they are comparable (whole region, harmonized fire-days). */
  history?: { i: number; value: number | null }[];
  /** Typical-year median per calendar month, under the same condition. */
  typical?: (number | null)[];
  /** Why history is hidden, when it is. */
  historyNote?: string;
  unit: string;
  onRetry: () => void;
  backLink: React.ReactNode;
}

const monthName = (ym: string) => {
  const i = parseYm(ym);
  return `${MONTH_ABBR[ymMonth(i) - 1]} ${ymYear(i)}`;
};
const pct = (x: number | null | undefined) => x != null && Number.isFinite(x) ? `${Math.round(100 * x)}%` : "–";
const signed = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(Math.round(100 * x))}%`;
const BASELINE: Record<OutlookScore["best_baseline"], string> = {
  seasonal_5y: "5-year average",
  typical_year: "typical year",
  last_year: "last year's value",
};

/** Compare the region's published six-month outlook with the statistical model and baselines. */
export function ForecastPage(p: Props) {
  const lede = (
    <>
      Six months of expected fire activity for {p.regionName}, in harmonized fire-days. You can also reach these months from the Overview timeline or the Burning calendar.
    </>
  );
  const head = <PageHead eyebrow={p.eyebrow} title="Burning outlook" lede={lede} />;

  if (p.status !== "ready" || !p.forecast)
    return (
      <>
        {head}
        <section className="card empty forecast-empty">
          {p.status === "loading" ? (
            <p>
              <span className="spinner" aria-hidden /> Loading the outlook for {p.regionName}…
            </p>
          ) : p.status === "failed" ? (
            <>
              <h3>The outlook didn't load</h3>
              <p className="muted">The data server didn't answer. Check that it is running, then try again.</p>
              <p>
                <button className="btn btn-primary" onClick={p.onRetry}>
                  Try again
                </button>
              </p>
            </>
          ) : (
            <>
              <span className="eyebrow">Coming soon</span>
              <h3>No outlook published for {p.regionName} yet</h3>
              <p className="muted">
                {p.status === "none"
                  ? "Outlooks come from the data server, so they are only shown for regions opened from the world map."
                  : "An outlook appears after a forecast is published for this region."}
              </p>
              {p.status !== "none" && (
                <ul className="forecast-promise">
                  <li>
                    <b>The next six months</b>, with the expected fire-days and a likely range
                  </li>
                  <li>
                    <b>How it compares</b> with a typical year for each month
                  </li>
                  <li>
                    <b>How accurate it has been</b>, tested on years the model never saw
                  </li>
                </ul>
              )}
              <p className="muted small">{p.backLink}</p>
            </>
          )}
        </section>
      </>
    );

  const { run, months } = p.forecast;
  const test = run.metrics.test;
  const conf = run.metrics.confirmation;
  const method = run.metrics.method_kind;
  const comparison = run.metrics.monthly_comparison;
  const testYears = run.metrics.test_years?.join("–") ?? "2022–2025";
  const methodYears = run.metrics.method_years?.join("–");
  const options = run.metrics.method_evaluation;
  const next = months[0];
  const total = months.reduce((s, m) => s + m.value, 0);
  const typ = (ym: string) => p.typical?.[ymMonth(parseYm(ym)) - 1] ?? null;
  const typTotal = p.typical ? months.reduce((s, m) => s + (typ(m.ym) ?? 0), 0) : null;
  const span = `${monthName(months[0].ym)} – ${monthName(months[months.length - 1].ym)}`;

  return (
    <>
      {head}
      {!run.is_current && (
        <div className="banner">
          <b>Made from an earlier data release</b> ({new Date(run.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}). Newer
          satellite data has arrived since; the outlook updates the next time the model runs.
        </div>
      )}
      {method && method !== "outlook" && (
        <div className="banner banner-soft">
          <b>Seasonal baseline in use.</b> The {OUTLOOK_METHOD_LABEL[method].toLowerCase()} matched or beat the model blend in the {methodYears} method comparison
          {options?.candidate && ` (${pct(options.model.wape)} error vs ${pct(options.candidate.wape)})`}.
        </div>
      )}
      {!method && test?.model && !test.beats_baselines && (
        <div className="banner banner-soft">
          <b>Read this as a seasonal guide.</b> In testing on 2022–2025, this forecast was no better here than the {BASELINE[test.best_baseline]} (typical error{" "}
          {pct(test.model.wape)} vs {pct(test[test.best_baseline].wape)}).
        </div>
      )}

      <section className="kpis forecast-kpis" aria-label="Outlook summary">
        <Kpi
          label={`First forecast · ${monthName(next.ym)}`}
          value={fmt(next.value)}
          num={next.value}
          sub={next.value_low !== null && next.value_high !== null ? `likely ${fmt(next.value_low)}–${fmt(next.value_high)} ${p.unit}` : p.unit}
        />
        <Kpi
          label="Next six months"
          value={fmt(total)}
          num={total}
          sub={typTotal ? `${signed(total / typTotal - 1)} vs a typical year` : span}
          tone={typTotal ? (total > typTotal * 1.15 ? "warm" : total < typTotal * 0.85 ? "cool" : undefined) : undefined}
        />
        <Kpi
          label="Backtest error"
          value={pct(test?.model?.wape)}
          sub={test?.model ? `${testYears} · ${test.candidate ? "model blend" : "5-year average"} error ${pct(test.candidate?.wape ?? test.seasonal_5y.wape)}` : "No score recorded"}
          tone={test?.beats_baselines ? "cool" : undefined}
        />
      </section>

      <section className="card">
        <CardHead
          title="Monthly outlook"
          subtitle={`${span} · observations through ${run.metrics.issued_after ? monthName(run.metrics.issued_after) : "the last complete month"} · range targets 80% coverage`}
          actions={<PngButton id="forecast" />}
        />
        <ForecastChart forecast={months} history={p.history} typical={p.typical} unit={p.unit} />
        {p.historyNote && <p className="legend-line muted small">{p.historyNote}</p>}
      </section>

      <div className="grid-2">
        <section className="card">
          <CardHead title="Month by month" subtitle={`Harmonized ${p.unit}, whole region`} />
          <table className="forecast-table">
            <thead>
              <tr>
                <th scope="col">Month</th>
                <th scope="col">Expected</th>
                <th scope="col">Likely range</th>
                {comparison ? <th scope="col">Model blend</th> : p.typical && <th scope="col">Typical</th>}
              </tr>
            </thead>
            <tbody>
              {months.map((m) => {
                const t = typ(m.ym);
                return (
                  <tr key={m.ym}>
                    <th scope="row">{monthName(m.ym)}</th>
                    <td>
                      <b>{fmt(m.value)}</b>
                    </td>
                    <td className="muted">{m.value_low !== null && m.value_high !== null ? `${fmt(m.value_low)} – ${fmt(m.value_high)}` : "–"}</td>
                    {comparison ? <td className="muted">{fmt(comparison[m.ym]?.candidate)}</td> : p.typical && (
                      <td className="muted">
                        {t === null ? "–" : fmt(t)}
                        {t ? <span className={`forecast-delta${m.value > t * 1.15 ? " tone-warm" : m.value < t * 0.85 ? " tone-cool" : ""}`}> {signed(m.value / t - 1)}</span> : null}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>

        <section className="card">
          <CardHead title="Backtest by lead time" subtitle={`${testYears} · total absolute error ÷ observed fire-days`} />
          {test?.by_horizon ? (
            <table className="forecast-table">
              <thead><tr><th scope="col">Ahead</th><th scope="col">Published</th><th scope="col">Best baseline</th><th scope="col">In range</th></tr></thead>
              <tbody>
                {Object.entries(test.by_horizon).map(([lead, score]) => (
                  <tr key={lead}>
                    <th scope="row">{lead} mo</th>
                    <td>{pct(score.model.wape)}</td>
                    <td title={BASELINE[score.best_baseline]}>{pct(score[score.best_baseline].wape)}</td>
                    <td>{pct(score.interval_coverage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="muted small">This run has no results by lead time.</p>}
          {conf?.months?.length ? <p className="muted small">Recent check over {conf.months.length} months · {pct(conf.model.wape)} error.</p> : null}
        </section>
      </div>
      <p className="muted small">
        Published method {run.metrics.method ?? "statistical outlook"} · history-based regional estimates · run {new Date(run.created_at).toLocaleDateString()}
      </p>
    </>
  );
}
