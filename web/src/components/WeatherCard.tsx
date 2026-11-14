import { useMemo } from "react";
import { EChart, tooltipStyle } from "../charts/EChart";
import { MONTH_ABBR, ymMonth, ymYear } from "../data/contract";
import type { RegionWeather, WeatherField, WeatherMonth } from "../data/api";
import { UI } from "../lib/colors";

/** Fire-relevant weather shown in the card, in reading order. */
type Shown = Exclude<WeatherField, "t_mean_c">;
const SHOWN: Shown[] = ["t_max_c", "precip_mm", "rh_pct", "wind_ms"];

const SHORT: Record<Shown, string> = {
  t_max_c: "Daytime high",
  precip_mm: "Rain",
  rh_pct: "Humidity",
  wind_ms: "Wind",
};

/** Which direction of change makes fires more likely: hot, dry, low humidity, windy. */
const FIRE_SIGN: Record<Shown, 1 | -1> = { t_max_c: 1, precip_mm: -1, rh_pct: -1, wind_ms: 1 };
/** Words for a value above / below its normal. */
const WORDS: Record<Shown, [above: string, below: string]> = {
  t_max_c: ["hotter", "cooler"],
  precip_mm: ["wetter", "drier"],
  rh_pct: ["more humid", "drier air"],
  wind_ms: ["windier", "calmer"],
};

/** A difference smaller than this many standard deviations reads as "near normal". */
const Z_NEAR = 0.5;
/** Below this monthly normal (mm) a rain percentage means little: it's the dry season. */
const DRY_SEASON_MM = 5;

const WARM = "#fca50a"; // --warm
const COOL = "#6fb3ff"; // --cool

type Tone = "warm" | "cool" | undefined;

interface Props {
  weather: RegionWeather;
  /** Selected month (contract month index). */
  selected: number;
  onSelect: (i: number) => void;
  /** True when the user picked a sub-area; weather stays region-wide. */
  subArea: boolean;
}

export function WeatherCard({ weather, selected, onSelect, subArea }: Props) {
  const year = ymYear(selected);
  const month = ymMonth(selected);
  const byYm = useMemo(() => new Map(weather.months.map((m) => [m.ym, m])), [weather]);
  const key = (y: number, mo: number) => `${y}-${String(mo).padStart(2, "0")}`;
  const cur = byYm.get(key(year, month));
  // Normals are per calendar month, so any year's row carries them.
  const normals = useMemo(() => {
    const out: (WeatherMonth | undefined)[] = Array(12).fill(undefined);
    for (const m of weather.months) if (!out[m.month - 1] && m.t_max_c_normal !== null) out[m.month - 1] = m;
    return out;
  }, [weather]);
  const yearRows = MONTH_ABBR.map((_, k) => byYm.get(key(year, k + 1)));

  const [b0, b1] = weather.baseline_years;
  const label = `${MONTH_ABBR[month - 1]} ${year}`;

  return (
    <section className="card weather-card">
      <header className="card-head">
        <div>
          <h3>Weather at the fire hotspots</h3>
          <p>
            {label} vs the {b0}–{b1} normal · past weather, not a forecast
            {subArea ? " · region-wide, it doesn't follow the drawn area" : ""}
          </p>
        </div>
      </header>

      {!weather.available || weather.months.length === 0 ? (
        <p className="muted small">No weather stored for this region yet. It appears here once the server has fetched it.</p>
      ) : (
        <>
          <p className="weather-headline">{headline(cur, label)}</p>
          <div className="weather-tiles">
            {SHOWN.map((f) => (
              <Tile key={f} field={f} m={cur} unit={weather.fields[f].unit} />
            ))}
          </div>
          <div className="weather-charts">
            {SHOWN.map((f) => (
              <MiniChart
                key={f}
                field={f}
                title={SHORT[f]}
                unit={weather.fields[f].unit}
                year={year}
                month={month}
                rows={yearRows}
                normals={normals}
                onSelectMonth={(mo) => onSelect(selected + (mo - month))}
              />
            ))}
          </div>
          <p className="legend-line">
            <span className="lg weather-lg-line" /> {year}
            <span className="lg weather-lg-normal" /> normal
            <span className="lg weather-lg-sel" /> selected month
            <span className="lg weather-lg-dot tone-warm" /> favours fire (hot, dry, windy)
            <span className="lg weather-lg-dot tone-cool" /> works against fire
            <span className="weather-attrib">
              Average of {weather.points.length} points weighted by fire activity · {weather.attribution}
            </span>
          </p>
        </>
      )}
    </section>
  );
}

