"""Publish measured Greek-inspired experiments without making new model choices."""
import argparse
import json
import hashlib
from pathlib import Path
import shutil
import zipfile

import joblib
import numpy as np
import pandas as pd


def publish(root):
    root = Path(root)
    out = root / 'outputs/greek-temporal-benchmark'
    result = json.loads((out / 'confirmation-results.json').read_text())
    data = json.loads((root / 'outputs/greek-temporal-data/manifest.json').read_text())
    validation = json.loads((out / 'validation-results.json').read_text())
    soil = json.loads((root / 'data/greek-soil/soil-report.json').read_text())
    ndvi = json.loads((root / 'data/greek-ndvi/ndvi-report.json').read_text())
    greek = json.loads((root / 'data/greek-daily-panel/archive-report.json').read_text())
    selected = result['selection']
    docs = root / 'docs'
    docs.mkdir(exist_ok=True)
    shutil.copyfile(out / 'confirmation-results.csv', docs / 'greek-confirmation-benchmark.csv')
    (docs / 'greek-validation-results.json').write_text(json.dumps(validation, indent=2))
    (docs / 'greek-experiment-results.json').write_text(json.dumps(result, indent=2))
    (docs / 'greek-temporal-dataset.json').write_text(json.dumps(data, indent=2))
    release = {'approved': False, 'mode': 'retrospective',
               'failed_requirements': ['issued_forecast_backtest', 'historical_input_availability',
                                       'adequate_independent_incident_confirmation', 'sufficient_test_seasons_and_events',
                                       'operational_calibration_and_threshold_review'],
               'reason': 'Only two new November dates; historical perfect-weather proxies and reprocessed inputs remain unvalidated for operational forecasting',
               'selected_by_validation': selected['best_lebanon'], 'selected_transfer': selected['best_transfer']}
    (docs / 'greek-release.json').write_text(json.dumps(release, indent=2))
    scope = json.loads((root / 'outputs/global-transfer-data/dataset-manifest.json').read_text())
    for label, identifier in [('lebanon', selected['best_lebanon']), ('transfer', selected['best_transfer'])]:
        original = out / 'frozen' / selected['artifacts'][identifier]['file']
        artifact = dict(joblib.load(original), conflict_excluded_cell_ids=scope['conflict_excluded_cell_ids'],
                        conflict_start=scope['conflict_policy']['start'], frozen_source_sha256=selected['artifacts'][identifier]['sha256'])
        joblib.dump(artifact, out / ('research-' + label + '.joblib'), compress=3)
    router = dict(joblib.load(out / 'router.joblib'), conflict_excluded_cell_ids=scope['conflict_excluded_cell_ids'], conflict_start=scope['conflict_policy']['start'])
    joblib.dump(router, out / 'research-router.joblib', compress=3)
    rows = []
    identifiers = [selected['best_global'], selected['best_lebanon'], selected['best_transfer'], 'regional_router']
    transfer_family = selected['best_transfer'].rsplit('-global_greek_lebanon', 1)[0].rsplit('-greek_lebanon', 1)[0]
    identifiers += [transfer_family + '-global', transfer_family + '-greek', transfer_family + '-lebanon']
    identifiers = list(dict.fromkeys(identifiers))
    def number(value):
        return 'not estimable' if value is None else f'{value:.5f}'
    for identifier in identifiers:
        domains = result['results'][identifier]
        rows.append('| ' + identifier + ' | ' + ' | '.join(number(domains[d].get('pr_auc_average_precision')) for d in ['global_temporal', 'global_geographic', 'lebanon']) + ' |')
    split_rows = ['| ' + name + ' | ' + str(v['feature_qualified_windows']) + ' | ' + str(v['feature_qualified_positive_windows']) + ' | ' + str(v['excluded_positive_windows']) + ' |' for name, v in data['parts'].items()]
    confirmation_rows = ['| ' + name + ' | ' + str(v['feature_qualified_windows']) + ' | ' + str(v['feature_qualified_positive_windows']) + ' | ' + str(v['quarantined_conflict_windows']) + ' |' for name, v in result['confirmation']['parts'].items()]
    text = [
        '# Greek-inspired NASA temporal experiment: measured results', '',
        '**Real-data fitting and new retrospective confirmation completed. Production approval remains false.**', '',
        'This is an adaptation of the Greek methodology to our satellite-detected occurrence target, not a reproduction of its >30 ha danger labels or selected-negative precision. Existing 2026 January–October test scores did not select these models. The original 2022 validation remains development data; repeated model searches on only 32 Lebanese validation positives are unstable.', '',
        '## NASA data obtained and cleaning', '',
        f"* {ndvi['months_obtained']} MOD13C2.061 monthly composites were obtained, retaining exact NDVI/quality/reliability subsets at {ndvi['cell_count']:,} cell samples, source-container and subset hashes, URLs and retrieval timestamps. Global containers were transient. Resolution is 0.05°, not 250 m or the Greek study's 1 km.",
        f"* {soil['point_days']:,} POWER modeled soil-wetness point-days at {soil['points']} points were acquired. {soil['missing_values']:,} missing/invalid wetness values remain missing; they never become zero wetness. GWETROOT/GWETTOP are dimensionless modeled relative wetness, not direct fuel moisture.",
        f"* Greek daily source collection retained {sum(t['retained_subsets'] for t in greek['tiles']):,} available VJ114A1.002 daily sources for 2018–2022. Missing catalogue days remain uncertain. The first two-days/month matched sample had no positive training examples; all dates were then acquired without selecting fire days.",
        f"* Outcome-independent development weather and terrain select {data['greek_matching']['selected_count']} of {data['greek_matching']['all_greek_cells']} Greek cells. This is selected panel matching, not proof that all Greece resembles Lebanon.",
        '* Fire labels retain the >=80% processed-vegetation rule, strict confidence screening, nonvegetation/QA quarantine and historical Lebanese review. New Greek/global labels do not have a complete FIRMS facility/incident review and are not certified clean.',
        '* MODIS CMG bits 14–15 mean spatial contribution, unlike tiled MOD13 snow/shadow bits. Use clear land, good reliability, mandatory good QA and >=50% contribution; exclude climatology-filled reliability=4. This was verified before model fitting.',
        '* NDVI is selected only after composite completion plus a declared 16-day lag, with a maximum age of 120 days. This lag is a retrospective design assumption, not proof of historical dissemination/version availability. Missing prior-change values have an explicit indicator.',
        '* Ten-day weather/wetness sequences end four days before target day. Current-day historical POWER values remain perfect-weather forecast proxies; they are not issued forecasts. All models share the same feature-qualified rows, including weather-only ablations.', '',
        '## Fitting and selection', '',
        'Fit: 2018–2020; separate natural-prevalence calibration: 2021; model/threshold selection: 2022. Fourteen-day split gaps exceed the ten-day history plus three-day lag. Source scalers fit only training data. No negative-only resampling is used.', '',
        '| Split | Feature-qualified windows | Positive windows | Positive windows excluded for missing features |',
        '|---|---:|---:|---:|', *split_rows, '',
        f"{selected['candidate_count']} predeclared stage candidates compare seasonal, logistic, random-forest, actual XGBoost, and 32/64-unit LSTM models; logistic/XGBoost weather-only controls isolate the added inputs on identical rows. LSTMs train for 10 epochs; adaptation continues weights for 6 epochs with frozen source scalers and a reset optimizer. Capped square-root positive weighting is followed by separate calibration. Tree/logistic transfer refits a local model with its frozen parent score; it does not fine-tune tree weights.", '',
        f"Validation choices: global `{selected['best_global']}`; Lebanese overall `{selected['best_lebanon']}`; transfer `{selected['best_transfer']}`. All artifacts and thresholds were hashed/frozen before the new confirmation fire collection. A separate fixed regional router uses the selected global model outside Lebanon and the selected transfer inside Lebanon; it does not refit or optimize from test outcomes.", '',
        '## New confirmation: 1 and 7 November 2026', '',
        'These outcome-independent dates were registered before their fire labels were acquired. They are new retrospective diagnostic examples, not a prospective operational backtest. Only two dates cannot establish seasonal robustness or useful local rare-event performance. Greece enters regional training in this protocol and is removed from independent geographic testing; five other full global panels remain held out.', '',
        '| Domain | Qualified windows | Positive windows | Conflict-quarantined windows |',
        '|---|---:|---:|---:|', *confirmation_rows, '',
        '| Validation-fixed model/control | Global temporal AP | Global geographic AP | Lebanese AP |',
        '|---|---:|---:|---:|', *rows, '',
        'AP is average precision, not accuracy. A single-class test has undefined AP here and is reported as not estimable. Full precision/recall/F1, Brier, ROC-AUC, calibration and confusion counts are in the [result JSON](greek-experiment-results.json) and [CSV](greek-confirmation-benchmark.csv). These are the same populations across candidates; they differ from the old 2023–2025 and January–October 2026 tests and cannot establish improvement by direct comparison with those old scores.', '',
        'The selected transfer confusion matrices are:', '',
    ]
    for domain, metric in result['results'][selected['best_transfer']].items():
        text.append(f"* {domain}: TN/FP/FN/TP = {metric.get('confusion_matrix_tn_fp_fn_tp')}; frozen threshold {metric.get('threshold')}; precision {metric.get('precision')}, recall {metric.get('recall')}.")
    text += ['', 'No test score changes the selected model, architecture, calibration, mixture or threshold. A high score on two November dates is not production readiness; a low score is retained. Further development must reserve new confirmation outcomes again.', '',
             '## Reproduction and limitations', '',
             'See [the forecasting README](../README.md#greek-inspired-temporal-experiment) and [statecharts](greek-temporal-statecharts.md). The optional CPU research dependencies are separate from the base uv.lock environment. Notebook 10 reads the shared modules and actual artifacts. Never load untrusted joblib files.', '',
             'NASA source access, point/subset provenance, split/tensor hashes, fitted parameters, runtime versions, seeds, model hashes, training losses and frozen selections are retained in local artifacts and committed reports. Original inactive daily-fire caches were losslessly packed and verified, not deleted; restore instructions are in the README.', '',
             'Remaining limitations: sparse global label dates, few independent local fire events, old/reprocessed land cover, coarse wetness/NDVI, unresolved managed/industrial/conflict attribution outside the broad exclusion, and no multi-year issued-forecast validation. ConvLSTM was not trained: coherent 1 km spatial histories and adequate independent incidents are lacking. The API release gate remains closed.', '']
    known_path = out / 'known-results.json'
    if known_path.exists():
        known = json.loads(known_path.read_text())
        if known['selection_sha256'] != result['selection_sha256']:
            raise ValueError('Known and new evaluation used different frozen choices')
        shutil.copyfile(known_path, docs / 'greek-known-benchmark.json')
        shutil.copyfile(out / 'known-results.csv', docs / 'greek-known-benchmark.csv')
        known_ids = list(dict.fromkeys([selected['best_global'], selected['best_lebanon'], selected['best_transfer'], 'lstm64-global_greek_lebanon', 'xgboost-global', 'xgboost_weather-global']))
        text += ['## Broader historical benchmark: already-known later years', '',
                 'The new November fold contains **zero Lebanese positive windows**; Lebanese AP and recall cannot be estimated from it. Further reporting therefore evaluates the same frozen models on already-viewed later years. These outcomes are not used for renewed selection and are not fresh independent confirmation. No weights, calibrators or thresholds change.', '',
                 'An additional 41 MODIS monthly composites and 542,124 POWER soil-wetness point-days complete the later-year feature history: **110 monthly composites and 1,293,732 soil-wetness point-days total**. Original fitting datasets/manifests remain unchanged. All-month raw subsets and their QA remain separately versioned.', '',
                 '| Known evaluation cohort | Feature-qualified windows | Positive windows |', '|---|---:|---:|']
        for name, cohort in known['manifest']['parts'].items():
            text.append(f"| {name} | {cohort['feature_qualified_windows']:,} | {cohort['feature_qualified_positive_windows']} |")
        text += ['', '| Frozen model/control | Source-panel 2023–2025 AP | Five held-out panels AP | Lebanese 2023–2025 AP | Known Lebanese Jan–Oct 2026 AP |', '|---|---:|---:|---:|---:|']
        for identifier in known_ids:
            values = known['results'][identifier]
            text.append('| ' + identifier + ' | ' + ' | '.join(number(values[d]['pr_auc_average_precision']) for d in ['global_known_2023_2025', 'geographic_known_2023_2025', 'lebanon_known_2023_2025', 'lebanon_known_2026_JanOct']) + ' |')
        text += ['', 'The common source-panel evaluation includes the original 18 global panels plus Greece, which is a source region in regional-training arms. The pure global model itself never trained on Greece. Five other geographic panels remain unseen by every fitting arm. Do not compare this population directly with the earlier six-panel holdout or infer worldwide skill.', '',
                 'The global LSTM and enriched XGBoost retain useful source-panel ranking, with much weaker geographic transfer. Enrichment improves XGBoost ranking over its weather-only control on source panels, but not on held-out panels. The neural Greek/Lebanon chain looks better on the known Lebanese benchmark than its matching source; it **did not win validation** and is not promoted after viewing these scores. The validation-selected local-only LSTM remains the overall Lebanese candidate, while the selected logistic transfer does not establish a local advantage.', '',
                 'For the validation-selected local-only model on known Lebanese January–October 2026, TN/FP/FN/TP = ' + str(known['results'][selected['best_lebanon']]['lebanon_known_2026_JanOct']['confusion_matrix_tn_fp_fn_tp']) + '. All 15 positives are missed at its frozen threshold. The neural chain detects 3/15 there with 508 false alerts; this is a retained diagnostic, not an independently validated alert policy.', '',
                 'Full historical [JSON](greek-known-benchmark.json) and [CSV](greek-known-benchmark.csv) include every retained model. There are only 133 eligible positive Lebanese windows in 2023–2025 and 15 in the known 2026 fold; these windows are not certified independent incidents. These constraints, weak precision and the lack of issued-weather backtesting keep release approval false.', '']
    live_report = root / 'outputs/greek-temporal-live/report.json'
    if live_report.exists():
        live = json.loads(live_report.read_text())
        (docs / 'greek-live-research.json').write_text(json.dumps(live, indent=2))
        shutil.copyfile(live_report.parent / 'risk.png', docs / 'figures/greek-temporal-live.png')
        text += ['## Actual issued-forecast research output', '',
                 f"NASA GEOS issued 2026-11-14 00 UTC supplies the 24-hour window beginning {live['prediction_time']}. All 72 hourly field subsets completed. Actual recent NASA POWER weather/wetness and selected MODIS observations were retrieved before that future prediction time. The local model returns {live['probabilities_returned']} probabilities over {live['cells']} eligible cells; {live['withheld_conflict_scope']} cells are flagged in the southern conflict scope. Missing vegetation remains unavailable, including overlapping reasons.", '',
                 '![Actual forecast-input research map](figures/greek-temporal-live.png)', '',
                 'This demonstrates ingestion and research inference, not operational skill. CSV/GeoJSON/JSON outputs retain model hashes, issue/availability times and limitations. The interface accepts no fire labels; future/missing inputs, wrong history windows and conflict scope suppress predictions. The production API remains gated.', '']
    (docs / 'greek-experiment-results.md').write_text('\n'.join(text))
    plot(root, result)
    build_bundle(root)
    print(json.dumps({'selected_global': selected['best_global'], 'selected_lebanon': selected['best_lebanon'], 'selected_transfer': selected['best_transfer'], 'production_approved': False}))


