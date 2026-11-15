import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type maplibregl from "maplibre-gl";
import { AnnualChart } from "./charts/AnnualChart";
import { type CalendarMode, CalendarHeatmap } from "./charts/CalendarHeatmap";
import { ClimatologyChart } from "./charts/ClimatologyChart";
import { FireRings } from "./charts/FireRings";
import { INFERNO } from "./lib/colors";
import { CardHead, Kpi, PageHead, PngButton, RegionHero } from "./components/Blocks";
import { CurrentVsMedian } from "./components/CurrentVsMedian";
import { type DrawMode, type LayerState, MapView } from "./components/MapView";
import { MethodsPage } from "./components/MethodsPage";
import { SeasonStrip } from "./components/SeasonStrip";
import { AreaPanel, DatePanel, EventsPanel, LayersPanel, PerformancePanel } from "./components/SidePanels";
import { AppSidebar, type ExportAction, type FilterTab, PAGE_LABEL, RegionCard, TopBar } from "./components/Shell";
import { type Command, CommandPalette, MOD_KEY } from "./components/CommandPalette";
import { YearCompare } from "./charts/YearCompare";
import { Timeline } from "./components/Timeline";
import { DEFAULT_METRIC, DEFAULT_SENSOR, DEFAULT_YEARS_BACK, REGION_INFO } from "./config";
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
import { type RegionForecast, type RegionSummary, type RegionWeather, apiSource, getForecast, getWeather, listRegions } from "./data/api";
import { ForecastPage } from "./components/ForecastPage";
import { WeatherCard } from "./components/WeatherCard";
import type { CellValues, DataSource } from "./data/sources";
import { WorldPicker } from "./components/WorldPicker";
import { AccountMenu } from "./account/AccountMenu";
import { MyAreasPanel } from "./account/MyAreasPanel";
import { NewsletterForm } from "./account/NewsletterForm";
import { SignInDialog } from "./account/SignInDialog";
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
  robustMax,
  seasonMetrics,
  toMonthPoints,
  typicalSeason,
} from "./lib/analytics";
import { analyticsCsv, calendarCsv, chartPng, downloadDataUrl, downloadText, slug } from "./lib/exporters";
import { type Area, areaFromBBox, pointInArea } from "./lib/geo";
import { PAGES, type Page, pageHref, pushPage, readHash, watchHash, writeHash } from "./lib/urlState";
import { animationsEnabled, fireCellsEnabled, setAnimations, setFireCells } from "./lib/motion";
import { useTheme } from "./lib/theme";

const DEFAULT_LAYERS: LayerState = {
  basemap: "satellite",
  glow: { on: true, opacity: 1 },
  cells: { on: true, opacity: 0.45 },
  heat: { on: false, opacity: 0.75 },
  hotspots: { on: false, opacity: 0.9 },
  extent: { on: true },
  mask: { on: true },
};

/** Pages with the filters sidebar (area, dates, events). The forecast covers the whole region, so it has none. */
const SIDEBAR_PAGES: Page[] = ["overview", "calendar", "trends", "weather"];
/** Pages that draw ECharts (their charts can be exported as PNG). */
const CHART_PAGES: Page[] = ["calendar", "trends", "forecast", "weather"];

