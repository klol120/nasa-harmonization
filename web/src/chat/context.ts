import type { RegionForecast, RegionSummary, RegionWeather, WeatherField } from "../data/api";
import { type DatasetMeta, METRIC_LABEL, MONTH_ABBR, type Metric, SENSOR_LABEL, type Sensor, ymKey, ymMonth, ymYear } from "../data/contract";
import type { AnomalyCell, CurrentVsMedian, KeyEvent, MonthClimatology, MonthPoint, SeasonMetrics, YearTotal } from "../lib/analytics";
import { typicalSeason } from "../lib/analytics";
import { regionInfo } from "../config";
import type { Area } from "../lib/geo";

/**
 * What the assistant is told about the view: the same figures the page shows, as compact JSON.
 * Key names are written to be read by the model, so they say what each number is.
 */

export interface ViewState {
  pageLabel: string;
  regions: RegionSummary[] | null;
  /** Everything below is only set once a region's record has loaded. */
  region?: {
    meta: DatasetMeta;
    area: Area;
    isWhole: boolean;
    cellCount: number;
    sensor: Sensor;
    metric: Metric;
    unit: string;
    range: [number, number];
    selected: number;
    excludePersistent: boolean;
    series: MonthPoint[];
    clim: MonthClimatology[];
    anoms: AnomalyCell[];
    totals: YearTotal[];
    trend: { pctPerDecade: number; from: number; to: number } | null;
    seasons: SeasonMetrics[];
    total: number;
    cvm: CurrentVsMedian | null;
    documented: KeyEvent[];
    forecast: RegionForecast | null;
    forecastStatus: string;
    weather: RegionWeather | null;
  };
}

/** Rounded for reading: three significant digits is as precise as anyone quotes these. */
const n = (v: number | null | undefined) => {
  if (v === null || v === undefined || !Number.isFinite(v)) return null;
  const a = Math.abs(v);
  return a >= 100 ? Math.round(v) : a >= 10 ? +v.toFixed(1) : +v.toFixed(2);
};
const label = (i: number) => `${MONTH_ABBR[ymMonth(i) - 1]} ${ymYear(i)}`;
const mon = (m: number | null | undefined) => (m ? MONTH_ABBR[m - 1] : null);

const WEATHER_FIELDS: WeatherField[] = ["t_mean_c", "t_max_c", "precip_mm", "wind_ms", "rh_pct"];

