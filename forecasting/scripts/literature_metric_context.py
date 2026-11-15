"""Describe frozen results for literature comparison; never fit or select a model.

Run from forecasting/: .venv/bin/python scripts/literature_metric_context.py
Only load trusted local artifacts. This is post-test reporting, not fresh validation.
"""
import hashlib
import json
from pathlib import Path
import sys

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from firecast.benchmark_global import load_part


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    folder = ROOT / "outputs/global-final-refit"
    frozen_path = folder / "refit-frozen.json"
    frozen_hash = sha(frozen_path)
    frozen = json.loads(frozen_path.read_text())
    identifier = "refit_validation_global_winner"
    record = frozen["artifacts"][identifier]
    model_path = folder / "frozen" / record["file"]
    if sha(model_path) != record["sha256"]:
        raise ValueError("Frozen artifact checksum mismatch")
    artifact = joblib.load(model_path)
    original = json.loads((folder / "results.json").read_text())["results"][identifier]
    domains = {
        "global_2026_temporal": ("global-2026-confirmation-data", "global-test-sealed"),
        "global_2026_geographic": ("global-2026-confirmation-data", "global-geographic-test-sealed"),
        "lebanon_2026_fixed_fold": ("global-transfer-data", "lebanon-confirmation-sealed"),
    }
    report = {
        "kind": "post_test_reporting_only",
        "model": identifier,
        "model_sha256": record["sha256"],
        "refit_manifest_sha256": frozen_hash,
        "training_or_threshold_selection_performed": False,
        "comparability": "Different labels, sampling and test populations prevent paper leaderboard comparisons.",
        "domains": {},
    }
    for domain, (data_name, part) in domains.items():
        data = ROOT / "outputs" / data_name
        manifest = json.loads((data / "dataset-manifest.json").read_text())
        frame = load_part(data, part, manifest)
        probabilities = artifact["model"].predict_proba(frame)[:, 1]
        if not np.isfinite(probabilities).all():
            raise ValueError("Nonfinite probabilities")
        ap = float(average_precision_score(frame.y, probabilities))
        if not np.isclose(ap, original[domain]["pr_auc_average_precision"], atol=1e-10, rtol=1e-7):
            raise ValueError("Frozen AP no longer reproduces")
        threshold = original[domain]["threshold"]
        prevalence = int(frame.y.sum()) / len(frame)
        report["domains"][domain] = {
            "observations": len(frame), "positive_windows": int(frame.y.sum()),
            "prevalence": prevalence, "average_precision": ap,
            "roc_auc": float(roc_auc_score(frame.y, probabilities)),
            "always_negative_accuracy": 1 - prevalence,
            "frozen_threshold": threshold,
            "accuracy_at_frozen_threshold": float(accuracy_score(frame.y, probabilities >= threshold)),
            "precision_at_frozen_threshold": original[domain]["precision"],
            "recall_at_frozen_threshold": original[domain]["recall"],
        }
    tpr, fpr = .8, .01
    report["hypothetical_prevalence_shift"] = {
        "note": "Arithmetic illustration only; does not assert any model retains these rates after transfer.",
        "recall": tpr, "false_positive_rate": fpr,
        "precision": {
            name: tpr * prevalence / (tpr * prevalence + fpr * (1 - prevalence))
            for name, prevalence in {
                "one_positive_two_negatives": 1 / 3,
                "our_global": report["domains"]["global_2026_temporal"]["prevalence"],
                "our_lebanon": report["domains"]["lebanon_2026_fixed_fold"]["prevalence"],
            }.items()
        },
    }
    if sha(frozen_path) != frozen_hash or sha(model_path) != record["sha256"]:
        raise ValueError("Frozen source changed during reporting")
    output = ROOT / "docs/literature-metric-context.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
