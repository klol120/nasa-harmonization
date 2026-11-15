import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from firecast.temporal_data import past_indices, ndvi_asof
from firecast.greek_environment import ndvi_good, cmg_indices


def test_daily_history_ends_before_lag_and_rejects_missing_days():
    dates = np.arange('2020-01-01', '2020-02-01', dtype='datetime64[D]')
    idx, valid = past_indices(['2020-01-20'], dates, days=10, lag=3)
    assert valid.tolist() == [True]
    assert dates[idx][0, 0] == np.datetime64('2020-01-07')
    assert dates[idx][0, -1] == np.datetime64('2020-01-16')
    _, valid = past_indices(['2020-01-20'], np.delete(dates, 12), days=10, lag=3)
    assert valid.tolist() == [False]
    with pytest.raises(ValueError):
        past_indices(['2020-01-20'], dates, lag=-1)


def test_ndvi_never_uses_incomplete_or_future_composites():
    values = np.array([[.3], [.8], [.99]])
    a = ndvi_asof(['2020-03-01'], [0], ['2020-01-01', '2020-02-01', '2020-03-01'], values)
    assert a[0, 0] == pytest.approx(.3)
    b = ndvi_asof(['2020-03-17'], [0], ['2020-01-01', '2020-02-01', '2020-03-01'], values)
    assert b[0, 0] == pytest.approx(.8) and b[0, 3] == 1
    assert np.isnan(ndvi_asof(['2021-01-01'], [0], ['2020-01-01'], values[:1])).all()


def test_cmg_high_bits_are_spatial_coverage_not_snow_or_shadow():
    good = np.uint16((3 << 14) | (1 << 11))
    q = np.array([good, good, good | (1 << 10), (1 << 11), good | 1])
    assert ndvi_good([6000] * 5, q, [0, 4, 0, 0, 0]).tolist() == [True, False, False, False, False]
    rows, cols = cmg_indices([89.975, -.025], [-179.975, .025])
    assert rows.tolist() == [0, 1800] and cols.tolist() == [0, 3600]


def test_explicit_confirmation_days_are_bounded_unique_and_midnight():
    from firecast.global_acquire import sample_days
    c = {'start': '2026-11-01T00:00:00Z', 'end_exclusive': '2026-11-08T00:00:00Z', 'sample_dates': ['2026-11-07', '2026-11-01']}
    assert sample_days(c).strftime('%Y-%m-%d').tolist() == ['2026-11-01', '2026-11-07']
    for dates in [['2026-10-31'], ['2026-11-01', '2026-11-01'], ['2026-11-01T01:00:00Z']]:
        with pytest.raises(ValueError):
            sample_days(dict(c, sample_dates=dates))


def test_noaa_originals_pack_and_restore_exact_bytes(tmp_path):
    from firecast.cache_pack import pack, restore
    raw, packed = tmp_path / 'raw', tmp_path / 'packed'
    raw.mkdir()
    p = raw / 'VJ114A1.example.h5'
    content = b'original NASA-format fixture bytes' * 20
    p.write_bytes(content)
    p.with_suffix('.h5.manifest.json').write_text(json.dumps({'sha256': hashlib.sha256(content).hexdigest()}))
    assert pack(raw, packed, target_free=10**20, product='VJ114A1') == 1
    assert not p.exists()
    restore(packed, raw)
    assert p.read_bytes() == content


def test_actual_lstm_continuation_updates_weights_and_preserves_source_scalers():
    pytest.importorskip('torch')
    from firecast.temporal_models import Temporal
    rng = np.random.default_rng(42)
    data = {'sequence': rng.normal(size=(40, 10, 3)).astype('float32'), 'static': rng.normal(size=(40, 4)).astype('float32'), 'y': np.tile([0, 1], 20)}
    model = Temporal(8, threads=1).fit(data, epochs=1, batch_size=20)
    state = {k: v.copy() for k, v in model.state.items()}
    mean = model.sequence_scaler.mean_.copy()
    adapted = Temporal(8, threads=1).fit(data, epochs=1, batch_size=20, parent=model)
    assert adapted.training['weight_change_l2'] > 0
    assert all(np.array_equal(model.state[k], v) for k, v in state.items())
    assert np.array_equal(adapted.sequence_scaler.mean_, mean)
    assert np.isfinite(adapted.predict(data)).all()
    without_labels = {k: v for k, v in data.items() if k != 'y'}
    assert np.array_equal(adapted.predict(data), adapted.predict(without_labels))


