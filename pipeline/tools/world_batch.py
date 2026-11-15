"""World batch: add every Natural Earth country, one at a time, with `python -m firecal add-country`.

Runs in the pipeline container on Azure (data/ is a mounted file share) or on a laptop. Slow on purpose:
one country after another, paced by the FIRMS rate limits, and resumable at any point.

  1. setup      FIRMS_MAP_KEY from the environment into .env (the downloader reads it there), Natural Earth
                boundaries, and config.d/ and docs/reports/ moved into data/ so they survive a restart.
  2. bootstrap  the base regions (lebanon, greece, eastmed): archives, this year through the area API, and
                `firecal all`. Thin countries borrow their calibration from the EastMed pool and the outage
                detection reads Greece and EastMed, so nothing else can run before this.
  3. countries  the Mediterranean and southern Europe first, then every other country by name.

It only writes export files (data/export/<region>/). It never connects to a database: loading a country
into the website is a separate, deliberate step (`firecal-db ingest <folder>` in backend/).

Restarts never redo finished work:
  - data/world_batch.json records every country as done or failed; those are skipped;
  - the downloader skips every archive file and API chunk already in data/raw, so an interrupted download
    continues where it stopped;
  - a country that was running when the container died gets one more try (the restart may have had nothing
    to do with it); if it dies again (usually out of memory) it is marked failed, so one large country
    cannot block the rest;
  - the base-region step is tried at most MAX_BOOTSTRAP_TRIES times.
When everything is done, or the base regions cannot be prepared, the script exits with code 0: with the
container's restart policy "on failure" the container then stops, and so does its cost.

    python tools/world_batch.py              # run / resume
    python tools/world_batch.py --status
    python tools/world_batch.py --retry-failed

Settings (environment): FIRMS_MAP_KEY; WORLD_PAUSE_S (default 60) between countries; WORLD_ONLY, a
comma-separated list of countries to limit a run to.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATE = DATA / "world_batch.json"
LOG = DATA / "world_batch.log"
NE_ZIP = DATA / "ext" / "ne_10m_admin_0_countries.zip"
NE_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"
BASE_REGIONS = ["greece", "eastmed", "lebanon"]
TIMEOUT_S = 6 * 3600
MAX_TRIES = 2            # per country: a second interrupted run marks it failed
MAX_BOOTSTRAP_TRIES = 3

# The Mediterranean and southern Europe first (where the method was validated), then everything else.
FIRST = ["Cyprus", "Jordan", "Portugal", "Syria", "Turkey", "Spain", "Italy", "France", "Croatia", "Albania",
         "Montenegro", "Bosnia and Herzegovina", "North Macedonia", "Bulgaria", "Israel", "Palestine", "Egypt", "Libya",
         "Tunisia", "Algeria", "Morocco", "Iraq", "Romania", "Republic of Serbia", "Slovenia", "Malta"]
# Covered by a base region of the same name.
SKIP = {"Antarctica", "Greece", "Lebanon"}


def slug(country: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", country.lower()).strip("_")


def say(msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S}Z {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(state: dict) -> None:
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(STATE)


def keep_in_data(folder: Path, name: str) -> None:
    """Keep `folder` inside data/ (the mounted volume) and leave a link in its place."""
    target = DATA / name
    if folder.is_symlink():
        return
    target.mkdir(parents=True, exist_ok=True)
    if folder.is_dir():
        for f in folder.rglob("*"):
            dst = target / f.relative_to(folder)
            if f.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)
        shutil.rmtree(folder)
    folder.symlink_to(target, target_is_directory=True)


def setup() -> None:
    DATA.mkdir(exist_ok=True)
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    env = ROOT / ".env"
    if key and not env.exists():
        env.write_text(f"FIRMS_MAP_KEY={key}\n")
        env.chmod(0o600)
    if not env.exists():
        sys.exit("FIRMS_MAP_KEY is not set (environment or pipeline/.env)")
    if os.environ.get("WORLD_KEEP_IN_DATA", "1") == "1":
        keep_in_data(ROOT / "config.d", "config.d")
        keep_in_data(ROOT / "docs" / "reports", "reports")
    if not NE_ZIP.exists():
        NE_ZIP.parent.mkdir(parents=True, exist_ok=True)
        tmp = NE_ZIP.with_suffix(".part")
        urllib.request.urlretrieve(NE_URL, tmp)
        tmp.replace(NE_ZIP)
        say("fetched the Natural Earth boundaries")


def run(args: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT_S} s"
    last = ((r.stderr or r.stdout).strip().splitlines() or [""])[-1]
    return r.returncode == 0, last[-300:]


def resume(state: dict, max_tries: int = MAX_TRIES) -> list[str]:
    """After a restart: countries that were running when the process died. One that has used all its tries
    is marked failed; the others are cleared so they run again. Returns the ones marked failed."""
    failed = []
    for c in [c for c, s in state.items() if not c.startswith("_") and s.get("ok") is None]:
        tries = state[c].get("tries", 1)
        if tries >= max_tries:
            state[c] = {"ok": False, "tries": tries,
                        "why": f"the run stopped {tries} times while this country was being processed (out of memory?)"}
            failed.append(c)
    return failed


def bootstrap(state: dict) -> bool | None:
    """True: ready. False: failed, try again after a restart. None: gave up."""
    b = state.get("_bootstrap", {})
    if b.get("ok"):
        return True
    tries = b.get("tries", 0) + 1
    if tries > MAX_BOOTSTRAP_TRIES:
        say(f"bootstrap failed {MAX_BOOTSTRAP_TRIES} times ({b.get('why', '')}); giving up. Fix it, then --retry-failed")
        return None
    state["_bootstrap"] = {"ok": False, "tries": tries, "why": "interrupted"}
    write_state(state)
    say(f"bootstrap (try {tries}): preparing the base regions {BASE_REGIONS}")
    t = time.time()
    today = dt.datetime.now(dt.timezone.utc).date()
    steps = [
        ["tools/download_firms.py", "archives", "--regions", *BASE_REGIONS],
        ["tools/download_firms.py", "api", "--start", f"{today.year}-01-01", "--end", str(today), "--regions", *BASE_REGIONS, "--assemble"],
        ["-m", "firecal", "all", "--region", *BASE_REGIONS],
    ]
    for args in steps:
        ok, why = run(args)
        if not ok:
            say(f"bootstrap FAILED at {' '.join(args[:3])}: {why}")
            state["_bootstrap"] = {"ok": False, "tries": tries, "why": why}
            write_state(state)
            return False
    state["_bootstrap"] = {"ok": True, "tries": tries, "seconds": round(time.time() - t)}
    write_state(state)
    say(f"bootstrap done in {state['_bootstrap']['seconds']} s")
    return True


def countries() -> list[str]:
    import geopandas as gpd

    names = sorted(set(gpd.read_file(NE_ZIP).ADMIN) - SKIP)
    only = [c.strip() for c in os.environ.get("WORLD_ONLY", "").split(",") if c.strip()]
    if only:
        return [c for c in only if c in names]
    return [c for c in FIRST if c in names] + [c for c in names if c not in FIRST]


def status(state: dict) -> None:
    done = [c for c, s in state.items() if not c.startswith("_") and s.get("ok")]
    failed = {c: s.get("why", "")[:100] for c, s in state.items() if not c.startswith("_") and s.get("ok") is False}
    print(f"bootstrap: {state.get('_bootstrap', 'not run')}")
    print(f"{len(done)} done, {len(failed)} failed, {len(countries()) - len(done) - len(failed)} to go")
    for c, why in failed.items():
        print(f"  failed {c}: {why}")


def main() -> None:
    setup()
    state = read_state()
    if "--status" in sys.argv:
        return status(state)
    if "--retry-failed" in sys.argv:
        state = {c: s for c, s in state.items() if s.get("ok")}
    for c in resume(state):
        say(f"FAILED {c}: {state[c]['why']}")
    write_state(state)
    ready = bootstrap(state)
    if ready is None:
        return  # exit 0: the container stops instead of restarting for nothing
    if not ready:
        time.sleep(600)  # not a tight restart loop
        sys.exit(1)
    pause = int(os.environ.get("WORLD_PAUSE_S", "60"))
    for country in countries():
        s = state.get(country, {})
        if s.get("ok") is not None:
            continue  # done or failed earlier: never redone
        tries = s.get("tries", 0) + 1
        say(f"start {country}" + (f" (try {tries})" if tries > 1 else ""))
        t = time.time()
        state[country] = {"ok": None, "tries": tries, "started": dt.datetime.now(dt.timezone.utc).isoformat()}
        write_state(state)
        ok, why = run(["-m", "firecal", "add-country", country, "--no-backend"])
        state[country] = {"ok": ok, "tries": tries, "why": why, "seconds": round(time.time() - t)}
        write_state(state)
        say(f"{'done' if ok else 'FAILED'} {country} in {state[country]['seconds']} s: {why[-160:]}")
        time.sleep(pause)
    say("world batch finished")


if __name__ == "__main__":
    main()
