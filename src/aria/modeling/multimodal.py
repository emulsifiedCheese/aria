"""deterministic phase 11.2 early-fusion model development"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import joblib
from aria.modeling.baselines import (
    BaselineBuildError,
    CLASS_LABELS,
    _candidate_sort_key,
    _cross_validated_predictions,
    _feature_records,
    _load_json,
    _metrics,
    _prepare_development_rows,
    _rf_pipeline,
    _sha256,
    _write_json_atomic,
    _write_text_atomic,
)

PHASE_ID = "11.2"
CONFIG_ID = "zone-a-phase11.2-multimodal-v1"
BASELINE_CONFIG_ID = "zone-a-phase11.1-baselines-v1"
FEATURE_ROOTS = {
    "camera_a1": (
        "camera_available", "pose_available", "camera", "a1_available", "esp_a1"
    ),
    "camera_a2": (
        "camera_available", "pose_available", "camera", "a2_available", "esp_a2"
    ),
    "camera_a1_a2": (
        "camera_available", "pose_available", "camera", "a1_available",
        "a2_available", "esp_a1", "esp_a2",
    ),
}
BASELINES = ("majority", "camera_only", "a1_only", "a1_a2")

class MultimodalBuildError(BaselineBuildError):
    """raised when the frozen phase 11.2 contract is violated"""

def _validate_config(config: dict) -> None:
    required = {
        "schema_version",
        "config_id",
        "split_policy_id",
        "random_seed",
        "selection_metric",
        "class_labels",
        "feature_sets",
        "random_forest_candidates",
        "source_hashes",
        "baseline_reference",
    }
    if set(config) != required:
        raise MultimodalBuildError("multimodal config fields differ from the frozen contract")
    if config["schema_version"] != 1 or config["config_id"] != CONFIG_ID:
        raise MultimodalBuildError("unsupported Phase 11.2 multimodal config")
    if config["random_seed"] != 3070:
        raise MultimodalBuildError("Phase 11.2 random seed must remain 3070")
    if config["selection_metric"] != "macro_f1":
        raise MultimodalBuildError("Phase 11.2 selection metric must be macro_f1")
    if tuple(config["class_labels"]) != CLASS_LABELS:
        raise MultimodalBuildError("class labels or their reporting order changed")
    expected_features = {name: list(roots) for name, roots in FEATURE_ROOTS.items()}
    if config["feature_sets"] != expected_features:
        raise MultimodalBuildError("feature sets differ from the Phase 11.2 contract")
    candidates = config["random_forest_candidates"]
    allowed = {"n_estimators", "max_depth", "min_samples_leaf", "class_weight"}
    if not isinstance(candidates, list) or not candidates:
        raise MultimodalBuildError("at least one Random Forest candidate is required")
    if any(not isinstance(item, dict) or set(item) != allowed for item in candidates):
        raise MultimodalBuildError("Random Forest candidate fields differ from the contract")
    baseline = config["baseline_reference"]
    if set(baseline) != {"config_id", "metrics_sha256", "macro_f1"}:
        raise MultimodalBuildError("baseline reference fields differ from the contract")
    if baseline["config_id"] != BASELINE_CONFIG_ID:
        raise MultimodalBuildError("Phase 11.1 baseline config reference changed")
    if set(baseline["macro_f1"]) != set(BASELINES):
        raise MultimodalBuildError("baseline comparison set changed")

def _validate_baselines(path: Path, reference: dict) -> dict:
    if _sha256(path) != reference["metrics_sha256"]:
        raise MultimodalBuildError("Phase 11.1 baseline metrics differ from the frozen config")
    report = _load_json(path)
    if (
        report.get("phase") != "11.1"
        or report.get("status") != "complete_development_only"
        or report.get("config_id") != BASELINE_CONFIG_ID
        or report.get("external_test", {}).get("evaluated") is not False
    ):
        raise MultimodalBuildError("Phase 11.1 baseline report is not accepted development evidence")
    observed = {
        name: report["baselines"][name]["aggregate_metrics"]["macro_f1"]
        for name in BASELINES
    }
    if observed != reference["macro_f1"]:
        raise MultimodalBuildError("Phase 11.1 comparison metrics changed")
    return observed

def _model_card(name: str, result: dict, sources: dict, baseline_f1: float) -> str:
    metric = result["aggregate_metrics"]
    return "\n".join([
        f"# ARIA Phase 11.2 model card: {name}",
        "",
        "## Scope",
        "",
        "This early-fusion candidate was selected and measured only on the frozen "
        "Phase 10.3 development folds. The locked external test was not evaluated.",
        "",
        "## Reproducibility",
        "",
        f"- Config: `{CONFIG_ID}`",
        f"- Development rows: {metric['row_count']}",
        f"- Frozen folds: {len(result['folds'])}",
        f"- Feature count: {len(result['feature_names'])}",
        f"- Source feature SHA-256: `{sources['participant_features_sha256']}`",
        f"- Selected parameters: `{json.dumps(result['selected_parameters'], sort_keys=True)}`",
        "",
        "## Development LOSO result",
        "",
        f"- Macro F1: {metric['macro_f1']:.6f}",
        f"- Balanced accuracy: {metric['balanced_accuracy']:.6f}",
        f"- Accuracy: {metric['accuracy']:.6f}",
        f"- Difference from Camera A-only macro F1: {metric['macro_f1'] - baseline_f1:+.6f}",
        "",
        "## Limitations",
        "",
        "Development validation is session-independent but not participant-independent. "
        "These results support model selection only. Reaching/Handling remains sparse, "
        "and availability features may reflect retained-session operating conditions.",
        "",
    ])

def _model_sort_key(item: tuple[str, dict]) -> tuple:
    name, result = item
    metrics = result["aggregate_metrics"]
    return -metrics["macro_f1"], -metrics["balanced_accuracy"], name

def build_phase_11_2_multimodal(
    *,
    feature_path: str | Path,
    split_manifest_path: str | Path,
    split_audit_path: str | Path,
    baseline_metrics_path: str | Path,
    config_path: str | Path,
    metrics_path: str | Path,
    model_dir: str | Path,
    model_card_dir: str | Path,
) -> dict:
    """train early-fusion candidates on development folds only"""

    feature_path = Path(feature_path)
    split_manifest_path = Path(split_manifest_path)
    split_audit_path = Path(split_audit_path)
    baseline_metrics_path = Path(baseline_metrics_path)
    config_path = Path(config_path)
    metrics_path = Path(metrics_path)
    model_dir = Path(model_dir)
    model_card_dir = Path(model_card_dir)
    config = _load_json(config_path)
    _validate_config(config)
    baseline_f1 = _validate_baselines(baseline_metrics_path, config["baseline_reference"])
    rows, folds, sources = _prepare_development_rows(feature_path, split_manifest_path, split_audit_path, config)
    labels = [row["activity"] for row in rows]
    if set(labels) != set(CLASS_LABELS):
        raise MultimodalBuildError("development data must contain every frozen activity class")
    row_folds = [row["validation_fold_id"] for row in rows]
    seed = config["random_seed"]
    model_dir.mkdir(parents=True, exist_ok=True)
    model_card_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for name, roots in FEATURE_ROOTS.items():
        matrix, feature_names = _feature_records(rows, roots)
        candidates = []
        for candidate in config["random_forest_candidates"]:
            predictions, fold_reports = _cross_validated_predictions(
                matrix,
                labels,
                row_folds,
                folds,
                lambda candidate=candidate: _rf_pipeline(candidate, seed),
            )
            candidates.append({
                "parameters": candidate,
                "aggregate_metrics": _metrics(labels, predictions),
                "folds": fold_reports,
            })
        selected = sorted(candidates, key=_candidate_sort_key)[0]
        result = {
            "model_type": "early-fusion median-imputed RandomForestClassifier",
            "feature_names": feature_names,
            "selected_parameters": selected["parameters"],
            "aggregate_metrics": selected["aggregate_metrics"],
            "folds": selected["folds"],
            "candidate_results": candidates,
        }
        results[name] = result
        fitted = _rf_pipeline(selected["parameters"], seed).fit(matrix, labels)
        joblib.dump(fitted, model_dir / f"{name}.joblib", compress=0)
        _write_text_atomic(_model_card(name, result, sources, baseline_f1["camera_only"]),model_card_dir / f"{name}.md",)

    selected_name = sorted(results.items(), key=_model_sort_key)[0][0]
    model_hashes = {f"{name}.joblib": _sha256(model_dir / f"{name}.joblib") for name in results}
    report = {
        "schema_version": 1,
        "phase": PHASE_ID,
        "status": "complete_development_only",
        "config_id": config["config_id"],
        "config_sha256": _sha256(config_path),
        "random_seed": seed,
        "selection_metric": config["selection_metric"],
        "source_evidence": {
            **sources,
            "phase_11_1_metrics_sha256": _sha256(baseline_metrics_path),
        },
        "development": {
            "row_count": len(rows),
            "fold_ids": folds,
            "class_counts": dict(sorted(Counter(labels).items())),
        },
        "external_test": {
            "evaluated": False,
            "row_count": sources["external_test_row_count_untouched"],
            "reason": "reserved for one final Phase 11 evaluation after model selection",
        },
        "baseline_macro_f1": baseline_f1,
        "multimodal_candidates": results,
        "selected_multimodal_candidate": selected_name,
        "selected_beats_camera_only": (
            results[selected_name]["aggregate_metrics"]["macro_f1"]
            > baseline_f1["camera_only"]
        ),
        "model_sha256": model_hashes,
    }
    _write_json_atomic(report, metrics_path)
    return report
