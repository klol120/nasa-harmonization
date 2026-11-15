"""Adapt external NASA-pretrained image encoders to Lebanese occurrence labels.

Fit/calibration/validation are separate. Previously viewed later-year tests are
diagnostics, not fresh confirmation. Never overwrite an evaluated run.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from .benchmark_global import select_threshold
from .benchmark_temporal import evaluate, sha
from .temporal_models import flat, Calibrated, Tabular, Seasonal


def subset(data, cells):
    use = np.isin(data['cell_id'], list(cells))
    return {k: a[use] for k, a in data.items()}, {
        'original_windows': len(use), 'original_positive_windows': int(data['y'].sum()),
        'kept_windows': int(use.sum()), 'kept_positive_windows': int(data['y'][use].sum()),
        'missing_hls_excluded_windows': int((~use).sum()),
        'missing_hls_excluded_positive_windows': int(data['y'][~use].sum())}


def head_network(width, weather_width, hidden):
    import torch
    from torch import nn

    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(width) if width else nn.Identity()
            self.head = nn.Sequential(nn.Linear(width + weather_width, hidden), nn.ReLU(), nn.Dropout(.2), nn.Linear(hidden, 1))

        def forward(self, tokens, weather, image_mean, image_std):
            if width:
                image = self.norm(tokens)[:, 1:].mean(dim=1)
                image = (image - image_mean) / image_std
                weather = torch.cat([weather, image], dim=1)
            return self.head(weather).squeeze(1)

    return Head()


class PretrainedHead:
    """Fine-tune final pretrained LayerNorm plus a new head, or freeze the encoder.

    Earlier encoder layers are immutable and their exact pre-LayerNorm tokens are
    cached. This is algebraically identical to rerunning those frozen layers; the
    trained normalization is part of the original pretrained encoder.
    """
    def __init__(self, tokens=None, tune_norm=False, config=None):
        self.tokens, self.tune_norm, self.config = tokens, tune_norm, config

    def image_indices(self, data):
        if self.tokens is None:
            return np.zeros(len(data['cell_id']), dtype=int)
        lookup = {str(c): i for i, c in enumerate(self.tokens['cell_id'])}
        try:
            return np.asarray([lookup[str(c)] for c in data['cell_id']])
        except KeyError as exc:
            raise ValueError('Missing real HLS image; withhold this cell') from exc

    def fit(self, data):
        import torch
        cfg = self.config
        torch.set_num_threads(cfg['threads'])
        torch.manual_seed(cfg['seed'])
        y = data['y']
        if len(np.unique(y)) != 2:
            raise ValueError('Head fitting needs both classes')
        self.scaler = StandardScaler().fit(flat(data))
        weather = torch.from_numpy(self.scaler.transform(flat(data)).astype(np.float32))
        width = self.tokens['tokens'].shape[-1] if self.tokens is not None else 0
        self.width, self.weather_width = width, weather.shape[-1]
        model = head_network(width, self.weather_width, cfg['hidden_width'])
        token_bank = torch.from_numpy(self.tokens['tokens']) if width else torch.zeros((1, 1, 1))
        initial = {}
        if width:
            initial = {'weight': torch.from_numpy(self.tokens['norm_weight'].copy()), 'bias': torch.from_numpy(self.tokens['norm_bias'].copy())}
            model.norm.load_state_dict(initial)
            for p in model.norm.parameters():
                p.requires_grad_(self.tune_norm)
            with torch.no_grad():
                source_embedding = model.norm(token_bank)[:, 1:].mean(dim=1).numpy()
            self.image_scaler = StandardScaler().fit(source_embedding[self.image_indices(data)])
            self.image_mean = self.image_scaler.mean_.astype(np.float32)
            self.image_std = self.image_scaler.scale_.astype(np.float32)
        else:
            self.image_mean, self.image_std = np.zeros(0, np.float32), np.ones(0, np.float32)
        image_mean, image_std = torch.from_numpy(self.image_mean), torch.from_numpy(self.image_std)
        indices = self.image_indices(data)
        positive_weight = float(min(10, np.sqrt((len(y) - y.sum()) / y.sum())))
        model.head[-1].bias.data.fill_(float(np.log(y.mean() / (1 - y.mean())) + np.log(positive_weight)))
        objective = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(positive_weight))
        groups = [{'params': model.head.parameters(), 'lr': cfg['learning_rate']}]
        if width and self.tune_norm:
            groups.append({'params': model.norm.parameters(), 'lr': cfg['layernorm_learning_rate']})
        optimizer = torch.optim.Adam(groups, weight_decay=.001)
        target = torch.tensor(y, dtype=torch.float32)
        rng = np.random.default_rng(cfg['seed'])
        self.losses = []
        started = time.perf_counter()
        model.train()
        for epoch in range(cfg['head_epochs']):
            total = 0.
            order = rng.permutation(len(y))
            for start in range(0, len(y), cfg['batch_size']):
                idx = order[start:start + cfg['batch_size']]
                optimizer.zero_grad(set_to_none=True)
                loss = objective(model(token_bank[indices[idx]], weather[idx], image_mean, image_std), target[idx])
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite transfer loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
                optimizer.step()
                total += float(loss.detach()) * len(idx)
            self.losses.append(total / len(y))
        self.state = {k: v.detach().numpy().copy() for k, v in model.state_dict().items()}
        delta = sum(float(np.square(self.state['norm.' + key] - value.numpy()).sum()) for key, value in initial.items())
        self.training = {'seconds': time.perf_counter() - started, 'fit_windows': len(y), 'positive_windows': int(y.sum()),
                         'epochs': cfg['head_epochs'], 'positive_weight': positive_weight, 'seed': cfg['seed'],
                         'pretrained_norm_tuned': self.tune_norm, 'norm_weight_change_l2': float(np.sqrt(delta)),
                         'backbone_trainable_parameters': 2 * width if self.tune_norm else 0,
                         'all_trainable_parameters': sum(p.numel() for p in model.parameters() if p.requires_grad),
                         'earlier_transformer_blocks_frozen': True}
        return self

    def predict(self, data):
        import torch
        model = head_network(self.width, self.weather_width, self.config['hidden_width'])
        model.load_state_dict({k: torch.from_numpy(v) for k, v in self.state.items()})
        model.eval()
        weather = self.scaler.transform(flat(data)).astype(np.float32)
        indices = self.image_indices(data)
        token_bank = torch.from_numpy(self.tokens['tokens']) if self.width else torch.zeros((1, 1, 1))
        result = []
        with torch.inference_mode():
            for i in range(0, len(weather), 4096):
                logits = model(token_bank[indices[i:i+4096]], torch.from_numpy(weather[i:i+4096]),
                               torch.from_numpy(self.image_mean), torch.from_numpy(self.image_std))
                result.append(torch.sigmoid(logits).numpy())
        return np.concatenate(result)


def load_part(root, split, record):
    path = root / 'outputs/greek-temporal-data' / ('lebanon-' + split + '.npz')
    if sha(path) != record['sha256']:
        raise ValueError('Supervised split hash differs')
    with np.load(path) as arrays:
        return {k: arrays[k] for k in arrays.files}


def fit(root, out, config_path):
    root, out = Path(root), Path(out)
    config = json.loads(Path(config_path).read_text())
    if (out / 'selection-frozen.json').exists():
        raise ValueError('Already frozen; use a new run directory instead of overwriting')
    folder = root / 'data/pretrained-models'
    tokens, source_meta, common = {}, {}, None
    for record in config['models']:
        path = folder / (record['id'] + '-tokens.npz')
        meta = json.loads(path.with_suffix('.json').read_text())
        if meta['model'] != record or sha(path) != meta['token_sha256']:
            raise ValueError('Source checkpoint/token identity mismatch')
        with np.load(path) as a:
            tokens[record['id']] = {k: a[k] for k in a.files}
        cells = set(tokens[record['id']]['cell_id'])
        common = cells if common is None else common & cells
        source_meta[record['id']] = meta
    manifest = json.loads((root / 'outputs/greek-temporal-data/manifest.json').read_text())
    image_manifest = json.loads((folder / 'hls-patches/manifest.json').read_text())
    conflict = json.loads((root / 'outputs/global-transfer-data/dataset-manifest.json').read_text())
    datasets, audits = {}, {}
    for name in ['train', 'calibration', 'validation']:
        data = load_part(root, name, manifest['parts']['lebanon-' + name])
        datasets[name], audits[name] = subset(data, common)
        if len(np.unique(datasets[name]['y'])) != 2:
            raise ValueError('Common image-qualified split lacks both classes')
    for before, after in [('train', 'calibration'), ('calibration', 'validation')]:
        if datasets[after]['time'].min() - datasets[before]['time'].max() <= 13:
            raise ValueError('Historical feature windows overlap split')
    out.mkdir(parents=True, exist_ok=True)
    candidates = [('seasonal', Seasonal()), ('weather-logistic', Tabular('logistic_weather', config['seed'])),
                  ('environment-logistic', Tabular('logistic', config['seed'])),
                  ('no-image-mlp', PretrainedHead(config=config))]
    for name, bank in tokens.items():
        for strategy in config['strategies']:
            candidates.append((name + '-' + strategy, PretrainedHead(bank, strategy == 'final_layernorm_tuning', config)))
    records, validations = {}, {}
    for name, base in candidates:
        base.fit(datasets['train'])
        model = Calibrated(base).fit(datasets['calibration'])
        probabilities = model.predict(datasets['validation'])
        threshold, useful_thresholds = select_threshold(datasets['validation']['y'], probabilities)
        result = evaluate(datasets['validation'], probabilities, threshold)
        validations[name] = result
        path = out / (name + '.joblib')
        artifact = {'model': model, 'threshold': threshold, 'mode': 'retrospective', 'production_approved': False,
                    'id': name, 'stage': 'external_lebanon', 'config': manifest['config'],
                    'feature_contract': {'dynamic': manifest['dynamic_features'], 'static': manifest['static_features']},
                    'required_image_cell_ids': sorted(common),
                    'image_provenance': {r['cell_id']: {k: r[k] for k in ['observation_time', 'retrieved_at', 'sha256']} for r in image_manifest['records']},
                    'source_checkpoint_retrieved_at': max(m['retrieved_at'] for m in source_meta.values()),
                    'conflict_excluded_cell_ids': conflict['conflict_excluded_cell_ids'], 'conflict_start': conflict['conflict_policy']['start'],
                    'training': getattr(base, 'training', {}), 'validation_precision_targets': useful_thresholds,
                    'input_contract': 'NASA historical features and cached pre-2018 HLS at exact known cell IDs; missing image requires withholding'}
        joblib.dump(artifact, path, compress=3)
        records[name] = {'file': path.name, 'sha256': sha(path), 'training': artifact['training']}
        print(name, 'validation AP', result['pr_auc_average_precision'], flush=True)
    ranked = sorted(validations, key=lambda k: (-validations[k]['pr_auc_average_precision'], validations[k]['brier']))
    pretrained_names = [x for x in ranked if x.startswith('prithvi')]
    previous_root = root / 'outputs/greek-temporal-benchmark'
    previous = json.loads((previous_root / 'selection-frozen.json').read_text())
    references = {}
    for identifier in [previous['best_global'], previous['best_lebanon'], previous['best_transfer']]:
        record = previous['artifacts'][identifier]
        path = previous_root / 'frozen' / record['file']
        if sha(path) != record['sha256']:
            raise ValueError('Previously frozen reference changed')
        artifact = joblib.load(path)
        references[identifier] = {'path': str(path.relative_to(root)), 'sha256': record['sha256'],
                                 'note': 'Earlier model trained before HLS row exclusions; unchanged reference, outside new candidate selection',
                                 'validation': evaluate(datasets['validation'], artifact['model'].predict(datasets['validation']), artifact['thresholds']['lebanon'])}
    frozen = {'frozen_at': datetime.now(timezone.utc).isoformat(), 'config': config, 'config_sha256': sha(config_path),
              'source_meta': source_meta, 'cohort': audits, 'common_cells': sorted(common),
              'candidate_count': len(records), 'selected_overall': ranked[0], 'selected_pretrained': pretrained_names[0],
              'validation': validations, 'artifacts': records, 'references': references, 'production_approved': False,
              'known_tests_already_viewed': True, 'fresh_confirmation_available': False}
    (out / 'selection-frozen.json').write_text(json.dumps(frozen, indent=2))
    return frozen


def score(root, out):
    root, out = Path(root), Path(out)
    frozen_path = out / 'selection-frozen.json'
    frozen_hash = sha(frozen_path)
    frozen = json.loads(frozen_path.read_text())
    folder = root / 'outputs/greek-known-benchmark-data'
    manifest = json.loads((folder / 'manifest.json').read_text())
    results, reference_results, audits, rows = {}, {}, {}, []
    for name in ['lebanon_known_2023_2025', 'lebanon_known_2026_JanOct']:
        path = folder / (name + '.npz')
        if sha(path) != manifest['parts'][name]['sha256']:
            raise ValueError('Known test tensor integrity mismatch')
        with np.load(path) as a:
            data, audits[name] = subset({k: a[k] for k in a.files}, frozen['common_cells'])
        for identifier, record in frozen['artifacts'].items():
            path = out / record['file']
            if sha(path) != record['sha256']:
                raise ValueError('Frozen candidate changed before testing')
            artifact = joblib.load(path)
            p = artifact['model'].predict(data)
            result = evaluate(data, p, artifact['threshold'])
            result['by_season'] = {}
            months = pd.to_datetime(data['time'], unit='D').month.to_numpy()
            seasons = (months % 12) // 3
            for season in np.unique(seasons):
                use = seasons == season
                result['by_season'][str(season)] = evaluate({'y': data['y'][use]}, p[use], artifact['threshold'])
            results.setdefault(identifier, {})[name] = result
            rows.append({'model': identifier, 'domain': name, **{k: result[k] for k in ['observations', 'positive_windows', 'pr_auc_average_precision', 'precision', 'recall', 'f1', 'brier', 'threshold', 'roc_auc']}})
        for identifier, record in frozen['references'].items():
            path = root / record['path']
            if sha(path) != record['sha256']:
                raise ValueError('Prior reference changed before evaluation')
            artifact = joblib.load(path)
            metric = evaluate(data, artifact['model'].predict(data), artifact['thresholds']['lebanon'])
            reference_results.setdefault(identifier, {})[name] = metric
        print('Scored fixed candidates', name, flush=True)
    if sha(frozen_path) != frozen_hash:
        raise ValueError('Selection changed during test reporting')
    report = {'selection_sha256': frozen_hash, 'selection': frozen, 'test_cohort': audits, 'results': results, 'reference_results': reference_results,
              'fresh_confirmation': False, 'production_approved': False,
              'note': 'Previously viewed outcomes, modern pretraining and repeated validation search: retrospective diagnostics only; no reselection from tests'}
    (out / 'results.json').write_text(json.dumps(report, indent=2))
    pd.DataFrame(rows).to_csv(out / 'results.csv', index=False)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['fit', 'score'])
    p.add_argument('--root', default='.')
    p.add_argument('--out', default='outputs/pretrained-transfer')
    p.add_argument('--config', default='configs/pretrained-transfer.json')
    a = p.parse_args()
    # Import the canonical module before creating serializable classes. Running
    # `python -m` otherwise gives them __main__ names that other CLIs cannot load.
    from firecast.benchmark_pretrained import fit as run_fit, score as run_score
    run_fit(a.root, a.out, a.config) if a.operation == 'fit' else run_score(a.root, a.out)
