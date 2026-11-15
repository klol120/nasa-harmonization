import json
from types import SimpleNamespace

import numpy as np
import pytest

from firecast.older_evaluation import evaluation_data, guard, older_hls_manifest, substitute_image_inputs


def test_unknown_labels_missing_features_and_old_image_exclusions_stay_separate():
    data = {'sequence': np.ones((4, 10, 9)), 'static': np.ones((4, 23)),
            'time': np.arange(4), 'region': np.asarray(['lebanon'] * 4),
            'cell_id': np.asarray(['a', 'b', 'c', 'd']),
            'feature_valid': np.asarray([True, True, False, True]),
            'y_strict': np.asarray([0., 1., 1., np.nan])}
    kept, audit = evaluation_data(data, 'strict', {'a'})
    assert kept['y'].tolist() == [0]
    assert audit['image_scope_excluded_positive_windows'] == 1
    assert data['y_strict'][2] == 1 and np.isnan(data['y_strict'][3])
    data['temporal_eligible'] = np.asarray([True, False, True, True])
    embargoed, _ = evaluation_data(data, 'strict')
    assert embargoed['y'].tolist() == [0]
    assert data['y_strict'][1] == 1


def test_substitute_older_imagery_preserves_all_fitted_state():
    old = {'tokens': np.ones((2, 5, 8)), 'norm_weight': np.ones(8), 'norm_bias': np.zeros(8)}
    bank = dict(old, tokens=np.zeros((2, 5, 8)))
    base = SimpleNamespace(tokens=old, state={'learned': np.asarray([2.])}, scaler=object())
    model = SimpleNamespace(base=base, calibrator=object())
    changed = substitute_image_inputs(model, bank)
    assert changed.base.tokens is bank and model.base.tokens is old
    assert changed.base.state is model.base.state
    assert changed.base.scaler is model.base.scaler
    assert changed.calibrator is model.calibrator
    with pytest.raises(ValueError, match='another pretrained checkpoint'):
        substitute_image_inputs(model, dict(bank, norm_weight=np.zeros(8)))


def test_hls_date_guard_rejects_2017_imagery_for_2016_evaluation(tmp_path):
    p = tmp_path / 'manifest.json'
    p.write_text(json.dumps({'selection': 'original', 'records': [{'observation_time': '2017-01-01T00:00:00Z'}]}))
    with pytest.raises(ValueError, match='pre-2016'):
        older_hls_manifest(p)
    p.write_text(json.dumps({'selection': '2017 June-October', 'records': [{'observation_time': '2015-07-01T00:00:00Z'}]}))
    result = older_hls_manifest(p)
    assert result['observation_years'] == ['2015']
    assert result['records'][0]['observation_time'] == '2015-07-01T00:00:00Z'


def test_evaluation_refuses_model_training_overlap(tmp_path):
    folder = tmp_path / 'outputs/greek-temporal-data'
    folder.mkdir(parents=True)
    np.savez(folder / 'global-train.npz', time=np.asarray([np.datetime64('2017-06-01', 'D').astype(int)]))
    config = {'frozen_inputs': {}, 'fit_allowed': False, 'calibration_allowed': False,
              'threshold_changes_allowed': False, 'evaluation_end_exclusive': '2018-01-01T00:00:00Z'}
    with pytest.raises(ValueError, match='trained on the older evaluation period'):
        guard(tmp_path, config)


def test_registration_and_scored_cohorts_cannot_be_silently_overwritten(tmp_path, monkeypatch):
    import firecast.older_evaluation as module
    monkeypatch.setattr(module, 'guard', lambda *_: {})
    (tmp_path / 'configs').mkdir()
    source = tmp_path / 'frozen-input'
    source.write_text('original')
    template = {'frozen_inputs': {'frozen-input': module.sha(source)}}
    path = tmp_path / 'configs/older-evaluation.json'
    path.write_text(json.dumps(template))
    module.register(tmp_path, path)
    source.write_text('changed')
    before = path.read_bytes()
    with pytest.raises(ValueError, match='existing registration'):
        module.register(tmp_path, path)
    assert path.read_bytes() == before
    folder = tmp_path / 'custom-scored-data'
    folder.mkdir()
    (folder / 'manifest.json').write_text('{}')
    (folder / 'scored-receipt.json').write_text('{}')
    with pytest.raises(ValueError, match='evaluated cohort'):
        module.prepare(tmp_path, path, folder, rebuild_unscored=True)
