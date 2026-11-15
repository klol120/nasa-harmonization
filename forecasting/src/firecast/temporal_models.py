"""CPU temporal models and explicit source-to-local adaptations on common tensors."""
import copy
import time

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier


def flat(data):
    return np.column_stack([data['sequence'].reshape(len(data['static']), -1), data['static']]).astype(np.float32)


class Tabular:
    def __init__(self, family, seed=42, parent=None):
        self.family, self.seed, self.parent = family, seed, parent

    def x(self, data):
        if self.family.endswith('_weather'):
            x = np.column_stack([data['sequence'][:, :, :7].reshape(len(data['static']), -1),
                                 data['static'][:, :9], data['static'][:, 15:19]]).astype(np.float32)
        else:
            x = flat(data)
        if self.parent is not None:
            x = np.column_stack([x, logit(np.clip(self.parent.predict(data), 1e-6, 1 - 1e-6))])
        return x

    def fit(self, data):
        x, y = self.x(data), data['y']
        if len(np.unique(y)) != 2:
            raise ValueError('Training requires both classes')
        self.scaler = None
        base_family = self.family.removesuffix('_weather')
        if base_family == 'logistic':
            self.scaler = StandardScaler().fit(x)
            x = self.scaler.transform(x)
            self.estimator = LogisticRegression(C=.1, max_iter=400, random_state=self.seed)
        elif base_family == 'random_forest':
            self.estimator = RandomForestClassifier(n_estimators=80, max_depth=12, max_leaf_nodes=256,
                                                   min_samples_leaf=25, max_samples=min(len(y), 100000),
                                                   n_jobs=3, random_state=self.seed)
        elif base_family == 'xgboost':
            from xgboost import XGBClassifier
            self.estimator = XGBClassifier(n_estimators=160, max_depth=3, learning_rate=.05,
                                           min_child_weight=10, reg_lambda=5, colsample_bytree=.8,
                                           tree_method='hist', n_jobs=3, random_state=self.seed)
        else:
            raise ValueError('Unknown tabular family')
        self.estimator.fit(x, y)
        self.fit_windows, self.fit_positive_windows = len(y), int(y.sum())
        return self

    def predict(self, data):
        x = self.x(data)
        if self.scaler is not None:
            x = self.scaler.transform(x)
        return self.estimator.predict_proba(x)[:, 1]


class Seasonal:
    def fit(self, data):
        months = pd.to_datetime(data['time'], unit='D').month.to_numpy()
        northern = data['static'][:, 14] >= 0
        self.rate = (data['y'].sum() + 1) / (len(data['y']) + 2)
        self.rates = {}
        for north in [False, True]:
            for month in range(1, 13):
                use = (northern == north) & (months == month)
                if use.any():
                    self.rates[(north, month)] = (data['y'][use].sum() + 1) / (use.sum() + 2)
        return self

    def predict(self, data):
        months = pd.to_datetime(data['time'], unit='D').month.to_numpy()
        return np.asarray([self.rates.get((bool(a), int(b)), self.rate) for a, b in zip(data['static'][:, 14] >= 0, months)])


