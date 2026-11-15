"""Development-only NASA environmental comparison; does not fit fire models."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import km_distance

WEATHER = ["T2M", "T2M_MAX", "RH2M", "PRECTOTCORR"]
TERRAIN = ["elevation_m", "slope_deg", "vegetation_fraction"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def weather_weights(weather, cells):
    """Equal eligible-cell weights assigned to their nearest actual weather point."""
    points = weather[["weather_point_id", "lat", "lon"]].drop_duplicates()
    if points.weather_point_id.duplicated().any() or cells.cell_id.duplicated().any():
        raise ValueError("Ambiguous weather points or duplicate cells")
    if len(points) == 0 or len(cells) == 0:
        raise ValueError("Empty environmental domain")
    if not np.isfinite(points[["lat", "lon"]].to_numpy()).all():
        raise ValueError("Invalid coordinates")
    assignments = []
    for cell in cells.itertuples():
        d = km_distance(points.lat, points.lon, cell.lat, cell.lon)
        assignments.append(points.loc[d.idxmin(), "weather_point_id"])
    weights = pd.Series(assignments).value_counts(normalize=True)
    return weights


def profile(weather, cells, start, end):
    """Select dates before any statistic; never reads labels or model scores."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.month != 1 or start.day != 1 or end.month != 1 or end.day != 1 or end <= start:
        raise ValueError("Profiles require complete calendar years")
    dates = pd.to_datetime(weather.date)
    w = weather.loc[(dates >= start) & (dates < end)].copy()
    w["date"] = dates.loc[w.index]
    weights = weather_weights(w, cells)
    w = w[w.weather_point_id.isin(weights.index)].copy()
    if w.duplicated(["weather_point_id", "date"]).any():
        raise ValueError("Duplicate point-day")
    expected = pd.date_range(start, end - pd.Timedelta(days=1), freq="D")
    for _, group in w.groupby("weather_point_id"):
        if not pd.DatetimeIndex(group.date.sort_values()).equals(expected):
            raise ValueError("Incomplete development weather history")
    if not np.isfinite(w[WEATHER].to_numpy()).all() or (w.PRECTOTCORR < 0).any():
        raise ValueError("Missing or invalid weather values")
    if not np.isfinite(cells[TERRAIN].to_numpy()).all():
        raise ValueError("Missing terrain or vegetation")
    w["weight"] = w.weather_point_id.map(weights)
    daily = w[WEATHER].multiply(w.weight, axis=0).groupby(w.date).sum()
    monthly = daily.groupby([daily.index.year, daily.index.month]).agg(
        temperature_c=("T2M", "mean"), maximum_temperature_c=("T2M_MAX", "mean"),
        humidity_pct=("RH2M", "mean"), monthly_rain_mm=("PRECTOTCORR", "sum"),
    ).groupby(level=1).mean().reindex(range(1, 13))
    terrain = {column + "_mean": float(cells[column].mean()) for column in TERRAIN}
    terrain.update({column + "_std": float(cells[column].std(ddof=0)) for column in TERRAIN})
    summary = {
        "eligible_cells": len(cells), "used_weather_points": len(weights),
        "development_point_days": len(w),
        "annual_temperature_c": float(daily.T2M.mean()),
        "annual_rain_mm": float(daily.PRECTOTCORR.sum() / (end.year - start.year)),
        "summer_rain_mm": float(monthly.loc[[6, 7, 8], "monthly_rain_mm"].sum()),
        "winter_rain_mm": float(monthly.loc[[12, 1, 2], "monthly_rain_mm"].sum()),
        "summer_temperature_c": float(monthly.loc[[6, 7, 8], "temperature_c"].mean()),
        "winter_temperature_c": float(monthly.loc[[12, 1, 2], "temperature_c"].mean()),
        **terrain,
    }
    return {"summary": summary, "monthly": monthly.reset_index(names="month").to_dict("records")}


