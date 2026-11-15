"""Container entrypoint (docker compose): keep data/ current and the exports fresh.

  seed  Fast, runs before the API starts. Copies the exports committed in git (mounted at /seed) into the data
        volume for every region whose volume copy is missing or older, and fetches the Natural Earth boundaries
        the pipeline needs. So the website always has data, even before the first pipeline run finishes.
  run   Downloads any missing FIRMS country archives, pulls this year's data through the area API up to
        yesterday (UTC), extends config `coverage` to what FIRMS now serves (config.d/zz_live_coverage.yaml,
        written inside the container only), and reruns `firecal all` for every region. It then writes
        data/pipeline_status.json, which tells the API to load the new exports.
  schedule
        `run` once if it never finished, then on day SCHEDULE_DAY (default 1) of every month at
        SCHEDULE_HOUR_UTC (default 3). A run missed while the machine was off runs at the next start; a run
        that failed is retried after SCHEDULE_RETRY_HOURS (default 6); an interrupted one right away.
        State: data/schedule.json (in the volume, so deleting the volume means a fresh first run).

Settings (environment): FIRMS_MAP_KEY (without it the committed exports are served), PIPELINE_RUN=0 to skip runs.
The key is never printed: the downloader redacts it, and this script only passes it through the environment.
Reports (validation, anomalies, ...) go to data/reports instead of docs/reports, so they are kept in the volume.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from firecal.config import as_date, load_config  # noqa: E402

DATA = ROOT / "data"
EXPORT = DATA / "export"
SEED = Path(os.environ.get("SEED_DIR", "/seed"))
OVERLAY = ROOT / "config.d" / "zz_live_coverage.yaml"
PATHS_OVERLAY = ROOT / "config.d" / "zz_container_paths.yaml"
STATUS = DATA / "pipeline_status.json"
STATE = DATA / "schedule.json"
UTC = dt.timezone.utc
NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
FIRMS = "https://firms.modaps.eosdis.nasa.gov"


def log(msg: str):
    print(f"[pipeline] {msg}", flush=True)


def generated_at(region_dir: Path) -> str:
    try:
        return json.loads((region_dir / "meta.json").read_text())["generated_at"]
    except (OSError, KeyError, ValueError):
        return ""


# ---------- seed ----------

def seed():
    EXPORT.mkdir(parents=True, exist_ok=True)
    for src in sorted(p for p in SEED.glob("*") if (p / "meta.json").exists()):
        dst = EXPORT / src.name
        if generated_at(src) > generated_at(dst):
            # Copy next to the target, then swap, so the API never sees a half-copied region.
            tmp = EXPORT / f".{src.name}.seed"
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.copytree(src, tmp)
            shutil.rmtree(dst, ignore_errors=True)
            tmp.rename(dst)
            log(f"seeded {src.name} from git (generated {generated_at(src)})")
    boundaries = ROOT / load_config()["paths"]["boundaries"]
    if not boundaries.exists():
        boundaries.parent.mkdir(parents=True, exist_ok=True)
        log("downloading Natural Earth country boundaries")
        body = fetch(NE_URL)
        zipfile.ZipFile(io.BytesIO(body)).testzip()  # fail here, not deep inside geopandas
        boundaries.with_suffix(".part").write_bytes(body)
        boundaries.with_suffix(".part").replace(boundaries)
    log("seed done")


def fetch(url: str, tries: int = 5) -> bytes:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except OSError as e:
            if i == tries - 1:
                raise
            log(f"retrying after {type(e).__name__}")
            time.sleep(5 * (i + 1))
    raise AssertionError


# ---------- run ----------

def drop_incomplete_chunks():
    """API chunks fetched while one of their days was still in progress would be reused forever by the
    downloader (it skips existing chunks), so delete them; they are fetched again, now complete."""
    n = 0
    for f in (DATA / "raw" / "api").glob("*/*/*_*d.csv"):
        start, days = f.stem.rsplit("_", 1)
        last_day = dt.date.fromisoformat(start) + dt.timedelta(days=int(days[:-1]) - 1)
        fetched = dt.datetime.fromtimestamp(f.stat().st_mtime, dt.UTC).date()
        if fetched <= last_day:
            f.unlink()
            n += 1
    if n:
        log(f"refetching {n} API chunks that were downloaded before their last day was complete")


def availability(key: str) -> dict[str, tuple[dt.date, dt.date]]:
    body = fetch(f"{FIRMS}/api/data_availability/csv/{key}/all").decode()
    rows = [line.split(",") for line in body.strip().splitlines()]
    head = rows[0]
    i, a, b = head.index("data_id"), head.index("min_date"), head.index("max_date")
    return {r[i]: (as_date(r[a]), as_date(r[b])) for r in rows[1:]}


def write_coverage_overlay(key: str, today: dt.date):
    """Extend each product's coverage end to what FIRMS serves now (never past yesterday, never shrinking).
    NRT starts the day after its SP ends, as in config.yaml. The satellite replaced by the continuation
    (S-NPP) keeps its configured end: it stopped delivering data."""
    OVERLAY.unlink(missing_ok=True)
    cfg = load_config()
    avail = availability(key)
    replaced = (cfg["sensors"].get("continuation") or {}).get("replaces")
    yesterday = today - dt.timedelta(days=1)
    cov = {k: [as_date(a), as_date(b)] for k, (a, b) in cfg["coverage"].items()}
    for src, span in cov.items():
        sat = src.split("_")[1] if src.startswith("VIIRS_") else None
        if src in avail and not (src.endswith("_NRT") and sat == replaced):
            span[1] = max(span[1], min(avail[src][1], yesterday))
    for src in [k for k in cov if k.endswith("_NRT")]:
        sp = src[: -len("_NRT")] + "_SP"
        if sp in cov:
            cov[src][0] = cov[sp][1] + dt.timedelta(days=1)
        if cov[src][0] > cov[src][1]:
            del cov[src]  # the SP product now covers everything this NRT product did
    lines = ["# Written by tools/refresh.py inside the pipeline container (not in git): coverage as FIRMS",
             f"# /api/data_availability reported on {today}. See the coverage section of config.yaml.",
             "coverage!:"]
    lines += [f"  {k}: [{a}, {b}]" for k, (a, b) in cov.items()]
    OVERLAY.write_text("\n".join(lines) + "\n")
    changed = {k: f"{cfg['coverage'][k][1]} -> {b}" for k, (a, b) in cov.items()
               if k in cfg["coverage"] and as_date(cfg["coverage"][k][1]) != b}
    log(f"coverage: {changed or 'unchanged'}")
    return cov


def step(cmd: list[str]) -> bool:
    log("$ " + " ".join(cmd))
    t = time.time()
    ok = subprocess.run([sys.executable, *cmd], cwd=ROOT).returncode == 0
    log(f"{'ok' if ok else 'FAILED'} in {time.time() - t:.0f}s")
    return ok


def disabled_reason() -> str | None:
    if os.environ.get("PIPELINE_RUN", "1") == "0":
        return "PIPELINE_RUN=0"
    if not os.environ.get("FIRMS_MAP_KEY", "").strip():
        return "FIRMS_MAP_KEY not set (see .env.example)"
    return None


def run() -> tuple[bool, str]:
    """One full refresh. Returns (finished, message); unfinished regions keep their previous release."""
    status = {"started_at": dt.datetime.now(UTC).isoformat(timespec="seconds"), "regions": {}}
    if reason := disabled_reason():
        log(f"{reason}: serving the committed exports")
        return False, reason
    key = os.environ["FIRMS_MAP_KEY"].strip()
    today = dt.datetime.now(UTC).date()
    PATHS_OVERLAY.write_text("# Written by tools/refresh.py (container only): keep reports in the data volume.\n"
                             "paths:\n  reports: data/reports\n")
    (DATA / "reports").mkdir(parents=True, exist_ok=True)
    cfg = load_config()
    if not step(["tools/download_firms.py", "archives"]):
        return False, "FIRMS archive download failed"
    drop_incomplete_chunks()
    api_year = cfg["download"]["api_year"]
    if today.year > api_year:
        log(f"warning: download.api_year is {api_year} but it is {today.year}; data after {api_year} is not "
            "fetched until config.yaml (api_year, archive_last_year, the *_{api_year}_api.csv inputs) is moved on")
    start, end = dt.date(api_year, 1, 1), min(dt.date(api_year, 12, 31), today - dt.timedelta(days=1))
    if not step(["tools/download_firms.py", "api", "--start", str(start), "--end", str(end), "--assemble"]):
        return False, "FIRMS area API download failed"
    try:
        status["coverage"] = {k: [str(a), str(b)] for k, (a, b) in write_coverage_overlay(key, today).items()}
    except OSError as e:
        return False, f"FIRMS data_availability failed ({type(e).__name__})"

    # Donor and outage-reference regions first: other regions read their intermediate files.
    regions = list(load_config()["regions"])
    first = {g["region"] for g in cfg.get("donors", {}).values()} | set(cfg["gaps"].get("reference_regions", []))
    regions.sort(key=lambda r: r not in first)
    for r in regions:
        t = time.time()
        ok = step(["-m", "firecal", "all", "--region", r])
        status["regions"][r] = {"ok": ok, "seconds": round(time.time() - t), "generated_at": generated_at(EXPORT / r)}
        if not ok:
            log(f"{r}: pipeline failed; the backend keeps serving its previous release")
    status["finished_at"] = dt.datetime.now(UTC).isoformat(timespec="seconds")
    STATUS.write_text(json.dumps(status, indent=1))  # the API watches this file and loads the new exports
    failed = [r for r, v in status["regions"].items() if not v["ok"]]
    log(f"done: {len(regions) - len(failed)}/{len(regions)} regions refreshed")
    return (not failed), ("ok" if not failed else f"failed: {', '.join(failed)}")


# ---------- schedule ----------

def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    v = int(os.environ.get(name, default))
    if not lo <= v <= hi:
        sys.exit(f"{name} must be between {lo} and {hi}, got {v}")
    return v


def slot_after(t: dt.datetime, day: int, hour: int) -> dt.datetime:
    """First scheduled time (day `day` of a month, `hour`:00 UTC) strictly after t."""
    s = dt.datetime(t.year, t.month, day, hour, tzinfo=UTC)
    if s <= t:
        y, m = (t.year + 1, 1) if t.month == 12 else (t.year, t.month + 1)
        s = dt.datetime(y, m, day, hour, tzinfo=UTC)
    return s


def due_at(state: dict, day: int, hour: int, retry: dt.timedelta, now: dt.datetime) -> dt.datetime:
    ts = {k: dt.datetime.fromisoformat(state[k]) for k in ("last_ok", "last_attempt") if state.get(k)}
    if "last_attempt" not in ts:
        return now                                            # never ran
    if state.get("last_result") == "running":
        return now                                            # interrupted (container stopped): carry on
    if "last_ok" not in ts or ts["last_attempt"] > ts["last_ok"]:
        return ts["last_attempt"] + retry                     # last run did not finish
    return slot_after(ts["last_ok"], day, hour)


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def write_state(**kw):
    s = {**read_state(), **kw}
    STATE.with_suffix(".part").write_text(json.dumps(s, indent=1))
    STATE.with_suffix(".part").replace(STATE)


def schedule():
    day = _env_int("SCHEDULE_DAY", 1, 1, 28)
    hour = _env_int("SCHEDULE_HOUR_UTC", 3, 0, 23)
    retry = dt.timedelta(hours=_env_int("SCHEDULE_RETRY_HOURS", 6, 1, 24 * 27))
    if reason := disabled_reason():
        log(f"{reason}: no pipeline runs; serving the committed exports")
        while True:          # stay up (restart: unless-stopped) without doing anything
            time.sleep(86400)
    announced = None
    while True:
        now = dt.datetime.now(UTC)
        due = due_at(read_state(), day, hour, retry, now)
        if due > now:
            if due != announced:
                log(f"next run {due:%Y-%m-%d %H:%M} UTC (schedule: day {day} of every month, {hour:02d}:00 UTC)")
                announced = due
            time.sleep(min(6 * 3600, (due - now).total_seconds()) + 1)
            continue
        write_state(last_attempt=now.isoformat(timespec="seconds"), last_result="running")
        try:
            ok, msg = run()
        except Exception as e:  # noqa: BLE001 - keep the schedule alive, retry later
            ok, msg = False, f"{type(e).__name__}: {e}"
        end = dt.datetime.now(UTC).isoformat(timespec="seconds")
        write_state(last_result=msg, **({"last_ok": end} if ok else {}))
        log("run finished" if ok else f"run did not finish ({msg}); retrying in {retry}")


if __name__ == "__main__":
    out = {"seed": seed, "run": run, "schedule": schedule}[sys.argv[1]]()
    sys.exit(0 if out is None or out[0] else 1)
