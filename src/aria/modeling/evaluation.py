"""guarded phase 11.3 external evaluation"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import platform
import sys
import time
import joblib
import numpy as np
import sklearn
from sklearn.metrics import log_loss
from aria.modeling.baselines import (
    CLASS_LABELS,
    _feature_records,
    _load_json,
    _load_jsonl,
    _metrics,
    _sha256,
    _write_json_atomic,
)

PHASE_ID = "11.3"
CONFIG_ID = "zone-a-phase11.3-evaluation-v1"
ABLATION_MODELS = (
    "majority",
    "camera_only",
    "a1_only",
    "a1_a2",
    "camera_a1",
    "camera_a2",
    "camera_a1_a2",
)

class EvaluationError(ValueError):
    """raised when phase 11.3 cannot follow its frozen contract"""

def _validate_contract(config: dict) -> None:
    required = {
        "schema_version",
        "config_id",
        "split_policy_id",
        "random_seed",
        "class_labels",
        "selected_model",
        "source_hashes",
        "external_evaluation",
        "classification_metrics",
        "reliability",
        "development_ablation_models",
        "missing_modality_policy",
        "latency_benchmark",
        "privacy_output",
    }
    if set(config) != required:
        raise EvaluationError("evaluation config fields differ from the frozen contract")
    if config["schema_version"] != 1 or config["config_id"] != CONFIG_ID:
        raise EvaluationError("unsupported Phase 11.3 evaluation config")
    if config["random_seed"] != 3070 or tuple(config["class_labels"]) != CLASS_LABELS:
        raise EvaluationError("seed or class order differs from the frozen contract")
    model = config["selected_model"]
    if (
        model.get("name") != "camera_only"
        or model.get("source_phase") != "11.1"
        or model.get("feature_roots") != ["camera_available", "pose_available", "camera"]
    ):
        raise EvaluationError("selected model differs from the frozen Camera-only choice")
    boundary = config["external_evaluation"]
    if (
        boundary.get("allowed_models") != ["camera_only"]
        or boundary.get("fit_allowed") is not False
        or boundary.get("parameter_changes_allowed") is not False
        or boundary.get("overwrite_allowed") is not False
        or boundary.get("row_level_output_allowed") is not False
    ):
        raise EvaluationError("external-test protections differ from the frozen contract")
    if tuple(config["development_ablation_models"]) != ABLATION_MODELS:
        raise EvaluationError("development ablation set changed")
    reliability = config["reliability"]
    if reliability.get("fit_calibrator") is not False:
        raise EvaluationError("external probability calibration is prohibited")
    privacy = config["privacy_output"]
    if privacy.get("aggregate_metrics_only") is not True or any(
        privacy.get(field) is not False
        for field in (
            "participant_ids",
            "session_ids",
            "track_ids",
            "raw_features",
            "raw_audio",
            "raw_or_masked_video",
        )
    ):
        raise EvaluationError("privacy output boundary changed")

def _verify_hash(path: Path, expected: str, name: str) -> None:
    if not path.is_file() or _sha256(path) != expected:
        raise EvaluationError(f"frozen {name} hash mismatch")

def _row_key(row: dict) -> tuple[str, str, str]:
    return row["session_id"], row["participant_id"], row["feature_vector"]["window_id"]

def _assignment_key(row: dict) -> tuple[str, str, str]:
    return row["session_id"], row["participant_id"], row["window_id"]

def preflight_phase_11_3(
    *,
    feature_path: str | Path,
    split_manifest_path: str | Path,
    split_audit_path: str | Path,
    phase_11_1_config_path: str | Path,
    phase_11_1_metrics_path: str | Path,
    phase_11_2_config_path: str | Path,
    phase_11_2_metrics_path: str | Path,
    model_path: str | Path,
    config_path: str | Path,
    metrics_path: str | Path,
) -> dict:
    """verify the frozen boundary without loading participant feature rows"""

    paths = {
        "participant_features_sha256": Path(feature_path),
        "split_manifest_sha256": Path(split_manifest_path),
        "split_audit_sha256": Path(split_audit_path),
        "phase_11_1_config_sha256": Path(phase_11_1_config_path),
        "phase_11_1_metrics_sha256": Path(phase_11_1_metrics_path),
        "phase_11_2_config_sha256": Path(phase_11_2_config_path),
        "phase_11_2_metrics_sha256": Path(phase_11_2_metrics_path),
    }
    config = _load_json(Path(config_path))
    _validate_contract(config)
    for name, path in paths.items():
        _verify_hash(path, config["source_hashes"][name], name)
    model_path = Path(model_path)
    if model_path.as_posix().endswith(config["selected_model"]["artifact_path"]):
        _verify_hash(model_path, config["selected_model"]["artifact_sha256"], "selected model")
    else:
        raise EvaluationError("selected model path differs from the frozen contract")
    audit = _load_json(Path(split_audit_path))
    if audit.get("status") != "pass":
        raise EvaluationError("Phase 10.3 split audit must pass")
    for path in (Path(phase_11_1_metrics_path), Path(phase_11_2_metrics_path)):
        report = _load_json(path)
        if report.get("external_test", {}).get("evaluated") is not False:
            raise EvaluationError("earlier Phase 11 report shows external evaluation")
    assignments = _load_jsonl(Path(split_manifest_path))
    external_count = sum(row.get("partition") == "external_test" for row in assignments)
    if external_count != config["external_evaluation"]["expected_row_count"]:
        raise EvaluationError("external row count differs from the frozen contract")
    if any(row.get("split_policy_id") != config["split_policy_id"] for row in assignments):
        raise EvaluationError("split policy differs from the frozen contract")
    metrics_path = Path(metrics_path)
    if metrics_path.exists():
        raise EvaluationError("accepted Phase 11.3 metrics already exist; overwrite prohibited")
    return {
        "status": "ready",
        "config_id": config["config_id"],
        "selected_model": config["selected_model"]["name"],
        "external_row_count": external_count,
        "external_rows_loaded_for_prediction": 0,
        "metrics_output_exists": False,
    }

def _external_rows(feature_path: Path, split_manifest_path: Path, config: dict) -> list[dict]:
    features = _load_jsonl(feature_path)
    assignments = _load_jsonl(split_manifest_path)
    feature_by_key = {_row_key(row): row for row in features}
    if len(feature_by_key) != len(features):
        raise EvaluationError("participant features contain duplicate row keys")
    assignment_keys = [_assignment_key(row) for row in assignments]
    if len(assignment_keys) != len(set(assignment_keys)):
        raise EvaluationError("split manifest contains duplicate row keys")
    if set(feature_by_key) != set(assignment_keys):
        raise EvaluationError("participant features and split assignments do not reconcile")
    rows = [
        feature_by_key[_assignment_key(assignment)]
        for assignment in assignments
        if assignment["partition"] == "external_test"
    ]
    if len(rows) != config["external_evaluation"]["expected_row_count"]:
        raise EvaluationError("external evaluation matrix has the wrong row count")
    return rows

def _ordered_probabilities(model, matrix: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(matrix), dtype=float)
    classes = list(model.classes_)
    if set(classes) != set(CLASS_LABELS):
        raise EvaluationError("model classes differ from the frozen class set")
    return probabilities[:, [classes.index(label) for label in CLASS_LABELS]]

def _reliability(labels: list[str], probabilities: np.ndarray, config: dict) -> dict:
    encoded = np.asarray([[float(label == expected) for expected in CLASS_LABELS] for label in labels])
    predictions = np.asarray(CLASS_LABELS)[np.argmax(probabilities, axis=1)]
    confidence = np.max(probabilities, axis=1)
    correct = predictions == np.asarray(labels)
    bin_count = config["binning"]["bin_count"]
    indexes = np.minimum((confidence * bin_count).astype(int), bin_count - 1)
    bins = []
    weighted_gap = 0.0
    maximum_gap = 0.0
    for index in range(bin_count):
        selected = indexes == index
        count = int(selected.sum())
        accuracy = float(correct[selected].mean()) if count else None
        mean_confidence = float(confidence[selected].mean()) if count else None
        gap = abs(accuracy - mean_confidence) if count else 0.0
        weighted_gap += count * gap
        maximum_gap = max(maximum_gap, gap)
        bins.append({
            "lower": index / bin_count,
            "upper": (index + 1) / bin_count,
            "row_count": count,
            "accuracy": accuracy,
            "mean_confidence": mean_confidence,
        })
    threshold = config["high_confidence_threshold"]
    return {
        "multiclass_log_loss": float(log_loss(labels, probabilities, labels=CLASS_LABELS)),
        "multiclass_brier_score": float(np.mean(np.sum((probabilities - encoded) ** 2, axis=1))),
        "expected_calibration_error": weighted_gap / len(labels),
        "maximum_calibration_error": maximum_gap,
        "high_confidence_threshold": threshold,
        "high_confidence_error_count": int(((confidence >= threshold) & ~correct).sum()),
        "bins": bins,
    }

def _ablation(phase_11_1: dict, phase_11_2: dict) -> dict:
    results = {}
    for name in ABLATION_MODELS[:4]:
        metrics = phase_11_1["baselines"][name]["aggregate_metrics"]
        results[name] = {key: metrics[key] for key in ("macro_f1", "balanced_accuracy", "accuracy", "per_class")}
    for name in ABLATION_MODELS[4:]:
        metrics = phase_11_2["multimodal_candidates"][name]["aggregate_metrics"]
        results[name] = {key: metrics[key] for key in ("macro_f1", "balanced_accuracy", "accuracy", "per_class")}
    camera_f1 = results["camera_only"]["macro_f1"]
    for result in results.values():
        result["macro_f1_difference_from_camera_only"] = result["macro_f1"] - camera_f1
    return results

def _latency(model, rows: list[dict], roots: tuple[str, ...], config: dict) -> dict:
    benchmark = config["latency_benchmark"]
    results = {}
    for batch_size in benchmark["batch_sizes"]:
        batch = [rows[index % len(rows)] for index in range(batch_size)]
        for _ in range(benchmark["warmup_iterations"]):
            matrix, _ = _feature_records(batch, roots)
            model.predict_proba(matrix)
        samples = []
        for _ in range(benchmark["measured_iterations"]):
            started = time.perf_counter_ns()
            matrix, _ = _feature_records(batch, roots)
            model.predict_proba(matrix)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        values = np.asarray(samples)
        results[str(batch_size)] = {
            "iterations": len(samples),
            "latency_ms": {
                f"p{percentile}": float(np.percentile(values, percentile))
                for percentile in benchmark["percentiles"]
            },
            "mean_ms": float(values.mean()),
            "throughput_rows_per_second": float(batch_size / (values.mean() / 1000)),
        }
    return {
        "scope": "feature flattening and model pipeline prediction only",
        "camera_capture_or_dashboard_included": False,
        "host": platform.platform(),
        "python_version": platform.python_version(),
        "scikit_learn_version": sklearn.__version__,
        "batches": results,
    }

def evaluate_phase_11_3(
    *,
    feature_path: str | Path,
    split_manifest_path: str | Path,
    split_audit_path: str | Path,
    phase_11_1_config_path: str | Path,
    phase_11_1_metrics_path: str | Path,
    phase_11_2_config_path: str | Path,
    phase_11_2_metrics_path: str | Path,
    model_path: str | Path,
    config_path: str | Path,
    metrics_path: str | Path,
) -> dict:
    """run the frozen one-time external evaluation and write aggregate results"""

    preflight_phase_11_3(
        feature_path=feature_path,
        split_manifest_path=split_manifest_path,
        split_audit_path=split_audit_path,
        phase_11_1_config_path=phase_11_1_config_path,
        phase_11_1_metrics_path=phase_11_1_metrics_path,
        phase_11_2_config_path=phase_11_2_config_path,
        phase_11_2_metrics_path=phase_11_2_metrics_path,
        model_path=model_path,
        config_path=config_path,
        metrics_path=metrics_path,
    )
    config = _load_json(Path(config_path))
    rows = _external_rows(Path(feature_path), Path(split_manifest_path), config)
    roots = tuple(config["selected_model"]["feature_roots"])
    matrix, feature_names = _feature_records(rows, roots)
    labels = [row["activity"] for row in rows]
    if set(labels) != set(CLASS_LABELS):
        raise EvaluationError("external data must contain every frozen activity class")
    model = joblib.load(model_path)
    predictions = model.predict(matrix).tolist()
    probabilities = _ordered_probabilities(model, matrix)
    phase_11_1 = _load_json(Path(phase_11_1_metrics_path))
    phase_11_2 = _load_json(Path(phase_11_2_metrics_path))
    report = {
        "schema_version": 1,
        "phase": PHASE_ID,
        "status": "complete_external_evaluation",
        "config_id": config["config_id"],
        "config_sha256": _sha256(Path(config_path)),
        "selected_model": config["selected_model"],
        "source_evidence": config["source_hashes"],
        "external_test": {
            "evaluated": True,
            "row_count": len(rows),
            "class_counts": dict(sorted(Counter(labels).items())),
        },
        "classification": _metrics(labels, predictions),
        "reliability": _reliability(labels, probabilities, config["reliability"]),
        "development_ablation": _ablation(phase_11_1, phase_11_2),
        "missing_modality_policy": config["missing_modality_policy"],
        "latency": _latency(model, rows, roots, config),
        "privacy": {
            "aggregate_only": True,
            "row_level_predictions_retained": False,
            "feature_names": feature_names,
        },
    }
    _write_json_atomic(report, Path(metrics_path))
    return report