import { MONTH_ABBR, ymMonth, ymYear } from "../data/contract";
import { type CurrentVsMedian as CVM, type MonthPoint, fmt, fmtPct } from "../lib/analytics";
import { ForecastMonthReadout, type ForecastMonthDetails } from "./ForecastMonthReadout";

interface Props {
  cvm: CVM | null;
  series: MonthPoint[];
  selected: number;
  unit: string;
  onStep: (delta: number) => void;
  onLatest: () => void;
  /** What one arrow click moves by. */
  stepUnit?: "month" | "year";
  forecast?: ForecastMonthDetails;
  canStep?: [boolean, boolean];
  forwardLabel?: string;
}

const ordinal = (n: number) => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

function verdict(z: number, pct: number) {
  if (z >= 2 || pct >= 100) return { text: "Far above normal", tone: "hot" };
  if (z >= 1 || pct >= 30) return { text: "Above normal", tone: "warm" };
  if (z <= -1 || pct <= -30) return { text: "Below normal", tone: "cool" };
  return { text: "Near normal", tone: "neutral" };
}

/** "Is this month above or below normal?" for the selected month. */
export function CurrentVsMedian({ cvm, series, selected, unit, onStep, onLatest, stepUnit = "month", forecast, canStep, forwardLabel = `Next ${stepUnit}` }: Props) {
  const month = ymMonth(selected);
  const year = ymYear(selected);
  const same = series.filter((p) => p.month === month && p.value !== null && !p.partial);
  const max = Math.max(1, ...same.map((p) => p.value!), cvm?.value ?? 0);

  return (
    <div className="cvm">
      <div className="cvm-head">
        <button className="icon-btn" disabled={canStep && !canStep[0]} onClick={() => onStep(-1)} aria-label={`Previous ${stepUnit}`} title={`Previous ${stepUnit}`}>‹</button>
        <div className="cvm-title">
          <span className={forecast ? "eyebrow time-forecast-label" : "eyebrow"}>{forecast ? "Forecast month" : "Selected month"}</span>
          <strong>
            {MONTH_ABBR[month - 1]} {year}
          </strong>
        </div>
        <button className="icon-btn" disabled={canStep && !canStep[1]} onClick={() => onStep(1)} aria-label={forwardLabel} title={forwardLabel}>›</button>
        <button className="chip" onClick={onLatest} title="Latest observed month">Latest</button>
      </div>

      {forecast ? <ForecastMonthReadout {...forecast} /> : !cvm ? (
        <p className="muted small">No coverage for this month, or not enough other years to compare against.</p>
      ) : (
        <>
          {(() => {
            const v = verdict(cvm.z, cvm.pct);
            return (
              <div className="cvm-body">
                <div className="cvm-big">
                  <span className={`cvm-pct tone-${v.tone}`}>{fmtPct(cvm.pct)}</span>
                  <span className={`badge tone-${v.tone}`}>{v.text}</span>
                </div>
                <dl className="cvm-stats">
                  <div>
                    <dt>This month</dt>
                    <dd>
                      {fmt(cvm.value)} <small>{unit}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Median {MONTH_ABBR[month - 1]}</dt>
                    <dd>
                      {fmt(cvm.median)} <small>{unit}</small>
                    </dd>
                  </div>
                  <div>
                    <dt>z-score</dt>
                    <dd>{cvm.z.toFixed(1)}</dd>
                  </div>
                  <div>
                    <dt>Rank</dt>
                    <dd>
                      {ordinal(cvm.rank)} <small>of {cvm.n + 1}</small>
                    </dd>
                  </div>
                </dl>
                {cvm.partial && <p className="note">Month still in progress: values will rise as data arrives.</p>}

                {/* Strip of every year's value for this calendar month. */}
                <div className="strip" aria-label={`All ${MONTH_ABBR[month - 1]} values`}>
                  <div className="strip-iqr" style={{ left: `${(cvm.q1 / max) * 100}%`, width: `${((cvm.q3 - cvm.q1) / max) * 100}%` }} />
                  <div className="strip-median" style={{ left: `${(cvm.median / max) * 100}%` }} />
                  {same.map((p) => (
                    <span
                      key={p.year}
                      className={`strip-dot${p.year === year ? " is-current" : ""}`}
                      style={{ left: `${(p.value! / max) * 100}%` }}
                      title={`${MONTH_ABBR[month - 1]} ${p.year}: ${fmt(p.value)} ${unit}`}
                    />
                  ))}
                  {cvm.partial && <span className="strip-dot is-current" style={{ left: `${(cvm.value / max) * 100}%` }} />}
                </div>
                <div className="strip-axis">
                  <span>0</span>
                  <span>
                    every {MONTH_ABBR[month - 1]} on record · band = middle 50%
                  </span>
                  <span>{fmt(max)}</span>
                </div>

                {cvm.ytd && (
                  <p className="ytd">
                    Year to date: <b>{fmt(cvm.ytd.value)}</b> vs median <b>{fmt(cvm.ytd.median)}</b>{" "}
                    <span className={cvm.ytd.pct >= 0 ? "tone-warm" : "tone-cool"}>({fmtPct(cvm.ytd.pct)})</span>
                  </p>
                )}
              </div>
            );
          })()}
        </>
      )}
    </div>
  );
}
