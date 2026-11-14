import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { AnnualChart } from "./charts/AnnualChart";
import { type CalendarMode, CalendarHeatmap } from "./charts/CalendarHeatmap";
import { ClimatologyChart } from "./charts/ClimatologyChart";
import { FireRings } from "./charts/FireRings";
import { INFERNO } from "./lib/colors";
import { CurrentVsMedian } from "./components/CurrentVsMedian";
import { ImportDialog } from "./components/ImportDialog";
import { type DrawMode, type LayerState, MapView } from "./components/MapView";
import { MethodsDrawer } from "./components/MethodsDrawer";
import { SeasonStrip } from "./components/SeasonStrip";
import { AreaPanel, DatePanel, EventsPanel, LayersPanel, PerformancePanel } from "./components/SidePanels";
import { Timeline } from "./components/Timeline";
import { type ExportAction, TopBar } from "./components/TopBar";
import { DEFAULT_METRIC, DEFAULT_SENSOR, DEFAULT_YEARS_BACK, HOTSPOT_EXPORT_LIMIT } from "./config";
import {
  type AreaSeries,
  type DatasetMeta,
  type HotspotRow,
  MONTH_ABBR,
  METRIC_LABEL,
  type Metric,
  SENSOR_LABEL,
  SENSORS,
  type Sensor,
  parseYm,
  unitFor,
  ym,
  ymKey,
  ymMonth,
  ymYear,
} from "./data/contract";
import { type RegionSummary, apiSource, listRegions } from "./data/api";
import type { CellValues, DataSource } from "./data/sources";
import { WorldPicker } from "./components/WorldPicker";
import {
  anomalies,
  annualTotals,
  climatology,
  currentVsMedian,
  documentedEvents,
  fmt,
  fmtPct,
  keyEvents,
  linearTrend,
  seasonMetrics,
  toMonthPoints,
  typicalSeason,
} from "./lib/analytics";
import { toCsv } from "./lib/csv";
import { analyticsCsv, calendarCsv, chartPng, downloadDataUrl, downloadText, slug } from "./lib/exporters";
import { type Area, areaFromBBox, pointInArea } from "./lib/geo";
import { readHash, reloadOnManualHashChange, writeHash } from "./lib/urlState";
import { animationsEnabled, fireCellsEnabled, reducedMotion, setAnimations, setFireCells } from "./lib/motion";

const DEFAULT_LAYERS: LayerState = {
  basemap: "satellite",
  glow: { on: true, opacity: 1 },
  cells: { on: true, opacity: 0.45 },
  heat: { on: false, opacity: 0.75 },
  hotspots: { on: false, opacity: 0.9 },
  extent: { on: true },
  mask: { on: true },
};

