"""Critical external-pretraining contracts; no downloads in the test suite."""
import numpy as np
import pytest

from firecast.pretrained_encoder import hls_clear_pixels, position_encoding
from firecast.benchmark_pretrained import subset


def test_hls_cloud_shadow_snow_water_fill_and_high_aerosol_are_uncertain():
    q = np.asarray([0, 1, 2, 4, 8, 16, 32, 64, 128, 192, 255], np.uint8)
    assert hls_clear_pixels(q).tolist() == [True, False, False, False, False, False, False, True, True, False, False]


def test_missing_hls_excludes_positive_without_relabelling():
    data = {'cell_id': np.asarray(['a', 'b', 'c']), 'y': np.asarray([0, 1, 1]), 'time': np.asarray([1, 2, 3])}
    kept, audit = subset(data, {'a', 'c'})
    assert kept['y'].tolist() == [0, 1]
    assert audit['missing_hls_excluded_positive_windows'] == 1
    assert audit['original_positive_windows'] == 2


def test_prithvi_positions_and_strict_encoder_attention():
    torch = pytest.importorskip('torch')
    from firecast.pretrained_encoder import build_encoder
    pos = position_encoding(32, 1, 14)
    assert pos.shape == (197, 32)
    assert np.array_equal(pos[0], np.zeros(32))
    model = build_encoder({'embed_dim': 32, 'num_heads': 2, 'depth': 1, 'num_frames': 1})
    image = torch.randn(2, 6, 1, 32, 32)
    assert model(image).shape == (2, 5, 32)
    state = model.state_dict()
    state.pop('blocks.0.attn.qkv.weight')
    with pytest.raises(RuntimeError):
        model.load_state_dict(state, strict=True)
    attn = model.blocks[0].attn
    x = torch.randn(2, 5, 32)
    q, k, v = attn.qkv(x).reshape(2, 5, 3, 2, 16).permute(2, 0, 3, 1, 4).unbind(0)
    expected = attn.proj((((q @ k.transpose(-2, -1)) / 4).softmax(-1) @ v).transpose(1, 2).reshape(2, 5, 32))
    assert torch.allclose(attn(x), expected, atol=1e-6)


def test_actual_pretrained_norm_tuning_and_label_free_prediction():
    pytest.importorskip('torch')
    from firecast.benchmark_pretrained import PretrainedHead
    rng = np.random.default_rng(42)
    bank = {'tokens': rng.normal(size=(3, 5, 8)).astype(np.float32), 'cell_id': np.asarray(['a', 'b', 'c']),
            'norm_weight': np.ones(8, np.float32), 'norm_bias': np.zeros(8, np.float32)}
    original = {k: v.copy() for k, v in bank.items()}
    cfg = {'threads': 1, 'seed': 42, 'hidden_width': 8, 'head_epochs': 3, 'batch_size': 16,
           'learning_rate': .01, 'layernorm_learning_rate': .01}
    data = {'sequence': rng.normal(size=(48, 10, 9)).astype(np.float32),
            'static': rng.normal(size=(48, 23)).astype(np.float32), 'cell_id': np.asarray(['a', 'b', 'c'] * 16),
            'y': np.asarray([0, 0, 1] * 16)}
    frozen = PretrainedHead(bank, False, cfg).fit(data)
    tuned = PretrainedHead(bank, True, cfg).fit(data)
    assert frozen.training['norm_weight_change_l2'] == 0
    assert tuned.training['norm_weight_change_l2'] > 0
    assert tuned.training['backbone_trainable_parameters'] == 16
    assert all(np.array_equal(original[k], bank[k]) for k in bank)
    no_labels = {k: v for k, v in data.items() if k != 'y'}
    np.testing.assert_array_equal(tuned.predict(data), tuned.predict(no_labels))
    no_labels['cell_id'] = np.asarray(['unknown'] * 48)
    with pytest.raises(ValueError, match='Missing real HLS'):
        tuned.predict(no_labels)


def test_external_inference_withholds_missing_images_and_future_pretraining():
    import pandas as pd
    from firecast.temporal_inference import predict

    class Model:
        def predict(self, data):
            assert 'y' not in data and data['cell_id'].tolist() == ['x']
            return np.asarray([.01])

    artifact = {'model': Model(), 'id': 'external', 'stage': 'external_lebanon', 'production_approved': False,
                'feature_contract': {'dynamic': ['x'], 'static': ['x']}, 'config': {'history_days': 10, 'history_lag_days': 3},
                'required_image_cell_ids': ['x'], 'image_provenance': {'x': {'observation_time': '2017-07-01T00:00:00Z',
                    'retrieved_at': '2026-11-15T00:00:00Z', 'sha256': 'known'}},
                'source_checkpoint_retrieved_at': '2026-11-15T00:00:00Z'}
    inputs = {'sequence': np.ones((1, 10, 1), np.float32), 'static': np.ones((1, 1), np.float32)}
    metadata = pd.DataFrame({'cell_id': ['x'], 'region': ['lebanon'], 'lat': [34.], 'lon': [36.],
        'prediction_time': ['2026-11-20T00:00:00Z'], 'forecast_issued_at': ['2026-11-19T00:00:00Z'],
        'forecast_available_at': ['2026-11-19T06:00:00Z'], 'history_latest_available_at': ['2026-11-19T00:00:00Z'],
        'vegetation_available_at': ['2026-11-15T00:00:00Z'], 'vegetation_composite_end': ['2026-11-01T00:00:00Z'],
        'static_available_at': ['2026-11-15T00:00:00Z'], 'forecast_valid_start': ['2026-11-20T00:00:00Z'],
        'forecast_valid_end': ['2026-11-21T00:00:00Z'], 'history_start': ['2026-11-07T00:00:00Z'], 'history_end': ['2026-11-16T00:00:00Z']})
    row = predict(artifact, inputs, metadata, research_only=True)[0]
    assert row['probability'] == .01 and row['hls_subset_sha256'] == 'known'
    assert predict(artifact, inputs, metadata.assign(cell_id='missing'), research_only=True)[0]['probability'] is None
    artifact['source_checkpoint_retrieved_at'] = '2026-11-21T00:00:00Z'
    assert predict(artifact, inputs, metadata, research_only=True)[0]['probability'] is None
    artifact['source_checkpoint_retrieved_at'] = None
    assert predict(artifact, inputs, metadata, research_only=True)[0]['probability'] is None
