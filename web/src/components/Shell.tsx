import { useEffect, useRef, useState } from "react";
import { METRIC_LABEL, MONTH_ABBR, type Metric, SENSOR_LABEL, SENSORS, type Sensor, ymMonth, ymYear } from "../data/contract";
import type { DataSource } from "../data/sources";
import { fmt } from "../lib/analytics";
import { SENSOR_COLOR } from "../lib/colors";
import { type ThemeChoice, useTheme } from "../lib/theme";
import { type Page, pageHref } from "../lib/urlState";
import { MOD_KEY, isMac } from "./CommandPalette";

export interface ExportAction {
  id: string;
  label: string;
  hint: string;
  run: () => void | Promise<void>;
  disabled?: boolean;
}

export const PAGE_LABEL: Record<Page, string> = {
  explore: "Explore",
  overview: "Overview",
  calendar: "Calendar",
  trends: "Trends",
  weather: "Weather",
  methods: "Methods",
};

const ICON: Record<Page, React.ReactNode> = {
  explore: (
    <>
      <circle cx="10" cy="10" r="7" />
      <path d="M3 10h14M10 3c2.2 2.2 2.2 11.8 0 14M10 3c-2.2 2.2-2.2 11.8 0 14" />
    </>
  ),
  overview: <path d="M3.5 3.5h5v5h-5zM11.5 3.5h5v5h-5zM3.5 11.5h5v5h-5zM11.5 11.5h5v5h-5z" />,
  calendar: (
    <>
      <rect x="3" y="4.5" width="14" height="12" rx="2" />
      <path d="M3 8.5h14M7 2.8v3.4M13 2.8v3.4" />
    </>
  ),
  trends: <path d="M3 15.5 7.5 10l3 3L17 5.5M12.5 5.5H17V10" />,
  weather: <path d="M6 15.5h8a3.5 3.5 0 0 0 .4-7A4.5 4.5 0 0 0 5.8 9 3.3 3.3 0 0 0 6 15.5z" />,
  methods: (
    <>
      <path d="M4 4.5h4.5a1.5 1.5 0 0 1 1.5 1.5v10a1.5 1.5 0 0 0-1.5-1.5H4z" />
      <path d="M16 4.5h-4.5A1.5 1.5 0 0 0 10 6v10a1.5 1.5 0 0 1 1.5-1.5H16z" />
    </>
  ),
};

/** Navigation entries, grouped: the world, then the pages of the open region. */
const NAV: { label: string; pages: Page[] }[] = [
  { label: "Discover", pages: ["explore"] },
  { label: "Region", pages: ["overview", "calendar", "trends", "weather"] },
  { label: "Reference", pages: ["methods"] },
];

const Icon = ({ page }: { page: Page }) => (
  <svg className="sb-icon" viewBox="0 0 20 20" aria-hidden>
    {ICON[page]}
  </svg>
);

