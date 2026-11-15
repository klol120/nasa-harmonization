"""Timestamp-checked research inference for the explicit temporal feature contract."""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

TIME_FIELDS = ['prediction_time', 'forecast_issued_at', 'forecast_available_at', 'history_latest_available_at',
               'vegetation_available_at', 'vegetation_composite_end', 'static_available_at', 'forecast_valid_start', 'forecast_valid_end', 'history_start', 'history_end']


def predict(artifact, inputs, metadata, research_only=False):
    if not research_only and not artifact.get('production_approved', False):
        raise ValueError('Production release is not approved; explicit research-only inference required')
    if 'sequence' not in inputs or 'static' not in inputs:
        raise ValueError('Missing temporal inputs')
    n = len(inputs['static'])
    contract = artifact['feature_contract']
    if inputs['sequence'].shape != (n, artifact['config']['history_days'], len(contract['dynamic'])) or inputs['static'].shape != (n, len(contract['static'])):
        raise ValueError('Temporal feature ordering/shape differs from trained contract')
    m = metadata.copy()
    if len(m) != n or not {'cell_id', 'lat', 'lon', 'region', *TIME_FIELDS} <= set(m):
        raise ValueError('Incomplete aligned location/time metadata')
    for field in TIME_FIELDS:
        # Refuse naive timestamps rather than guessing their timezone.
        if any(pd.notna(v) and pd.Timestamp(v).tzinfo is None for v in m[field]):
            raise ValueError('Every data timestamp must include a timezone')
        m[field] = pd.to_datetime(m[field], utc=True, errors='raise')
    missing_timestamp = m[TIME_FIELDS].isna().any(axis=1).to_numpy()
    if not np.isfinite(m[['lat', 'lon']].to_numpy(float)).all() or not m.lat.between(-90, 90).all() or not m.lon.between(-180, 180).all():
        raise ValueError('Invalid inference coordinates')
    valid = np.isfinite(inputs['sequence']).all(axis=(1, 2)) & np.isfinite(inputs['static']).all(axis=1)
    valid &= ~missing_timestamp
    flags = [[] for _ in range(n)]
    for i, row in enumerate(m.itertuples()):
        flags[i] = ['RETROSPECTIVE_MODEL_NOT_OPERATIONALLY_VALIDATED', 'COVERAGE_CONDITIONAL_RESEARCH_ESTIMATE', 'WEATHER_SOURCE_TRANSFER_REQUIRES_VALIDATION']
        if not valid[i]: flags[i].append('missing_input')
        if 'required_image_cell_ids' in artifact:
            if row.cell_id not in artifact['required_image_cell_ids']:
                valid[i] = False; flags[i].append('missing_hls_or_outside_image_qualified_domain')
            else:
                image = artifact['image_provenance'][row.cell_id]
                dates = [pd.Timestamp(value) for value in [image['observation_time'], image['retrieved_at'], artifact['source_checkpoint_retrieved_at']]]
                if any(pd.isna(value) or value.tzinfo is None for value in dates):
                    valid[i] = False; flags[i].append('missing_or_naive_pretrained_image_timestamp')
                elif any(value > row.prediction_time for value in dates):
                    valid[i] = False; flags[i].append('pretrained_image_or_weights_unavailable_at_prediction')
            flags[i].append('STATIC_2017_HLS_LANDSCAPE_PROXY_NOT_CURRENT_FUEL')
        if row.cell_id in artifact.get('conflict_excluded_cell_ids', []) and (pd.isna(row.forecast_valid_end) or row.forecast_valid_end > pd.Timestamp(artifact.get('conflict_start', '2023-10-07T00:00:00Z'))):
            valid[i] = False; flags[i].append('outside_evaluated_southern_conflict_scope')
        if missing_timestamp[i]:
            flags[i].append('missing_data_timestamp')
            continue
        if any(getattr(row, key) > row.prediction_time for key in ['forecast_issued_at', 'forecast_available_at', 'history_latest_available_at', 'vegetation_available_at', 'vegetation_composite_end', 'static_available_at']):
            valid[i] = False; flags[i].append('input_not_available_at_prediction')
        if row.forecast_valid_start != row.prediction_time or row.forecast_valid_end != row.prediction_time + pd.Timedelta(hours=24):
            valid[i] = False; flags[i].append('wrong_forecast_window')
        expected_end = row.prediction_time.normalize() - pd.Timedelta(days=artifact['config']['history_lag_days'] + 1)
        expected_start = expected_end - pd.Timedelta(days=artifact['config']['history_days'] - 1)
        if row.history_start != expected_start or row.history_end != expected_end:
            valid[i] = False; flags[i].append('wrong_history_range')
        age = (row.prediction_time - row.vegetation_composite_end).total_seconds() / 86400
        if age < artifact['config'].get('ndvi_lag_days_after_composite_end', 16) or age > artifact['config'].get('ndvi_max_age_days', 120):
            valid[i] = False; flags[i].append('vegetation_outside_valid_age')
        if row.forecast_available_at < row.forecast_issued_at or row.vegetation_available_at < row.vegetation_composite_end or row.history_latest_available_at < row.history_end:
            valid[i] = False; flags[i].append('inconsistent_data_timestamps')
        if artifact.get('stage', '').endswith('lebanon') and artifact['id'] != 'regional_router' and row.region != 'lebanon':
            valid[i] = False; flags[i].append('outside_local_model_domain')
        if row.region == 'lebanon': flags[i].append('LOW_LEBANESE_EVENT_COUNTS')
        else: flags[i].append('SAMPLED_PANELS_NOT_WORLDWIDE_VALIDATION')
    values = np.full(n, np.nan)
    if valid.any():
        data = {'sequence': inputs['sequence'][valid], 'static': inputs['static'][valid],
                'time': m.prediction_time.to_numpy(dtype='datetime64[D]')[valid].astype('int64'),
                'cell_id': np.asarray(m.cell_id, dtype='U32')[valid],
                'region': np.asarray(m.region, dtype='U32')[valid]}
        values[valid] = artifact['model'].predict(data)
    result = []
    def timestamp(value):
        return None if pd.isna(value) else value.isoformat()
    for i, row in enumerate(m.itertuples()):
        result.append({'cell_id': row.cell_id, 'lat': float(row.lat), 'lon': float(row.lon), 'region': row.region,
                       'prediction_time': timestamp(row.prediction_time), 'window_end': timestamp(row.forecast_valid_end),
                       'probability': None if not np.isfinite(values[i]) else float(values[i]),
                       'model_id': artifact['id'], 'forecast_issued_at': timestamp(row.forecast_issued_at),
                       'forecast_available_at': timestamp(row.forecast_available_at),
                       'history_latest_available_at': timestamp(row.history_latest_available_at),
                       'vegetation_available_at': timestamp(row.vegetation_available_at),
                       'static_available_at': timestamp(row.static_available_at),
                       'vegetation_composite_end': timestamp(row.vegetation_composite_end),
                       'production_approved': False, 'flags': flags[i]})
        if 'required_image_cell_ids' in artifact:
            image = artifact['image_provenance'].get(row.cell_id, {})
            result[-1].update(hls_observation_time=image.get('observation_time'), hls_retrieved_at=image.get('retrieved_at'),
                              hls_subset_sha256=image.get('sha256'), pretrained_weights_retrieved_at=artifact['source_checkpoint_retrieved_at'])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--inputs', required=True)
    p.add_argument('--metadata', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--research-only', action='store_true')
    a = p.parse_args()
    artifact = joblib.load(a.model)  # trusted local producer only
    with np.load(a.inputs) as raw:
        inputs = {k: raw[k] for k in ['sequence', 'static']}
    rows = predict(artifact, inputs, pd.read_csv(a.metadata), a.research_only)
    version = hashlib.sha256(Path(a.model).read_bytes()).hexdigest()
    for row in rows: row['model_sha256'] = version
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'predictions.json').write_text(json.dumps(rows, indent=2))
    pd.DataFrame(rows).assign(flags=lambda f: f['flags'].map('|'.join)).to_csv(out / 'predictions.csv', index=False)
    features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [r['lon'], r['lat']]}, 'properties': r} for r in rows]
    (out / 'predictions.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}))


if __name__ == '__main__':
    main()
