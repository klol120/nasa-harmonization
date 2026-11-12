"""Resumable FIRMS downloader.

Commands:
  archives            download yearly country archives and build region-year files
  api --start --end   pull a date range via the area API for every region
  manifest            write data/raw/MANIFEST.md

The MAP_KEY is read from .env (FIRMS_MAP_KEY) and is redacted from every log line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
BASE = "https://firms.modaps.eosdis.nasa.gov"
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
DL = CFG["download"]
RAW = ROOT / DL["raw_dir"]

log = logging.getLogger("firms")
_SECRET: str | None = None


def redact(text: str) -> str:
    return text.replace(_SECRET, "<KEY>") if _SECRET else text


def map_key() -> str:
    key = dotenv_values(ROOT / ".env").get("FIRMS_MAP_KEY")
    if not key:
        sys.exit("FIRMS_MAP_KEY missing from .env")
    return key


class Redact(logging.Filter):
    def __init__(self, secret: str | None):
        super().__init__()
        self.secret = secret

    def filter(self, record):
        if self.secret:
            record.msg = str(record.msg).replace(self.secret, "<KEY>")
        return True


def setup_logging(secret: str | None):
    global _SECRET
    _SECRET = secret
    RAW.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for h in (logging.FileHandler(RAW / "download.log"), logging.StreamHandler()):
        h.setFormatter(fmt)
        h.addFilter(Redact(secret))
        log.addHandler(h)
    log.setLevel(logging.INFO)


def fetch(url: str, pause: float, ok_404: bool = False, header: str = "latitude") -> str | None:
    """GET with retry/backoff. Returns body, or None on 404 when ok_404."""
    for attempt in range(DL["max_retries"]):
        try:
            r = requests.get(url, timeout=120)
            log.info(f"GET {url} -> {r.status_code} {len(r.content)}B")
            time.sleep(pause)
            if r.status_code == 404 and ok_404:
                return None
            if r.status_code == 200 and r.text.startswith(header):
                return r.text
            if r.status_code == 200 and r.text.strip() == "":
                return ""
            log.warning(f"unexpected response: {r.text[:120]!r}")
            if "Invalid" in r.text:
                raise RuntimeError(redact(f"API rejected request: {r.text[:120]}"))
        except requests.RequestException as e:
            log.warning(f"error {e!r}")
        wait = 2 ** (attempt + 1)
        log.info(f"retry in {wait}s")
        time.sleep(wait)
    raise RuntimeError(redact(f"giving up on {url}"))


def write_atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(text)
    tmp.replace(path)


def in_bbox(df: pd.DataFrame, bbox) -> pd.Series:
    w, s, e, n = bbox
    return df.latitude.between(s, n) & df.longitude.between(w, e)


# ---------- archives ----------

def archive_path(source: str, country: str, year: int) -> Path:
    return RAW / "archive" / source / f"{country}_{year}.csv"


def download_archives():
    countries = sorted({c for r in CFG["regions"].values() for c in r["countries"]})
    for source, s in DL["sources"].items():
        p = s["archive_prefix"]
        for year in range(s["first_year"], DL["archive_last_year"] + 1):
            for c in countries:
                path = archive_path(source, c, year)
                missing = path.with_suffix(".missing")
                if path.exists() or missing.exists():
                    continue
                url = f"{BASE}/data/country/{p}/{year}/{p}_{year}_{c}.csv"
                body = fetch(url, DL["archive_pause_s"], ok_404=True)
                if body is None:
                    write_atomic(missing, f"404 {url}\n")
                else:
                    write_atomic(path, body)
    build_region_files()


def build_region_files():
    for region, r in CFG["regions"].items():
        for source, s in DL["sources"].items():
            for year in range(s["first_year"], DL["archive_last_year"] + 1):
                out = RAW / region / f"{source}_{year}.csv"
                if out.exists():
                    continue
                parts = []
                for c in r["countries"]:
                    path = archive_path(source, c, year)
                    if path.exists() and path.stat().st_size > 0:
                        df = pd.read_csv(path, dtype={"acq_time": str})
                        df["country"] = c
                        parts.append(df)
                if not parts:
                    log.warning(f"{region} {source} {year}: no archive files")
                    continue
                df = pd.concat(parts, ignore_index=True)
                keep = in_bbox(df, r["bbox"])
                if (~keep).any():
                    log.info(f"{region} {source} {year}: clipped {(~keep).sum()} rows outside bbox")
                out.parent.mkdir(parents=True, exist_ok=True)
                df[keep].to_csv(out.with_suffix(".part"), index=False)
                out.with_suffix(".part").replace(out)
                log.info(f"wrote {out.relative_to(ROOT)} rows={keep.sum()}")


# ---------- area API ----------

def availability(key: str) -> dict:
    body = fetch(f"{BASE}/api/data_availability/csv/{key}/all", 0, header="data_id")
    df = pd.read_csv(io.StringIO(body))
    return {r.data_id: (r.min_date, r.max_date) for r in df.itertuples()}


def throttle(key: str):
    try:
        st = requests.get(f"{BASE}/mapserver/mapkey_status/?MAP_KEY={key}", timeout=60).json()
    except Exception as e:
        log.warning(redact(f"mapkey_status failed: {e!r}"))
        return
    log.info(f"mapkey_status: {st.get('current_transactions')}/{st.get('transaction_limit')}")
    used = st.get("current_transactions", 0)
    if used > 0.8 * st.get("transaction_limit", 5000):
        log.info(f"{used} transactions used; sleeping 10 min")
        time.sleep(600)


def pull_api(key: str, start: dt.date, end: dt.date, regions: list[str]):
    avail = availability(key)
    step = DL["api_day_range"]
    n = 0
    for region in regions:
        bbox = ",".join(f"{v:.2f}" for v in CFG["regions"][region]["bbox"])
        for source in DL["sources"]:
            last = min(end, dt.date.fromisoformat(avail[source][1]))
            d = start
            while d <= last:
                days = min(step, (last - d).days + 1)
                chunk = RAW / "api" / region / source / f"{d}_{days}d.csv"
                if not chunk.exists():
                    if n % 50 == 0:
                        throttle(key)
                    url = f"{BASE}/api/area/csv/{key}/{source}/{bbox}/{days}/{d}"
                    write_atomic(chunk, fetch(url, DL["api_pause_s"]))
                    n += 1
                d += dt.timedelta(days=days)
    log.info(f"api: {n} new requests")


def assemble_api_year(year: int):
    """Build data/raw/{region}/{source}_{year}_api.csv from API chunks, clipped to the
    archive footprint: country-tagged (tools/footprint.py) and limited to the region's
    countries, so every year covers the same area."""
    from footprint import tag_country

    for region, r in CFG["regions"].items():
        for source in DL["sources"]:
            chunks = sorted((RAW / "api" / region / source).glob(f"{year}-*.csv"))
            dfs = [pd.read_csv(c, dtype={"acq_time": str}) for c in chunks if c.stat().st_size > 0]
            if not dfs:
                continue
            df = pd.concat(dfs, ignore_index=True).drop_duplicates(ignore_index=True)
            df["country"] = tag_country(df, CFG["footprint"]["max_sea_km"])
            keep = df.country.isin(r["countries"])
            dropped = df.country[~keep].fillna("<sea>").value_counts().to_dict()
            out = RAW / region / f"{source}_{year}_api.csv"
            df[keep].to_csv(out, index=False)
            log.info(f"wrote {out.relative_to(ROOT)} rows={keep.sum()} from {len(chunks)} chunks; "
                     f"dropped outside footprint: {dropped}")


# ---------- manifest ----------

def write_manifest():
    rows = []
    for f in sorted(RAW.glob("*/*_*.csv")):
        if f.parent.name in ("archive", "api"):
            continue
        df = pd.read_csv(f, usecols=["acq_date", "country"])
        parts = f.stem.split("_")
        api = parts[-1] == "api"
        year = int(parts[-2] if api else parts[-1])
        source = "_".join(parts[:-2] if api else parts[:-1])
        rows.append(dict(region=f.parent.name, source=source, year=year,
                         origin="area API" if api else "country archive",
                         rows=len(df), first=df.acq_date.min(), last=df.acq_date.max(),
                         by_country=df.country.value_counts().to_dict()))
    m = pd.DataFrame(rows)
    missing = sorted(p.stem for p in (RAW / "archive").rglob("*.missing"))
    lines = [
        "# Raw data manifest",
        "",
        f"Generated {dt.date.today()} by `tools/download_firms.py`. Request log: `download.log` (key redacted).",
        "",
        "## Sources",
        "- `MODIS_SP`: MODIS Collection 6.1 standard processing (Terra + Aqua), 1 km.",
        "- `VIIRS_SNPP_SP`: VIIRS S-NPP 375 m standard processing.",
        f"- Country archives (full years {min(s['first_year'] for s in DL['sources'].values())}"
        f"-{DL['archive_last_year']}): `{BASE}/data/country/{{prefix}}/{{year}}/{{prefix}}_{{year}}_{{Country}}.csv`."
        " Verbatim copies in `archive/{source}/{Country}_{year}.csv`.",
        f"- Area API ({DL['api_year']}): `{BASE}/api/area/csv/<KEY>/{{source}}/{{bbox}}/{DL['api_day_range']}/{{date}}`."
        " Verbatim chunks in `api/{region}/{source}/`.",
        "",
        "## Regions",
        "| region | bbox (W,S,E,N) | archive countries |",
        "|---|---|---|",
    ]
    for k, r in CFG["regions"].items():
        lines.append(f"| {k} | {', '.join(f'{v:.2f}' for v in r['bbox'])} | {', '.join(r['countries'])} |")
    lines += [
        "",
        "Region files `{region}/{source}_{year}.csv` = the listed countries' archive files concatenated, "
        "clipped to the bbox, with an added `country` column. "
        "`{region}/{source}_{year}_api.csv` = API detections in the bbox, country-tagged with Natural Earth "
        "(`tools/footprint.py`) and limited to the same archive countries, so every year covers the same area.",
        "",
        "## Files",
        "| region | source | year | origin | rows | first | last |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in m.sort_values(["region", "source", "year"]).itertuples():
        lines.append(f"| {r.region} | {r.source} | {r.year} | {r.origin} | {r.rows} | {r.first} | {r.last} |")
    lines += ["", "## Totals", "| region | source | origin | rows | first | last |", "|---|---|---|---|---|---|"]
    for (reg, src, org), g in m.groupby(["region", "source", "origin"]):
        lines.append(f"| {reg} | {src} | {org} | {g.rows.sum()} | {g['first'].min()} | {g['last'].max()} |")
    ec = m[(m.region == "eastmed") & (m.origin == "country archive")]
    if len(ec):
        lines += ["", "## eastmed rows by country (archives)", "| source | country | rows |", "|---|---|---|"]
        for src, g in ec.groupby("source"):
            tot = pd.Series(dtype=int)
            for d in g.by_country:
                tot = tot.add(pd.Series(d), fill_value=0)
            for c, v in tot.astype(int).items():
                lines.append(f"| {src} | {c} | {v} |")
    lines += ["", "## Archive files not published (404)", ""]
    lines += [f"- {m}" for m in missing] or ["- none"]
    notes = RAW / "MANIFEST_NOTES.md"
    if notes.exists():
        lines += ["", notes.read_text()]
    (RAW / "MANIFEST.md").write_text("\n".join(lines) + "\n")
    log.info("wrote MANIFEST.md")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("archives")
    a = sub.add_parser("api")
    a.add_argument("--start", type=dt.date.fromisoformat, required=True)
    a.add_argument("--end", type=dt.date.fromisoformat, required=True)
    a.add_argument("--regions", nargs="+", default=list(CFG["regions"]))
    a.add_argument("--assemble", action="store_true", help="also build {source}_{year}_api.csv")
    sub.add_parser("manifest")
    args = ap.parse_args()

    key = map_key() if args.cmd == "api" else None
    setup_logging(key)
    try:
        run(args, key)
    except Exception as e:
        sys.exit(redact(f"{type(e).__name__}: {e}"))


def run(args, key):
    if args.cmd == "archives":
        download_archives()
    elif args.cmd == "api":
        pull_api(key, args.start, args.end, args.regions)
        if args.assemble:
            assemble_api_year(args.start.year)
    else:
        write_manifest()


if __name__ == "__main__":
    main()
