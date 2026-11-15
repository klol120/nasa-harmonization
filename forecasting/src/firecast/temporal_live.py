"""Actual GEOS + observed NASA histories for timestamp-checked temporal research output."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .forecast_features import build_features
from .transfer_forecast import augment
from .temporal_data import HistoryStore, sha
from .temporal_inference import predict


def run(root, forecast_dir, out):
    root, forecast_dir, out = Path(root), Path(forecast_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    artifact_path = root / 'outputs/greek-temporal-benchmark/research-lebanon.joblib'
    artifact = joblib.load(artifact_path)
    build_features(forecast_dir, root / 'outputs/noaa20-real/cells.csv', root / 'data/environment', out / 'base')
    frame = augment(out / 'base/forecast-features.csv', out / 'features')
    store = HistoryStore(root, artifact['config'])
    weather_path = root / 'data/greek-live-weather/weather.csv.gz'
    soil_path = root / 'data/greek-live-soil/soil.csv.gz'
    weather_report = json.loads((weather_path.parent / 'weather-report.json').read_text())
    soil_report = json.loads((soil_path.parent / 'soil-report.json').read_text())
    if sha(weather_path) != weather_report['data_sha256'] or sha(soil_path) != soil_report['sha256']:
        raise ValueError('Actual recent history source checksum mismatch')
    weather = pd.read_csv(weather_path).merge(pd.read_csv(soil_path), on=['weather_region', 'weather_point_id', 'date'], how='left', validate='one_to_one')
    store.set_weather(weather)
    tensors, feature_report = store.make(frame, keep_unqualified=True)
    np.savez_compressed(out / 'inputs.npz', sequence=tensors['sequence'], static=tensors['static'])
    metadata = frame[['cell_id', 'lat', 'lon', 'region', 'prediction_time']].copy()
    metadata['forecast_issued_at'] = frame.issue_time
    metadata['forecast_available_at'] = frame.available_at
    metadata['static_available_at'] = frame.static_available_at
    latest_history = max(pd.Timestamp(weather_report['generated_at']), pd.Timestamp(soil_report['generated_at']), pd.to_datetime(frame.history_available_at, utc=True).max())
    metadata['history_latest_available_at'] = latest_history
    available = [pd.Timestamp(json.loads(p.read_text())['downloaded_at']) for p in (root / 'data/greek-ndvi/subsets').glob('*.manifest.json')]
    metadata['vegetation_available_at'] = max(available)
    prediction = pd.to_datetime(frame.prediction_time, utc=True)
    metadata['vegetation_composite_end'] = prediction - pd.to_timedelta(tensors['static'][:, 20], unit='D')
    metadata['forecast_valid_start'] = frame.valid_start
    metadata['forecast_valid_end'] = frame.valid_end
    metadata['history_start'] = prediction.dt.normalize() - pd.Timedelta(days=artifact['config']['history_days'] + artifact['config']['history_lag_days'])
    metadata['history_end'] = prediction.dt.normalize() - pd.Timedelta(days=artifact['config']['history_lag_days'] + 1)
    metadata.to_csv(out / 'metadata.csv', index=False)
    rows = predict(artifact, tensors, metadata, research_only=True)
    for row in rows:
        row['model_sha256'] = sha(artifact_path)
        row['weather_source'] = 'NASA GEOS-FP issued forecast'
    (out / 'predictions.json').write_text(json.dumps(rows, indent=2))
    pd.DataFrame(rows).assign(flags=lambda f: f['flags'].map('|'.join)).to_csv(out / 'predictions.csv', index=False)
    export_map(rows, root, out, artifact['thresholds']['lebanon'])
    report = {'actual_issued_forecast': True, 'model_operationally_validated': False, 'model_id': artifact['id'],
              'model_sha256': sha(artifact_path), 'prediction_time': rows[0]['prediction_time'], 'window_end': rows[0]['window_end'],
              'cells': len(rows), 'probabilities_returned': sum(r['probability'] is not None for r in rows),
              'withheld_conflict_scope': sum('outside_evaluated_southern_conflict_scope' in r['flags'] for r in rows),
              'feature_report': feature_report, 'forecast_report_sha256': sha(forecast_dir / 'forecast-report.json'),
              'weather_history_sha256': sha(weather_path), 'soil_history_sha256': sha(soil_path),
              'note': 'Real future forecast inputs and timestamps; retrospective model and source-transfer/coverage limitations remain. No emergency warning or production approval.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


def export_map(rows, root, out, threshold):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch
    from shapely.geometry import shape, box, mapping
    country = shape(json.loads((Path(root) / 'data/environment/lebanon.geojson').read_text())['geometry'])
    finite = [r['probability'] for r in rows if r['probability'] is not None]
    norm = plt.Normalize(0, max([threshold, 1e-6, *finite]))
    fig, ax = plt.subplots(figsize=(6, 7))
    features = []
    for row in rows:
        i, j = map(int, row['cell_id'].split('_'))
        polygon = box(j * .1 - 180, i * .1 - 90, (j + 1) * .1 - 180, (i + 1) * .1 - 90).intersection(country)
        features.append({'type': 'Feature', 'geometry': mapping(polygon), 'properties': row})
        geoms = list(polygon.geoms) if polygon.geom_type == 'MultiPolygon' else [polygon]
        for geometry in geoms:
            if geometry.is_empty or geometry.geom_type != 'Polygon': continue
            color = '#b8b8b8' if row['probability'] is None else plt.cm.YlOrRd(norm(row['probability']))
            ax.add_patch(Patch(np.asarray(geometry.exterior.coords), facecolor=color, edgecolor='#777777', linewidth=.2))
    (Path(out) / 'predictions.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}))
    ax.set_xlim(country.bounds[0] - .1, country.bounds[2] + .1); ax.set_ylim(country.bounds[1] - .1, country.bounds[3] + .1)
    ax.set_aspect(1 / np.cos(np.radians(34)))
    ax.set_title('RESEARCH ONLY — actual NASA forecast inputs\n' + rows[0]['prediction_time'] + '\nRetrospective model; grey = withheld/missing', fontsize=10)
    ax.set_xlabel('Longitude'); ax.set_ylabel('Latitude')
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='YlOrRd'), ax=ax, label='Detected-fire probability; no approved alert categories')
    fig.tight_layout(); fig.savefig(Path(out) / 'risk.png', dpi=150); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--forecast', default='data/geos-temporal-20261116')
    p.add_argument('--out', default='outputs/greek-temporal-live')
    a = p.parse_args()
    run(Path(a.root).resolve(), Path(a.forecast).resolve(), Path(a.out).resolve())


if __name__ == '__main__':
    main()
