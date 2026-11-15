import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { MOD_KEY } from "./CommandPalette";

/**
 * The newcomer tour: a short walk through the Overview page. Each step dims the page, outlines one
 * part of it and explains it in a sentence or two. It opens by itself the first time someone reaches a
 * region (remembered in the browser) and again from the "?" button or the command palette.
 */
export interface TourStep {
  id: string;
  title: string;
  body: React.ReactNode;
  /** CSS selector of what to point at; every visible match is outlined together. Without one the card is centred. */
  target?: string;
  /** Marks the recently added features. */
  isNew?: boolean;
}

const SEEN_KEY = "phoenical.tour.seen";
/** True once the tour was shown in this browser. Blocked storage counts as seen, so it never nags. */
export const tourSeen = () => {
  try {
    return localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true;
  }
};
const markSeen = () => {
  try {
    localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // storage blocked: the tour just isn't remembered
  }
};

export const TOUR_STEPS: TourStep[] = [
  {
    id: "welcome",
    title: "Welcome to Phoenical",
    body: (
      <>
        <p>Twenty-five years of NASA satellite fire detections, merged into one consistent record you can explore by place and by time.</p>
        <p>This short tour shows where everything is.</p>
      </>
    ),
  },
  {
    id: "pages",
    target: ".sb-nav",
    title: "The pages",
    body: (
      <p>
        <b>Overview</b> is the map. <b>Calendar</b> shows every month of every year at once. <b>Trends</b> compares years and seasons. <b>Forecast</b>,{" "}
        <b>Weather</b> and <b>Methods</b> are right below.
      </p>
    ),
  },
  {
    id: "sensors",
    target: ".sensor-seg",
    title: "Three views of the record",
    body: (
      <p>
        MODIS and VIIRS are two satellite sensors that see fires differently. <b>Harmonized</b> converts everything to one scale, so 2003 can be compared with
        2023. Start there.
      </p>
    ),
  },
  {
    id: "time",
    target: ".period-seg, .topbar-controls .stepper",
    title: "One time control",
    isNew: true,
    body: (
      <p>
        Pick <b>Month</b>, <b>Year</b> or <b>All</b> to set what the map shows. The arrows then move one month or one year at a time, and the map and the
        numbers change together.
      </p>
    ),
  },
  {
    id: "map",
    target: ".stage .map-tools",
    title: "The map",
    body: (
      <p>
        Each column is a grid cell of about 6 km: taller and brighter means more fire-days. With these tools you can draw a box or a shape around your own
        area, switch the 3D view, or go full screen.
      </p>
    ),
  },
  {
    id: "normal",
    target: ".stage .cvm-card",
    title: "This month vs normal",
    body: <p>Compares the selected month with the same month in every other year: how far above or below the usual level it is, and where it ranks.</p>,
  },
  {
    id: "timeline",
    target: ".timeline",
    title: "The timeline",
    body: <p>Press play to watch the whole record, or drag to jump to any month.</p>,
  },
  {
    id: "live",
    target: ".live-pill",
    title: "Live data",
    isNew: true,
    body: <p>New detections arrive from NASA every 15 minutes. The current month is still filling in, so it is marked as partial.</p>,
  },
  {
    id: "forecast",
    target: '.sb-nav a[href^="#/forecast"]',
    title: "Burning outlook",
    isNew: true,
    body: (
      <p>A forecast of the next six months, with a likely range and how accurate it has been on years it never saw. Forecast months also show on the calendar.</p>
    ),
  },
  {
    id: "assistant",
    target: ".chat-launcher",
    title: "Ask the assistant",
    isNew: true,
    body: <p>Ask a question in plain words about what is on screen, for example why a month stands out.</p>,
  },
  {
    id: "search",
    target: ".search-pill",
    title: "Search, share and export",
    body: (
      <p>
        Search ({MOD_KEY} K) jumps to any page, region, year or action. At the top right you can copy a link to exactly this view and export the data or the
        charts.
      </p>
    ),
  },
  {
    id: "account",
    target: ".sb-foot",
    title: "Optional: save your areas",
    body: (
      <>
        <p>Sign in to save areas and get an email when burning there is unusually high. Everything else works without an account.</p>
        <p>
          That's it. The <b>?</b> button at the top of the sidebar opens this tour again.
        </p>
      </>
    ),
  },
];

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** What a selector points at right now: the box around every match that is on screen. */
function visibleMatches(selector: string): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const el of document.querySelectorAll<HTMLElement>(selector)) {
    const q = el.getBoundingClientRect();
    if (q.width < 2 || q.height < 2) continue; // hidden page or collapsed control
    if (q.right <= 0 || q.left >= window.innerWidth) continue; // off-canvas (the phone sidebar)
    if (getComputedStyle(el).visibility === "hidden") continue;
    out.push(el);
  }
  return out;
}

function boxOf(selector?: string): Box | null {
  if (!selector) return null;
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity;
  for (const el of visibleMatches(selector)) {
    const q = el.getBoundingClientRect();
    l = Math.min(l, q.left);
    t = Math.min(t, q.top);
    r = Math.max(r, q.right);
    b = Math.max(b, q.bottom);
  }
  return l === Infinity ? null : { left: l, top: t, width: r - l, height: b - t };
}

