import { ForecastChart } from "../charts/ForecastChart";
import type { OutlookScore, RegionForecast } from "../data/api";
import { MONTH_ABBR, parseYm, ymMonth, ymYear } from "../data/contract";
import { fmt } from "../lib/analytics";
import { CardHead, Kpi, PageHead, PngButton } from "./Blocks";

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
const pct = (x: number) => `${Math.round(100 * x)}%`;
const signed = (x: number) => `${x > 0 ? "+" : x < 0 ? "−" : "±"}${Math.abs(Math.round(100 * x))}%`;
const BASELINE: Record<OutlookScore["best_baseline"], string> = {
  seasonal_5y: "5-year average",
  typical_year: "typical year",
  last_year: "last year's value",
};

/** The region's burning outlook: the next six months from the shared machine-learning model. */
export function ForecastPage(p: Props) {
  const lede = (
    <>
      Expected fire activity for the next six months, from a machine-learning model trained on the fire history of {p.regionName} and its neighbours. It covers the whole
      region, in harmonized fire-days.
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
                  : "The forecasting model has not been run on this region's latest data yet. When it has, this page shows:"}
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
  const next = months[0];
  const total = months.reduce((s, m) => s + m.value, 0);
  const typ = (ym: string) => p.typical?.[ymMonth(parseYm(ym)) - 1] ?? null;
  const typTotal = p.typical ? months.reduce((s, m) => s + (typ(m.ym) ?? 0), 0) : null;
  const span = `${monthName(months[0].ym)} – ${monthName(months[months.length - 1].ym)}`;

  return (
    <>
      {head}
      {test && !test.beats_baselines && (
        <div className="banner banner-soft">
          <b>Read this as a seasonal guide.</b> In testing on 2022–2025, this forecast was no better here than the {BASELINE[test.best_baseline]} (typical error{" "}
          {pct(test.model.wape)} vs {pct(test[test.best_baseline].wape)}).
        </div>
      )}

      <section className="kpis forecast-kpis" aria-label="Outlook summary">
        <Kpi
          label={`Next month · ${monthName(next.ym)}`}
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
          label="Tested accuracy"
          value={test ? `±${pct(test.model.wape)}` : "–"}
          sub={test ? `typical monthly error, 2022–2025 · 5-year average ±${pct(test.seasonal_5y.wape)}` : "not recorded"}
          tone={test ? (test.beats_baselines ? "cool" : undefined) : undefined}
        />
      </section>

      <section className="card">
        <CardHead
          title="Next six months"
          subtitle={`${span} · forecast issued after ${run.metrics.issued_after ? monthName(run.metrics.issued_after) : "the last complete month"} · band = likely range (8 in 10 months)`}
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
                {p.typical && <th scope="col">Typical</th>}
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
                    {p.typical && (
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
          <CardHead title="How this forecast works" subtitle={`${run.model_name} v${run.model_version}`} />
          <ul className="forecast-how">
            <li>
              <b>One model for every region.</b> It learns from each 5 km cell's past: the same month in earlier years, recent months, and whether the region is running hot
              or quiet.
            </li>
            <li>
              <b>Blended with the 5-year average</b>, which kept it steadier when tested on years it never saw.
            </li>
            <li>
              <b>Tested honestly.</b>{" "}
              {test
                ? `Trained on data up to 2021 and scored on 2022–2025: it landed within 25% of the actual in ${pct(test.within_25pct)} of months.`
                : "Scored on years kept out of training."}
              {conf?.months?.length ? ` On ${conf.months.length} newer months of 2026 its typical error was ${pct(conf.model.wape)}.` : ""}
            </li>
            <li>
              <b>Not yet included:</b> weather forecasts, rainfall or vegetation dryness. It shows where the season usually goes, not individual fires.
            </li>
          </ul>
        </section>
      </div>
    </>
  );
}
