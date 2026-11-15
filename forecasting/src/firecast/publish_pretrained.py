"""Publish measured external-checkpoint experiments without selecting on tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile


def live(root, out):
    import joblib
    import numpy as np
    import pandas as pd
    from .temporal_inference import predict
    from .temporal_live import export_map
    root, out = Path(root), Path(out)
    frozen = json.loads((out / 'selection-frozen.json').read_text())
    identifier = frozen['selected_pretrained']
    record = frozen['artifacts'][identifier]
    path = out / record['file']
    if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
        raise ValueError('Frozen pretrained example artifact changed')
    artifact = joblib.load(path)
    previous = root / 'outputs/greek-temporal-live'
    with np.load(previous / 'inputs.npz') as a:
        inputs = {k: a[k] for k in ['sequence', 'static']}
    rows = predict(artifact, inputs, pd.read_csv(previous / 'metadata.csv'), research_only=True)
    target = root / 'outputs/pretrained-live'
    target.mkdir(exist_ok=True)
    for row in rows:
        row['model_sha256'] = record['sha256']
    (target / 'predictions.json').write_text(json.dumps(rows, indent=2))
    pd.DataFrame(rows).assign(flags=lambda f: f['flags'].map('|'.join)).to_csv(target / 'predictions.csv', index=False)
    export_map(rows, root, target, artifact['threshold'])
    report = {'model': identifier, 'model_sha256': record['sha256'], 'selection': 'pretrained arm selected on validation only',
              'cells': len(rows), 'probabilities_returned': sum(r['probability'] is not None for r in rows),
              'withheld_conflict_scope': sum('outside_evaluated_southern_conflict_scope' in r['flags'] for r in rows),
              'withheld_image_scope': sum('missing_hls_or_outside_image_qualified_domain' in r['flags'] for r in rows),
              'prediction_time': rows[0]['prediction_time'], 'window_end': rows[0]['window_end'],
              'source_forecast_report_sha256': hashlib.sha256((previous / 'report.json').read_bytes()).hexdigest(),
              'production_approved': False, 'actual_issued_forecast_inputs': True,
              'note': 'Retrospective model, old limited landscape sample and weather-source transfer; no operational skill demonstrated'}
    (target / 'report.json').write_text(json.dumps(report, indent=2))
    return report


def publish(root, out):
    root, out = Path(root), Path(out)
    report = json.loads((out / 'results.json').read_text())
    frozen = report['selection']
    docs = root / 'docs'
    shutil.copyfile(out / 'results.json', docs / 'pretrained-results.json')
    shutil.copyfile(out / 'results.csv', docs / 'pretrained-results.csv')
    hls = json.loads((root / 'data/pretrained-models/hls-patches/manifest.json').read_text())
    (docs / 'pretrained-hls-manifest.json').write_text(json.dumps(hls, indent=2))
    release = {'approved': False, 'selected_overall': frozen['selected_overall'], 'selected_pretrained': frozen['selected_pretrained'],
               'mode': 'retrospective', 'failed_requirements': ['issued_forecast_backtest', 'historical_pretraining_and_input_availability',
                                                               'fresh_independent_incident_confirmation', 'useful_calibrated_alert_skill'],
               'source_selection_sha256': report['selection_sha256']}
    (docs / 'pretrained-release.json').write_text(json.dumps(release, indent=2))
    text = ['# External NASA-pretrained encoders: measured Lebanese adaptation', '',
            '**Real published checkpoints and real NASA HLS images were used. Production approval remains false.**', '',
            'These are three pretrained geospatial image encoders with newly trained fire-occurrence heads. They are not three previously trained wildfire forecasting systems. See [source/license review](pretrained-sources.md) and [statecharts](pretrained-statecharts.md).', '',
            f"NASA HLS L30 v2 supplied qualifying pre-2018 landscape crops for **{hls['cells_obtained']}/{hls['cells_requested']} cells**. Each crop samples only 960m square within a roughly 10km cell. Exact six-band crops, Fmask, coordinates, observation dates, source URLs and subset hashes are retained; full COG containers are not copied locally. Static old imagery is not current fuel condition.", '',
            'The published full checkpoint bytes were downloaded into RAM, checked against pinned SHA256/size, and their entire encoder state loaded strictly. Reconstruction decoders are unused. Model receipts include source revisions, original normalization, upstream file hashes and encoder parameter counts. Cached tokens precede the original final LayerNorm; other encoder blocks are frozen.', '',
            'For each checkpoint compare a frozen encoder with a head-only fit, and limited fine-tuning of the pretrained final LayerNorm plus the head. The latter actually updates pretrained scale/bias, not attention blocks. Twelve fixed epochs use Lebanese 2018–2020 data, capped positive weighting and train-only scaling. Natural-prevalence calibration uses 2021, validation/model/threshold selection uses 2022, with fourteen-day gaps. No test result changes those choices.', '',
            '| Split | Kept windows | Positive windows | Missing-image excluded positives |', '|---|---:|---:|---:|']
    for name, a in {**frozen['cohort'], **report['test_cohort']}.items():
        text.append(f"| {name} | {a['kept_windows']:,} | {a['kept_positive_windows']} | {a['missing_hls_excluded_positive_windows']} |")
    text += ['', f"**Validation-selected within this new comparison:** `{frozen['selected_overall']}`. **Validation-selected external-pretrained arm:** `{frozen['selected_pretrained']}`. All {frozen['candidate_count']} candidates remain in the report, including seasonal, weather/environment logistic and no-image MLP controls. This does not replace the earlier project selection.", '',
             '| Candidate | Validation AP | Known 2023–2025 AP | Known Jan–Oct 2026 AP | 2023–2025 precision | 2023–2025 recall |', '|---|---:|---:|---:|---:|---:|']
    for name, val in frozen['validation'].items():
        old = report['results'][name]['lebanon_known_2023_2025']
        recent = report['results'][name]['lebanon_known_2026_JanOct']
        text.append(f"| {name} | {val['pr_auc_average_precision']:.6f} | {old['pr_auc_average_precision']:.6f} | {recent['pr_auc_average_precision']:.6f} | {old['precision']:.4%} | {old['recall']:.4%} |")
    text += ['', '## Earlier frozen references on the same evaluation rows', '',
             'These earlier models are unchanged and remain outside new candidate selection. Their original fitting used the full feature-qualified population before HLS exclusions, so their training populations differ from this image-qualified experiment.', '',
             '| Reference | Matched validation AP | Matched known 2023–2025 AP | Matched known Jan–Oct 2026 AP |', '|---|---:|---:|---:|']
    for name, values in report['reference_results'].items():
        text.append(f"| {name} | {frozen['references'][name]['validation']['pr_auc_average_precision']:.6f} | {values['lebanon_known_2023_2025']['pr_auc_average_precision']:.6f} | {values['lebanon_known_2026_JanOct']['pr_auc_average_precision']:.6f} |")
    chosen = report['results'][frozen['selected_pretrained']]
    older = chosen['lebanon_known_2023_2025']
    recent = chosen['lebanon_known_2026_JanOct']
    _, false_alerts, missed, detected = older['confusion_matrix_tn_fp_fn_tp']
    _, recent_false_alerts, recent_missed, recent_detected = recent['confusion_matrix_tn_fp_fn_tp']
    text += ['', f"The selected external arm detects **{detected}/{older['positive_windows']}** positive windows with **{false_alerts} false alerts** in 2023–2025. On the known 2026 fold it detects **{recent_detected}/{recent['positive_windows']}** with **{recent_false_alerts} false alerts**. Better ranking on the older cohort does not establish useful alerts or sustained transfer.", '',
             'The final-LayerNorm tuning arms are retained even when they lose validation. The slightly higher 2023–2025 AP of a nonselected arm does not promote it after tests. The earlier local LSTM also has higher matched validation AP than the new selected external arm; this experiment does not justify replacing it on test results.']
    text += ['', 'AP is average precision, not accuracy. Precision/recall use each candidate’s validation-fixed threshold. Full confusion matrices, Brier, ROC-AUC, reliability bins and seasonal metrics are in [JSON](pretrained-results.json); compact [CSV](pretrained-results.csv) is also available.', '',
             '## Interpretation and remaining gaps', '',
             'These later-year outcomes were already viewed in previous experiments. They are diagnostics, not new independent confirmation. Only 32 positive Lebanese validation windows existed before any HLS exclusions, and repeated searches make selection unstable. Current weights were unavailable in the historical prediction years; globally pretrained EO2 may have seen Lebanese imagery. HLS reprocessing dates do not prove historical availability. Thus this experiment does not satisfy a strict operational historical-as-of backtest.', '',
             'Current-day historical POWER meteorology remains an observed-weather proxy, not an archived issued forecast. Cloud/QA-conditioned satellite labels miss some events. Source labels, conflict exclusions, missing-image audits and natural class imbalance remain part of interpretation. No production approval or high-precision alert claim follows from image pretraining.', '',
             'The predictor accepts no fire labels during inference. It requires an exact image-qualified cell or a newly acquired/encoded compatible image; a missing image must withhold prediction. The shipped heads use cached 2017 landscape tokens, so the bundle is explicitly a bounded retrospective research artifact, not a worldwide live satellite service.', '',
             '## Reproduce', '',
             'Use the [README instructions](../README.md#external-pretrained-encoders) and notebook 11. Runtime uses the existing CPU torch environment plus a system GDAL Python for HLS COG reads. No timm/TerraTorch package or remote Python code execution is needed. Rebuilding tokens requires downloading roughly 1.04 GB of pinned checkpoint bytes in total; peak RAM should allow several GB. Source weights are streamed to RAM and are not retained as full checkpoint files.', '']
    live_folder = root / 'outputs/pretrained-live'
    if (live_folder / 'report.json').exists():
        current = json.loads((live_folder / 'report.json').read_text())
        shutil.copyfile(live_folder / 'report.json', docs / 'pretrained-live.json')
        shutil.copyfile(live_folder / 'risk.png', docs / 'figures/pretrained-live.png')
        text += ['## Actual NASA forecast-input example', '',
                 f"The validation-selected pretrained arm produces {current['probabilities_returned']} research estimates over {current['cells']} cells for {current['prediction_time']} through {current['window_end']}. All {current['withheld_conflict_scope']} southern-scope cells are withheld; missing HLS/NDVI reasons can overlap. This uses the already acquired actual NASA GEOS forecast and actual antecedent inputs, without future fire labels.", '',
                 '![Research forecast from pretrained encoder arm](figures/pretrained-live.png)', '',
                 'HLS observation/retrieval and pretrained-weight retrieval times are retained separately; future or missing source timestamps suppress scores. The production API remains gated.', '']
    (docs / 'pretrained-results.md').write_text('\n'.join(text))
    delivery = root / 'outputs/delivery'
    delivery.mkdir(exist_ok=True)
    bundle = delivery / 'lebanon-external-pretrained-RESEARCH-ONLY.zip'
    files = {'README.txt': ('RESEARCH ONLY. Not production approved. Modern external image pretraining; already-viewed retrospective tests.\n'
                            'Only original final LayerNorm and new occurrence heads are tuned. Attention blocks stay frozen.\n'
                            'Models include exact cached-cell HLS tokens. Never load untrusted joblib files.\n').encode(),
             'pretrained-transfer.json': (root / 'configs/pretrained-transfer.json').read_bytes(),
             'requirements-temporal-cpu.txt': (root / 'requirements-temporal-cpu.txt').read_bytes(),
             'licenses/Prithvi-Apache-2.0.txt': (root / 'licenses/Prithvi-Apache-2.0.txt').read_bytes(),
             'source-checkpoint-records.json': json.dumps(frozen['source_meta'], indent=2).encode(),
             'pretrained-sources.md': (docs / 'pretrained-sources.md').read_bytes(),
             'pretrained-release.json': (docs / 'pretrained-release.json').read_bytes(),
             'results.csv': (out / 'results.csv').read_bytes()}
    for name in dict.fromkeys([frozen['selected_overall'], frozen['selected_pretrained']]):
        source = out / frozen['artifacts'][name]['file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != frozen['artifacts'][name]['sha256']:
            raise ValueError('Research delivery artifact differs from frozen candidate')
        files[source.name] = source.read_bytes()
    if (live_folder / 'report.json').exists():
        for name in ['predictions.csv', 'predictions.geojson', 'risk.png', 'report.json']:
            files['forecast-example/' + name] = (live_folder / name).read_bytes()
    files['SHA256.json'] = json.dumps({k: hashlib.sha256(v).hexdigest() for k, v in files.items()}, indent=2).encode()
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in json.loads(archive.read('SHA256.json')).items())
    return {'report': str(docs / 'pretrained-results.md'), 'bundle': str(bundle), 'production_approved': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--out', default='outputs/pretrained-transfer')
    p.add_argument('--live', action='store_true', help='Run timestamp-checked research prediction from the existing actual NASA forecast tensors')
    a = p.parse_args()
    if a.live:
        print(json.dumps(live(a.root, a.out)))
    print(json.dumps(publish(a.root, a.out)))