export default function App() {
  const initial = useRef(readHash()).current;
  // Regions served by the API (null while loading). The pipeline is the only data source.
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
  const [hotspots, setHotspots] = useState<HotspotRow[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  // Sidebar: collapsed to an icon rail (remembered), and open as a drawer on phones.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => readPref("wel3a.sidebar") === "collapsed");
  const [mobileNav, setMobileNav] = useState(false);
  useEffect(() => savePref("wel3a.sidebar", sidebarCollapsed ? "collapsed" : "open"), [sidebarCollapsed]);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // What the global shortcuts act on; refreshed every render so the listener never goes stale.
  const keys = useRef<{ step?: (months: number) => void }>({});
  useEffect(() => {
    const typing = (t: EventTarget | null) => t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName));
    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
        return;
      }
      if (mod && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setSidebarCollapsed((c) => !c);
        return;
      }
      if (e.key === "Escape") setMobileNav(false);
      // Arrows step through time, unless something else already used the key (rings, map, inputs).
      if (e.defaultPrevented || mod || e.altKey || typing(e.target)) return;
      if (e.target instanceof Element && e.target.closest(".maplibregl-map, [role=dialog]")) return;
      if (e.key === "/" && !e.shiftKey) {
        e.preventDefault();
        setPaletteOpen(true);
      } else if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && keys.current.step) {
        e.preventDefault();
        keys.current.step((e.key === "ArrowLeft" ? -1 : 1) * (e.shiftKey ? 12 : 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  // Performance switches, remembered between visits.
  const [animations, setAnimationsState] = useState(animationsEnabled);
  const [showData, setShowData] = useState(fireCellsEnabled);
  useEffect(() => setAnimations(animations), [animations]);
  useEffect(() => setFireCells(showData), [showData]);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const firstLoad = useRef(true);
  const [theme, setTheme, themeChoice] = useTheme();

  // Which page is showing. Without a shared link the site opens on the world map.
  const [page, setPage] = useState<Page>(() => (initial.source ? (initial.page ?? "overview") : "explore"));
  const navigate = useCallback((p: Page) => {
    setPage(p);
    pushPage(p);
    setMobileNav(false);
    window.scrollTo({ top: 0 });
  }, []);
  // Back / forward between pages.
  useEffect(
    () =>
      watchHash((p) => {
        setPage(p);
        window.scrollTo({ top: 0 });
      }),
    [],
  );

  const source = sources.find((s) => s.id === sourceId);

  // ---- regions on the data server ---------------------------------------
  useEffect(() => {
    let alive = true;
    setRegionsError(null);
    listRegions()
      .then((rs) => {
        if (!alive) return;
        setRegions(rs);
        setSources(rs.map(apiSource));
      })
      .catch((e) => alive && setRegionsError(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, [regionsKey]);

  // A shared link to a region the server no longer has: back to the world map.
  useEffect(() => {
    if (regions && sourceId && !source) {
      setSourceId(null);
      setPage("explore");
    }
  }, [regions, sourceId, source]);

  const enterRegion = useCallback(
    (regionId: string) => {
      setSourceId(`api:${regionId}`);
      navigate("overview");
    },
    [navigate],
  );

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

  // ---- past weather at the region's hotspots (API regions only) ----
  const [weather, setWeather] = useState<RegionWeather | null>(null);
  const [weatherStatus, setWeatherStatus] = useState<"none" | "loading" | "ready" | "failed">("none");
  const weatherRegion = source && meta && dsSource === source.id ? meta.id : null;
  useEffect(() => {
    setWeather(null);
    setWeatherStatus(weatherRegion ? "loading" : "none");
    if (!weatherRegion) return;
    const ctl = new AbortController();
    getWeather(weatherRegion, ctl.signal)
      .then((w) => {
        if (ctl.signal.aborted) return;
        setWeather(w);
        setWeatherStatus("ready");
      })
      .catch(() => !ctl.signal.aborted && setWeatherStatus("failed"));
    return () => ctl.abort();
  }, [weatherRegion, reloadKey]);

  // ---- burning outlook (machine-learning forecast, API regions only) ----
  const [forecast, setForecast] = useState<RegionForecast | null>(null);
  const [forecastStatus, setForecastStatus] = useState<"none" | "loading" | "ready" | "unpublished" | "failed">("none");
  useEffect(() => {
    setForecast(null);
    setForecastStatus(weatherRegion ? "loading" : "none");
    if (!weatherRegion) return;
    const ctl = new AbortController();
    getForecast(weatherRegion, ctl.signal)
      .then((f) => {
        if (ctl.signal.aborted) return;
        setForecast(f);
        setForecastStatus(f && f.months.length ? "ready" : "unpublished");
      })
      .catch(() => !ctl.signal.aborted && setForecastStatus("failed"));
    return () => ctl.abort();
  }, [weatherRegion, reloadKey]);

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

  // One colour/height scale for every month (or year) of the range, so the map can be compared
  // through time: the largest per-window 98th-percentile cell value. Without it each window would
  // be rescaled to its own max and a quiet December would look like an August peak.
  const [cellScale, setCellScale] = useState<number | undefined>();
  useEffect(() => {
    if (!source || !meta || dsSource !== source.id || windowMode === "range") {
      setCellScale(undefined);
      return;
    }
    let alive = true;
    const windows: [number, number][] = [];
    if (windowMode === "month") for (let i = r[0]; i <= r[1]; i++) windows.push([i, i]);
    else for (let y = ymYear(r[0]); y <= ymYear(r[1]); y++) windows.push([Math.max(r[0], ym(y, 1)), Math.min(r[1], ym(y, 12))]);
    (async () => {
      let s = 0;
      for (const [from, to] of windows) {
        const c = await source.cellWindow({ sensor, metric, from, to, excludePersistent });
        if (!alive) return;
        s = Math.max(s, robustMax([...c.values()].map((v) => v.value)));
      }
      setCellScale(s > 0 ? s : undefined);
    })().catch(() => alive && setCellScale(undefined));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, meta, dsSource, sensor, metric, r[0], r[1], windowMode, excludePersistent]);

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

  // Individual detections (only if a source provides them; the API serves fire-days): points / true pixel footprints,
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

  // The Overview map stays mounted while other pages show (no reload when coming back). Camera
  // moves asked for meanwhile are held until it is visible again, so it measures itself first.
  const onOverview = page === "overview";
  const shownFit = useRef(fitKey);
  const shownFocus = useRef(focus);
  if (onOverview) {
    shownFit.current = fitKey;
    shownFocus.current = focus;
  }

  // ---- URL sync --------------------------------------------------------
  useEffect(() => {
    // Skip while a newly picked dataset is still loading, so the URL never mixes two datasets.
    if (!meta || !area || !range || !sourceId || dsSource !== sourceId) return;
    writeHash({ page, source: sourceId, sensor, metric, area, areaAll: isWhole, range, selected: sel });
  }, [page, meta, dsSource, sourceId, sensor, metric, area, isWhole, range, sel]);

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
  const selectMonth = (i: number) => {
    setSelected(Math.max(r[0], Math.min(r[1], i)));
    setWindowMode("month");
  };
  const stepMonths = (d: number) => setSelected(Math.max(r[0], Math.min(r[1], sel + d)));

  // Two years side by side on the Trends page; until picked, the selected year and the one before it.
  const [compareYears, setCompareYears] = useState<[number, number] | null>(null);

  /** Shares a link to exactly this view: the system share sheet on phones, the clipboard elsewhere. */
  const share = async () => {
    const url = window.location.href;
    const title = `${meta?.name ?? "Phoenical"} · burning calendar`;
    try {
      if (navigator.share && window.matchMedia("(pointer: coarse)").matches) await navigator.share({ title, url });
      else {
        await navigator.clipboard.writeText(url);
        flash("Link copied");
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") flash("Couldn't copy the link: copy it from the address bar");
    }
  };

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
  const base = () => `phoenical_${slug(meta?.id ?? "data")}_${slug(area?.name ?? "area")}_${ymKey(r[0])}_${ymKey(r[1])}`;

  const exportsList: ExportAction[] = [
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
      hint: CHART_PAGES.includes(page) ? "Every chart on this page as a separate image" : "Open Calendar, Trends, Forecast or Weather to export their charts",
      disabled: !CHART_PAGES.includes(page),
      run: () => {
        chartPng();
        flash("Charts saved as PNG");
      },
    },
    {
      id: "map",
      label: "Map PNG",
      hint: onOverview ? "Current map view" : "Open Overview to export the map",
      disabled: !onOverview,
      run: () => {
        const m = mapRef.current;
        if (!m) return;
        downloadDataUrl(`${base()}_map.png`, m.getCanvas().toDataURL("image/png"));
        flash("Map saved as PNG");
      },
    },
  ];

  // ---- render ----------------------------------------------------------
  const ready = !!(meta && area && a && dsSource === sourceId);
  const failure = error ?? (meta && dsSource === sourceId ? seriesError : null) ?? (!source && regionsError ? regionsError : null);
  const regionPage = page !== "explore" && !!sourceId;
  const shownPage: Page = regionPage ? page : "explore";
  const dataPage = regionPage && ready && page !== "methods";
  keys.current.step = dataPage ? stepMonths : undefined;

  // ---- command palette -------------------------------------------------
  const commands: Command[] = [];
  const cmd = (group: string, id: string, label: string, run: () => void, extra: Partial<Command> = {}) => commands.push({ group, id: `${group}:${id}`, label, run, ...extra });
  for (const p of PAGES)
    if (p === "explore" || sourceId) cmd("Pages", p, p === "explore" ? "World map" : PAGE_LABEL[p], () => navigate(p), { hint: p === shownPage ? "Current page" : undefined, keywords: `go open ${p}` });
  for (const s of sources)
    cmd("Regions", s.id, s.label, () => {
      setSourceId(s.id);
      navigate("overview");
    }, { hint: s.id === sourceId ? "Open" : undefined, keywords: `region dataset country ${s.description ?? ""}` });
  if (ready) {
    const m = meta!;
    for (const pr of [defaultArea(m), ...(REGION_INFO[m.id]?.presets ?? []).map((p) => areaFromBBox(p.name, p.bbox))])
      cmd("Areas", pr.name, pr.name, () => onArea(pr), { hint: pr.name === area!.name ? "Showing" : undefined, keywords: "area zone district place" });
    for (let y = ymYear(r[1]); y >= ymYear(r[0]); y--)
      cmd("Years", String(y), `Jump to ${y}`, () => {
        selectYear(y);
        if (page === "methods") navigate("overview");
      }, { searchOnly: true, keywords: "year" });
    cmd("Years", "latest", "Jump to the latest month", () => setSelected(Math.min(r[1], parseYm(m.last_month))), { keywords: "now newest recent current" });
    for (const s of SENSORS.filter((s) => m.sensor_start[s]))
      cmd("Sensor", s, `Show ${SENSOR_LABEL[s]}`, () => setSensor(s), { hint: s === sensor ? "On" : undefined, keywords: "sensor satellite modis viirs harmonized" });
    cmd("Actions", "share", "Copy a link to this view", share, { keywords: "share url link" });
    for (const x of exportsList.filter((x) => !x.disabled)) cmd("Export", x.id, `Export ${x.label}`, () => void x.run(), { hint: x.hint, keywords: "download save csv png" });
  }
  cmd("Actions", "sidebar", sidebarCollapsed ? "Expand the sidebar" : "Collapse the sidebar", () => setSidebarCollapsed(!sidebarCollapsed), { hint: `${MOD_KEY} B` });
  for (const t of ["light", "dark", "auto"] as const)
    cmd("Appearance", t, t === "auto" ? "Match the system appearance" : `${t === "light" ? "Light" : "Dark"} appearance`, () => setTheme(t), {
      hint: themeChoice === t ? "On" : undefined,
      keywords: "theme mode colour color dark light",
    });

  const overlays = (
    <>
      {/* Mounted fresh on every open, so it always starts with an empty search. */}
      {paletteOpen && <CommandPalette open onClose={() => setPaletteOpen(false)} commands={commands} />}
      <SignInDialog />
      {loading && regionPage && <div className="loading-bar" aria-hidden />}
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </>
  );

  /** Sidebar + top bar around a page's content. */
  const shell = (content: React.ReactNode, filters?: FilterTab[]) => (
    <div className={`app${sidebarCollapsed ? " sb-collapsed" : ""}`}>
      <AppSidebar
        page={shownPage}
        onPage={navigate}
        hasRegion={!!sourceId}
        regionCard={
          source ? (
            <RegionCard
              pulse={a && ready ? a.series.filter((p) => p.i <= r[1]).slice(-36).map((p) => ({ i: p.i, value: p.value })) : undefined}
              selected={sel}
              onSelect={selectMonth}
              unit={unit}
            />
          ) : undefined
        }
        filters={filters}
        account={<AccountMenu onFlash={flash} />}
        collapsed={sidebarCollapsed}
        onCollapse={setSidebarCollapsed}
        mobileOpen={mobileNav}
        onMobileClose={() => setMobileNav(false)}
      />
      <div className={`shell-main${shownPage === "explore" ? " is-explore" : ""}`}>
        <TopBar
          page={shownPage}
          dataset={
            source
              ? {
                  name: meta && dsSource === sourceId ? meta.name : source.label,
                  sources,
                  sourceId: source.id,
                  onSource: setSourceId,
                }
              : undefined
          }
          onMenu={() => setMobileNav(true)}
          onPage={navigate}
          exports={regionPage && ready ? exportsList : null}
          onSearch={() => setPaletteOpen(true)}
          onShare={regionPage && ready ? share : undefined}
          data={
            dataPage
              ? {
                  sensor,
                  onSensor: setSensor,
                  sensors: SENSORS.filter((s) => meta!.sensor_start[s]),
                  metric,
                  metrics: meta!.metrics,
                  onMetric: setMetric,
                  selected: sel,
                  canStep: [sel > r[0], sel < r[1]],
                  onStep: stepMonths,
                }
              : undefined
          }
        />
        {content}
      </div>
      {overlays}
    </div>
  );

  if (!regionPage)
    return shell(
      <WorldPicker
        regions={regions}
        error={regionsError}
        onRetry={() => setRegionsKey((k) => k + 1)}
        onEnter={enterRegion}
        current={sourceId?.startsWith("api:") ? sourceId.slice(4) : undefined}
        extras={
          <div className="world-newsletter">
            <span className="eyebrow">Stay informed</span>
            <NewsletterForm source="landing" />
          </div>
        }
      />,
    );

  if (failure)
    return shell(
      <div className="boot">
        <div className="boot-orb" aria-hidden>
          <img src="./emblem.png" alt="" width={64} height={64} />
        </div>
        <p className="boot-title">The fire record didn't load</p>
        <p className="warn">{failure}</p>
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
          <button className="btn" onClick={() => navigate("explore")}>
            Back to the world map
          </button>
        </div>
      </div>,
    );

  // While loading, the page's own layout in placeholder glass, so nothing jumps when the data lands.
  if (!ready)
    return shell(
      <div className="page-wrap" aria-busy="true" aria-label={`Loading the fire record${source ? ` for ${source.label}` : ""}`}>
        <div className={`skeleton-page is-${page}`}>
          <div className="skeleton-head">
            <i className="sk sk-line" style={{ width: 180 }} />
            <i className="sk sk-title" />
            <i className="sk sk-line" style={{ width: "46%" }} />
          </div>
          {page === "overview" ? (
            <>
              <i className="sk sk-card sk-stage" />
              <div className="sk-row">
                {[0, 1, 2, 3, 4].map((k) => (
                  <i key={k} className="sk sk-card sk-kpi" />
                ))}
              </div>
            </>
          ) : (
            <>
              <i className="sk sk-card sk-tall" />
              <div className="sk-row">
                <i className="sk sk-card sk-mid" />
                <i className="sk sk-card sk-mid" />
              </div>
            </>
          )}
        </div>
      </div>,
    );

  // Narrowed by `ready` above.
  const m = meta!;
  const ar = area!;
  const an = a!;

  const viirsStart = m.sensor_start.viirs_raw ? ymYear(parseYm(m.sensor_start.viirs_raw)) : undefined;
  const peakMonth = an.clim.reduce((p, c) => (Number.isFinite(c.median) && c.median > (p?.median ?? -1) ? c : p), an.clim[0]);
  const hasPeak = !!peakMonth && Number.isFinite(peakMonth.median);
  const record = an.completeYears.length ? an.completeYears.reduce((p, c) => (c.total > p.total ? c : p)) : null;
  const selYearSeries = an.series.filter((p) => p.year === ymYear(sel));
  const coveredFrom = an.series.find((p) => p.value !== null)?.year;
  const years = `${coveredFrom ?? ymYear(r[0])}–${ymYear(r[1])}`;
  const eyebrow = `${m.name}${isWhole ? "" : ` / ${ar.name}`} · ${SENSOR_LABEL[sensor]} · ${years}`;
  const withSidebar = SIDEBAR_PAGES.includes(page);
  // Years for the comparison: those with any data, newest default first.
  const dataYears = [...new Set(an.series.filter((p) => p.value !== null).map((p) => p.year))];
  const fallbackB = dataYears.includes(ymYear(sel) - 1) ? ymYear(sel) - 1 : (record?.year ?? dataYears[0]);
  const [cmpA, cmpB] = compareYears && compareYears.every((y) => dataYears.includes(y)) ? compareYears : [ymYear(sel), fallbackB];

  const banners = (
    <>
      {sensor !== "harmonized" && (
        <div className="banner">
          <b>Raw {SENSOR_LABEL[sensor].replace(" raw", "")} view.</b>{" "}
          {sensor === "viirs_raw"
            ? `VIIRS starts in ${m.sensor_start.viirs_raw ?? "2012"} and detects many more, smaller fires, so it has no record before then.`
            : "MODIS sees roughly 3–6× fewer fire-days than VIIRS for the same activity, so its values use their own scale. Switch to Harmonized for one consistent record."}{" "}
          <button className="link" onClick={() => setSensor("harmonized")}>
            Show harmonized
          </button>
        </div>
      )}
      {sensor === "harmonized" && m.estimate_until && r[0] <= parseYm(m.estimate_until) && (
        <div className="banner banner-soft">
          <b>Before {m.splice_date?.slice(0, 7) ?? "2012"}, values are modelled estimates.</b> They are converted from MODIS, not VIIRS detections
          {an.series.some((p) => p.lowConfidence) ? ", and months marked low confidence should be read with extra caution" : ""}.
        </div>
      )}
    </>
  );

  const pageLink = (p: Page, label: string) => (
    <a
      className="link"
      href={pageHref(p)}
      onClick={(e) => {
        e.preventDefault();
        navigate(p);
      }}
    >
      {label}
    </a>
  );

  const overview = (
    <main className="main page page-overview" hidden={!onOverview} aria-label="Overview">
      {banners}

      <section className="hero stage">
        <div className="card map-card">
          <MapView
            // The street map and lighting differ per theme, so the map is rebuilt when the theme changes.
            key={theme}
            theme={theme}
            area={ar}
            extent={m.bbox}
            gridDeg={fineCells ? FINE_GRID : m.grid_deg}
            cells={fineCells ?? cells}
            scaleMax={fineCells ? undefined : cellScale}
            resolution={resolution}
            onResolution={setResolution}
            detections={hasDetections}
            gridLabel={`${m.grid_deg}° (~${Math.round(m.grid_deg * 111)} km)`}
            note={
              fineCells
                ? `~1 km cells from individual ${sensor === "harmonized" ? "MODIS + VIIRS" : SENSOR_LABEL[sensor]} detections (not calibrated)${detectionsCapped ? ` · first ${DETECTION_LIMIT.toLocaleString()} detections` : ""}`
                : mapNote
            }
            hotspots={hotspots}
            outline={m.outline}
            focus={shownFocus.current}
            areaIsRegion={isWhole}
            layers={layers}
            showData={showData}
            animate={animations && onOverview}
            unit={unit}
            windowLabel={windowLabel}
            drawMode={drawMode}
            setDrawMode={setDrawMode}
            onArea={onArea}
            fitKey={shownFit.current}
            mapRef={mapRef}
          />
          <Timeline series={an.series} selected={sel} onSelect={setSelected} windowMode={windowMode} setWindowMode={setWindowMode} unit={unit} />
        </div>
        <div className="stage-title glass">
          <RegionHero
            name={m.name}
            areaName={ar.name}
            blurb={source?.description}
            sensor={SENSOR_LABEL[sensor]}
            years={years}
            grid={m.grid_deg}
            cells={cellCount}
            season={typicalSeason(an.seasons)}
            peakMonth={hasPeak ? peakMonth.month : undefined}
            record={record?.year}
            trend={an.trend?.pctPerDecade}
            localName={m.local_name}
          />
        </div>
        <div className="card cvm-card glass">
          <CardHead title="This month vs normal" subtitle={`${SENSOR_LABEL[sensor]} · ${METRIC_LABEL[metric]}`} />
          <CurrentVsMedian
            cvm={cvm}
            series={an.series}
            selected={sel}
            unit={unit}
            onStep={(d) => setSelected(Math.max(r[0], Math.min(r[1], sel + d)))}
            onLatest={() => setSelected(Math.min(r[1], parseYm(m.last_month)))}
          />
        </div>
      </section>

      <section className="kpis" aria-label="Summary">
        <Kpi
          label={`Total ${unit}`}
          value={fmt(an.total)}
          num={an.total}
          sub={`${years} · ${SENSOR_LABEL[sensor]}`}
          spark={{ values: an.totals.map((t) => (t.coveredMonths ? t.total : 0)), highlight: an.totals.findIndex((t) => t.year === ymYear(sel)) }}
        />
        <Kpi label="Average per year" value={fmt(an.completeYears.length ? an.completeYears.reduce((s, t) => s + t.total, 0) / an.completeYears.length : NaN)} sub={`${an.completeYears.length} complete years`} />
        <Kpi
          label="Peak month"
          value={hasPeak ? MONTH_ABBR[peakMonth.month - 1] : "–"}
          sub={peakMonth ? `median ${fmt(peakMonth.median)} ${unit}` : ""}
          spark={{ values: an.clim.map((c) => (Number.isFinite(c.median) ? c.median : 0)), highlight: peakMonth ? peakMonth.month - 1 : -1 }}
        />
        <Kpi
          label="Record year"
          value={record ? String(record.year) : "–"}
          sub={record ? `${fmt(record.total)} ${unit}` : ""}
          spark={{ values: an.totals.map((t) => (t.coveredMonths ? t.total : 0)), highlight: record ? an.totals.findIndex((t) => t.year === record.year) : -1 }}
        />
        <Kpi
          label="Trend"
          value={an.trend ? `${fmtPct(an.trend.pctPerDecade)}` : "–"}
          sub={an.trend ? `per decade, ${an.trend.from}–${an.trend.to}` : "needs 3+ complete years"}
          tone={an.trend ? (an.trend.pctPerDecade > 5 ? "warm" : an.trend.pctPerDecade < -5 ? "cool" : undefined) : undefined}
        />
      </section>

      <nav className="next-grid" aria-label="Explore this region">
        <NextCard page="calendar" onGo={navigate} title="Burning calendar" text="Every month of the record as a grid and as fire rings, with anomalies against the normal." stat={hasPeak ? `Peaks in ${MONTH_ABBR[peakMonth.month - 1]}` : undefined} />
        <NextCard
          page="trends"
          onGo={navigate}
          title="Trends & seasons"
          text="The typical year, annual totals across sensors, and when each fire season started and ended."
          stat={an.trend ? `${fmtPct(an.trend.pctPerDecade)} per decade` : undefined}
        />
        <NextCard
          page="forecast"
          onGo={navigate}
          title="Burning outlook"
          text="The next six months from a machine-learning model, with a likely range and how accurate it has been."
          stat={
            forecastStatus === "ready" && forecast
              ? `${MONTH_ABBR[ymMonth(parseYm(forecast.months[0].ym)) - 1]}: ${fmt(forecast.months[0].value)} expected`
              : forecastStatus === "loading"
                ? "Loading…"
                : "Coming soon"
          }
        />
        <NextCard
          page="weather"
          onGo={navigate}
          title="Weather at the fires"
          text="Temperature, rain, humidity and wind at the hotspots, month by month against normal."
          stat={weatherStatus === "ready" ? "Available" : weatherStatus === "loading" ? "Loading…" : "Not for this dataset"}
        />
      </nav>
    </main>
  );

  let other: React.ReactNode = null;
  if (page === "calendar")
    other = (
      <>
        <PageHead eyebrow={eyebrow} title="Burning calendar" lede="Each month of the record, read two ways: as the rings of a tree, and as a month-by-year grid. Click any month to select it." />
        {banners}
        <section className="card rings-card">
          <FireRings
            cells={an.anoms}
            unit={unit}
            selected={sel}
            onSelect={selectMonth}
            events={eventMarks}
            markerYear={sensor !== "modis_raw" ? viirsStart : undefined}
            markerLabel="VIIRS joins"
          />
          <div className="rings-aside">
            <span className="eyebrow">Signature view</span>
            <h2>Fire rings</h2>
            <p className="rings-lede">
              {m.name}'s fire record, read like the rings of a tree. Each ring is a year, starting from <b>{coveredFrom ?? ymYear(r[0])}</b> at the core. A{" "}
              <b>thicker ring</b> is a year with more fire, and the twelve sectors are the months, coloured by activity.
            </p>
            <div className="rings-try">
              <span className="field-label">See what harmonizing does</span>
              <div className="seg seg-full sensor-seg" role="radiogroup" aria-label="Sensor for the rings">
                {SENSORS.filter((s) => m.sensor_start[s]).map((s) => (
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
            title="Month × year grid"
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
            cells={an.anoms}
            mode={calendarMode}
            unit={unit}
            selected={sel}
            onSelect={selectMonth}
            markers={sensor !== "modis_raw" && viirsStart ? [{ year: viirsStart, label: "VIIRS" }] : []}
            events={eventMarks}
          />
          <p className="legend-line">
            <span className="lg lg-hatch" /> no data (not zero) <span className="lg lg-dash" /> partial year, not in medians
            {an.series.some((p) => p.lowConfidence) && (
              <>
                <span className="lg lg-dots" /> low-confidence estimate
              </>
            )}
            <span className="lg lg-sel" /> selected
          </p>
        </section>
      </>
    );
  else if (page === "trends")
    other = (
      <>
        <PageHead
          eyebrow={eyebrow}
          title="Trends & seasons"
          lede={
            <>
              What a normal year looks like, how the years compare, and when each season ran.
              {an.trend ? (
                <>
                  {" "}
                  Activity is changing by <b>{fmtPct(an.trend.pctPerDecade)}</b> per decade ({an.trend.from}–{an.trend.to}).
                </>
              ) : null}
            </>
          }
        />
        {banners}
        <div className="grid-2">
          <section className="card">
            <CardHead title="Typical year" subtitle={`Median and spread per month · line = ${ymYear(sel)} · not a forecast`} actions={<PngButton id="climatology" />} />
            <ClimatologyChart clim={an.clim} year={ymYear(sel)} yearSeries={selYearSeries} unit={unit} onSelectMonth={(mo) => setSelected(Math.max(r[0], Math.min(r[1], ym(ymYear(sel), mo))))} />
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
            <AnnualChart totals={an.totalsBy} sensor={sensor} compare={compare} unit={unit} selectedYear={ymYear(sel)} viirsStartYear={viirsStart} events={eventMarks} onSelectYear={selectYear} />
          </section>
        </div>
        <YearCompare
          series={an.series}
          clim={an.clim}
          years={dataYears}
          a={cmpA}
          b={cmpB}
          onChange={(x, y) => setCompareYears([x, y])}
          unit={unit}
          onSelectMonth={(y, mo) => selectMonth(ym(y, mo))}
        />
        <section className="card">
          <CardHead title="Fire season by year" subtitle="When each year's season started, peaked and ended · click a year to select it" />
          <SeasonStrip peakMonth={hasPeak ? peakMonth.month : undefined} seasons={an.seasons} selectedYear={ymYear(sel)} unit={unit} onSelectYear={selectYear} />
        </section>
      </>
    );
  else if (page === "forecast") {
    // The model forecasts whole-region harmonized fire-days (all cells), so history and the typical
    // year are only drawn alongside it when the current view measures the same thing.
    const comparable = isWhole && sensor === "harmonized" && metric === "cell_days" && !excludePersistent;
    other = (
      <ForecastPage
        eyebrow={`${m.name} · whole region · harmonized fire-days`}
        regionName={m.name}
        status={forecastStatus}
        forecast={forecast}
        history={comparable ? an.series.filter((p) => !p.partial).slice(-24).map((p) => ({ i: p.i, value: p.value })) : undefined}
        typical={comparable ? an.clim.map((c) => (Number.isFinite(c.median) ? c.median : null)) : undefined}
        historyNote={
          comparable
            ? undefined
            : `Recent months and the typical year are hidden: they would show ${isWhole ? "" : `${ar.name}, `}${SENSOR_LABEL[sensor]}${metric !== "cell_days" ? `, ${METRIC_LABEL[metric]}` : ""}${excludePersistent ? " without industrial sites" : ""}, not the whole region's harmonized fire-days the forecast uses.`
        }
        unit="fire-days"
        onRetry={() => setReloadKey((k) => k + 1)}
        backLink={pageLink("overview", "Back to the overview")}
      />
    );
  } else if (page === "weather")
    other = (
      <>
        <PageHead eyebrow={eyebrow} title="Weather at the fires" lede="Past conditions at the region's fire hotspots for the selected year, against the normal for each month." />
        {weather ? (
          <WeatherCard weather={weather} selected={sel} onSelect={selectMonth} subArea={!isWhole} />
        ) : (
          <section className="card empty">
            {weatherStatus === "loading" ? (
              <p>
                <span className="spinner" aria-hidden /> Loading weather for {m.name}…
              </p>
            ) : (
              <>
                <h3>No weather for this dataset</h3>
                <p className="muted">
                  {weatherStatus === "failed"
                    ? "The data server has no weather stored for this region yet."
                    : "Weather comes from the data server, so it is only shown for regions opened from the world map, not for files loaded in the browser."}
                </p>
                <p>{pageLink("overview", "Back to the overview")}</p>
              </>
            )}
          </section>
        )}
      </>
    );
  else if (page === "methods") other = <MethodsPage meta={m} sourceLabel={source?.label ?? ""} />;

  const filters: FilterTab[] | undefined = withSidebar
    ? [
        {
          id: "area",
          label: "Area",
          content: (
            <>
              <AreaPanel
                meta={m}
                whole={whole!}
                area={ar}
                cellCount={cellCount}
                onArea={onArea}
                drawMode={drawMode}
                setDrawMode={(dm) => {
                  // Drawing happens on the map.
                  if (dm !== "none" && !onOverview) navigate("overview");
                  setMobileNav(false);
                  setDrawMode(dm);
                }}
                excludePersistent={excludePersistent}
                onExcludePersistent={setExcludePersistent}
                mapTools={onOverview}
              />
              {!onOverview && (
                <p className="muted small sb-hint">
                  To draw your own area, open the {pageLink("overview", "Overview map")}.
                </p>
              )}
              <MyAreasPanel region={m.id} area={ar} isWhole={isWhole} excludePersistent={excludePersistent} onOpen={onArea} onFlash={flash} />
            </>
          ),
        },
        {
          id: "time",
          label: "Time",
          content: (
            <>
              <DatePanel meta={m} range={r} onRange={setRange} bounds={bounds} />
              <EventsPanel
                documented={documented}
                activeId={activeEvent}
                // Spikes that are already explained by a documented event are not listed twice.
                events={an.events.filter((e) => !(e.id.startsWith("anom-") && documented.some((d) => d.i === e.i)))}
                onJump={(e) => {
                  if (e.i === undefined) return;
                  setSelected(e.i);
                  setWindowMode(e.year !== undefined ? "year" : "month");
                  setActiveEvent(e.id);
                  setFocus(e.loc ? { ...e.loc, key: `${e.id}-${Date.now()}` } : null);
                }}
              />
            </>
          ),
        },
        // Map settings only where the map is.
        ...(onOverview
          ? [
              {
                id: "map",
                label: "Map",
                content: (
                  <>
                    <LayersPanel layers={layers} setLayers={setLayers} detections={hasDetections} />
                    <PerformancePanel animations={animations} onAnimations={setAnimationsState} showData={showData} onShowData={setShowData} />
                  </>
                ),
              },
            ]
          : []),
      ]
    : undefined;

  return shell(
    <div className="page-wrap">
      {overview}
      {other && (
        // Charts take their colours when built, so they are rebuilt when the theme changes.
        <main key={`${page}-${theme}`} className={`main page page-${page}`}>
          {other}
        </main>
      )}

      <footer className="site-foot">
        <div className="site-foot-text">
          <span>
            Source data: NASA FIRMS (MODIS, VIIRS 375 m), harmonized by the Wel3a pipeline{m.generated_at ? ` (export of ${m.generated_at.slice(0, 10)})` : ""}. Fire-days measure burning
            activity, not burned area or individual fires.
          </span>
          {page !== "methods" && pageLink("methods", "Methods & limitations")}
        </div>
        <div className="site-foot-news">
          <span className="eyebrow">Monthly digest</span>
          <p className="small muted">One short email a month with each region's newest month. No account needed.</p>
          <NewsletterForm source="dashboard" compact />
        </div>
      </footer>
    </div>,
    filters,
  );
}

/** Link card from the overview to another page of the region. */
function NextCard({ page, onGo, title, text, stat }: { page: Page; onGo: (p: Page) => void; title: string; text: string; stat?: string }) {
  return (
    <a
      className="next-card"
      href={pageHref(page)}
      onClick={(e) => {
        e.preventDefault();
        onGo(page);
      }}
    >
      <span className="next-card-title">
        {title} <span aria-hidden>→</span>
      </span>
      <span className="next-card-text">{text}</span>
      {stat && <span className="next-card-stat">{stat}</span>}
    </a>
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

const readPref = (key: string) => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};
const savePref = (key: string, value: string) => {
  try {
    localStorage.setItem(key, value);
  } catch {
    // storage blocked: the setting lasts for this visit only
  }
};
