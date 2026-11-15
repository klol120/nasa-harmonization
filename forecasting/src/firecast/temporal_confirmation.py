"""Acquire and score registered November labels only after temporal models are frozen."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .benchmark_temporal import sha, verify_frozen, evaluate
from .global_acquire import acquire as acquire_global, sample_days
from .lebanon_confirmation import acquire as acquire_lebanon
from .global_data import build_global, count_pixels, quality_labels, add_features, join_weather, FEATURES
from .conflict_review import load_geometry, apply_quarantine
from .temporal_data import HistoryStore
from .temporal_models import RegionalRouter


def register(root, out):
    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'confirmation-registration.json'
    record = {'experiment_config_sha256': sha(root / 'configs/greek-experiment.json'),
              'confirmation_config_sha256': sha(root / 'configs/greek-confirmation.json'),
              'dates': json.loads((root / 'configs/greek-experiment.json').read_text())['fresh_confirmation_dates'],
              'source_fire_cache_present': any((root / 'data/greek-confirmation-panel/fire').glob('*.npz')),
              'purpose': 'Register scope before fitting/opening labels; reproduction does not make viewed outcomes independent again'}
    if path.exists():
        previous = json.loads(path.read_text())
        if any(previous[k] != record[k] for k in ['experiment_config_sha256', 'confirmation_config_sha256', 'dates']):
            raise ValueError('Existing registration differs; create a new experiment output')
        return previous
    if (out / 'selection-frozen.json').exists():
        raise ValueError('Register confirmation scope before freezing this experiment')
    path.write_text(json.dumps(record, indent=2))
    return record


def guard(root, out):
    root, out = Path(root), Path(out)
    frozen, frozen_hash = verify_frozen(out)
    registration = json.loads((out / 'confirmation-registration.json').read_text())
    if sha(root / 'configs/greek-experiment.json') != registration['experiment_config_sha256']:
        raise ValueError('Experiment changed after confirmation registration')
    if sha(root / 'configs/greek-confirmation.json') != registration['confirmation_config_sha256']:
        raise ValueError('Confirmation dates/scope changed after registration')
    if frozen['experiment_config_sha256'] != registration['experiment_config_sha256']:
        raise ValueError('Frozen models belong to a different experiment')
    if not frozen['artifacts'] or frozen['best_transfer'] not in frozen['artifacts']:
        raise ValueError('No complete frozen selection')
    return frozen, frozen_hash


def prepare(root, out, token_file):
    root, out = Path(root), Path(out)
    frozen, frozen_hash = guard(root, out)
    router_path = out / 'router.joblib'
    router_manifest = out / 'router-frozen.json'
    if not router_manifest.exists():
        global_artifact = joblib.load(out / 'frozen' / frozen['artifacts'][frozen['best_global']]['file'])
        local_artifact = joblib.load(out / 'frozen' / frozen['artifacts'][frozen['best_transfer']]['file'])
        router = dict(local_artifact, model=RegionalRouter(global_artifact['model'], local_artifact['model']), id='regional_router',
                      thresholds={'global': global_artifact['thresholds']['global'], 'lebanon': local_artifact['thresholds']['lebanon']})
        joblib.dump(router, router_path, compress=3)
        router_manifest.write_text(json.dumps({'source_ids': [frozen['best_global'], frozen['best_transfer']],
            'rule': 'Fixed geographic routing, no new fitting or tuning', 'sha256': sha(router_path),
            'selection_sha256': frozen_hash}, indent=2))
    router_record = json.loads(router_manifest.read_text())
    if router_record['selection_sha256'] != frozen_hash or sha(router_path) != router_record['sha256']:
        raise ValueError('Regional router changed before confirmation')
    test_root = root / 'outputs/greek-temporal-confirmation'
    test_root.mkdir(parents=True, exist_ok=True)
    receipt_path = test_root / 'opened-after-freeze.json'
    registration = json.loads((out / 'confirmation-registration.json').read_text())
    receipt = {'selection_sha256': frozen_hash, 'router_manifest_sha256': sha(router_manifest), 'dates_registered_before_fire_collection': not registration.get('source_fire_cache_present', False), 'first_label_acquisition_requires_frozen_models': True}
    if receipt_path.exists() and json.loads(receipt_path.read_text()) != receipt:
        raise ValueError('Previously opened confirmation belongs to different frozen artifacts')
    receipt_path.write_text(json.dumps(receipt, indent=2))
    config_path = root / 'configs/greek-confirmation.json'
    config = json.loads(config_path.read_text())
    env = root / 'data/environment'
    global_archive = root / 'data/greek-confirmation-panel'
    acquire_global(config_path, global_archive, token_file, env, root / 'data/gridded-noaa20', stage='fire', reuse_from=root / 'data/global-panel')
    if not json.loads((global_archive / 'archive-report.json').read_text())['complete']:
        raise ValueError('New global confirmation acquisition incomplete')
    local_archive = root / 'data/greek-confirmation-local-masks'
    acquire_lebanon(config_path, root / 'outputs/noaa20-real', local_archive, token_file)
    if not json.loads((local_archive / 'archive-report.json').read_text())['complete']:
        raise ValueError('New Lebanese confirmation acquisition incomplete')
    global_frame = build_global(config, global_archive, root / 'data/greek-confirmation-weather/weather.csv.gz')
    plan = json.loads((root / 'configs/greek-experiment.json').read_text())
    global_frame['geographic_holdout'] = global_frame.region.isin(plan['global_geographic_holdouts'])
    global_frame['conflict_excluded'] = False
    cells = pd.read_csv(root / 'outputs/noaa20-real/cells.csv')
    maps = {p.stem.removeprefix('pixel-map-'): dict(np.load(p)) for p in (root / 'outputs/noaa20-real').glob('pixel-map-*.npz')}
    counts = []
    for path in sorted((local_archive / 'fire').glob('*.npz')):
        meta = json.loads(path.with_suffix('.npz.manifest.json').read_text())
        if meta['date'] not in plan['fresh_confirmation_dates']:
            continue
        if sha(path) != meta['subset_sha256']:
            raise ValueError('Local confirmation mask integrity failed')
        with np.load(path) as a:
            counts.append(count_pixels(a['FireMask'], a['QA'], maps[meta['tile']], 'lebanon', meta['date']))
    daily = pd.concat(counts).groupby(['region', 'cell_id', 'prediction_time']).sum().reset_index()
    local = cells.merge(pd.DataFrame({'prediction_time': sample_days(config)}), how='cross').merge(daily, on=['region', 'cell_id', 'prediction_time'], how='left', validate='one_to_one')
    local = quality_labels(local, config)
    local['window_end'] = local.prediction_time + pd.Timedelta(days=1)
    local = add_features(join_weather(local, pd.read_csv(root / 'data/greek-confirmation-local-weather/weather.csv.gz')))
    conflict = json.loads((root / 'configs/conflict-review.json').read_text())
    geometry = load_geometry(root / 'data/conflict-review/southern_governorates.geojson', conflict)
    local = apply_quarantine(local, conflict, geometry, config['grid_deg'])
    store = HistoryStore(root, plan)
    soil = pd.read_csv(root / 'data/greek-soil/soil.csv.gz')
    fresh_weather = pd.concat([pd.read_csv(root / 'data/greek-confirmation-weather/weather.csv.gz'), pd.read_csv(root / 'data/greek-confirmation-local-weather/weather.csv.gz')], ignore_index=True)
    fresh_weather = fresh_weather.merge(soil, on=['weather_region', 'weather_point_id', 'date'], how='left', validate='one_to_one')
    store.set_weather(pd.concat([store.weather, fresh_weather], ignore_index=True))
    parts = {'global_temporal': global_frame[~global_frame.geographic_holdout], 'global_geographic': global_frame[global_frame.geographic_holdout], 'lebanon': local}
    report = {'selection_sha256': frozen_hash, 'dates': plan['fresh_confirmation_dates'], 'mode': 'retrospective', 'parts': {}}
    for name, frame in parts.items():
        frame.to_csv(test_root / (name + '-audit.csv.gz'), index=False, compression={'method': 'gzip', 'mtime': 0})
        eligible = frame.y.notna() & np.isfinite(frame[FEATURES].to_numpy(float)).all(axis=1)
        tensors, part = store.make(frame[eligible])
        part['all_windows'] = len(frame)
        part['quarantined_conflict_windows'] = int(frame.conflict_excluded.sum())
        part['conflict_positive_windows_excluded'] = int(frame.loc[frame.conflict_excluded, 'y_before_conflict_quarantine'].fillna(0).sum()) if name == 'lebanon' else 0
        path = test_root / (name + '.npz')
        np.savez_compressed(path, **tensors)
        part['sha256'] = sha(path)
        report['parts'][name] = part
        print('New registered confirmation', name, part, flush=True)
    if verify_frozen(out)[1] != frozen_hash:
        raise ValueError('Selection changed while preparing confirmation')
    (test_root / 'manifest.json').write_text(json.dumps(report, indent=2))
    return report


def score(root, out):
    root, out = Path(root), Path(out)
    frozen, frozen_hash = guard(root, out)
    test_root = root / 'outputs/greek-temporal-confirmation'
    manifest = json.loads((test_root / 'manifest.json').read_text())
    receipt = json.loads((test_root / 'opened-after-freeze.json').read_text())
    if sha(out / 'router-frozen.json') != receipt['router_manifest_sha256']:
        raise ValueError('Router selection changed after confirmation was opened')
    router_record = json.loads((out / 'router-frozen.json').read_text())
    if sha(out / 'router.joblib') != router_record['sha256']:
        raise ValueError('Router weights changed after confirmation was opened')
    if manifest['selection_sha256'] != frozen_hash:
        raise ValueError('Confirmation belongs to a different frozen selection')
    parts = {}
    for name, record in manifest['parts'].items():
        path = test_root / (name + '.npz')
        if sha(path) != record['sha256']:
            raise ValueError('Confirmation tensor integrity failed')
        with np.load(path) as a:
            parts[name] = {k: a[k] for k in a.files}
    results, rows = {}, []
    artifacts = {identifier: out / 'frozen' / record['file'] for identifier, record in frozen['artifacts'].items()}
    artifacts['regional_router'] = out / 'router.joblib'
    for identifier, path in artifacts.items():
        artifact = joblib.load(path)
        results[identifier] = {}
        for domain, data in parts.items():
            if not len(data['y']):
                results[identifier][domain] = {'observations': 0, 'status': 'no_feature_qualified_windows'}
                continue
            p = artifact['model'].predict(data)
            threshold = artifact['thresholds']['lebanon' if domain == 'lebanon' else 'global']
            result = evaluate(data, p, threshold)
            result['by_region'] = {}
            for region in np.unique(data['region']):
                use = data['region'] == region
                result['by_region'][str(region)] = evaluate({'y': data['y'][use]}, p[use], threshold)
            results[identifier][domain] = result
            rows.append({'model': identifier, 'domain': domain, **{k: result[k] for k in ['observations', 'positive_windows', 'pr_auc_average_precision', 'roc_auc', 'precision', 'recall', 'f1', 'brier', 'threshold', 'prevalence', 'mean_probability']}})
        print('Scored frozen temporal model', identifier, flush=True)
    if verify_frozen(out)[1] != frozen_hash:
        raise ValueError('Model choices changed during confirmation evaluation')
    report = {'mode': 'retrospective', 'production_approved': False, 'selection': frozen,
              'selection_sha256': frozen_hash, 'confirmation': manifest, 'results': results,
              'interpretation': 'Only two November dates; insufficient for operational validation. No model/threshold changes from these scores.'}
    (out / 'confirmation-results.json').write_text(json.dumps(report, indent=2))
    pd.DataFrame(rows).to_csv(out / 'confirmation-results.csv', index=False)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['register', 'prepare', 'score'])
    p.add_argument('--root', default='.')
    p.add_argument('--out', default='outputs/greek-temporal-benchmark')
    p.add_argument('--token-file')
    a = p.parse_args()
    if a.operation == 'register':
        register(Path(a.root).resolve(), Path(a.out).resolve())
    elif a.operation == 'prepare':
        prepare(Path(a.root).resolve(), Path(a.out).resolve(), a.token_file)
    else:
        score(Path(a.root).resolve(), Path(a.out).resolve())


if __name__ == '__main__':
    main()