def distances(profiles, target, candidates, block_weights):
    if target in candidates or len(set(candidates)) != len(candidates):
        raise ValueError("Target must not enter source standardization")
    weights = np.asarray(block_weights, float)
    if weights.shape != (4,) or not np.isfinite(weights).all() or (weights < 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError("Invalid block weights")
    blocks = {}
    for name, p in profiles.items():
        monthly = pd.DataFrame(p["monthly"])
        blocks[name] = [monthly[c].to_numpy(float) for c in ["temperature_c", "monthly_rain_mm", "humidity_pct"]]
        blocks[name].append(np.asarray([p["summary"][c + suffix] for c in TERRAIN for suffix in ["_mean", "_std"]]))
    components = {name: [] for name in candidates}
    for block in range(4):
        source = np.stack([blocks[name][block] for name in candidates])
        scale = source.std(axis=0)
        # Constant dimensions do not identify relative similarity; omit them.
        use = scale > 1e-10
        for name in candidates:
            delta = (blocks[name][block][use] - blocks[target][block][use]) / scale[use]
            components[name].append(float(np.sqrt(np.mean(delta ** 2))) if use.any() else 0.)
    return sorted([
        {"region": name, "standardized_distance": float(np.dot(values, weights)),
         "block_distances": dict(zip(["temperature", "rain", "humidity", "terrain_vegetation"], values))}
        for name, values in components.items()
    ], key=lambda row: row["standardized_distance"])


def run(config_path, root, output):
    root = Path(root)
    config = json.loads(Path(config_path).read_text())
    candidates = config["candidate_panels"]
    global_weather = root / "data/global-weather/weather.csv.gz"
    local_weather = root / "data/nasa-lebanon/weather_historical.csv"
    global_report = json.loads((global_weather.parent / "weather-report.json").read_text())
    if not global_report["complete"] or digest(global_weather) != global_report["data_sha256"]:
        raise ValueError("NASA weather archive integrity failed")
    source_paths = [Path(config_path), global_weather, local_weather]
    parts = []
    for chunk in pd.read_csv(global_weather, usecols=["date", "weather_point_id", "lat", "lon", "weather_region", *WEATHER], chunksize=50000):
        use = chunk.weather_region.isin(candidates) & chunk.date.ge(config["development_start"]) & chunk.date.lt(config["development_end_exclusive"])
        parts.append(chunk.loc[use])
    global_frame = pd.concat(parts, ignore_index=True)
    profiles = {}
    for region in [*candidates, config["target_region"]]:
        path = root / ("outputs/noaa20-real/cells.csv" if region == config["target_region"] else "data/global-panel/static/" + region + "-cells.csv")
        source_paths.append(path)
        cells = pd.read_csv(path)
        weather = pd.read_csv(local_weather) if region == config["target_region"] else global_frame[global_frame.weather_region.eq(region)]
        profiles[region] = profile(weather, cells, config["development_start"], config["development_end_exclusive"])
    report = {
        "purpose": "Exploratory environmental similarity, not fire-model performance or evidence of transfer benefit",
        "period": [config["development_start"], config["development_end_exclusive"]],
        "weighting": "Equal eligible grid cells; nearest NASA POWER point; no ocean point without an assigned cell",
        "profiles": profiles,
        "distances": distances(profiles, config["target_region"], candidates, config["distance_block_weights"]),
        "sources_sha256": {str(p.relative_to(root) if p.is_relative_to(root) else p): digest(p) for p in source_paths},
        "fire_labels_or_test_metrics_read": False,
        "limitations": ["Three years of weather, not a long-term climate classification", "Fixed two-degree panels do not represent whole countries", "Coarse weather and reprocessed 2010 static layers", "Distance weights are descriptive choices, not validated transfer weights", "Greece remains held out in existing model artifacts; future inclusion changes the protocol"],
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    plot_seasonality(report, Path(output).parent / "figures/greek-lebanon-seasonality.png")
    print(json.dumps({"profiles": {k: v["summary"] for k, v in profiles.items()}, "distances": report["distances"]}, indent=2))
    return report


def plot_seasonality(report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), layout="constrained")
    for region, label, color in [("greece", "Sampled Greek panel", "#245b9b"), ("lebanon", "Eligible Lebanese grid", "#b35122")]:
        monthly = pd.DataFrame(report["profiles"][region]["monthly"])
        axes[0].plot(monthly.month, monthly.temperature_c, "o-", label=label, color=color)
        axes[1].plot(monthly.month, monthly.monthly_rain_mm, "o-", label=label, color=color)
    for ax in axes:
        ax.set_xticks(range(1, 13), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
        ax.grid(alpha=.2)
        ax.set_xlabel("Month")
    axes[0].set_ylabel("NASA POWER mean temperature (°C)")
    axes[1].set_ylabel("NASA POWER monthly precipitation (mm)")
    axes[1].legend(frameon=False)
    fig.suptitle("2018–2020 development weather; equal eligible-cell weighting\nSelected areas and coarse weather, not whole-country climate or model skill", fontsize=10)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/greek-study-focus.json")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="docs/greek-lebanon-similarity.json")
    args = parser.parse_args()
    run(Path(args.config).resolve(), Path(args.root).resolve(), args.out)


if __name__ == "__main__":
    main()