def build_bundle(root):
    root = Path(root)
    out = root / 'outputs/greek-temporal-benchmark'
    entries = {'README.txt': ('RESEARCH ONLY. No production or emergency-warning approval.\n'
        'Install the matching repository source and optional CPU requirements. Load only trusted joblib artifacts.\n'
        'research-lebanon is the validation-selected local LSTM; research-transfer is the validation-selected logistic transfer.\n'
        'research-router uses the fixed selected global model outside Lebanon and fixed transfer inside it.\n'
        'Do not promote another model from known historical scores. Two November dates include zero Lebanese positives.\n'
        'Use firecast.temporal_inference with genuine sequence/static tensors and actual issue/availability metadata.\n'
        'The forecast example uses real NASA inputs but a retrospectively trained model; it is not validated warning performance.\n').encode()}
    for name in ['research-lebanon.joblib', 'research-transfer.joblib', 'research-router.joblib']:
        entries[name] = (out / name).read_bytes()
    for path in [root / 'requirements-temporal-cpu.txt', root / 'configs/greek-experiment.json', root / 'docs/greek-release.json',
                 root / 'docs/greek-confirmation-benchmark.csv', root / 'docs/greek-known-benchmark.csv']:
        if path.exists(): entries[path.name] = path.read_bytes()
    live = root / 'outputs/greek-temporal-live'
    for name in ['predictions.csv', 'predictions.geojson', 'risk.png', 'report.json']:
        if (live / name).exists(): entries['forecast-example/' + name] = (live / name).read_bytes()
    entries['SHA256.json'] = json.dumps({name: hashlib.sha256(value).hexdigest() for name, value in entries.items()}, indent=2).encode()
    folder = root / 'outputs/delivery'
    folder.mkdir(exist_ok=True)
    with zipfile.ZipFile(folder / 'lebanon-greek-temporal-RESEARCH-ONLY.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items(): archive.writestr(name, value)


def plot(root, result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    selected = result['selection']
    ids = [selected['best_global'], selected['best_transfer'], selected['best_lebanon'], 'regional_router']
    ids = list(dict.fromkeys(ids))
    fig, axes = plt.subplots(1, 3, figsize=(12, 4), layout='constrained')
    for ax, domain in zip(axes, ['global_temporal', 'global_geographic', 'lebanon']):
        values = [result['results'][i][domain].get('pr_auc_average_precision') for i in ids]
        ax.barh(range(len(ids)), [v if v is not None else 0 for v in values], color='#315b7d')
        ax.set_yticks(range(len(ids)), ids if ax is axes[0] else [''] * len(ids), fontsize=8)
        ax.set_title(domain)
        ax.set_xlabel('Average precision; not accuracy')
        for j, value in enumerate(values):
            if value is None:
                ax.text(.01, j, 'Not estimable', va='center', transform=ax.get_yaxis_transform())
        ax.grid(axis='x', alpha=.2)
    fig.suptitle('Validation-fixed choices on two new November 2026 dates\nRetrospective research; insufficient operational confirmation', fontsize=11)
    folder = Path(root) / 'docs/figures'
    folder.mkdir(exist_ok=True)
    fig.savefig(folder / 'greek-temporal-confirmation.png', dpi=140)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    a = p.parse_args()
    publish(Path(a.root).resolve())


if __name__ == '__main__':
    main()