interface SidebarProps {
  page: Page;
  onPage: (p: Page) => void;
  /** False until a region is open: its pages are greyed out. */
  hasRegion: boolean;
  regionCard?: React.ReactNode;
  /** Filter groups for the current page (area, time…), shown one at a time as tabs. */
  filters?: FilterTab[];
  account: React.ReactNode;
  collapsed: boolean;
  onCollapse: (c: boolean) => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

/** The app's one sidebar: brand, the open region, page links, and the filters for the page. */
export function AppSidebar(p: SidebarProps) {
  return (
    <>
      <div className={`sb-scrim${p.mobileOpen ? " is-open" : ""}`} onClick={p.onMobileClose} aria-hidden />
      <aside className={`sidebar${p.collapsed ? " is-collapsed" : ""}${p.mobileOpen ? " is-open" : ""}`} aria-label="Sidebar">
        <div className="sb-head">
          <a
            className="sb-brand"
            href={pageHref("explore")}
            onClick={(e) => {
              e.preventDefault();
              p.onPage("explore");
            }}
            aria-label="Phoenical: world map"
          >
            <img src="./emblem.png" alt="" width={30} height={30} />
            <span className="sb-brand-text">
              <strong>Phoenical</strong>
              <small>Burning calendar</small>
            </span>
          </a>
          <button className="icon-btn sb-collapse" onClick={() => p.onCollapse(!p.collapsed)} aria-label={p.collapsed ? "Expand sidebar" : "Collapse sidebar"} title={`${p.collapsed ? "Expand" : "Collapse"} sidebar (Ctrl+B)`}>
            <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
              <rect x="3" y="3.5" width="14" height="13" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 3.5v13" stroke="currentColor" strokeWidth="1.5" />
            </svg>
          </button>
        </div>

        <div className="sb-body">
          {/* Pinned: the open region and the page links stay put while the filters below scroll. */}
          <div className="sb-pinned">
            {p.regionCard}

            <nav className="sb-nav" aria-label="Pages">
              {NAV.map((g) => (
                <div className="sb-nav-group" key={g.label} role="group" aria-label={g.label}>
                  {g.pages.map((id) => {
                    const off = id !== "explore" && !p.hasRegion;
                    const on = p.page === id;
                    return (
                      <a
                        key={id}
                        href={off ? undefined : pageHref(id)}
                        className={`sb-link${on ? " is-on" : ""}${off ? " is-off" : ""}`}
                        aria-current={on ? "page" : undefined}
                        aria-disabled={off || undefined}
                        title={off ? "Pick a region on the world map first" : PAGE_LABEL[id]}
                        onClick={(e) => {
                          e.preventDefault();
                          if (!off) p.onPage(id);
                        }}
                      >
                        <Icon page={id} />
                        <span>{PAGE_LABEL[id]}</span>
                      </a>
                    );
                  })}
                </div>
              ))}
            </nav>
          </div>

          {p.filters && p.filters.length > 0 && <FilterTabs tabs={p.filters} />}
        </div>

        <div className="sb-foot">
          <ThemeSwitch />
          {p.account}
        </div>
      </aside>
    </>
  );
}

export interface FilterTab {
  id: string;
  label: string;
  content: React.ReactNode;
}

const TAB_PREF = "wel3a.filterTab";
const readTab = () => {
  try {
    return localStorage.getItem(TAB_PREF);
  } catch {
    return null;
  }
};

/**
 * The page's filters as tabs: the tab row stays put and only the open group scrolls,
 * so every control is one click away. Hidden panels stay mounted to keep their state.
 */
function FilterTabs({ tabs }: { tabs: FilterTab[] }) {
  const [want, setWant] = useState(readTab);
  const active = tabs.some((t) => t.id === want) ? want! : tabs[0].id;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const pick = (id: string, focus = false) => {
    setWant(id);
    try {
      localStorage.setItem(TAB_PREF, id);
    } catch {
      // storage blocked: the choice lasts for this visit only
    }
    if (focus) refs.current[id]?.focus();
  };
  const onKey = (e: React.KeyboardEvent) => {
    const i = tabs.findIndex((t) => t.id === active);
    const to = ({ ArrowLeft: i - 1, ArrowRight: i + 1, Home: 0, End: tabs.length - 1 } as Record<string, number>)[e.key];
    if (to === undefined) return;
    e.preventDefault();
    pick(tabs[(to + tabs.length) % tabs.length].id, true);
  };

  return (
    <div className="sb-filters">
      <div className="seg seg-sm seg-full sb-tabs" role="tablist" aria-label="Filters" onKeyDown={onKey}>
        {tabs.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            id={`sb-tab-${t.id}`}
            role="tab"
            aria-selected={t.id === active}
            aria-controls={`sb-panel-${t.id}`}
            tabIndex={t.id === active ? 0 : -1}
            className={t.id === active ? "is-on" : ""}
            onClick={() => pick(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="sb-scroll">
        {tabs.map((t) => (
          <div key={t.id} id={`sb-panel-${t.id}`} className="sb-panel" role="tabpanel" aria-labelledby={`sb-tab-${t.id}`} hidden={t.id !== active}>
            {t.content}
          </div>
        ))}
      </div>
    </div>
  );
}

export interface DatasetSwitchProps {
  name: string;
  sources: DataSource[];
  sourceId: string;
  onSource: (id: string) => void;
  onImport: () => void;
}

/** The open region's name in the top bar, doubling as the dataset switcher. */
function DatasetSwitch(p: DatasetSwitchProps) {
  return (
    <label className="ds-switch" title="Switch dataset">
      <span className="sr-only">Dataset</span>
      <span className="ds-switch-mark" aria-hidden>
        {p.name.charAt(0)}
      </span>
      <span className="ds-switch-name">{p.name}</span>
      <svg viewBox="0 0 20 20" width="13" height="13" aria-hidden>
        <path d="m6 8 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <select value={p.sourceId} onChange={(e) => (e.target.value === "__import" ? p.onImport() : p.onSource(e.target.value))}>
        {p.sources.map((s) => (
          <option key={s.id} value={s.id}>
            {s.kind === "upload" ? "File · " : ""}
            {s.label}
          </option>
        ))}
        <option value="__import">Load your own file…</option>
      </select>
    </label>
  );
}

interface RegionCardProps {
  /** The last months of the record, oldest first, for the pulse strip. */
  pulse?: { i: number; value: number | null }[];
  selected?: number;
  onSelect?: (i: number) => void;
  unit?: string;
}

/** A strip of the open region's recent monthly fire activity; click a bar to select that month. */
export function RegionCard(p: RegionCardProps) {
  const pulse = p.pulse ?? [];
  const max = Math.max(1e-9, ...pulse.map((m) => m.value ?? 0));
  const cur = pulse.find((m) => m.i === p.selected);
  if (pulse.length < 2) return null;
  return (
    <section className="region-card" aria-label="Recent fire activity">
          <div className="pulse-head">
            <span>Last {pulse.length} months</span>
            {cur && (
              <span className="pulse-now">
                {MONTH_ABBR[ymMonth(cur.i) - 1]} {ymYear(cur.i)} · <b>{cur.value === null ? "no data" : fmt(cur.value)}</b>
              </span>
            )}
          </div>
          <div className="pulse-bars" role="group" aria-label={`Monthly ${p.unit ?? "fire activity"}, last ${pulse.length} months`}>
            {pulse.map((m) => (
              <button
                key={m.i}
                className={`pulse-bar${m.i === p.selected ? " is-on" : ""}${m.value === null ? " is-empty" : ""}`}
                style={{ ["--h" as string]: m.value === null ? 0 : Math.max(0.04, m.value / max) }}
                onClick={() => p.onSelect?.(m.i)}
                title={`${MONTH_ABBR[ymMonth(m.i) - 1]} ${ymYear(m.i)}: ${m.value === null ? "no data" : `${fmt(m.value)} ${p.unit ?? ""}`}`}
                aria-label={`${MONTH_ABBR[ymMonth(m.i) - 1]} ${ymYear(m.i)}`}
                aria-pressed={m.i === p.selected}
              />
            ))}
          </div>
    </section>
  );
}

interface TopBarProps {
  page: Page;
  /** The open region; its name in the breadcrumb switches datasets. */
  dataset?: DatasetSwitchProps;
  onMenu: () => void;
  onPage: (p: Page) => void;
  exports: ExportAction[] | null;
  /** Opens the command palette. */
  onSearch: () => void;
  /** Shares a link to the current view; absent where there is nothing to link to. */
  onShare?: () => void;
  /** Live-data badge (regions fed by the live pipeline). */
  live?: React.ReactNode;
  /** Sensor, metric and month controls; hidden where they change nothing. */
  data?: {
    sensor: Sensor;
    onSensor: (s: Sensor) => void;
    sensors: Sensor[];
    metric: Metric;
    metrics: Metric[];
    onMetric: (m: Metric) => void;
    selected: number;
    canStep: [boolean, boolean];
    onStep: (d: number) => void;
  };
}

/** Slim bar over the page: where you are, and the controls that change what every page shows. */
export function TopBar(p: TopBarProps) {
  const d = p.data;
  return (
    <header className="topbar">
      <button className="icon-btn topbar-menu" onClick={p.onMenu} aria-label="Open the sidebar">
        <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden>
          <path d="M3.5 6h13M3.5 10h13M3.5 14h13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      </button>

      <nav className="crumbs" aria-label="Breadcrumb">
        {p.dataset && p.page !== "explore" ? (
          <>
            <DatasetSwitch {...p.dataset} />
            <span aria-hidden>/</span>
          </>
        ) : null}
        <b aria-current="page">{p.page === "explore" ? "World map" : PAGE_LABEL[p.page]}</b>
      </nav>

      <button className="search-pill" onClick={p.onSearch} aria-label="Search pages, places, years and actions" aria-keyshortcuts={isMac ? "Meta+K" : "Control+K"}>
        <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden>
          <circle cx="9" cy="9" r="5.5" fill="none" stroke="currentColor" strokeWidth="1.7" />
          <path d="M13.2 13.2 17 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        <span>Search</span>
        <kbd>{MOD_KEY} K</kbd>
      </button>

      {d && (
        <div className="topbar-controls">
          <div className="seg sensor-seg" role="radiogroup" aria-label="Sensor">
            {SENSORS.filter((s) => d.sensors.includes(s)).map((s) => (
              <button key={s} role="radio" aria-checked={d.sensor === s} className={d.sensor === s ? "is-on" : ""} onClick={() => d.onSensor(s)}>
                <i style={{ background: SENSOR_COLOR[s] }} aria-hidden />
                {SENSOR_LABEL[s]}
              </button>
            ))}
          </div>
          {d.metrics.length > 1 && (
            <label className="select-wrap" title="Metric">
              <span className="sr-only">Metric</span>
              <select value={d.metric} onChange={(e) => d.onMetric(e.target.value as Metric)}>
                {d.metrics.map((m) => (
                  <option key={m} value={m}>
                    {METRIC_LABEL[m]}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="stepper" role="group" aria-label="Selected month">
            <button className="icon-btn" disabled={!d.canStep[0]} onClick={() => d.onStep(-1)} aria-label="Previous month">
              <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden>
                <path d="m12 5-5 5 5 5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            <output aria-live="polite">
              {MONTH_ABBR[ymMonth(d.selected) - 1]} {ymYear(d.selected)}
            </output>
            <button className="icon-btn" disabled={!d.canStep[1]} onClick={() => d.onStep(1)} aria-label="Next month">
              <svg viewBox="0 0 20 20" width="14" height="14" aria-hidden>
                <path d="m8 5 5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {p.live}
      {p.onShare && (
        <button className="icon-btn glass-btn" onClick={p.onShare} aria-label="Share a link to this view" title="Share a link to this view">
          <svg viewBox="0 0 20 20" width="17" height="17" aria-hidden>
            <path d="M10 12.5V3m0 0L6.5 6.5M10 3l3.5 3.5M5.5 9.5H5A1.5 1.5 0 0 0 3.5 11v4.5A1.5 1.5 0 0 0 5 17h10a1.5 1.5 0 0 0 1.5-1.5V11A1.5 1.5 0 0 0 15 9.5h-.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {p.exports && <ExportMenu actions={p.exports} />}
    </header>
  );
}

/** Appearance switch in the sidebar footer: light, dark, or follow the system. */
function ThemeSwitch() {
  const [, setTheme, choice] = useTheme();
  const opt = (t: ThemeChoice, label: string, icon: React.ReactNode) => (
    <button role="radio" aria-checked={choice === t} aria-label={label} className={choice === t ? "is-on" : ""} onClick={() => setTheme(t)} title={t === "auto" ? "Auto: match the system appearance" : `${label} appearance`}>
      <svg viewBox="0 0 20 20" width="15" height="15" aria-hidden>
        {icon}
      </svg>
    </button>
  );
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Appearance">
      {opt(
        "light",
        "Light",
        <>
          <circle cx="10" cy="10" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M10 2.5v1.8M10 15.7v1.8M2.5 10h1.8M15.7 10h1.8M4.7 4.7l1.3 1.3M14 14l1.3 1.3M4.7 15.3 6 14M14 6l1.3-1.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </>,
      )}
      {opt("dark", "Dark", <path d="M16 12.4A6.5 6.5 0 0 1 7.6 4a6.5 6.5 0 1 0 8.4 8.4z" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />)}
      {opt(
        "auto",
        "Auto",
        <>
          <circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M10 3a7 7 0 0 1 0 14z" fill="currentColor" />
        </>,
      )}
    </div>
  );
}

function ExportMenu({ actions }: { actions: ExportAction[] }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  return (
    <div className="menu-wrap" ref={ref}>
      <button className="btn btn-primary" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
          <path d="M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M3 13h10" stroke="currentColor" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="btn-text">Export</span>
      </button>
      {open && (
        <div className="menu" role="menu">
          {actions.map((a) => (
            <button
              key={a.id}
              role="menuitem"
              disabled={a.disabled || busy !== null}
              onClick={async () => {
                setBusy(a.id);
                try {
                  await a.run();
                } finally {
                  setBusy(null);
                  setOpen(false);
                }
              }}
            >
              <b>{busy === a.id ? "Preparing…" : a.label}</b>
              <small>{a.hint}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
