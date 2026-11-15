"""Fit Greek-inspired real-data models; freeze validation choices before new tests."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.metrics import roc_auc_score

from .benchmark_global import select_threshold
from .models import metrics
from .temporal_models import Tabular, Seasonal, Temporal, Calibrated


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def numerical_digest(data):
    h = hashlib.sha256()
    for key in ['sequence', 'static', 'y', 'time']:
        a = np.ascontiguousarray(data[key])
        h.update(key.encode()); h.update(str(a.shape).encode()); h.update(str(a.dtype).encode()); h.update(a.tobytes())
    return h.hexdigest()


def cached_source(family, domain, data, config, folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (family + '-' + domain + '.joblib')
    key = {'data_sha256': numerical_digest(data), 'seed': config['seed'], 'epochs': config['lstm_epochs'], 'batch_size': config['lstm_batch_size'], 'family': family}
    if path.exists():
        meta = json.loads(path.with_suffix('.json').read_text())
        if meta['key'] != key or sha(path) != meta['sha256']:
            raise ValueError('Pretrained source cache differs from current training data/settings')
        return joblib.load(path)
    model = Temporal(int(family.removeprefix('lstm')), config['seed'], config['torch_threads']).fit(data, epochs=config['lstm_epochs'], batch_size=config['lstm_batch_size'])
    joblib.dump(model, path, compress=3)
    path.with_suffix('.json').write_text(json.dumps({'key': key, 'sha256': sha(path)}, indent=2))
    return model


def pretrain(data_folder, out, config_path):
    config = json.loads(Path(config_path).read_text())
    for family in [f for f in config['model_families'] if f.startswith('lstm')]:
        for domain in ['global', 'lebanon']:
            with np.load(Path(data_folder) / (domain + '-train.npz')) as a:
                data = {k: a[k] for k in ['sequence', 'static', 'y', 'time']}
            cached_source(family, domain, data, config, Path(out) / 'source-cache')
            print('Completed source pretraining', family, domain, flush=True)


def load_data(folder, name, manifest):
    path = Path(folder) / (name + '.npz')
    if sha(path) != manifest['parts'][name]['sha256']:
        raise ValueError('Temporal split integrity failed')
    with np.load(path) as a:
        result = {k: a[k] for k in a.files}
    if len(np.unique(result['y'])) != 2:
        raise ValueError('Fitting/calibration/validation requires both classes')
    return result


def evaluate(data, p, threshold):
    result = metrics(data['y'], p, threshold)
    from .review import reliability
    result['quantile_reliability'] = reliability(data['y'], p)
    result['predicted_positive_windows'] = int(np.sum(p >= threshold))
    result['recall_estimable'] = bool(np.sum(data['y']) > 0)
    result['precision_estimable'] = bool(np.sum(p >= threshold) > 0)
    result['roc_auc'] = float(roc_auc_score(data['y'], p)) if len(np.unique(data['y'])) == 2 else None
    result['prevalence'] = int(data['y'].sum()) / len(data['y'])
    result['mean_probability'] = float(np.mean(p))
    return result


def fit(data_folder, out):
    data_folder, out = Path(data_folder), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    frozen_path = out / 'selection-frozen.json'
    if frozen_path.exists():
        raise ValueError('Selection already frozen; do not overwrite an evaluated experiment')
    manifest = json.loads((data_folder / 'manifest.json').read_text())
    config = manifest['config']
    data = {name: load_data(data_folder, name, manifest) for name in manifest['parts']}
    # Assert a full history-length embargo, not only non-overlapping target days.
    for domain in ['global', 'greek', 'lebanon']:
        for before, after in [('train', 'calibration'), ('calibration', 'validation')]:
            gap = data[domain + '-' + after]['time'].min() - data[domain + '-' + before]['time'].max()
            if gap <= config['history_days'] + config['history_lag_days']:
                raise ValueError('History overlaps adjacent modeling split')
    models, rows, records = {}, [], {}
    folder = out / 'frozen'
    folder.mkdir(exist_ok=True)
    started = time.perf_counter()

    def train(family, domain, parent=None):
        part = data[domain + '-train']
        if family == 'seasonal':
            return Seasonal().fit(part)
        if family.startswith('lstm'):
            hidden = int(family.removeprefix('lstm'))
            if parent is None and domain in {'global', 'lebanon'}:
                return cached_source(family, domain, part, config, out / 'source-cache')
            return Temporal(hidden, config['seed'], config['torch_threads']).fit(part,
                epochs=config['lstm_adaptation_epochs'] if parent is not None else config['lstm_epochs'],
                batch_size=config['lstm_batch_size'], lr=.0003 if parent is not None else .001, parent=parent)
        return Tabular(family, config['seed'], parent=parent).fit(part)

    def keep(family, stage, model, calibration_domain):
        identifier = family + '-' + stage
        calibration = data[calibration_domain + '-calibration']
        calibrated = Calibrated(model).fit(calibration)
        thresholds, validation = {}, {}
        for domain in ['global', 'lebanon', 'greek']:
            part = data[domain + '-validation']
            p = calibrated.predict(part)
            threshold, precision_targets = select_threshold(part['y'], p)
            thresholds[domain] = threshold
            validation[domain] = evaluate(part, p, threshold)
            validation[domain]['validation_precision_target_thresholds'] = precision_targets
        artifact = {'model': calibrated, 'family': family, 'stage': stage, 'id': identifier,
                    'mode': 'retrospective', 'production_approved': False, 'thresholds': thresholds,
                    'config': config, 'data_manifest_sha256': sha(data_folder / 'manifest.json'),
                    'calibration_domain': calibration_domain,
                    'feature_contract': {'dynamic': manifest['dynamic_features'], 'static': manifest['static_features']}}
        path = folder / (identifier + '.joblib')
        joblib.dump(artifact, path, compress=3)
        records[identifier] = {'file': path.name, 'sha256': sha(path)}
        row = {'id': identifier, 'family': family, 'stage': stage, 'calibration_domain': calibration_domain,
               'validation': validation, 'thresholds': thresholds,
               'training': getattr(model, 'training', None),
               'training_windows': getattr(model, 'fit_windows', None),
               'training_positive_windows': getattr(model, 'fit_positive_windows', None)}
        rows.append(row)
        (out / 'validation-results.json').write_text(json.dumps(rows, indent=2))
        print('Validation', identifier, 'Lebanon AP', validation['lebanon']['pr_auc_average_precision'], 'global AP', validation['global']['pr_auc_average_precision'], flush=True)
        return model

    for family in config['model_families']:
        source = keep(family, 'global', train(family, 'global'), 'global')
        local = keep(family, 'lebanon', train(family, 'lebanon'), 'lebanon')
        greek = keep(family, 'greek', train(family, 'greek'), 'greek')
        if family != 'seasonal':
            greek_local = keep(family, 'greek_lebanon', train(family, 'lebanon', parent=greek), 'lebanon')
            source_greek = keep(family, 'global_greek', train(family, 'greek', parent=source), 'greek')
            keep(family, 'global_greek_lebanon', train(family, 'lebanon', parent=source_greek), 'lebanon')
    def best(candidates, domain):
        return max(candidates, key=lambda row: (row['validation'][domain]['pr_auc_average_precision'], -row['validation'][domain]['brier']))['id']
    frozen = {
        'frozen_at': datetime.now(timezone.utc).isoformat(), 'artifacts': records,
        'best_global': best(rows, 'global'), 'best_lebanon': best(rows, 'lebanon'),
        'best_transfer': best([r for r in rows if r['stage'] in {'greek_lebanon', 'global_greek_lebanon'}], 'lebanon'),
        'candidate_count': len(rows), 'selection': config['selection'],
        'data_manifest_sha256': sha(data_folder / 'manifest.json'),
        'experiment_config_sha256': manifest['source_config_sha256'],
        'new_confirmation_opened': False,
        'fit_seconds': time.perf_counter() - started,
        'runtime': {'python': platform.python_version(), **{name: importlib.metadata.version(name) for name in ['numpy', 'pandas', 'scikit-learn', 'torch', 'xgboost-cpu']}},
        'source_code_sha256': {name: sha(Path(__file__).parent / name) for name in ['temporal_models.py', 'temporal_data.py', 'benchmark_temporal.py', 'greek_environment.py']},
        'tree_adaptation': 'Local tree/logistic refitting with the frozen parent score as an additional feature; neural models continue actual weights and preserve source scalers',
    }
    frozen_path.write_text(json.dumps(frozen, indent=2))
    print('Frozen validation selections', {k: frozen[k] for k in ['best_global', 'best_lebanon', 'best_transfer', 'candidate_count', 'fit_seconds']}, flush=True)
    return frozen


def verify_frozen(out):
    out = Path(out)
    path = out / 'selection-frozen.json'
    frozen = json.loads(path.read_text())
    for record in frozen['artifacts'].values():
        if sha(out / 'frozen' / record['file']) != record['sha256']:
            raise ValueError('Frozen temporal artifact changed')
    return frozen, sha(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pretrain-only', action='store_true')
    p.add_argument('--config', default='configs/greek-experiment.json')
    p.add_argument('--data', default='outputs/greek-temporal-data')
    p.add_argument('--out', default='outputs/greek-temporal-benchmark')
    a = p.parse_args()
    if a.pretrain_only:
        pretrain(a.data, a.out, a.config)
    else:
        fit(a.data, a.out)


if __name__ == '__main__':
    main()
