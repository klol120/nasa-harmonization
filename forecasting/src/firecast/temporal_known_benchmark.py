"""Score immutable temporal models on known later years; never claim fresh selection."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .benchmark_global import load_part
from .benchmark_temporal import sha, verify_frozen, evaluate
from .temporal_data import HistoryStore


def prepare(root, out):
    root, out = Path(root), Path(out)
    frozen, frozen_hash = verify_frozen(out)
    config = json.loads((root / 'configs/greek-experiment.json').read_text())
    data_root = root / 'outputs/global-transfer-data'
    old = json.loads((data_root / 'dataset-manifest.json').read_text())
    store = HistoryStore(root, config, include_known=True)
    coords = pd.read_csv(root / 'data/greek-ndvi/cells.csv')[['region', 'cell_id', 'lon']]
    global_old = load_part(data_root, 'global-test-sealed', old)
    geographic_old = load_part(data_root, 'global-geographic-test-sealed', old)
    greek = geographic_old[geographic_old.region.eq('greece')]
    domains = {
        'global_known_2023_2025': pd.concat([global_old, greek], ignore_index=True),
        'geographic_known_2023_2025': geographic_old[~geographic_old.region.eq('greece')],
        'lebanon_known_2023_2025': load_part(data_root, 'lebanon-known-test', old),
        'lebanon_known_2026_JanOct': load_part(data_root, 'lebanon-confirmation-sealed', old),
    }
    folder = root / 'outputs/greek-known-benchmark-data'
    folder.mkdir(exist_ok=True)
    report = {'selection_sha256': frozen_hash, 'fresh_confirmation': False, 'note': 'Previously viewed later-year benchmark; never used for fitting or renewed selection of these frozen models', 'parts': {},
              'source_soil_sha256': sha(root / 'data/greek-soil-known/soil.csv.gz'), 'source_ndvi_report_sha256': sha(root / 'data/greek-ndvi-known/ndvi-report.json')}
    for name, frame in domains.items():
        frame = frame.merge(coords, on=['region', 'cell_id'], validate='many_to_one')
        tensors, audit = store.make(frame)
        path = folder / (name + '.npz')
        np.savez_compressed(path, **tensors)
        report['parts'][name] = dict(audit, sha256=sha(path))
        print('Prepared known benchmark', name, audit, flush=True)
    if verify_frozen(out)[1] != frozen_hash:
        raise ValueError('Model selection changed during known-year preparation')
    (folder / 'manifest.json').write_text(json.dumps(report, indent=2))
    return report


def score(root, out):
    root, out = Path(root), Path(out)
    frozen, frozen_hash = verify_frozen(out)
    folder = root / 'outputs/greek-known-benchmark-data'
    manifest = json.loads((folder / 'manifest.json').read_text())
    if manifest['selection_sha256'] != frozen_hash:
        raise ValueError('Known-year cohort belongs to different frozen models')
    results, rows = {}, []
    # Evaluate every retained candidate: no test-selected shortlist or model promotion.
    for name, record in manifest['parts'].items():
        path = folder / (name + '.npz')
        if sha(path) != record['sha256']:
            raise ValueError('Known-year tensor integrity failed')
        with np.load(path) as a:
            data = {k: a[k] for k in a.files}
        for identifier, model_record in frozen['artifacts'].items():
            artifact = joblib.load(out / 'frozen' / model_record['file'])
            p = artifact['model'].predict(data)
            threshold = artifact['thresholds']['lebanon' if name.startswith('lebanon') else 'global']
            result = evaluate(data, p, threshold)
            results.setdefault(identifier, {})[name] = result
            rows.append({'model': identifier, 'domain': name, **{k: result[k] for k in ['observations', 'positive_windows', 'pr_auc_average_precision', 'roc_auc', 'precision', 'recall', 'f1', 'brier', 'threshold', 'prevalence', 'mean_probability']}})
        print('Scored all frozen models on', name, flush=True)
    if verify_frozen(out)[1] != frozen_hash:
        raise ValueError('Frozen selections changed after known-year reporting')
    report = {'selection_sha256': frozen_hash, 'fresh_confirmation': False, 'manifest': manifest, 'results': results,
              'note': 'Models/thresholds unchanged. Known 2023-2026 outcomes are diagnostic only; do not promote a model from these scores.'}
    (out / 'known-results.json').write_text(json.dumps(report, indent=2))
    pd.DataFrame(rows).to_csv(out / 'known-results.csv', index=False)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['prepare', 'score'])
    p.add_argument('--root', default='.')
    p.add_argument('--out', default='outputs/greek-temporal-benchmark')
    a = p.parse_args()
    if a.operation == 'prepare':
        prepare(Path(a.root).resolve(), Path(a.out).resolve())
    else:
        score(Path(a.root).resolve(), Path(a.out).resolve())


if __name__ == '__main__':
    main()