// ---------------------------------------------------------------------------

function toneOf(f: Shown, m: WeatherMonth | undefined): Tone {
  const z = m?.[`${f}_z`];
  if (z === null || z === undefined || Math.abs(z) < Z_NEAR) return undefined;
  if (f === "precip_mm" && (m!.precip_mm_normal ?? 0) < DRY_SEASON_MM) return undefined;
  return Math.sign(z) === FIRE_SIGN[f] ? "warm" : "cool";
}

function headline(m: WeatherMonth | undefined, label: string) {
  if (!m) return `No weather for ${label} yet.`;
  if (!m.complete) return `${label} so far (${m.n_days} days): too early to compare with normal.`;
  const fire: string[] = [];
  const calm: string[] = [];
  for (const f of SHOWN) {
    const t = toneOf(f, m);
    if (!t) continue;
    const z = m[`${f}_z`]!;
    const word = WORDS[f][z > 0 ? 0 : 1];
    if (t === "warm") {
      if (!fire.includes(word) && !(word === "drier air" && fire.includes("drier"))) fire.push(word);
    } else if (!calm.includes(word) && !(word === "more humid" && calm.includes("wetter"))) calm.push(word);
  }
  if (!fire.length && !calm.length) return `${label} was close to normal.`;
  const list = (ws: string[]) => (ws.length < 2 ? ws.join("") : `${ws.slice(0, -1).join(", ")} and ${ws.at(-1)}`);
  const parts = [fire.length && list(fire), calm.length && list(calm)].filter(Boolean).join(", but ");
  const note = fire.length >= 2 && !calm.length ? ": weather that favours fire" : fire.length === 0 ? ": weather that works against fire" : "";
  return `${label} was ${parts} than normal${note}.`;
}