const sameBox = (a: Box | null, b: Box | null) =>
  a === b || (!!a && !!b && Math.abs(a.left - b.left) < 0.5 && Math.abs(a.top - b.top) < 0.5 && Math.abs(a.width - b.width) < 0.5 && Math.abs(a.height - b.height) < 0.5);

const GAP = 14; // between the outlined part and the card
const EDGE = 12; // between the card and the window edge
const PAD = 6; // outline around the part

/** Where the card goes: beside the outlined part on the roomiest side, else over its lower half. */
function place(box: Box | null, w: number, h: number): { left: number; top: number } {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const clampX = (x: number) => Math.max(EDGE, Math.min(vw - w - EDGE, x));
  const clampY = (y: number) => Math.max(EDGE, Math.min(vh - h - EDGE, y));
  if (!box) return { left: clampX((vw - w) / 2), top: clampY((vh - h) / 2) };
  const cx = box.left + box.width / 2;
  const cy = box.top + box.height / 2;
  const sides = [
    { room: vw - (box.left + box.width) - GAP - EDGE, need: w, at: { left: box.left + box.width + PAD + GAP, top: clampY(cy - h / 2) } },
    { room: box.left - GAP - EDGE, need: w, at: { left: box.left - PAD - GAP - w, top: clampY(cy - h / 2) } },
    { room: vh - (box.top + box.height) - GAP - EDGE, need: h, at: { left: clampX(cx - w / 2), top: box.top + box.height + PAD + GAP } },
    { room: box.top - GAP - EDGE, need: h, at: { left: clampX(cx - w / 2), top: box.top - PAD - GAP - h } },
  ].filter((s) => s.room >= s.need + PAD);
  if (sides.length) return sides.sort((a, b) => b.room - b.need - (a.room - a.need))[0].at;
  return { left: clampX(cx - w / 2), top: clampY(box.top + box.height - h - GAP) };
}

interface Props {
  steps?: TourStep[];
  onClose: () => void;
}

export function Tour({ steps = TOUR_STEPS, onClose }: Props) {
  // Parts that are not on screen (no live data for this region, the assistant switched off, the
  // sidebar tucked away on a phone) are left out when the tour opens.
  const [list] = useState(() => steps.filter((s) => !s.target || boxOf(s.target)));
  const [i, setI] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  const step = list[i];
  const last = i === list.length - 1;

  const close = useCallback(() => {
    markSeen();
    onClose();
  }, [onClose]);
  const go = useCallback(
    (d: number) => {
      if (d > 0 && i === list.length - 1) return close();
      setI(Math.max(0, Math.min(list.length - 1, i + d)));
    },
    [i, list.length, close],
  );

  // Remembered as soon as it has been shown, so a reload mid-tour doesn't start it again.
  useEffect(markSeen, []);

  // Bring the part into view, then keep the outline on it while the page settles or resizes.
  useLayoutEffect(() => {
    if (step.target) {
      const el = visibleMatches(step.target)[0];
      const q = el?.getBoundingClientRect();
      if (el && q && (q.top < 0 || q.bottom > window.innerHeight)) el.scrollIntoView({ block: "center" });
    }
    const measure = () => {
      const next = boxOf(step.target);
      setBox((prev) => (sameBox(prev, next) ? prev : next));
    };
    measure();
    const t = window.setInterval(measure, 250);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearInterval(t);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step]);

  useLayoutEffect(() => {
    const el = card.current;
    if (el) setPos(place(box, el.offsetWidth, el.offsetHeight));
  }, [box, step]);

  useEffect(() => {
    primary.current?.focus({ preventScroll: true });
  }, [step]);

  // Keys work wherever the focus is, and never reach the page underneath (its arrows change the month).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") go(1);
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "Tab") {
        // Keep the focus inside the card.
        const f = [...(card.current?.querySelectorAll<HTMLElement>("button") ?? [])];
        if (!f.length) return;
        const at = f.indexOf(document.activeElement as HTMLElement);
        f[(at + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      } else return;
      e.preventDefault();
      e.stopImmediatePropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [close, go]);

  return (
    <div className="tour">
      {box ? (
        <div className="tour-spot" style={{ left: box.left - PAD, top: box.top - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 }} aria-hidden />
      ) : (
        <div className="tour-dim" aria-hidden />
      )}
      <div
        ref={card}
        className="tour-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: "hidden" }}
      >
        <div className="tour-head">
          <span className="eyebrow">
            Step {i + 1} of {list.length}
          </span>
          {step.isNew && <span className="tour-new">New</span>}
          <button className="icon-btn tour-close" onClick={close} aria-label="Close the tour">
            ✕
          </button>
        </div>
        <h2 id="tour-title">{step.title}</h2>
        <div id="tour-body" className="tour-body" aria-live="polite">
          {step.body}
        </div>
        <div className="tour-progress" aria-hidden>
          {list.map((s, k) => (
            <i key={s.id} className={k === i ? "is-on" : k < i ? "is-done" : ""} />
          ))}
        </div>
        <div className="tour-actions">
          {!last && (
            <button className="btn btn-ghost tour-skip" onClick={close}>
              Skip
            </button>
          )}
          {i > 0 && (
            <button className="btn btn-ghost" onClick={() => go(-1)}>
              Back
            </button>
          )}
          <button ref={primary} className="btn btn-primary" onClick={() => go(1)}>
            {last ? "Done" : i === 0 ? "Start the tour" : "Next"}
          </button>
        </div>
      </div>
    </div>
  );
}
