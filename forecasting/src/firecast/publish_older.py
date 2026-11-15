"""Publish immutable older-year transfer diagnostics and explicit limitations."""
import argparse
import json
from pathlib import Path
import shutil
from .benchmark_temporal import sha


def publish(root, out):
    root, out = Path(root), Path(out)
    r = json.loads((out / 'results.json').read_text())
    docs = root / 'docs'
    shutil.copyfile(out / 'results.json', docs / 'older-evaluation-results.json')
    shutil.copyfile(out / 'results.csv', docs / 'older-evaluation-results.csv')
    source_manifest = root / 'data/older-pretrained/hls-patches/manifest.json'
    image_manifest = json.loads(source_manifest.read_text())
    image_manifest['cached_manifest_sha256'] = sha(source_manifest)
    if any('Static 2017' in text for text in image_manifest['limitations']):
        image_manifest['published_metadata_correction'] = 'Legacy reader hardcoded 2017 in one limitation sentence. All exact source records are 2015; cached extraction evidence is preserved under its original hash.'
        image_manifest['limitations'] = [text.replace('Static 2017', 'Static 2015') for text in image_manifest['limitations']]
    (docs / 'older-hls-manifest.json').write_text(json.dumps(image_manifest, indent=2))
    chosen = r['selected_external_unchanged']
    def number(value):
        return 'not estimable' if value is None else f'{value:.6f}'
    def precision(metric):
        return f"{metric['precision']:.3%}" if metric['precision_estimable'] else 'no alerts'
    lines = ['# Frozen-model evaluation on Lebanese 2016–2017 data', '',
             '**Evaluation only: no training, calibration, threshold changes or model selection. Production approval remains false.**', '',
             'The current models were fitted on 2018–2020 labels, so 2016–2017 labels were not in their supervised fitting. Evaluating earlier years is a backward-time transfer diagnostic, not the later-year test required to establish forecasting skill. Modern weights and reprocessed inputs were not available at historical issue times.', '',
             '## NASA sources and contamination checks', '',
             '* Labels: existing NASA S-NPP VNP14A1.002 daily 1km fire masks, including cloud/unknown/coverage evidence and original FIRMS review. Current training labels use NOAA-20 VJ114A1.002, which does not cover 2016–2017. This is explicit cross-sensor evaluation, not a homogeneous NOAA-20 history.',
             '* Earlier S-NPP-specific local models had already trained on 2016–2017 and are excluded from held-out comparisons. Current-model fitting tensor dates and artifact hashes are checked before preparation and scoring.',
             '* The previous external heads contained 2017 HLS image inputs. Those would be future images for 2016, so separate QA-screened **2015 HLS** crops are encoded with the same pinned source weights. Only image inputs are substituted; all learned weights, scalers, calibrators and thresholds remain unchanged.',
             '* 28 monthly MOD13C2.061 NDVI composites and 9,144 POWER modeled soil-wetness point-days were acquired. Four identical NDVI months and 372 identical soil point-days overlap the original caches; deduplicate with recorded checks, retaining original versions. Historical POWER weather already covers both years.',
             '* Ten-day histories, past-composite NDVI availability and missing-feature exclusions remain unchanged. Target-day observed weather remains a retrospective proxy, not an issued forecast archive.',
             '* Full daily 124-cell panels are retained. A fourteen-day embargo before the earliest fitting target, 5 January 2018, withholds 21–31 December 2017: 1,364 cell-windows before other exclusions. No eligible positives are lost to this embargo. Southern Lebanon is included: the requested post-7-October-2023 conflict quarantine does not apply to these years.',
             '* Raw uncertain/excluded positives remain uncertain/excluded, not negatives. Strict/conservative label policies use the same frozen predictions and thresholds; their differing target populations are reported.', '',
             '## Evaluated cohorts', '',
             '| Year / label policy | Full feature-qualified windows | Full positive windows | Matched-image windows | Matched-image positives | Image-scope excluded positives |', '|---|---:|---:|---:|---:|---:|']
    for key, cohort in r['cohorts'].items():
        full, matched = cohort['full_feature_qualified'], cohort['matched_images']
        lines.append(f"| {key} | {full['windows']:,} | {full['positive_windows']} | {matched['windows']:,} | {matched['positive_windows']} | {matched['image_scope_excluded_positive_windows']} |")
    lines += ['', f"The matched image population intersects the original image-qualified training domain with valid 2015 crops: **{len(r['image_cells'])} cells**. All ten external-experiment candidates use this identical evaluation population. Earlier frozen references are scored both on it and on the full feature-qualified grid. Fire windows are not certified independent incidents.", '',
              '## Strict-policy results on identical image-qualified rows', '',
              '| Frozen model | 2016 AP | 2016 precision | 2016 recall | 2017 AP | 2017 precision | 2017 recall |', '|---|---:|---:|---:|---:|---:|---:|']
    for name, values in r['results'].items():
        a, b = values['2016-strict-matched'], values['2017-strict-matched']
        lines.append(f"| {name} | {number(a['pr_auc_average_precision'])} | {precision(a)} | {a['recall']:.3%} | {number(b['pr_auc_average_precision'])} | {precision(b)} | {b['recall']:.3%} |")
    lines += ['', 'AP is average precision, not accuracy. Every threshold was fixed on the original 2022 validation; none was optimized on older outcomes. When no alerts are issued, precision is not estimable; the JSON retains a zero convention with precision_estimable=false.', '',
              '## Filtering-policy sensitivity', '',
              '| Model | Year / policy | AP | TN / FP / FN / TP | Brier |', '|---|---|---:|---|---:|']
    for name in [chosen, 'lstm64-lebanon']:
        for year in [2016, 2017]:
            for policy in ['strict', 'conservative']:
                m = r['results'][name][f'{year}-{policy}-matched']
                lines.append(f"| {name} | {year} / {policy} | {number(m['pr_auc_average_precision'])} | {m['confusion_matrix_tn_fp_fn_tp']} | {m['brier']:.6f} |")
    lines += ['', '## Earlier frozen references over the full grid', '',
              '| Reference | 2016 strict AP | 2017 strict AP |', '|---|---:|---:|']
    for name in r['references']:
        values = r['results'][name]
        lines.append(f"| {name} | {number(values['2016-strict-full']['pr_auc_average_precision'])} | {number(values['2017-strict-full']['pr_auc_average_precision'])} |")
    lines += ['', '## Interpretation', '',
              f"The external candidate selected before this experiment remains `{chosen}`. The earlier project primary is also unchanged. Older scores do not select a new model, normalization strategy or threshold.", '']
    for year in [2016, 2017]:
        m = r['results'][chosen][f'{year}-strict-matched']
        tn, fp, fn, tp = m['confusion_matrix_tn_fp_fn_tp']
        lines.append(f"For the selected external candidate in {year}, the strict matched cohort contains {m['observations']:,} observations and {m['positive_windows']} positive windows: **{tp} detected, {fn} missed, {fp} false alerts**, AP {number(m['pr_auc_average_precision'])}.")
    lines += ['', 'Differences from 2023–2026 scores can reflect sensor, image age, fire prevalence, weather regime and observable-population changes. They do not by themselves demonstrate improvement, explain the cause of newer failures or validate production. The 2015 images sample only 960m squares inside roughly 10km cells. EO2 unsupervised image exposure cannot be ruled out; modern pretraining and reprocessing availability remain retrospective limitations. Label adjudication also uses historical review and later recurring-hotspot evidence.', '',
              'Full precision/recall/F1, confusion matrices, Brier scores, calibration, ROC-AUC and seasonal breakdowns are in [JSON](older-evaluation-results.json); [CSV](older-evaluation-results.csv) contains all candidates/cohorts. See [statecharts](older-evaluation-statecharts.md), [setup](../README.md#older-year-evaluation-20162017) and notebook 12.', '']
    (docs / 'older-evaluation-results.md').write_text('\n'.join(lines))
    release = {'approved': False, 'evaluation_only': True, 'no_refitting': True, 'project_primary_replaced': False,
               'selected_external_unchanged': chosen, 'reason': 'Backward-time, cross-sensor retrospective diagnostic; no operational validation'}
    (docs / 'older-evaluation-release.json').write_text(json.dumps(release, indent=2))
    return {'report': str(docs / 'older-evaluation-results.md'), 'production_approved': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default='.')
    p.add_argument('--out', default='outputs/older-evaluation')
    a = p.parse_args()
    print(json.dumps(publish(a.root, a.out)))
