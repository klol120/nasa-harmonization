import { useEffect, useRef, useState } from "react";
import { MONTH_ABBR } from "../data/contract";
import { fmt, type typicalSeason } from "../lib/analytics";
import { chartPng } from "../lib/exporters";
import { reducedMotion } from "../lib/motion";

/** Title block at the top of a region page. */
export function PageHead({ eyebrow, title, lede, actions }: { eyebrow: string; title: string; lede?: React.ReactNode; actions?: React.ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {lede && <p className="page-lede">{lede}</p>}
      </div>
      {actions && <div className="page-head-actions">{actions}</div>}
    </header>
  );
}

interface HeroProps {
  name: string;
  areaName: string;
  blurb?: string;
  sensor: string;
  years: string;
  grid: number;
  cells: number;
  season: ReturnType<typeof typicalSeason>;
  /** Month with the highest median activity (same as the Peak month tile). */
  peakMonth?: number;
  record?: number;
  trend?: number;
  /** Name in the local script, shown as a watermark. */
  localName?: string;
}

/** Region title plus a one-line, plain-language reading of the record. */
export function RegionHero(p: HeroProps) {
  const sub = p.areaName.startsWith("All of") ? null : p.areaName;
  return (
    <section className="region-hero">
      {p.localName && (
        <span className="region-hero-mark" lang="ar" aria-hidden>
          {p.localName}
        </span>
      )}
      <div className="region-hero-text">
        <span className="eyebrow">
          {p.sensor} burning record · {p.years}
        </span>
        <h1>
          {p.name}
          {sub && <span className="region-hero-sub"> / {sub}</span>}
        </h1>
        {p.season ? (
          <p className="region-hero-story">
            Fire season usually runs <b>{MONTH_ABBR[p.season.start - 1]}</b> → <b>{MONTH_ABBR[p.season.end - 1]}</b> and peaks in{" "}
            <b>{MONTH_ABBR[(p.peakMonth ?? p.season.peak) - 1]}</b>.{p.record ? <> The most active year on record is <b>{p.record}</b>.</> : null}
            {p.trend !== undefined && Math.abs(p.trend) >= 5 ? (
              <>
                {" "}
                Activity is {p.trend > 0 ? "rising" : "falling"} by about <b>{Math.abs(Math.round(p.trend))}%</b> per decade.
              </>
            ) : null}
          </p>
        ) : (
          <p className="region-hero-story">Not enough complete years in this selection to describe a typical season.</p>
        )}
        {p.blurb && <p className="region-hero-blurb">{p.blurb}</p>}
      </div>
      <dl className="region-hero-facts">
        <div>
          <dt>Grid</dt>
          <dd>{p.grid}°</dd>
        </div>
        <div>
          <dt>Cells</dt>
          <dd>{p.cells}</dd>
        </div>
      </dl>
    </section>
  );
}

/** Number that counts up (or down) to its new value. */
export function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const a = from.current;
    if (a === value || reducedMotion()) return setShown(value);
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const x = Math.min(1, (now - start) / 900);
      const v = a + (value - a) * (1 - (1 - x) ** 3);
      from.current = v;
      setShown(v);
      if (x < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    // Hidden tabs get no frames: still land on the value.
    const settle = window.setTimeout(() => {
      from.current = value;
      setShown(value);
    }, 1300);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [value]);
  return <>{fmt(shown)}</>;
}

export function Kpi({ label, value, num, sub, tone, spark }: { label: string; value: string; num?: number; sub?: string; tone?: string; spark?: { values: number[]; highlight?: number } }) {
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className={`kpi-value${tone ? ` tone-${tone}` : ""}`}>{num !== undefined && Number.isFinite(num) ? <CountUp value={num} /> : value}</span>
      {sub && <span className="kpi-sub">{sub}</span>}
      {spark && spark.values.length > 1 && <MiniBars {...spark} />}
    </div>
  );
}

/** Tiny bar strip for KPI tiles; the highlighted bar is drawn in the bright end of the ramp. */
export function MiniBars({ values, highlight = -1 }: { values: number[]; highlight?: number }) {
  const max = Math.max(1e-9, ...values);
  const w = 100 / values.length;
  return (
    <svg className="kpi-spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden>
      {values.map((v, k) => {
        const h = Math.max(0.8, (v / max) * 24);
        return <rect key={k} x={k * w + w * 0.15} y={24 - h} width={w * 0.7} height={h} rx={0.6} className={k === highlight ? "is-hl" : ""} />;
      })}
    </svg>
  );
}

export function CardHead({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <header className="card-head">
      <div>
        <h3>{title}</h3>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="card-actions">{actions}</div>}
    </header>
  );
}

export function PngButton({ id }: { id: string }) {
  return (
    <button className="icon-btn" title="Download PNG" aria-label="Download chart as PNG" onClick={() => chartPng(id)}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
        <path d="M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M3 13h10" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