def network(dynamic, static, hidden):
    # Import is optional for the base pipeline; only this temporal extra needs torch.
    import torch
    from torch import nn

    class Architecture(nn.Module):
        def __init__(self):
            super().__init__()
            self.norm = nn.LayerNorm(dynamic)
            self.lstm = nn.LSTM(dynamic, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(hidden + static, hidden), nn.ReLU(), nn.Dropout(.5),
                                      nn.Linear(hidden, hidden // 2), nn.ReLU(), nn.Dropout(.5), nn.Linear(hidden // 2, 1))

        def forward(self, history, context):
            out, _ = self.lstm(self.norm(history))
            return self.head(torch.cat([out[:, -1], context], dim=1)).squeeze(1)

    return Architecture()


class Temporal:
    def __init__(self, hidden=64, seed=42, threads=3):
        self.hidden, self.seed, self.threads = hidden, seed, threads

    def fit(self, data, epochs=10, batch_size=2048, lr=.001, parent=None):
        import torch
        torch.set_num_threads(self.threads)
        torch.manual_seed(self.seed)
        rng = np.random.default_rng(self.seed)
        y = data['y']
        if len(np.unique(y)) != 2:
            raise ValueError('Training requires both classes')
        if parent is None:
            self.sequence_scaler = StandardScaler().fit(data['sequence'].reshape(-1, data['sequence'].shape[-1]))
            self.static_scaler = StandardScaler().fit(data['static'])
            self.dynamic_width = data['sequence'].shape[-1]
            self.static_width = data['static'].shape[-1]
            self.state = None
        else:
            if self.hidden != parent.hidden:
                raise ValueError('Adaptation architecture mismatch')
            self.sequence_scaler = copy.deepcopy(parent.sequence_scaler)
            self.static_scaler = copy.deepcopy(parent.static_scaler)
            self.dynamic_width, self.static_width = parent.dynamic_width, parent.static_width
            self.state = {k: v.copy() for k, v in parent.state.items()}
        model = network(self.dynamic_width, self.static_width, self.hidden)
        if self.state is not None:
            model.load_state_dict({k: torch.from_numpy(v) for k, v in self.state.items()})
        history = self.sequence_scaler.transform(data['sequence'].reshape(-1, self.dynamic_width)).reshape(data['sequence'].shape).astype(np.float32)
        static = self.static_scaler.transform(data['static']).astype(np.float32)
        history, static, target = torch.from_numpy(history), torch.from_numpy(static), torch.tensor(y, dtype=torch.float32)
        positive_weight = float(min(10, np.sqrt((len(y) - y.sum()) / y.sum())))
        objective = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(positive_weight))
        optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=.001)
        self.losses = []
        started = time.perf_counter()
        model.train()
        for epoch in range(epochs):
            order = rng.permutation(len(y))
            total = 0.
            for start in range(0, len(y), batch_size):
                idx = order[start:start + batch_size]
                optimizer.zero_grad(set_to_none=True)
                loss = objective(model(history[idx], static[idx]), target[idx])
                if not torch.isfinite(loss):
                    raise ValueError('Nonfinite temporal loss')
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.)
                optimizer.step()
                total += float(loss.detach()) * len(idx)
            self.losses.append(total / len(y))
            print('LSTM', self.hidden, 'epoch', epoch + 1, '/', epochs, 'loss', round(self.losses[-1], 6), flush=True)
        self.state = {k: v.detach().cpu().numpy().copy() for k, v in model.state_dict().items()}
        self.fit_windows, self.fit_positive_windows = len(y), int(y.sum())
        self.training = {'epochs': epochs, 'batch_size': batch_size, 'lr': lr, 'positive_weight': positive_weight,
                         'seconds': time.perf_counter() - started, 'continued_weights': parent is not None,
                         'scalers_frozen_from_parent': parent is not None}
        if parent is not None:
            self.training['weight_change_l2'] = float(np.sqrt(sum(np.square(self.state[k] - parent.state[k]).sum() for k in self.state)))
        return self

    def predict(self, data):
        import torch
        torch.set_num_threads(self.threads)
        model = network(self.dynamic_width, self.static_width, self.hidden)
        model.load_state_dict({k: torch.from_numpy(v) for k, v in self.state.items()})
        model.eval()
        result = []
        with torch.inference_mode():
            for start in range(0, len(data['static']), 4096):
                stop = start + 4096
                history = data['sequence'][start:stop]
                history = self.sequence_scaler.transform(history.reshape(-1, self.dynamic_width)).reshape(history.shape).astype(np.float32)
                static = self.static_scaler.transform(data['static'][start:stop]).astype(np.float32)
                result.append(torch.sigmoid(model(torch.from_numpy(history), torch.from_numpy(static))).numpy())
        return np.concatenate(result)


class Calibrated:
    def __init__(self, base):
        self.base = base

    def fit(self, data):
        if len(np.unique(data['y'])) != 2:
            raise ValueError('Natural-prevalence calibration needs both classes')
        x = logit(np.clip(self.base.predict(data), 1e-7, 1 - 1e-7)).reshape(-1, 1)
        self.calibrator = LogisticRegression(C=1, max_iter=300).fit(x, data['y'])
        self.calibration_windows, self.calibration_positive_windows = len(data['y']), int(data['y'].sum())
        return self

    def predict(self, data):
        x = logit(np.clip(self.base.predict(data), 1e-7, 1 - 1e-7)).reshape(-1, 1)
        return self.calibrator.predict_proba(x)[:, 1]


class RegionalRouter:
    """Use fixed global weights outside Lebanon and fixed adapted weights inside it."""
    def __init__(self, global_model, lebanon_model):
        self.global_model, self.lebanon_model = global_model, lebanon_model

    def predict(self, data):
        p = self.global_model.predict(data)
        use = data['region'] == 'lebanon'
        if use.any():
            subset = {k: v[use] for k, v in data.items()}
            p[use] = self.lebanon_model.predict(subset)
        return p