export default function App() {
  const initial = useRef(readHash()).current;
  // Regions served by the API (null while loading), plus any files the user loaded.
  const [regions, setRegions] = useState<RegionSummary[] | null>(null);
  const [regionsError, setRegionsError] = useState<string | null>(null);
  const [regionsKey, setRegionsKey] = useState(0);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [sourceId, setSourceId] = useState<string | null>(initial.source ?? null);
  const [meta, setMeta] = useState<DatasetMeta | null>(null);
  const [dsSource, setDsSource] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [areaSeries, setAreaSeries] = useState<AreaSeries | null>(null);
  const [seriesError, setSeriesError] = useState<string | null>(null);
  const [excludePersistent, setExcludePersistent] = useState(false);

  const [area, setArea] = useState<Area | null>(initial.area ?? null);
  const [fitKey, setFitKey] = useState("init");
  const [sensor, setSensor] = useState<Sensor>(initial.sensor ?? DEFAULT_SENSOR);
  const [metric, setMetric] = useState<Metric>(initial.metric ?? DEFAULT_METRIC);
  const [range, setRange] = useState<[number, number] | null>(initial.range ?? null);
  const [selected, setSelected] = useState<number | null>(initial.selected ?? null);
  const [windowMode, setWindowMode] = useState<"month" | "year" | "range">("year");
  const [calendarMode, setCalendarMode] = useState<CalendarMode>("value");
  const [compare, setCompare] = useState(false);
  const [layers, setLayers] = useState<LayerState>(DEFAULT_LAYERS);
  const [drawMode, setDrawMode] = useState<DrawMode>("none");
  const [methodsOpen, setMethodsOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [hotspots, setHotspots] = useState<HotspotRow[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  // Performance switches, remembered between visits.
  const [animations, setAnimationsState] = useState(animationsEnabled);
  const [showData, setShowData] = useState(fireCellsEnabled);
  useEffect(() => setAnimations(animations), [animations]);
  useEffect(() => setFireCells(showData), [showData]);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const firstLoad = useRef(true);
  // Without a shared link the app opens on the world view.
  const [view, setView] = useState<"world" | "dash">(initial.source ? "dash" : "world");

  const source = sources.find((s) => s.id === sourceId);

  // ---- regions on the data server ---------------------------------------
  useEffect(() => {
    let alive = true;
    setRegionsError(null);
    listRegions()
      .then((rs) => {
        if (!alive) return;
        setRegions(rs);
        setSources((prev) => [...rs.map(apiSource), ...prev.filter((p) => p.kind !== "api")]);
      })
      .catch((e) => alive && setRegionsError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [regionsKey]);

  // A shared link to a region the server no longer has: back to the world view.
  useEffect(() => {
    if (regions && sourceId && !source && sourceId.startsWith("api:")) {
      setSourceId(null);
      setView("world");
    }
  }, [regions, sourceId, source]);

  const enterRegion = useCallback((regionId: string) => {
    setSourceId(`api:${regionId}`);
    setView("dash");
  }, []);

  // ---- load the dataset description ---------------------------------------
  useEffect(() => {
    if (!source) return;
    let alive = true;
    setLoading(true);
    setError(null);
    source
      .load()
      .then((m) => {
        if (!alive) return;
        setMeta(m);
        setAreaSeries(null);
        setDsSource(source.id);
        // Files without a harmonized series (e.g. raw FIRMS) open on the first sensor they do have.
        setSensor((cur) => (m.sensor_start[cur] ? cur : (SENSORS.find((s) => m.sensor_start[s]) ?? cur)));
        setMetric((cur) => (m.metrics.includes(cur) ? cur : m.metrics[0]));
        const bounds = metaBounds(m);
        // Keep URL-restored state on first load; reset when the user switches datasets.
        if (!firstLoad.current || !initial.area) setArea(defaultArea(m));
        if (!firstLoad.current || !initial.range) {
          const from = DEFAULT_YEARS_BACK ? Math.max(bounds[0], ym(ymYear(bounds[1]) - DEFAULT_YEARS_BACK + 1, 1)) : bounds[0];
          setRange([from, bounds[1]]);
        }
        if (!firstLoad.current || initial.selected === undefined) setSelected(parseYm(m.last_complete_month));
        firstLoad.current = false;
        setFitKey(`ds-${m.id}-${Date.now()}`);
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, reloadKey]);

  // ---- the area's monthly record (summed by the source) --------------------
  const whole = useMemo(() => (meta ? defaultArea(meta) : null), [meta]);
  const isWhole = !!area && !!whole && area.name === whole.name;
  useEffect(() => {
    if (!source || !meta || !area || dsSource !== source.id) return;
    const ctl = new AbortController();
    setSeriesError(null);
    source
      .areaSeries({ area, whole: isWhole, metric, excludePersistent }, ctl.signal)
      .then((s) => !ctl.signal.aborted && setAreaSeries(s))
      .catch((e) => !ctl.signal.aborted && (e as Error).name !== "AbortError" && setSeriesError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [source, meta, dsSource, area, isWhole, metric, excludePersistent, reloadKey]);

  // ---- derived analytics ----------------------------------------------
  const bounds = useMemo(() => (meta ? metaBounds(meta) : ([0, 0] as [number, number])), [meta]);
  const r: [number, number] = range ?? bounds;
  const sel = Math.max(r[0], Math.min(r[1], selected ?? r[1]));
  const unit = unitFor(sensor, metric);
  const cellCount = areaSeries?.nCells ?? 0;

  const seriesBy = useMemo(() => {
    if (!areaSeries) return null;
    const out = {} as Record<Sensor, ReturnType<typeof toMonthPoints>>;
    for (const s of SENSORS) out[s] = toMonthPoints(areaSeries, s, r);
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [areaSeries, r[0], r[1]]);

  const a = useMemo(() => {
    if (!seriesBy) return null;
    const series = seriesBy[sensor];
    const clim = climatology(series);
    const anoms = anomalies(series, clim);
    const totalsBy = Object.fromEntries(SENSORS.map((s) => [s, annualTotals(seriesBy[s])])) as Record<Sensor, ReturnType<typeof annualTotals>>;
    const totals = totalsBy[sensor];
    const trend = linearTrend(totals);
    const seasons = seasonMetrics(series);
    const events = keyEvents(series, anoms, totals, clim, sensor, unit);
    const covered = series.filter((p) => p.value !== null && !p.partial);
    const total = covered.reduce((s, p) => s + p.value!, 0);
    const completeYears = totals.filter((t) => t.complete);
    return { series, clim, anoms, totalsBy, totals, trend, seasons, events, total, completeYears };
  }, [seriesBy, sensor, unit]);

  const cvm = useMemo(() => (a ? currentVsMedian(a.series, sel) : null), [a, sel]);

  // Documented events near the area and in range, plus a lookup for chart annotations.
  const documented = useMemo(() => (meta && area && a ? documentedEvents(meta.events, area, r, a.anoms) : []), [meta, area, a, r[0], r[1]]); // eslint-disable-line react-hooks/exhaustive-deps
  const eventMarks = useMemo(() => {
    const byMonth = new Map<number, string>();
    for (const e of meta?.events ?? []) if (documented.some((d) => d.i === parseYm(e.from))) byMonth.set(parseYm(e.from), e.short ?? e.label);
    return byMonth;
  }, [meta, documented]);
  const [activeEvent, setActiveEvent] = useState<string | undefined>();
  const [focus, setFocus] = useState<{ lat: number; lon: number; radius: number; key: string } | null>(null);

  const win: [number, number] = useMemo(() => {
    if (windowMode === "month") return [sel, sel];
    if (windowMode === "year") return [Math.max(r[0], ym(ymYear(sel), 1)), Math.min(r[1], ym(ymYear(sel), 12))];
    return r;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [windowMode, sel, r[0], r[1]]);
  const windowLabel =
    windowMode === "month" ? `${MONTH_ABBR[ymMonth(sel) - 1]} ${ymYear(sel)}` : windowMode === "year" ? String(ymYear(sel)) : `${ymYear(r[0])}–${ymYear(r[1])}`;

  // Per-cell values for the map window (the API reads them from the compact per-year series).
  const [cells, setCells] = useState<CellValues>(new Map());
  useEffect(() => {
    if (!source || !meta || dsSource !== source.id) return;
    let alive = true;
    source
      .cellWindow({ sensor, metric, from: win[0], to: win[1], excludePersistent })
      .then((c) => alive && setCells(c))
      .catch((e) => alive && flash(`Map data failed: ${e instanceof Error ? e.message : String(e)}`));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, meta, dsSource, sensor, metric, win[0], win[1], excludePersistent]);

  // What the map is showing, in words: estimates must never pass for detections (data contract).
  const mapNote = useMemo(() => {
    if (!areaSeries) return undefined;
    const ms = areaSeries.months.filter((m) => m.i >= win[0] && m.i <= win[1] && m.values[sensor] !== null);
    if (sensor === "modis_raw") return "MODIS fire-days: MODIS's own scale (3–6× fewer than VIIRS), not comparable with harmonized or VIIRS values";
    if (sensor !== "harmonized" || !ms.length) return undefined;
    const est = ms.filter((m) => m.estimate);
    const low = est.some((m) => m.lowConfidence) ? " · low confidence" : "";
    if (est.length === ms.length) return `Modelled estimate from MODIS (not detections)${low}`;
    if (est.length) return `Includes modelled months before ${meta?.splice_date?.slice(0, 7) ?? "2012"} (not detections)${low}`;
    return undefined;
  }, [areaSeries, win, sensor, meta]);

  // Individual detections (imported FIRMS files only): drawn as points / true pixel footprints,
  // and aggregated into the ~1 km grid. Harmonized view shows both raw sensors.
  const [resolution, setResolution] = useState<"grid" | "1km">("grid");
  const [detectionsCapped, setDetectionsCapped] = useState(false);
  const hasDetections = !!source?.hotspots;
  useEffect(() => {
    if ((!layers.hotspots.on && resolution === "grid") || !meta || !area || !source?.hotspots) {
      setHotspots([]);
      return;
    }
    let alive = true;
    source.hotspots(win, area.bbox, DETECTION_LIMIT).then((h) => {
      if (!alive) return;
      setDetectionsCapped(h.length >= DETECTION_LIMIT);
      const instruments = sensor === "harmonized" ? ["MODIS", "VIIRS"] : [sensor === "modis_raw" ? "MODIS" : "VIIRS"];
      setHotspots(h.filter((p) => instruments.includes(p.instrument) && pointInArea(p.longitude, p.latitude, area)));
    });
    return () => {
      alive = false;
    };
  }, [layers.hotspots.on, resolution, meta, area, sensor, win, source]);
  useEffect(() => {
    if (!hasDetections) setResolution("grid");
  }, [hasDetections]);

  const fineCells = useMemo(() => (resolution === "1km" ? detectionGrid(hotspots, FINE_GRID, metric) : null), [resolution, hotspots, metric]);

  // Sections fade up as they scroll into view.
  useEffect(() => {
    if (view !== "dash" || !meta || !animations || !("IntersectionObserver" in window)) return;
    const main = document.querySelector(".main");
    if (!main) return;
    main.classList.add("reveal");
    const io = new IntersectionObserver((entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("in")), { rootMargin: "0px 0px -8% 0px" });
    [...main.children].forEach((c) => io.observe(c));
    return () => {
      io.disconnect();
      main.classList.remove("reveal");
    };
  }, [view, meta, dsSource, sourceId, animations, !!areaSeries]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- URL sync --------------------------------------------------------
  useEffect(reloadOnManualHashChange, []);
  useEffect(() => {
    // Skip while a newly picked dataset is still loading, so the URL never mixes two datasets.
    // Imported files only live in this browser, so they are not put in the link.
    if (view !== "dash" || !meta || !area || !range || !sourceId || dsSource !== sourceId || !sourceId.startsWith("api:")) return;
    writeHash({ source: sourceId, sensor, metric, area, areaAll: isWhole, range, selected: sel });
  }, [view, meta, dsSource, sourceId, sensor, metric, area, isWhole, range, sel]);

  // ---- actions ---------------------------------------------------------
  const flash = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2600);
  }, []);

  const onArea = useCallback((next: Area) => {
    setArea(next);
    setFitKey(`area-${Date.now()}`);
  }, []);

  const selectYear = useCallback(
    (y: number) => {
      const m = selected !== null ? ymMonth(selected) : 1;
      setSelected(Math.max(r[0], Math.min(r[1], ym(y, m))));
      setWindowMode("year");
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selected, r[0], r[1]],
  );

  const header = () => ({
    dataset: meta?.name ?? "",
    release: meta?.generated_at ? `export generated ${meta.generated_at}` : "",
    area: area ? `${area.name} [${area.bbox.map((v) => v.toFixed(3)).join(", ")}]` : "",
    sensor: SENSOR_LABEL[sensor],
    metric: `${METRIC_LABEL[metric]} (${unit})`,
    range: `${ymKey(r[0])} to ${ymKey(r[1])}`,
    persistent_sources: excludePersistent ? "excluded" : "included",
    estimates: meta?.estimate_until ? `harmonized values up to ${meta.estimate_until} are modelled from MODIS, not detections` : "",
    exported: new Date().toISOString(),
  });
  const base = () => `wel3a_${slug(meta?.id ?? "data")}_${slug(area?.name ?? "area")}_${ymKey(r[0])}_${ymKey(r[1])}`;

  const exportsList: ExportAction[] = [
    {
      id: "hotspots",
      label: "Hotspots CSV",
      hint: source?.hotspots ? `FIRMS-style rows in area & range (max ${HOTSPOT_EXPORT_LIMIT.toLocaleString()})` : "Only for loaded FIRMS files (the server stores fire-days, not detections)",
      disabled: !source?.hotspots,
      run: async () => {
        if (!meta || !area || !source?.hotspots) return;
        const h = (await source.hotspots(r, area.bbox, HOTSPOT_EXPORT_LIMIT)).filter((p) => pointInArea(p.longitude, p.latitude, area));
        h.sort((p, q) => p.acq_date.localeCompare(q.acq_date));
        downloadText(`${base()}_hotspots.csv`, toCsv(h));
        flash(`${h.length.toLocaleString()} hotspots exported${h.length >= HOTSPOT_EXPORT_LIMIT ? " (limit reached)" : ""}`);
      },
    },
    {
      id: "calendar",
      label: "Calendar CSV",
      hint: "Month × year values, coverage and anomalies",
      run: () => {
        if (!a) return;
        downloadText(`${base()}_calendar.csv`, calendarCsv(a.anoms, header()));
        flash("Calendar exported");
      },
    },
    {
      id: "analytics",
      label: "Analytics CSV",
      hint: "Climatology, annual totals, season metrics",
      run: () => {
        if (!a) return;
        downloadText(`${base()}_analytics.csv`, analyticsCsv(a.clim, a.totals, a.seasons, header()));
        flash("Analytics exported");
      },
    },
    {
      id: "charts",
      label: "Charts PNG",
      hint: "Every chart as a separate image",
      run: () => {
        chartPng();
        flash("Charts saved as PNG");
      },
    },
    {
      id: "map",
      label: "Map PNG",
      hint: "Current map view",
      run: () => {
        const m = mapRef.current;
        if (!m) return;
        downloadDataUrl(`${base()}_map.png`, m.getCanvas().toDataURL("image/png"));
        flash("Map saved as PNG");
      },
    },
  ];

  // ---- render ----------------------------------------------------------
  if (view === "world" || !sourceId)
    return (
      <WorldPicker
        regions={regions}
        error={regionsError}
        onRetry={() => setRegionsKey((k) => k + 1)}
        onEnter={enterRegion}
        current={sourceId?.startsWith("api:") ? sourceId.slice(4) : undefined}
      />
    );

  const failure = error ?? (meta && dsSource === sourceId ? seriesError : null) ?? (!source && regionsError ? regionsError : null);
  if (!meta || !area || !a || dsSource !== sourceId || failure) {
    return (
      <div className="boot">
        <div className="boot-orb" aria-hidden>
          <img src="./emblem.png" alt="" width={72} height={72} />
        </div>
        {failure ? (
          <>
            <p className="warn">Could not load data: {failure}</p>
            <div className="boot-actions">
              <button
                className="btn btn-primary"
                onClick={() => {
                  setError(null);
                  setSeriesError(null);
                  if (!source) setRegionsKey((k) => k + 1);
                  else setReloadKey((k) => k + 1);
                }}
              >
                Try again
              </button>
              <button className="btn btn-ghost" onClick={() => setView("world")}>
                Back to the world map
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="boot-title">Loading the fire record{source ? ` for ${source.label}` : ""}</p>
            <p className="muted small">Reading the harmonized calendar from the data server</p>
          </>
        )}
      </div>
    );
  }

  const viirsStart = meta.sensor_start.viirs_raw ? ymYear(parseYm(meta.sensor_start.viirs_raw)) : undefined;
  const peakMonth = a.clim.reduce((p, c) => (Number.isFinite(c.median) && c.median > (p?.median ?? -1) ? c : p), a.clim[0]);
  const record = a.completeYears.length ? a.completeYears.reduce((p, c) => (c.total > p.total ? c : p)) : null;
  const selYearSeries = a.series.filter((p) => p.year === ymYear(sel));
  const coveredFrom = a.series.find((p) => p.value !== null)?.year;

  return (
    <div className="app">
      <TopBar
        sources={sources}
        sourceId={sourceId}
        onSource={setSourceId}
        onImport={() => setImportOpen(true)}
        sensor={sensor}
        onSensor={setSensor}
        metric={metric}
        metrics={meta.metrics}
        onMetric={setMetric}
        exports={exportsList}
        onMethods={() => setMethodsOpen(true)}
        onWorld={() => setView("world")}
      />

      <div className="layout">
        <button className="filters-bar" aria-expanded={filtersOpen} aria-controls="filters" onClick={() => setFiltersOpen(!filtersOpen)}>
          <span>
            <b>{area.name}</b>
            <small>
              {ymKey(r[0])} → {ymKey(r[1])} · {SENSOR_LABEL[sensor]}
            </small>
          </span>
          <span className="filters-bar-action">{filtersOpen ? "Hide filters" : "Edit filters"}</span>
        </button>
        <aside id="filters" className={`sidebar${filtersOpen ? " is-open" : ""}`} aria-label="Filters">
          <PerformancePanel animations={animations} onAnimations={setAnimationsState} showData={showData} onShowData={setShowData} />
          <AreaPanel
            meta={meta}
            whole={whole!}
            area={area}
            cellCount={cellCount}
            onArea={onArea}
            drawMode={drawMode}
            setDrawMode={setDrawMode}
            excludePersistent={excludePersistent}
            onExcludePersistent={setExcludePersistent}
          />
          <DatePanel meta={meta} range={r} onRange={setRange} bounds={bounds} />
          <EventsPanel
            documented={documented}
            activeId={activeEvent}
            // Spikes that are already explained by a documented event are not listed twice.
            events={a.events.filter((e) => !(e.id.startsWith("anom-") && documented.some((d) => d.i === e.i)))}
            onJump={(e) => {
              if (e.i === undefined) return;
              setSelected(e.i);
              setWindowMode(e.year !== undefined ? "year" : "month");
              setActiveEvent(e.id);
              setFocus(e.loc ? { ...e.loc, key: `${e.id}-${Date.now()}` } : null);
            }}
          />
          <LayersPanel layers={layers} setLayers={setLayers} detections={hasDetections} />
        </aside>

        <main className="main">
          {sensor !== "harmonized" && (
            <div className="banner">
              <b>Raw {SENSOR_LABEL[sensor].replace(" raw", "")} view.</b>{" "}
              {sensor === "viirs_raw"
                ? `VIIRS starts in ${meta.sensor_start.viirs_raw ?? "2012"} and detects many more, smaller fires, so it has no record before then.`
                : "MODIS sees roughly 3–6× fewer fire-days than VIIRS for the same activity, so its values use their own scale. Switch to Harmonized for one consistent record."}{" "}
              <button className="link" onClick={() => setSensor("harmonized")}>
                Show harmonized
              </button>
            </div>
          )}
          {sensor === "harmonized" && meta.estimate_until && r[0] <= parseYm(meta.estimate_until) && (
            <div className="banner banner-soft">
              <b>Before {meta.splice_date?.slice(0, 7) ?? "2012"}, values are modelled estimates.</b> They are converted from MODIS, not VIIRS detections
              {a.series.some((p) => p.lowConfidence) ? ", and months marked low confidence should be read with extra caution" : ""}.
            </div>
          )}

          <section className="hero stage">
            <div className="card map-card">
              <MapView
                area={area}
                extent={meta.bbox}
                gridDeg={fineCells ? FINE_GRID : meta.grid_deg}
                cells={fineCells ?? cells}
                resolution={resolution}
                onResolution={setResolution}
                detections={hasDetections}
                gridLabel={`${meta.grid_deg}° (~${Math.round(meta.grid_deg * 111)} km)`}
                note={
                  fineCells
                    ? `~1 km cells from individual ${sensor === "harmonized" ? "MODIS + VIIRS" : SENSOR_LABEL[sensor]} detections (not calibrated)${detectionsCapped ? ` · first ${DETECTION_LIMIT.toLocaleString()} detections` : ""}`
                    : mapNote
                }
                hotspots={hotspots}
                outline={meta.outline}
                focus={focus}
                areaIsRegion={isWhole}
                layers={layers}
                showData={showData}
                animate={animations}
                unit={unit}
                windowLabel={windowLabel}
                drawMode={drawMode}
                setDrawMode={setDrawMode}
                onArea={onArea}
                fitKey={fitKey}
                mapRef={mapRef}
              />
              <Timeline series={a.series} selected={sel} onSelect={setSelected} windowMode={windowMode} setWindowMode={setWindowMode} unit={unit} />
            </div>
            <div className="stage-title glass">
              <RegionHero
                name={meta.name}
                areaName={area.name}
                blurb={source?.description}
                sensor={SENSOR_LABEL[sensor]}
                years={`${coveredFrom ?? ymYear(r[0])}–${ymYear(r[1])}`}
                grid={meta.grid_deg}
                cells={cellCount}
                season={typicalSeason(a.seasons)}
                peakMonth={peakMonth && Number.isFinite(peakMonth.median) ? peakMonth.month : undefined}
                record={record?.year}
                trend={a.trend?.pctPerDecade}
                localName={meta.local_name}
              />
            </div>
            <div className="card cvm-card glass">
              <CardHead title="This month vs normal" subtitle={`${SENSOR_LABEL[sensor]} · ${METRIC_LABEL[metric]}`} />
              <CurrentVsMedian
                cvm={cvm}
                series={a.series}
                selected={sel}
                unit={unit}
                onStep={(d) => setSelected(Math.max(r[0], Math.min(r[1], sel + d)))}
                onLatest={() => setSelected(Math.min(r[1], parseYm(meta.last_month)))}
              />
            </div>
          </section>

          <section className="kpis" aria-label="Summary">
            <Kpi
              label={`Total ${unit}`}
              value={fmt(a.total)}
              num={a.total}
              sub={`${coveredFrom ?? ymYear(r[0])}–${ymYear(r[1])} · ${SENSOR_LABEL[sensor]}`}
              spark={{ values: a.totals.map((t) => (t.coveredMonths ? t.total : 0)), highlight: a.totals.findIndex((t) => t.year === ymYear(sel)) }}
            />
            <Kpi label="Average per year" value={fmt(a.completeYears.length ? a.completeYears.reduce((s, t) => s + t.total, 0) / a.completeYears.length : NaN)} sub={`${a.completeYears.length} complete years`} />
            <Kpi
              label="Peak month"
              value={peakMonth && Number.isFinite(peakMonth.median) ? MONTH_ABBR[peakMonth.month - 1] : "–"}
              sub={peakMonth ? `median ${fmt(peakMonth.median)} ${unit}` : ""}
              spark={{ values: a.clim.map((c) => (Number.isFinite(c.median) ? c.median : 0)), highlight: peakMonth ? peakMonth.month - 1 : -1 }}
            />
            <Kpi
              label="Record year"
              value={record ? String(record.year) : "–"}
              sub={record ? `${fmt(record.total)} ${unit}` : ""}
              spark={{ values: a.totals.map((t) => (t.coveredMonths ? t.total : 0)), highlight: record ? a.totals.findIndex((t) => t.year === record.year) : -1 }}
            />
            <Kpi
              label="Trend"
              value={a.trend ? `${fmtPct(a.trend.pctPerDecade)}` : "–"}
              sub={a.trend ? `per decade, ${a.trend.from}–${a.trend.to}` : "needs 3+ complete years"}
              tone={a.trend ? (a.trend.pctPerDecade > 5 ? "warm" : a.trend.pctPerDecade < -5 ? "cool" : undefined) : undefined}
            />
          </section>

          <section className="card rings-card">
            <FireRings
              cells={a.anoms}
              unit={unit}
              selected={sel}
              onSelect={(i) => {
                setSelected(i);
                setWindowMode("month");
              }}
              events={eventMarks}
              markerYear={sensor !== "modis_raw" ? viirsStart : undefined}
              markerLabel="VIIRS joins"
            />
            <div className="rings-aside">
              <span className="eyebrow">Signature view</span>
              <h2>Fire rings</h2>
              <p className="rings-lede">
                {meta.name}'s fire record, read like the rings of a tree. Each ring is a year, starting from <b>{coveredFrom ?? ymYear(r[0])}</b> at the core. A{" "}
                <b>thicker ring</b> is a year with more fire, and the twelve sectors are the months, coloured by activity.
              </p>
              <div className="rings-try">
                <span className="field-label">See what harmonizing does</span>
                <div className="seg seg-full sensor-seg" role="radiogroup" aria-label="Sensor for the rings">
                  {SENSORS.filter((s) => meta.sensor_start[s]).map((s) => (
                    <button key={s} role="radio" aria-checked={sensor === s} className={sensor === s ? "is-on" : ""} onClick={() => setSensor(s)}>
                      {SENSOR_LABEL[s]}
                    </button>
                  ))}
                </div>
                <p className="rings-note">
                  {sensor === "viirs_raw"
                    ? "Raw VIIRS: the rings only start in 2012 and are swollen, because VIIRS sees many more small fires."
                    : sensor === "modis_raw"
                      ? "Raw MODIS: one sensor all the way through, but it misses many small fires, so its rings are thin and on their own scale."
                      : "Harmonized: one VIIRS-equivalent scale throughout (modelled from MODIS before 2012), so ring thickness means fire, not which satellite was looking."}
                </p>
              </div>
              <ul className="rings-key">
                <li>
                  <span className="rk rk-ramp" style={{ background: `linear-gradient(90deg, ${INFERNO.join(",")})` }} /> quiet month → intense month
                </li>
                <li>
                  <span className="rk rk-ember" /> documented fire
                </li>
                <li>
                  <span className="rk rk-dash" /> a new sensor joins
                </li>
              </ul>
              <p className="muted small">Hover a month to read it, click to select it. Arrow keys move through time.</p>
            </div>
          </section>

          <section className="card">
            <CardHead
              title="Burning calendar"
              subtitle={
                calendarMode === "value"
                  ? `${METRIC_LABEL[metric]} per month · ${SENSOR_LABEL[sensor]} · click a cell to select it`
                  : "Each month vs its own historical median (z-score) · blue = quieter, red = more active"
              }
              actions={
                <>
                  <div className="seg seg-sm" role="radiogroup" aria-label="Calendar colouring">
                    <button role="radio" aria-checked={calendarMode === "value"} className={calendarMode === "value" ? "is-on" : ""} onClick={() => setCalendarMode("value")}>
                      Values
                    </button>
                    <button role="radio" aria-checked={calendarMode === "anomaly"} className={calendarMode === "anomaly" ? "is-on" : ""} onClick={() => setCalendarMode("anomaly")}>
                      Anomaly
                    </button>
                  </div>
                  <PngButton id="calendar" />
                </>
              }
            />
            <CalendarHeatmap
              cells={a.anoms}
              mode={calendarMode}
              unit={unit}
              selected={sel}
              onSelect={(i) => {
                setSelected(i);
                setWindowMode("month");
              }}
              markers={sensor !== "modis_raw" && viirsStart ? [{ year: viirsStart, label: "VIIRS" }] : []}
              events={eventMarks}
            />
            <p className="legend-line">
              <span className="lg lg-hatch" /> no data (not zero) <span className="lg lg-dash" /> partial year, not in medians
              {a.series.some((p) => p.lowConfidence) && (
                <>
                  <span className="lg lg-dots" /> low-confidence estimate
                </>
              )}
              <span className="lg lg-sel" /> selected
            </p>
          </section>

          <div className="grid-2">
            <section className="card">
              <CardHead
                title="Typical year"
                subtitle={`Median and spread per month · line = ${ymYear(sel)} · not a forecast`}
                actions={<PngButton id="climatology" />}
              />
              <ClimatologyChart clim={a.clim} year={ymYear(sel)} yearSeries={selYearSeries} unit={unit} onSelectMonth={(m) => setSelected(Math.max(r[0], Math.min(r[1], ym(ymYear(sel), m))))} />
            </section>
            <section className="card">
              <CardHead
                title="Annual totals"
                subtitle={compare ? "Raw sensors vs harmonized: the 2012 jump is the sensor, not the fires" : `${SENSOR_LABEL[sensor]} per year · dashed = trend`}
                actions={
                  <>
                    <label className="toggle toggle-sm">
                      <input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} />
                      <span className="toggle-ui" aria-hidden />
                      <span className="toggle-text">Compare sensors</span>
                    </label>
                    <PngButton id="annual" />
                  </>
                }
              />
              <AnnualChart totals={a.totalsBy} sensor={sensor} compare={compare} unit={unit} selectedYear={ymYear(sel)} viirsStartYear={viirsStart} events={eventMarks} onSelectYear={selectYear} />
            </section>
          </div>

          <section className="card">
            <CardHead title="Fire season by year" subtitle="When each year's season started, peaked and ended · click a year to select it" />
            <SeasonStrip peakMonth={peakMonth && Number.isFinite(peakMonth.median) ? peakMonth.month : undefined} seasons={a.seasons} selectedYear={ymYear(sel)} unit={unit} onSelectYear={selectYear} />
          </section>

          <footer className="foot">
            <span>
              Source data: NASA FIRMS (MODIS, VIIRS 375 m), harmonized by the Wel3a pipeline{meta.generated_at ? ` (export of ${meta.generated_at.slice(0, 10)})` : ""}. Fire-days measure
              burning activity, not burned area or individual fires.
            </span>
            <button className="link" onClick={() => setMethodsOpen(true)}>
              Methods &amp; limitations
            </button>
          </footer>
        </main>
      </div>

      <MethodsDrawer open={methodsOpen} onClose={() => setMethodsOpen(false)} meta={meta} sourceLabel={source?.label ?? ""} />
      <ImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onLoad={(src) => {
          setSources((prev) => [src, ...prev.filter((p) => p.id !== src.id)]);
          setSourceId(src.id);
          flash(`Loaded ${src.label}`);
        }}
      />
      {loading && <div className="loading-bar" aria-hidden />}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

/** The whole region ("All of Lebanon"): every cell of the dataset. */
export function defaultArea(m: DatasetMeta): Area {
  return areaFromBBox(`All of ${m.name}`, m.bbox);
}

/** ~1 km (0.01°) grid for the precise map view. */
const FINE_GRID = 0.01;
const DETECTION_LIMIT = 60_000;

/**
 * Aggregates detections onto a fine grid with the same metrics as the contract:
 * active cell-days (a cell counts once per day), detections, or summed FRP.
 */
function detectionGrid(hs: HotspotRow[], g: number, metric: Metric) {
  const cells = new Map<string, { lat: number; lon: number; value: number }>();
  const days = new Set<string>();
  for (const h of hs) {
    const iy = Math.floor(h.latitude / g + 1e-9);
    const ix = Math.floor(h.longitude / g + 1e-9);
    const id = `${iy}_${ix}`;
    const c = cells.get(id) ?? { lat: +((iy + 0.5) * g).toFixed(4), lon: +((ix + 0.5) * g).toFixed(4), value: 0 };
    if (metric === "fire_count") c.value += 1;
    else if (metric === "sum_frp") c.value += h.frp;
    else if (!days.has(`${id}|${h.acq_date}`)) {
      days.add(`${id}|${h.acq_date}`);
      c.value += 1;
    }
    cells.set(id, c);
  }
  return cells;
}

/** First month with any data to the last month with data (a partial year is included and flagged). */
function metaBounds(m: DatasetMeta): [number, number] {
  const starts = Object.values(m.sensor_start).filter(Boolean).map((s) => parseYm(s!));
  const first = starts.length ? Math.min(...starts) : ym(m.first_year, 1);
  return [first, parseYm(m.last_month)];
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
function RegionHero(p: HeroProps) {
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
function CountUp({ value }: { value: number }) {
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

function Kpi({ label, value, num, sub, tone, spark }: { label: string; value: string; num?: number; sub?: string; tone?: string; spark?: { values: number[]; highlight?: number } }) {
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
function MiniBars({ values, highlight = -1 }: { values: number[]; highlight?: number }) {
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

function CardHead({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
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

function PngButton({ id }: { id: string }) {
  return (
    <button className="icon-btn" title="Download PNG" aria-label="Download chart as PNG" onClick={() => chartPng(id)}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
        <path d="M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M3 13h10" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}