def test_confirmation_refuses_missing_or_changed_selection_before_acquisition(tmp_path):
    from firecast.temporal_confirmation import guard
    with pytest.raises(FileNotFoundError):
        guard(tmp_path, tmp_path / 'missing')
    out = tmp_path / 'out'
    (out / 'frozen').mkdir(parents=True)
    model = out / 'frozen/model.joblib'
    model.write_bytes(b'altered model')
    (out / 'selection-frozen.json').write_text(json.dumps({'artifacts': {'model': {'file': model.name, 'sha256': '0' * 64}}}))
    with pytest.raises(ValueError, match='artifact changed'):
        guard(tmp_path, out)


def test_weather_ablation_cannot_see_wetness_vegetation_or_terrain():
    from firecast.temporal_models import Tabular
    rng = np.random.default_rng(23)
    a = {'sequence': rng.normal(size=(10, 10, 9)), 'static': rng.normal(size=(10, 23)), 'y': np.tile([0, 1], 5)}
    b = {k: v.copy() for k, v in a.items()}
    b['sequence'][:, :, 7:] = 9999.
    b['static'][:, 9:15] = 9999.
    b['static'][:, 19:] = 9999.
    model = Tabular('xgboost_weather')
    assert np.array_equal(model.x(a), model.x(b))
    assert not np.array_equal(Tabular('xgboost').x(a), Tabular('xgboost').x(b))


def test_missing_ndvi_excludes_a_positive_without_turning_it_into_a_negative():
    from firecast.temporal_data import HistoryStore, DYNAMIC
    from firecast.global_data import FEATURES
    store = HistoryStore.__new__(HistoryStore)
    store.config = {'history_days': 10, 'history_lag_days': 3, 'ndvi_lag_days_after_composite_end': 16, 'ndvi_max_age_days': 120}
    points = pd.DataFrame({'weather_point_id': ['p'], 'lat': [34.], 'lon': [36.]})
    store.points = {'lebanon': points}
    dates = np.arange('2020-01-01', '2020-02-01', dtype='datetime64[D]')
    store.series = {('lebanon', 'p'): (dates, np.ones((len(dates), len(DYNAMIC)), dtype='float32'))}
    store.ndvi_cells = {('lebanon', 'x'): 0}
    store.ndvi_months = ['2019-12-01']
    store.ndvi_values = np.array([[np.nan]])
    frame = pd.DataFrame({c: [0.] for c in FEATURES})
    frame = frame.assign(region='lebanon', cell_id='x', lat=34., lon=36., y=1,
                         prediction_time=pd.Timestamp('2020-01-20', tz='UTC'))
    data, audit = store.make(frame)
    assert len(data['y']) == 0 and audit['excluded_positive_windows'] == 1
    assert frame.y.tolist() == [1]


class ConstantResearchModel:
    def predict(self, data):
        assert 'y' not in data
        return np.full(len(data['static']), .1)


def test_research_inference_rejects_future_inputs_wrong_history_and_unapproved_release():
    from firecast.temporal_inference import predict
    artifact = {'model': ConstantResearchModel(), 'id': 'research', 'production_approved': False,
                'feature_contract': {'dynamic': ['x'], 'static': ['x']},
                'config': {'history_days': 10, 'history_lag_days': 3}}
    inputs = {'sequence': np.ones((1, 10, 1), dtype='float32'), 'static': np.ones((1, 1), dtype='float32')}
    metadata = pd.DataFrame({'cell_id': ['x'], 'region': ['lebanon'], 'lat': [34.], 'lon': [36.],
        'prediction_time': ['2026-11-20T00:00:00Z'], 'forecast_issued_at': ['2026-11-19T00:00:00Z'],
        'forecast_available_at': ['2026-11-19T06:00:00Z'], 'history_latest_available_at': ['2026-11-19T00:00:00Z'],
        'vegetation_available_at': ['2026-11-15T00:00:00Z'], 'vegetation_composite_end': ['2026-11-01T00:00:00Z'],
        'static_available_at': ['2026-11-15T00:00:00Z'],
        'forecast_valid_start': ['2026-11-20T00:00:00Z'], 'forecast_valid_end': ['2026-11-21T00:00:00Z'],
        'history_start': ['2026-11-07T00:00:00Z'], 'history_end': ['2026-11-16T00:00:00Z']})
    with pytest.raises(ValueError, match='release'):
        predict(artifact, inputs, metadata)
    assert predict(artifact, inputs, metadata, research_only=True)[0]['probability'] == .1
    future = metadata.assign(forecast_available_at='2026-11-21T00:00:00Z')
    row = predict(artifact, inputs, future, research_only=True)[0]
    assert row['probability'] is None and 'input_not_available_at_prediction' in row['flags']
    assert predict(artifact, inputs, metadata.assign(history_end='2026-11-19T00:00:00Z'), research_only=True)[0]['probability'] is None
    assert predict(artifact, inputs, metadata.assign(static_available_at='2026-11-21T00:00:00Z'), research_only=True)[0]['probability'] is None