function Tile({ field: f, m, unit }: { field: Shown; m: WeatherMonth | undefined; unit: string }) {
  const v = m?.[f] ?? null;
  const normal = m?.[`${f}_normal`] ?? null;
  const anom = m?.[`${f}_anom`] ?? null;
  const tone = toneOf(f, m);
  const digits = f === "precip_mm" && v !== null && v >= 10 ? 0 : 1;
  const sp = unit === "%" ? "" : " ";

  let diff = "";
  if (m && !m.complete) diff = `${m.n_days} days so far`;
  else if (anom !== null) {
    if (f === "precip_mm") {
      diff =
        (normal ?? 0) < DRY_SEASON_MM
          ? "dry season"
          : m!.precip_pct_of_normal !== null
            ? `${m!.precip_pct_of_normal}% of normal`
            : "";
    } else if (!tone) diff = "near normal";
    else {
      const sign = anom > 0 ? "+" : "−";
      const u = f === "rh_pct" ? " pts" : `${sp}${unit}`;
      diff = `${sign}${Math.abs(anom).toFixed(1)}${u} · ${WORDS[f][anom > 0 ? 0 : 1]}`;
    }
  }
  const arrow = tone && anom !== null ? (anom > 0 ? "▲" : "▼") : "";

  return (
    <div className="weather-tile">
      <span className="kpi-label">{SHORT[f]}</span>
      <span className="weather-value">
        {v === null ? "–" : v.toFixed(digits)}
        {v !== null && <small>{sp + unit}</small>}
      </span>
      <span className={`weather-diff${tone ? ` tone-${tone}` : ""}`}>
        {arrow && <span aria-hidden>{arrow} </span>}
        {diff || " "}
      </span>
      <span className="weather-normal">{normal !== null ? `normal ${normal.toFixed(digits)}${sp}${unit}` : " "}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------

interface MiniProps {
  field: Shown;
  title: string;
  unit: string;
  year: number;
  month: number;
  rows: (WeatherMonth | undefined)[];
  normals: (WeatherMonth | undefined)[];
  onSelectMonth: (month: number) => void;
}

/** One variable across the selected year, against its normal. Each variable gets its own chart and axis. */
function MiniChart({ field: f, title, unit, year, month, rows, normals, onSelectMonth }: MiniProps) {
  const option = useMemo(() => {
    const vals = rows.map((r) => r?.[f] ?? null);
    const norm = normals.map((r) => r?.[`${f}_normal`] ?? null);
    const isRain = f === "precip_mm";
    const sp = unit === "%" ? "" : " ";
    const fmtV = (v: number | null) => (v === null ? "–" : `${v.toFixed(isRain && v >= 10 ? 0 : 1)}${sp}${unit}`);
    // Points coloured by whether the month leaned towards fire weather; neutral otherwise.
    const pointColor = (k: number) => {
      const t = toneOf(f, rows[k]);
      return t === "warm" ? WARM : t === "cool" ? COOL : UI.text;
    };
    const sel = month - 1;

    return {
      tooltip: {
        ...tooltipStyle,
        trigger: "axis",
        axisPointer: { type: "line", lineStyle: { color: UI.faint } },
        formatter: (ps: any[]) => {
          const k = ps[0].dataIndex;
          const r = rows[k];
          const lines = [`<b>${MONTH_ABBR[k]} ${year}</b> · ${title}`, `${fmtV(vals[k])}`, `normal ${fmtV(norm[k])}`];
          if (r && !r.complete) lines.push(`${r.n_days} days so far`);
          return lines.join("<br/>");
        },
      },
      grid: { left: 34, right: 6, top: 8, bottom: 20 },
      xAxis: {
        type: "category",
        data: MONTH_ABBR.map((m) => m[0]),
        boundaryGap: isRain,
        axisLine: { lineStyle: { color: UI.grid } },
        axisTick: { show: false },
        axisLabel: { color: UI.faint, fontSize: 10, interval: 0 },
      },
      yAxis: {
        type: "value",
        scale: !isRain,
        splitNumber: 3,
        splitLine: { lineStyle: { color: UI.grid } },
        axisLabel: { color: UI.faint, fontSize: 10 },
      },
      series: [
        isRain
          ? {
              name: String(year),
              type: "bar",
              data: vals.map((v, k) => ({ value: v, itemStyle: { color: pointColor(k) === UI.text ? UI.barNeutral : pointColor(k), borderRadius: [3, 3, 0, 0] } })),
              barWidth: "58%",
              markLine: selLine(sel),
            }
          : {
              name: String(year),
              type: "line",
              data: vals.map((v, k) => ({ value: v, itemStyle: { color: pointColor(k) } })),
              connectNulls: false,
              lineStyle: { color: UI.text, width: 2 },
              symbol: "circle",
              symbolSize: (_: unknown, p: any) => (p.dataIndex === sel ? 9 : 5),
              itemStyle: { borderColor: UI.surface, borderWidth: 1.5 },
              z: 5,
              markLine: selLine(sel),
            },
        {
          name: "normal",
          type: "line",
          data: norm,
          lineStyle: { color: UI.muted, width: 1.5, type: "dashed" },
          symbol: "none",
          silent: true,
          z: 4,
        },
      ],
    };
  }, [f, title, unit, year, month, rows, normals]);

  return (
    <figure className="weather-mini">
      <figcaption>
        {title} <span>{unit}</span>
      </figcaption>
      <EChart
      id={`weather-${f}`}
      title={`Weather: ${title}`}
      option={option}
      height={140}
      ariaLabel={`${title} each month of ${year} against the normal`}
      onClick={(p) => typeof p.dataIndex === "number" && onSelectMonth(p.dataIndex + 1)}
      />
    </figure>
  );
}

const selLine = (k: number) => ({
  silent: true,
  symbol: "none",
  label: { show: false },
  lineStyle: { color: UI.faint, width: 1, type: "solid" },
  data: [{ xAxis: k }],
});
