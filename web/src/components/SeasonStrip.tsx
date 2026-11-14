import { MONTH_ABBR } from "../data/contract";
import { type SeasonMetrics, fmt } from "../lib/analytics";

interface Props {
  seasons: SeasonMetrics[];
  selectedYear: number;
  unit: string;
  /** Month with the highest median activity, so the page names one peak everywhere. */
  peakMonth?: number;
  onSelectYear: (y: number) => void;
}

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length ? s[Math.floor((s.length - 1) / 2)] : null;
};

/** Gantt-like strip: each year's fire season (10%→90% of activity) with its peak month. */
export function SeasonStrip({ seasons, selectedYear, unit, peakMonth, onSelectYear }: Props) {
  const done = seasons.filter((s) => s.complete && s.start !== null);
  const typStart = median(done.map((s) => s.start!));
  const typPeak = median(done.map((s) => s.peak!));
  const typEnd = median(done.map((s) => s.end!));
  const maxTotal = Math.max(1, ...seasons.map((s) => s.total));
  const rows = [...seasons].reverse();

  return (
    <div className="season">
      {typStart !== null && (
        <p className="season-summary">
          Typical season <b>{MONTH_ABBR[typStart - 1]}</b> → <b>{MONTH_ABBR[typEnd! - 1]}</b>, peaking in <b>{MONTH_ABBR[(peakMonth ?? typPeak!) - 1]}</b>
          <span className="muted"> (median of {done.length} complete years)</span>
        </p>
      )}
      <div className="season-grid" role="table" aria-label="Fire season per year">
        <div className="season-row season-header" role="row">
          <span role="columnheader">Year</span>
          <span className="season-months" role="columnheader">
            {MONTH_ABBR.map((m) => (
              <i key={m}>{m[0]}</i>
            ))}
          </span>
          <span role="columnheader" className="num">Total</span>
        </div>
        <div className="season-body">
          {rows.map((s) => (
            <button
              key={s.year}
              role="row"
              className={`season-row${s.year === selectedYear ? " is-selected" : ""}${s.complete ? "" : " is-partial"}`}
              onClick={() => onSelectYear(s.year)}
              title={
                s.start
                  ? `${s.year}: starts ${MONTH_ABBR[s.start - 1]}, peaks ${MONTH_ABBR[s.peak! - 1]}, ends ${MONTH_ABBR[s.end! - 1]}${s.complete ? "" : " (incomplete year)"}`
                  : `${s.year}: no activity`
              }
            >
              <span role="cell">{s.year}</span>
              <span className="season-months" role="cell">
                {typStart !== null && (
                  <span className="season-typical" style={{ left: `${((typStart - 1) / 12) * 100}%`, width: `${((typEnd! - typStart + 1) / 12) * 100}%` }} />
                )}
                {s.start !== null && (
                  <span
                    className="season-bar"
                    style={{
                      left: `${((s.start - 1) / 12) * 100}%`,
                      width: `${((s.end! - s.start + 1) / 12) * 100}%`,
                      opacity: 0.45 + 0.55 * (s.total / maxTotal),
                    }}
                  />
                )}
                {s.peak !== null && <span className="season-peak" style={{ left: `${((s.peak - 0.5) / 12) * 100}%` }} />}
              </span>
              <span role="cell" className="num">
                {fmt(s.total)}
              </span>
            </button>
          ))}
        </div>
      </div>
      <p className="legend-line">
        <span className="lg lg-bar" /> season (10%–90% of the year's {unit}) <span className="lg lg-peak" /> peak month{" "}
        <span className="lg lg-typ" /> typical
      </p>
    </div>
  );
}
