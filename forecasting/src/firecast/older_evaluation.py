"""Evaluate frozen post-2018 models on 2016/2017 NASA S-NPP labels.

No fitting, calibration, threshold selection or older-test model selection occurs.
Pretrained image inputs are replaced by genuinely earlier 2015 HLS observations.
This remains a backward-time, cross-sensor retrospective diagnostic.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
import urllib.request

import joblib
import numpy as np
import pandas as pd

from .benchmark_temporal import sha, evaluate
from .global_data import add_features, join_weather
from .global_weather import history_features
from .temporal_data import HistoryStore


def register(root, config_path):
    root, config_path = Path(root), Path(config_path)
    template = json.loads((root / 'configs/older-evaluation.json').read_text())
    proposed = dict(template)
    proposed['frozen_inputs'] = {path: sha(root / path) for path in template['frozen_inputs']}
    guard(root, proposed)
    if config_path.exists():
        existing = json.loads(config_path.read_text())
        if existing['frozen_inputs'] != proposed['frozen_inputs']:
            raise ValueError('Refuse to replace an existing registration; choose a new config filename')
        return
    proposed['registered_at'] = datetime.now(timezone.utc).isoformat()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(proposed, indent=2))


def discover(root, config_path):
    config = json.loads(Path(config_path).read_text())
    folder = Path(root) / 'data/older-pretrained'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'hls-catalog.json'
    metadata = path.with_suffix('.json.manifest.json')
    if path.exists():
        if not metadata.exists() or sha(path) != json.loads(metadata.read_text())['sha256']:
            raise ValueError('Cached older HLS catalogue lacks matching provenance')
        return
    params = {'short_name': 'HLSL30', 'version': '2.0', 'bounding_box': '35,33,36.7,34.75',
              'temporal': ','.join(config['hls_period']), 'page_size': 200, 'sort_key': 'start_date'}
    url = 'https://cmr.earthdata.nasa.gov/search/granules.json?' + urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as response:
        raw = response.read()
    if len(json.loads(raw)['feed']['entry']) >= 200:
        raise ValueError('Possibly truncated older HLS catalogue; pagination required before expansion')
    path.write_bytes(raw)
    metadata.write_text(json.dumps({'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(), 'sha256': sha(path)}, indent=2))


def guard(root, config):
    root = Path(root)
    for path, expected in config['frozen_inputs'].items():
        if sha(root / path) != expected:
            raise ValueError('Registered frozen input changed: ' + path)
    if config['fit_allowed'] or config['calibration_allowed'] or config['threshold_changes_allowed']:
        raise ValueError('Older experiment must remain evaluation-only')
    first = np.datetime64(config['evaluation_end_exclusive'][:10], 'D').astype(int)
    for domain in ['global', 'greek', 'lebanon']:
        with np.load(root / 'outputs/greek-temporal-data' / (domain + '-train.npz')) as a:
            if a['time'].min() < first:
                raise ValueError('A proposed source model trained on the older evaluation period')
    current = json.loads((root / 'outputs/pretrained-transfer/selection-frozen.json').read_text())
    if current['config']['train_years'][0] < 2018:
        raise ValueError('External heads overlap older evaluation years')
    for record in current['artifacts'].values():
        if sha(root / 'outputs/pretrained-transfer' / record['file']) != record['sha256']:
            raise ValueError('Frozen external candidate changed')
    return current


def older_hls_manifest(path):
    """Repair an old reader's descriptive year text using exact source metadata.

    Pixel files are never changed. The historical reader formerly hardcoded 2017
    in this one explanatory string even when supplied an explicit 2015 catalogue.
    """
    path = Path(path)
    m = json.loads(path.read_text())
    years = sorted({r['observation_time'][:4] for r in m['records']})
    if years != ['2015']:
        raise ValueError('Older image archive must contain only pre-2016 observations')
    if m['selection'].startswith('2017'):
        m['original_selection_text'] = m['selection']
        m['selection'] = '2015 June-October catalogue, cloud ordering; no fire outcomes used'
        m['metadata_correction'] = 'Corrected hardcoded descriptive year; source observation timestamps and raw crops unchanged'
    m['observation_years'] = years
    path.write_text(json.dumps(m, indent=2))
    return m


def read_older_labels(root, policy, config):
    pieces = []
    path = Path(root) / 'outputs/gridded-real' / ('dataset-' + policy + '.csv.gz')
    for chunk in pd.read_csv(path, chunksize=100000):
        use = chunk.prediction_time.ge(config['evaluation_start'][:10]) & chunk.prediction_time.lt(config['evaluation_end_exclusive'][:10])
        pieces.append(chunk.loc[use])
    frame = pd.concat(pieces, ignore_index=True)
    for field in ['prediction_time', 'window_end']:
        frame[field] = pd.to_datetime(frame[field], utc=True)
    if frame.duplicated(['cell_id', 'prediction_time']).any():
        raise ValueError('Duplicate historical cell-day')
    return frame


def prepare(root, config_path, out, rebuild_unscored=False):
    root, out = Path(root), Path(out)
    config = json.loads(Path(config_path).read_text())
    guard(root, config)
    if (out / 'manifest.json').exists():
        if not rebuild_unscored or (out / 'scored-receipt.json').exists() or (root / 'outputs/older-evaluation/results.json').exists():
            raise ValueError('Older tensors already exist; do not overwrite an evaluated cohort')
        (out / 'manifest-superseded-unscored.json').write_bytes((out / 'manifest.json').read_bytes())
    base_config = json.loads((root / 'configs/greek-experiment.json').read_text())
    store = HistoryStore(root, base_config, extra_soil_paths=[root / 'data/older-soil/soil.csv.gz'],
                         extra_ndvi_roots=[root / 'data/older-ndvi'])
    strict = read_older_labels(root, 'strict', config)
    conservative = read_older_labels(root, 'conservative', config)
    keys = ['cell_id', 'prediction_time']
    strict = strict.rename(columns={'y': 'y_strict', 'label_status': 'status_strict'})
    frame = strict.merge(conservative[keys + ['y', 'label_status']].rename(columns={'y': 'y_conservative', 'label_status': 'status_conservative'}), on=keys, validate='one_to_one')
    raw = pd.read_csv(root / 'data/nasa-lebanon/weather_historical.csv')
    weather = history_features(raw, base_config['history_lag_days'])
    weather['weather_region'] = 'lebanon'
    # Recreate current model features from raw NASA values, not older baseline lags.
    remove = ['weather_point_id', 'temperature_c', 'humidity_pct', 'precip_mm', 'wind_u_ms', 'wind_v_ms', 'rain7_mm']
    frame = join_weather(frame.drop(columns=[c for c in remove if c in frame]), weather)
    frame = add_features(frame)
    out.mkdir(parents=True, exist_ok=True)
    report = {'config': config, 'config_sha256': sha(config_path), 'source_product': 'VNP14A1.002',
              'training_label_product': 'VJ114A1.002', 'sensor_transfer': True, 'feature_config': base_config,
              'source_overlaps': store.extra_source_audit, 'parts': {}, 'production_approved': False,
              'source_sha256': {'soil': sha(root / 'data/older-soil/soil.csv.gz'),
                                'ndvi_report': sha(root / 'data/older-ndvi/ndvi-report.json'),
                                'original_snpp_report': sha(root / 'outputs/gridded-real/dataset-report.json')}}
    starts = []
    for domain in ['global', 'greek', 'lebanon']:
        with np.load(root / 'outputs/greek-temporal-data' / (domain + '-train.npz')) as arrays:
            starts.append(int(arrays['time'].min()))
    earliest_fit = min(starts)
    report['earliest_fitting_target'] = str(np.datetime64(int(earliest_fit), 'D'))
    report['temporal_embargo_days'] = config['embargo_days']
    for year in config['years']:
        f = frame[frame.prediction_time.dt.year.eq(year)].reset_index(drop=True)
        expected = len(pd.date_range(str(year) + '-01-01', str(year) + '-12-31')) * f.cell_id.nunique()
        if len(f) != expected or f.cell_id.nunique() != 124:
            raise ValueError('Historical panel is not the full configured daily grid')
        inputs, audit = store.make(f, keep_unqualified=True)
        feature_valid = np.isfinite(inputs['sequence']).all(axis=(1, 2)) & np.isfinite(inputs['static']).all(axis=1)
        inputs['feature_valid'] = feature_valid
        temporal_eligible = inputs['time'] + 1 < earliest_fit - config['embargo_days']
        inputs['temporal_eligible'] = temporal_eligible
        detail = {'windows': len(f), 'cells': f.cell_id.nunique(), 'feature_audit': audit, 'policies': {}}
        detail['embargo_excluded_cell_windows'] = int((~temporal_eligible).sum())
        detail['last_temporally_eligible_target'] = str(np.datetime64(int(inputs['time'][temporal_eligible].max()), 'D'))
        for policy in config['policies']:
            y = f['y_' + policy].to_numpy(np.float32)
            inputs['y_' + policy] = y
            qualified = np.isfinite(y)
            use = qualified & feature_valid
            detail['policies'][policy] = {'status_counts': f['status_' + policy].value_counts().to_dict(),
                'label_qualified_windows': int(qualified.sum()), 'label_positive_windows': int(np.nansum(y)),
                'feature_qualified_windows': int(use.sum()), 'feature_qualified_positive_windows': int(y[use].sum()),
                'excluded_missing_feature_windows': int((qualified & ~feature_valid).sum()),
                'excluded_missing_feature_positive_windows': int(np.nansum(y[qualified & ~feature_valid]))}
            detail['policies'][policy]['embargo_excluded_qualified_windows'] = int((qualified & feature_valid & ~temporal_eligible).sum())
            detail['policies'][policy]['embargo_excluded_positive_windows'] = int(np.nansum(y[qualified & feature_valid & ~temporal_eligible]))
        path = out / (str(year) + '.npz')
        np.savez_compressed(path, **inputs)
        detail['sha256'] = sha(path)
        report['parts'][str(year)] = detail
        print('Prepared older year', year, detail, flush=True)
    (out / 'manifest.json').write_text(json.dumps(report, indent=2))
    guard(root, config)
    return report


def evaluation_data(arrays, policy, cells=None):
    y = arrays['y_' + policy]
    use = np.isfinite(y) & arrays['feature_valid'] & arrays.get('temporal_eligible', np.ones(len(y), bool))
    before = use.copy()
    if cells is not None:
        use &= np.isin(arrays['cell_id'], list(cells))
    data = {k: arrays[k][use] for k in ['sequence', 'static', 'time', 'region', 'cell_id']}
    data['y'] = y[use].astype(np.int8)
    audit = {'windows': int(use.sum()), 'positive_windows': int(data['y'].sum()),
             'image_scope_excluded_windows': int((before & ~use).sum()),
             'image_scope_excluded_positive_windows': int(y[before & ~use].sum())}
    return data, audit


def substitute_image_inputs(model, bank):
    """Replace observed inputs, never learned weights/scalers/calibration."""
    original_base = model.base
    if getattr(original_base, 'tokens', None) is None:
        return model
    for key in ['norm_weight', 'norm_bias']:
        if not np.array_equal(original_base.tokens[key], bank[key]):
            raise ValueError('Old-image tokens were produced by another pretrained checkpoint')
    result = copy.copy(model)
    result.base = copy.copy(original_base)
    result.base.tokens = bank
    # Verify every other learned/state object is literally retained.
    for key, value in original_base.__dict__.items():
        if key != 'tokens' and result.base.__dict__[key] is not value:
            raise ValueError('Image replacement changed a fitted parameter')
    if result.calibrator is not model.calibrator:
        raise ValueError('Image replacement altered calibration')
    return result


def detailed_metrics(data, p, threshold):
    result = evaluate(data, p, threshold)
    months = pd.to_datetime(data['time'], unit='D').month.to_numpy()
    result['by_season'] = {str(s): evaluate({'y': data['y'][(months % 12) // 3 == s]}, p[(months % 12) // 3 == s], threshold)
                           for s in np.unique((months % 12) // 3)}
    return result


def score(root, config_path, data_folder, out):
    root, data_folder, out = Path(root), Path(data_folder), Path(out)
    config = json.loads(Path(config_path).read_text())
    frozen = guard(root, config)
    manifest = json.loads((data_folder / 'manifest.json').read_text())
    if sha(config_path) != manifest['config_sha256']:
        raise ValueError('Protocol changed after tensor preparation')
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'results.json').exists():
        raise ValueError('Older evaluation already exists; do not overwrite')
    image_manifest = json.loads((root / 'data/older-pretrained/hls-patches/manifest.json').read_text())
    if any(r['observation_time'] >= '2016-01-01' for r in image_manifest['records']):
        raise ValueError('Future landscape imagery would contaminate older evaluation')
    banks, receipts = {}, {}
    common = set(frozen['common_cells'])
    for record in config['models']:
        path = root / 'data/older-pretrained' / (record['id'] + '-tokens.npz')
        receipt = json.loads(path.with_suffix('.json').read_text())
        if receipt['model'] != record or sha(path) != receipt['token_sha256']:
            raise ValueError('Older token checkpoint identity/integrity failed')
        if receipt['hls_manifest_sha256'] != sha(root / 'data/older-pretrained/hls-patches/manifest.json'):
            raise ValueError('Older HLS archive differs from token extraction')
        with np.load(path) as a:
            banks[record['id']] = {k: a[k] for k in a.files}
        common &= set(banks[record['id']]['cell_id'])
        receipts[record['id']] = receipt
    reference_root = root / 'outputs/greek-temporal-benchmark'
    reference_selection = json.loads((reference_root / 'selection-frozen.json').read_text())
    references = {identifier: dict(reference_selection['artifacts'][identifier]) for identifier in
                  [reference_selection['best_global'], reference_selection['best_lebanon'], reference_selection['best_transfer'], 'lstm64-global_greek_lebanon']}
    results, cohorts, rows = {}, {}, []
    for year, detail in manifest['parts'].items():
        path = data_folder / (year + '.npz')
        if sha(path) != detail['sha256']:
            raise ValueError('Older tensor checksum failed')
        with np.load(path) as a:
            arrays = {k: a[k] for k in a.files}
        for policy in config['policies']:
            full, full_audit = evaluation_data(arrays, policy)
            matched, matched_audit = evaluation_data(arrays, policy, common)
            domain = year + '-' + policy
            cohorts[domain] = {'full_feature_qualified': full_audit, 'matched_images': matched_audit}
            for identifier, record in frozen['artifacts'].items():
                artifact = joblib.load(root / 'outputs/pretrained-transfer' / record['file'])
                base = artifact['model'].base
                model_id = next((name for name in banks if identifier.startswith(name + '-')), None)
                model = substitute_image_inputs(artifact['model'], banks[model_id]) if model_id else artifact['model']
                inputs = {k: v for k, v in matched.items() if k != 'y'}
                metric = detailed_metrics(matched, model.predict(inputs), artifact['threshold'])
                results.setdefault(identifier, {})[domain + '-matched'] = metric
            for identifier, record in references.items():
                path = reference_root / 'frozen' / record['file']
                if sha(path) != record['sha256']:
                    raise ValueError('Frozen reference changed before older evaluation')
                artifact = joblib.load(path)
                for cohort_name, data in [('full', full), ('matched', matched)]:
                    p = artifact['model'].predict({k: v for k, v in data.items() if k != 'y'})
                    metric = detailed_metrics(data, p, artifact['thresholds']['lebanon'])
                    results.setdefault(identifier, {})[domain + '-' + cohort_name] = metric
            print('Scored frozen models', domain, cohorts[domain], flush=True)
    for model, values in results.items():
        for domain, metric in values.items():
            rows.append({'model': model, 'domain': domain, **{k: metric[k] for k in ['observations', 'positive_windows', 'pr_auc_average_precision', 'precision', 'recall', 'f1', 'brier', 'threshold', 'roc_auc']}})
    guard(root, config)
    report = {'generated_at': datetime.now(timezone.utc).isoformat(), 'config': config,
              'mode': 'retrospective_backward_temporal_and_sensor_transfer', 'source_product': 'VNP14A1.002',
              'training_label_product': 'VJ114A1.002', 'model_weights_calibrators_thresholds_unchanged': True,
              'selected_external_unchanged': frozen['selected_pretrained'], 'project_primary_replaced': False,
              'production_approved': False, 'fresh_prospective_confirmation': False,
              'image_cells': sorted(common), 'image_receipts': receipts, 'cohorts': cohorts, 'manifest': manifest,
              'frozen_model_records': frozen['artifacts'], 'references': references, 'results': results,
              'limitations': ['Earlier model versions trained on S-NPP 2016/2017 are excluded',
                             'Current models were unavailable in 2016/2017; this is not a forward operational backtest',
                             'Sensor and label processing differ from NOAA-20 training',
                             '2015 landscape crops are old limited-area proxies; future 2017 imagery is not used',
                             'Label quality uses retrospective FIRMS review, including later recurrence evidence',
                             'Historical observed POWER weather and reprocessed environmental availability remain limitations']}
    (out / 'results.json').write_text(json.dumps(report, indent=2))
    pd.DataFrame(rows).to_csv(out / 'results.csv', index=False)
    (data_folder / 'scored-receipt.json').write_text(json.dumps({'results': str(out / 'results.json'), 'results_sha256': sha(out / 'results.json'), 'config_sha256': sha(config_path)}, indent=2))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['register', 'discover', 'prepare', 'score', 'check-hls'])
    p.add_argument('--root', default='.')
    p.add_argument('--config', default='configs/older-evaluation.json')
    p.add_argument('--data', default='outputs/older-evaluation-data')
    p.add_argument('--out', default='outputs/older-evaluation')
    p.add_argument('--rebuild-unscored', action='store_true')
    a = p.parse_args()
    if a.operation == 'register':
        register(a.root, a.config)
    elif a.operation == 'discover':
        discover(a.root, a.config)
    elif a.operation == 'prepare':
        prepare(a.root, a.config, a.data, a.rebuild_unscored)
    elif a.operation == 'score':
        score(a.root, a.config, a.data, a.out)
    else:
        older_hls_manifest(Path(a.root) / 'data/older-pretrained/hls-patches/manifest.json')
