import type { ForecastMonth, OutlookMethod } from "../data/api";
import { MONTH_ABBR, parseYm, ymMonth, ymYear } from "../data/contract";
import { fmt } from "../lib/analytics";

export const OUTLOOK_METHOD_LABEL: Record<OutlookMethod, string> = {
  outlook: "Statistical model",
  seasonal_5y: "5-year same-month average",
  typical_year: "Historical same-month median",
  last_year: "Last year's same month",
};

export const outlookMonthName = (ym: string) => {
  const i = parseYm(ym);
  return `${MONTH_ABBR[ymMonth(i) - 1]} ${ymYear(i)}`;
};

export interface ForecastMonthDetails {
  month: ForecastMonth;
  method?: OutlookMethod;
  issuedAfter?: string;
  observedToDate?: number | null;
}

export function ForecastMonthReadout({ month, method, issuedAfter, observedToDate }: ForecastMonthDetails) {
  return (
    <div className="outlook-month" aria-live="polite">
      <p className="outlook-month-value"><strong>{fmt(month.value)}</strong> expected fire-days</p>
      {month.value_low !== null && month.value_high !== null && (
        <p className="muted">Estimated range {fmt(month.value_low)}–{fmt(month.value_high)}</p>
      )}
      {observedToDate != null && <p>Observed so far this month <b>{fmt(observedToDate)} fire-days</b></p>}
      <p className="muted small">
        {method ? OUTLOOK_METHOD_LABEL[method] : "Monthly outlook"}
        {issuedAfter && ` · based on data through ${outlookMonthName(issuedAfter)}`}
      </p>
    </div>
  );
}