export function buildChatContext(v: ViewState): Record<string, unknown> {
  const out: Record<string, unknown> = {
    page: v.pageLabel,
    regions_in_the_app: v.regions?.map((r) => regionInfo(r.region).name) ?? "loading",
  };
  const r = v.region;
  if (!r) {
    out.note = "The person is on the world map and has not opened a region yet, so there are no figures on screen.";
    return out;
  }
  const { meta: m, series, clim, sensor } = r;
  const flags = (p: MonthPoint) => [p.estimate && "modelled estimate", p.lowConfidence && "low confidence", p.partial && "partial", p.gap && "satellite outage"].filter(Boolean);

  out.region = {
    name: m.name,
    record: `${m.sensor_start.harmonized ?? m.first_year} to ${m.last_month}`,
    last_complete_month: m.last_complete_month,
    grid: `${m.grid_deg} degree cells`,
    cells: m.n_cells,
    cells_with_persistent_industrial_sources: m.n_persistent_cells,
    viirs_starts: m.sensor_start.viirs_raw,
    harmonized_is_modelled_estimate_until: m.estimate_until,
    anomaly_baseline_years: m.baseline_years,
    harmonization_check: m.validation
      ? { held_out_years: m.validation.holdout_years, error_wape_pct: n(m.validation.wape), bias_pct: n(m.validation.bias), note: m.validation.note }
      : undefined,
    caveats: m.caveats,
  };

  out.showing = {
    area: r.isWhole ? `${r.area.name} (whole region)` : r.area.name,
    cells_in_area: r.cellCount,
    series: SENSOR_LABEL[sensor],
    measure: METRIC_LABEL[r.metric],
    unit: r.unit,
    date_range: `${ymKey(r.range[0])} to ${ymKey(r.range[1])}`,
    industrial_sites: r.excludePersistent ? "excluded" : "included",
    selected_month: label(r.selected),
  };

  // The selected month against the same calendar month in other years.
  const point = series.find((p) => p.i === r.selected);
  const c = r.cvm;
  out.selected_month = {
    month: label(r.selected),
    value: n(point?.value),
    notes: point ? flags(point) : [],
    ...(c
      ? {
          typical_median_for_this_calendar_month: n(c.median),
          typical_middle_half: [n(c.q1), n(c.q3)],
          pct_vs_typical: n(c.pct),
          z_score: n(c.z),
          rank_among_same_calendar_months: `${c.rank} of ${c.n + 1} (1 = most active)`,
          year_to_date: c.ytd ? { value: n(c.ytd.value), typical: n(c.ytd.median), pct_vs_typical: n(c.ytd.pct) } : undefined,
        }
      : {}),
  };

  const complete = r.totals.filter((t) => t.complete);
  const record = complete.length ? complete.reduce((a, b) => (b.total > a.total ? b : a)) : null;
  const quietest = complete.length ? complete.reduce((a, b) => (b.total < a.total ? b : a)) : null;
  const peak = clim.filter((x) => Number.isFinite(x.median)).reduce<MonthClimatology | null>((a, b) => (!a || b.median > a.median ? b : a), null);
  const season = typicalSeason(r.seasons);
  out.summary = {
    total_in_range: n(r.total),
    average_per_complete_year: complete.length ? n(complete.reduce((s, t) => s + t.total, 0) / complete.length) : null,
    complete_years: complete.length,
    peak_month_of_a_typical_year: peak ? { month: mon(peak.month), median: n(peak.median) } : null,
    record_year: record ? { year: record.year, total: n(record.total) } : null,
    quietest_year: quietest ? { year: quietest.year, total: n(quietest.total) } : null,
    trend: r.trend ? { pct_per_decade: n(r.trend.pctPerDecade), fitted_on: `${r.trend.from} to ${r.trend.to}`, method: "linear fit on complete years" } : null,
    typical_season: season ? { starts: mon(season.start), peaks: mon(season.peak), ends: mon(season.end), definition: "months where 10% and 90% of a year's activity are reached" } : null,
  };

  out.typical_year_median_by_month = Object.fromEntries(clim.map((x) => [MONTH_ABBR[x.month - 1], n(x.median)]));
  out.annual_totals = Object.fromEntries(r.totals.map((t) => [t.year, t.complete ? n(t.total) : { total_so_far: n(t.total), months_counted: t.coveredMonths, incomplete: true }]));

  const year = ymYear(r.selected);
  out.selected_year_by_month = {
    year,
    values: Object.fromEntries(series.filter((p) => p.year === year).map((p) => [MONTH_ABBR[p.month - 1], n(p.value)])),
    season: (() => {
      const s = r.seasons.find((x) => x.year === year);
      return s && s.start !== null ? { starts: mon(s.start), peaks: mon(s.peak), ends: mon(s.end) } : undefined;
    })(),
  };

  out.latest_24_months = r.anoms
    .filter((p) => p.value !== null)
    .slice(-24)
    .map((p) => ({ month: ymKey(p.i), value: n(p.value), z: p.z, pct_vs_typical: p.pct, ...(flags(p).length ? { notes: flags(p) } : {}) }));

  // The most unusual months of the record, so "when was the worst" has an answer.
  out.most_unusual_months = [...r.anoms]
    .filter((p) => p.z !== null && (p.value ?? 0) > 0)
    .sort((a, b) => b.z! - a.z!)
    .slice(0, 8)
    .map((p) => ({ month: ymKey(p.i), value: n(p.value), z: p.z, pct_vs_typical: p.pct, ...(flags(p).length ? { notes: flags(p) } : {}) }));

  if (r.documented.length) out.documented_events = r.documented.map((e) => ({ event: e.label, compared_with_normal: e.detail, note: e.note }));

  if (r.forecast?.months.length) {
    const score = r.forecast.run.metrics.test;
    const wape = score?.model?.wape;
    const baselineWape = score?.[score.best_baseline]?.wape;
    out.burning_outlook = {
      what: "monthly outlook for whole-region harmonized fire-days, including all cells",
      method: r.forecast.run.metrics.method,
      issued: r.forecast.run.created_at.slice(0, 10),
      months: r.forecast.months.map((f) => ({ month: f.ym, expected: n(f.value), likely_range: [n(f.value_low), n(f.value_high)] })),
      accuracy_on_held_out_months: score?.model
        ? {
            month_lead_pairs_tested: score.n,
            error_wape_pct: wape == null ? null : n(wape * 100),
            best_simple_baseline: score.best_baseline,
            best_baseline_error_wape_pct: baselineWape == null ? null : n(baselineWape * 100),
            beats_simple_baselines: score.beats_baselines,
            share_within_25pct: n(score.within_25pct),
          }
        : undefined,
    };
  } else out.burning_outlook = r.forecastStatus === "loading" ? "loading" : "not published for this region yet";

  const w = r.weather?.months.find((x) => x.ym === ymKey(r.selected));
  if (r.weather && w) {
    out.weather_at_the_fire_hotspots = {
      month: label(r.selected),
      complete_month: w.complete,
      source: r.weather.provider,
      normal_is: `the average for this calendar month over ${r.weather.baseline_years.join("–")}`,
      scope: r.isWhole ? undefined : "the whole region's hotspots, not the selected sub-area",
      ...Object.fromEntries(
        WEATHER_FIELDS.filter((f) => w[f] !== null).map((f) => [
          `${r.weather!.fields[f]?.label ?? f} (${r.weather!.fields[f]?.unit ?? ""})`,
          { value: n(w[f]), normal: n(w[`${f}_normal`]), difference: n(w[`${f}_anom`]), z: n(w[`${f}_z`]) },
        ]),
      ),
      rain_pct_of_normal: n(w.precip_pct_of_normal),
    };
  } else out.weather_at_the_fire_hotspots = r.weather ? "no weather stored for the selected month" : "not available for this region";

  return out;
}

/** Questions offered before the first message, picked for what is on screen. */
export function suggestionsFor(v: ViewState): string[] {
  const r = v.region;
  if (!r) return ["What does this app show?", "What is a fire-day?", "Why combine MODIS and VIIRS?", "Which regions can I explore?"];
  const month = label(r.selected);
  const out = [`Was ${month} unusual in ${r.isWhole ? r.meta.name : r.area.name}?`];
  if (v.pageLabel.includes("Forecast")) out.push("What does the outlook expect, and how reliable is it?");
  else if (v.pageLabel.includes("Weather")) out.push(`How did the weather in ${month} compare with normal?`);
  else if (v.pageLabel.includes("Trends")) out.push("Is fire activity increasing here?");
  else out.push("When is the fire season here?");
  out.push(r.sensor === "harmonized" ? "What does harmonized mean?" : `Why does ${SENSOR_LABEL[r.sensor]} look different from harmonized?`);
  out.push("Which years were the worst on record?");
  return out;
}
