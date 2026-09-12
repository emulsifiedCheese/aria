import json
from hashlib import sha256
from pathlib import Path
import joblib
import pytest
from aria.modeling.baselines import _feature_records, _rf_pipeline
from aria.modeling.evaluation import (
    EvaluationError,
    evaluate_phase_11_3,
    preflight_phase_11_3,
)

LABELS = ("Serving/Processing", "Idle/Waiting", "Reaching/Handling")
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),encoding="utf-8",)

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _row(session, participant, window, activity, value):
    return {
        "session_id": session,
        "participant_id": participant,
        "activity": activity,
        "feature_vector": {
            "window_id": window,
            "camera_available": True,
            "pose_available": True,
            "camera": {"movement": value, "confidence": 0.8},
        },
    }

def _metric(value):
    return {
        "macro_f1": value,
        "balanced_accuracy": value,
        "accuracy": value,
        "per_class": {label: {"f1": value} for label in LABELS},
    }

def _fixture(tmp_path):
    features = []
    assignments = []
    for index, label in enumerate(LABELS):
        for partition in ("development", "external_test"):
            session = f"{partition}_session"
            participant = "P0001" if partition == "development" else "P0009"
            window = f"{partition}_{index}"
            row = _row(session, participant, window, label, index + 0.1)
            features.append(row)
            assignments.append({
                "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
                "partition": partition,
                "validation_fold_id": "fold_01" if partition == "development" else None,
                "session_id": session,
                "participant_id": participant,
                "window_id": window,
            })

    paths = {
        "feature_path": tmp_path / "features.jsonl",
        "split_manifest_path": tmp_path / "split.jsonl",
        "split_audit_path": tmp_path / "audit.json",
        "phase_11_1_config_path": tmp_path / "phase_11_1_config.json",
        "phase_11_1_metrics_path": tmp_path / "phase_11_1_metrics.json",
        "phase_11_2_config_path": tmp_path / "phase_11_2_config.json",
        "phase_11_2_metrics_path": tmp_path / "phase_11_2_metrics.json",
        "model_path": tmp_path / "camera_only.joblib",
        "config_path": tmp_path / "phase_11_3_config.json",
        "metrics_path": tmp_path / "external_metrics.json",
    }
    _write_jsonl(paths["feature_path"], features)
    _write_jsonl(paths["split_manifest_path"], assignments)
    _write_json(paths["split_audit_path"], {"status": "pass"})
    _write_json(paths["phase_11_1_config_path"], {"config_id": "phase_11_1"})
    _write_json(paths["phase_11_2_config_path"], {"config_id": "phase_11_2"})
    _write_json(paths["phase_11_1_metrics_path"], {
        "external_test": {"evaluated": False, "row_count": 3},
        "baselines": {
            name: {"aggregate_metrics": _metric(value)}
            for name, value in {
                "majority": 0.2,
                "camera_only": 0.4,
                "a1_only": 0.3,
                "a1_a2": 0.31,
            }.items()
        },
    })
    _write_json(paths["phase_11_2_metrics_path"], {
        "external_test": {"evaluated": False, "row_count": 3},
        "multimodal_candidates": {
            name: {"aggregate_metrics": _metric(value)}
            for name, value in {
                "camera_a1": 0.38,
                "camera_a2": 0.37,
                "camera_a1_a2": 0.36,
            }.items()
        },
    })
    development = [row for row in features if row["session_id"] == "development_session"]
    matrix, _ = _feature_records(development, ("camera_available", "pose_available", "camera"))
    model = _rf_pipeline({
        "n_estimators": 5,
        "max_depth": 3,
        "min_samples_leaf": 1,
        "class_weight": "balanced_subsample",
    }, 3070).fit(matrix, list(LABELS))
    joblib.dump(model, paths["model_path"], compress=0)

    source_paths = {
        "participant_features_sha256": "feature_path",
        "split_manifest_sha256": "split_manifest_path",
        "split_audit_sha256": "split_audit_path",
        "phase_11_1_config_sha256": "phase_11_1_config_path",
        "phase_11_1_metrics_sha256": "phase_11_1_metrics_path",
        "phase_11_2_config_sha256": "phase_11_2_config_path",
        "phase_11_2_metrics_sha256": "phase_11_2_metrics_path",
    }
    contract = json.loads(
        (PROJECT_ROOT / "config/phase_11_3_evaluation.json").read_text(encoding="utf-8")
    )
    contract["selected_model"]["artifact_path"] = "camera_only.joblib"
    contract["selected_model"]["artifact_sha256"] = _sha256(paths["model_path"])
    contract["external_evaluation"]["expected_row_count"] = 3
    contract["source_hashes"] = {name: _sha256(paths[path_name]) for name, path_name in source_paths.items()}
    contract["latency_benchmark"].update({
        "warmup_iterations": 1,
        "measured_iterations": 2,
        "batch_sizes": [1],
        "percentiles": [50],
    })
    _write_json(paths["config_path"], contract)
    return paths

def test_preflight_checks_boundary_without_loading_feature_rows(tmp_path, monkeypatch):
    paths = _fixture(tmp_path)

    def fail_if_loaded(path):
        if path == paths["feature_path"]:
            raise AssertionError("preflight loaded participant features")
        from aria.modeling.baselines import _load_jsonl as load_jsonl
        return load_jsonl(path)

    monkeypatch.setattr("aria.modeling.evaluation._load_jsonl", fail_if_loaded)
    report = preflight_phase_11_3(**paths)

    assert report["status"] == "ready"
    assert report["external_row_count"] == 3
    assert report["external_rows_loaded_for_prediction"] == 0
    assert not paths["metrics_path"].exists()

def test_evaluator_writes_aggregate_external_metrics_only(tmp_path):
    paths = _fixture(tmp_path)

    report = evaluate_phase_11_3(**paths)

    assert report["status"] == "complete_external_evaluation"
    assert report["external_test"]["evaluated"] is True
    assert report["external_test"]["row_count"] == 3
    assert report["classification"]["row_count"] == 3
    assert report["reliability"]["bins"]
    assert set(report["development_ablation"]) == {"majority", "camera_only", "a1_only", "a1_a2","camera_a1", "camera_a2", "camera_a1_a2",}
    assert report["privacy"]["row_level_predictions_retained"] is False
    encoded = json.dumps(report)
    assert "P0001" not in encoded
    assert "P0009" not in encoded
    assert "development_session" not in encoded
    assert "external_session" not in encoded
    assert json.loads(paths["metrics_path"].read_text(encoding="utf-8")) == report

def test_evaluator_refuses_to_overwrite_accepted_output(tmp_path):
    paths = _fixture(tmp_path)
    evaluate_phase_11_3(**paths)

    with pytest.raises(EvaluationError, match="overwrite prohibited"):
        evaluate_phase_11_3(**paths)

def test_preflight_rejects_source_drift(tmp_path):
    paths = _fixture(tmp_path)
    paths["split_audit_path"].write_text('{"status":"fail"}\n', encoding="utf-8")

    with pytest.raises(EvaluationError, match="hash mismatch"):
        preflight_phase_11_3(**paths)