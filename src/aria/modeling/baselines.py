"""leakage-safe, deterministic phase 11.1 baseline modelling"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline

PHASE_ID = "11.1"
CONFIG_ID = "zone-a-phase11.1-baselines-v1"
CLASS_LABELS = ("Serving/Processing","Idle/Waiting","Reaching/Handling",)
FEATURE_ROOTS = {
    "camera_only": ("camera_available", "pose_available", "camera"),
    "a1_only": ("a1_available", "esp_a1"),
    "a1_a2": ("a1_available", "a2_available", "esp_a1", "esp_a2"),
}

class BaselineBuildError(ValueError):
    """raised when frozen phase 11.1 baseline contract is violated"""

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineBuildError(f"Cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise BaselineBuildError(f"{path} must contain a JSON object")
    return value

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise BaselineBuildError(
                        f"{path}:{line_number}: expected a JSON object"
                    )
                records.append(value)
    except json.JSONDecodeError as error:
        raise BaselineBuildError(f"{path}: invalid JSONL: {error}") from error
    except OSError as error:
        raise BaselineBuildError(f"Cannot read {path}: {error}") from error
    return records

def _write_json_atomic(value: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise

def _write_text_atomic(value: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise

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
    }
    if set(config) != required:
        raise BaselineBuildError("baseline config fields differ from the frozen contract")
    if config["schema_version"] != 1 or config["config_id"] != CONFIG_ID:
        raise BaselineBuildError("unsupported Phase 11.1 baseline config")
    if config["selection_metric"] != "macro_f1":
        raise BaselineBuildError("Phase 11.1 model selection metric must be macro_f1")
    if tuple(config["class_labels"]) != CLASS_LABELS:
        raise BaselineBuildError("class labels or their reporting order changed")
    if config["feature_sets"] != {name: list(roots) for name, roots in FEATURE_ROOTS.items()}:
        raise BaselineBuildError("feature sets differ from the Phase 11.1 contract")
    candidates = config["random_forest_candidates"]
    if not isinstance(candidates, list) or not candidates:
        raise BaselineBuildError("at least one Random Forest candidate is required")
    allowed = {"n_estimators", "max_depth", "min_samples_leaf", "class_weight"}
    if any(not isinstance(item, dict) or set(item) != allowed for item in candidates):
        raise BaselineBuildError("Random Forest candidate fields differ from the contract")
    if not isinstance(config["random_seed"], int):
        raise BaselineBuildError("random_seed must be an integer")

def _row_key(row: dict) -> tuple[str, str, str]:
    return (
        row["session_id"],
        row["participant_id"],
        row["feature_vector"]["window_id"],
    )

def _assignment_key(row: dict) -> tuple[str, str, str]:
    return row["session_id"], row["participant_id"], row["window_id"]

def _prepare_development_rows(
    feature_path: Path,
    split_manifest_path: Path,
    split_audit_path: Path,
    config: dict,
) -> tuple[list[dict], list[str], dict]:
    hashes = {
        "participant_features_sha256": _sha256(feature_path),
        "split_manifest_sha256": _sha256(split_manifest_path),
        "split_audit_sha256": _sha256(split_audit_path),
    }
    if hashes != config["source_hashes"]:
        raise BaselineBuildError("source hashes differ from the frozen baseline config")
    audit = _load_json(split_audit_path)
    if audit.get("status") != "pass":
        raise BaselineBuildError("Phase 10.3 split audit must pass before modelling")

    features = _load_jsonl(feature_path)
    assignments = _load_jsonl(split_manifest_path)
    feature_by_key = {_row_key(row): row for row in features}
    if len(feature_by_key) != len(features):
        raise BaselineBuildError("participant features contain duplicate row keys")
    assignment_keys = [_assignment_key(row) for row in assignments]
    if len(assignment_keys) != len(set(assignment_keys)):
        raise BaselineBuildError("split manifest contains duplicate row keys")
    if set(feature_by_key) != set(assignment_keys):
        raise BaselineBuildError("participant features and split assignments do not reconcile")

    development = []
    external_count = 0
    for assignment in assignments:
        if assignment.get("split_policy_id") != config["split_policy_id"]:
            raise BaselineBuildError("split policy differs from the baseline config")
        if assignment["partition"] == "external_test":
            external_count += 1
            continue
        if assignment["partition"] != "development":
            raise BaselineBuildError("unknown split partition")
        fold_id = assignment.get("validation_fold_id")
        if not fold_id:
            raise BaselineBuildError("development row has no validation fold")
        row = feature_by_key[_assignment_key(assignment)].copy()
        row["validation_fold_id"] = fold_id
        development.append(row)
    folds = sorted({row["validation_fold_id"] for row in development})
    if len(folds) < 2 or external_count == 0:
        raise BaselineBuildError("both grouped development folds and locked external rows are required")
    return development, folds, {**hashes, "external_test_row_count_untouched": external_count}

def _flatten_numeric(value: Any, prefix: str, output: dict[str, float | None]) -> None:
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten_numeric(value[key], f"{prefix}.{key}" if prefix else key, output)
    elif isinstance(value, bool):
        output[prefix] = float(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        output[prefix] = float(value)
    elif value is None:
        output[prefix] = None
    else:
        raise BaselineBuildError(f"non-numeric modelling feature encountered: {prefix}")

def _feature_records(rows: list[dict], roots: tuple[str, ...]) -> tuple[np.ndarray, list[str]]:
    flattened = []
    for row in rows:
        record = {}
        vector = row["feature_vector"]
        for root in roots:
            if root not in vector:
                raise BaselineBuildError(f"feature vector is missing frozen root: {root}")
            _flatten_numeric(vector[root], root, record)
        flattened.append(record)
    names = sorted(flattened[0])
    if any(sorted(record) != names for record in flattened):
        raise BaselineBuildError("feature fields are inconsistent across rows")
    matrix = np.asarray(
        [[np.nan if record[name] is None else record[name] for name in names]
         for record in flattened],
        dtype=float,
    )
    return matrix, names

def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=CLASS_LABELS,
        zero_division=0,
    )
    return {
        "row_count": len(y_true),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(CLASS_LABELS)
        },
        "confusion_matrix": confusion_matrix(
            y_true, y_pred, labels=CLASS_LABELS
        ).astype(int).tolist(),
    }

def _rf_pipeline(candidate: dict, seed: int) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(
            strategy="median",
            add_indicator=True,
            keep_empty_features=True,
        )),
        ("classifier", RandomForestClassifier(
            random_state=seed,
            n_jobs=1,
            **candidate,
        )),
    ])

def _cross_validated_predictions(
    matrix: np.ndarray,
    labels: list[str],
    row_folds: list[str],
    folds: list[str],
    estimator_factory,
) -> tuple[list[str], list[dict]]:
    predictions = [None] * len(labels)
    fold_reports = []
    for fold_id in folds:
        training = np.asarray([value != fold_id for value in row_folds])
        validation = ~training
        estimator = estimator_factory()
        estimator.fit(matrix[training], np.asarray(labels)[training])
        fold_predictions = estimator.predict(matrix[validation]).tolist()
        validation_indexes = np.flatnonzero(validation).tolist()
        for index, prediction in zip(validation_indexes, fold_predictions):
            predictions[index] = prediction
        fold_reports.append({
            "fold_id": fold_id,
            "training_row_count": int(training.sum()),
            "validation_row_count": int(validation.sum()),
            "metrics": _metrics(np.asarray(labels)[validation].tolist(), fold_predictions),
        })
    if any(value is None for value in predictions):
        raise BaselineBuildError("cross-validation did not predict every development row")
    return predictions, fold_reports

def _candidate_sort_key(result: dict) -> tuple:
    params = result["parameters"]
    return (
        -result["aggregate_metrics"]["macro_f1"],
        -result["aggregate_metrics"]["balanced_accuracy"],
        params["n_estimators"],
        -1 if params["max_depth"] is None else params["max_depth"],
        params["min_samples_leaf"],
        str(params["class_weight"]),
    )

def _model_card(name: str, result: dict, sources: dict, feature_names: list[str]) -> str:
    metric = result["aggregate_metrics"]
    params = result.get("selected_parameters")
    lines = [
        f"# ARIA Phase 11.1 model card: {name}",
        "",
        "## Scope",
        "",
        "This baseline was selected and measured only on the frozen Phase 10.3 "
        "development folds. The locked external test was not evaluated.",
        "",
        "## Reproducibility",
        "",
        f"- Config: `{CONFIG_ID}`",
        f"- Development rows: {metric['row_count']}",
        f"- Frozen folds: {len(result['folds'])}",
        f"- Feature count: {len(feature_names)}",
        f"- Source feature SHA-256: `{sources['participant_features_sha256']}`",
        f"- Split manifest SHA-256: `{sources['split_manifest_sha256']}`",
    ]
    if params is not None:
        lines.append(f"- Selected parameters: `{json.dumps(params, sort_keys=True)}`")
    lines.extend([
        "",
        "## Development LOSO result",
        "",
        f"- Macro F1: {metric['macro_f1']:.6f}",
        f"- Balanced accuracy: {metric['balanced_accuracy']:.6f}",
        f"- Accuracy: {metric['accuracy']:.6f}",
        "",
        "## Limitations",
        "",
        "Development validation is session-independent but not participant-independent. "
        "These metrics are model-selection evidence, not final external-test performance. "
        "The minority Reaching/Handling class is sparse, and missing-value indicators may "
        "capture operational availability patterns specific to the retained sessions.",
        "",
    ])
    return "\n".join(lines)

def build_phase_11_1_baselines(
    *,
    feature_path: str | Path,
    split_manifest_path: str | Path,
    split_audit_path: str | Path,
    config_path: str | Path,
    metrics_path: str | Path,
    model_dir: str | Path,
    model_card_dir: str | Path,
) -> dict:
    """select baselines with development loso only and save reproducible artifacts"""

    feature_path = Path(feature_path)
    split_manifest_path = Path(split_manifest_path)
    split_audit_path = Path(split_audit_path)
    config_path = Path(config_path)
    metrics_path = Path(metrics_path)
    model_dir = Path(model_dir)
    model_card_dir = Path(model_card_dir)
    config = _load_json(config_path)
    _validate_config(config)
    rows, folds, sources = _prepare_development_rows(
        feature_path, split_manifest_path, split_audit_path, config
    )
    labels = [row["activity"] for row in rows]
    if set(labels) != set(CLASS_LABELS):
        raise BaselineBuildError("development data must contain every frozen activity class")
    row_folds = [row["validation_fold_id"] for row in rows]
    seed = config["random_seed"]

    majority_matrix = np.zeros((len(rows), 1), dtype=float)
    majority_predictions, majority_folds = _cross_validated_predictions(
        majority_matrix,
        labels,
        row_folds,
        folds,
        lambda: DummyClassifier(strategy="most_frequent"),
    )
    results = {
        "majority": {
            "model_type": "DummyClassifier(most_frequent)",
            "feature_names": [],
            "aggregate_metrics": _metrics(labels, majority_predictions),
            "folds": majority_folds,
        }
    }

    model_dir.mkdir(parents=True, exist_ok=True)
    model_card_dir.mkdir(parents=True, exist_ok=True)
    majority_model = DummyClassifier(strategy="most_frequent").fit(
        majority_matrix, labels
    )
    majority_path = model_dir / "majority.joblib"
    joblib.dump(majority_model, majority_path, compress=0)

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
        ranked = sorted(candidates, key=_candidate_sort_key)
        selected = ranked[0]
        result = {
            "model_type": "median-imputed RandomForestClassifier",
            "feature_names": feature_names,
            "selected_parameters": selected["parameters"],
            "aggregate_metrics": selected["aggregate_metrics"],
            "folds": selected["folds"],
            "candidate_results": candidates,
        }
        results[name] = result
        fitted = _rf_pipeline(selected["parameters"], seed).fit(matrix, labels)
        joblib.dump(fitted, model_dir / f"{name}.joblib", compress=0)

    for name, result in results.items():
        _write_text_atomic(_model_card(name, result, sources, result["feature_names"]),model_card_dir / f"{name}.md",)

    model_hashes = {path.name: _sha256(path) for path in sorted(model_dir.glob("*.joblib"))}
    report = {
        "schema_version": 1,
        "phase": PHASE_ID,
        "status": "complete_development_only",
        "config_id": config["config_id"],
        "config_sha256": _sha256(config_path),
        "random_seed": seed,
        "selection_metric": config["selection_metric"],
        "source_evidence": sources,
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
        "baselines": results,
        "model_sha256": model_hashes,
    }
    _write_json_atomic(report, metrics_path)
    return report
