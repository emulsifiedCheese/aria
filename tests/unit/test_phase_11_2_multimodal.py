import json
from hashlib import sha256
import joblib
import pytest
from aria.modeling.multimodal import MultimodalBuildError, build_phase_11_2_multimodal

SESSIONS = ("session_1", "session_2", "session_3")
LABELS = ("Serving/Processing", "Idle/Waiting", "Reaching/Handling")
BASELINE_F1 = {
    "majority": 0.26,
    "camera_only": 0.44,
    "a1_only": 0.36,
    "a1_a2": 0.37,
}

def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),encoding="utf-8",)

def _feature_row(session, participant, window, activity, value):
    return {
        "session_id": session,
        "participant_id": participant,
        "activity": activity,
        "feature_vector": {
            "window_id": f"window_{window}",
            "camera_available": True,
            "pose_available": True,
            "a1_available": True,
            "a2_available": True,
            "camera": {"movement": value, "confidence": 0.8},
            "esp_a1": {"pir": value, "audio": value * 2},
            "esp_a2": {"pir": value, "audio": value * 3},
        },
    }

def _fixture(tmp_path):
    rows = []
    assignments = []
    for fold_index, session in enumerate(SESSIONS, 1):
        for label_index, label in enumerate(LABELS, 1):
            window = fold_index * 10 + label_index
            row = _feature_row(session, "P0001", window, label, label_index + fold_index / 10)
            rows.append(row)
            assignments.append({
                "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
                "partition": "development",
                "validation_fold_id": f"fold_{fold_index:02d}",
                "session_id": session,
                "participant_id": "P0001",
                "window_id": row["feature_vector"]["window_id"],
            })
    external = _feature_row("external_session", "P0009", 99, LABELS[0], 9.9)
    rows.append(external)
    assignments.append({
        "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
        "partition": "external_test",
        "validation_fold_id": None,
        "session_id": "external_session",
        "participant_id": "P0009",
        "window_id": external["feature_vector"]["window_id"],
    })

    feature_path = tmp_path / "features.jsonl"
    manifest_path = tmp_path / "manifest.jsonl"
    audit_path = tmp_path / "audit.json"
    baseline_path = tmp_path / "baseline.json"
    config_path = tmp_path / "config.json"
    _write_jsonl(feature_path, rows)
    _write_jsonl(manifest_path, assignments)
    _write_json(audit_path, {"status": "pass"})
    _write_json(baseline_path, {
        "phase": "11.1",
        "status": "complete_development_only",
        "config_id": "zone-a-phase11.1-baselines-v1",
        "external_test": {"evaluated": False},
        "baselines": {
            name: {"aggregate_metrics": {"macro_f1": value}}
            for name, value in BASELINE_F1.items()
        },
    })
    _write_json(config_path, {
        "schema_version": 1,
        "config_id": "zone-a-phase11.2-multimodal-v1",
        "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
        "random_seed": 3070,
        "selection_metric": "macro_f1",
        "class_labels": list(LABELS),
        "feature_sets": {
            "camera_a1": [
                "camera_available", "pose_available", "camera", "a1_available", "esp_a1"
            ],
            "camera_a2": [
                "camera_available", "pose_available", "camera", "a2_available", "esp_a2"
            ],
            "camera_a1_a2": [
                "camera_available", "pose_available", "camera", "a1_available",
                "a2_available", "esp_a1", "esp_a2",
            ],
        },
        "random_forest_candidates": [{
            "n_estimators": 5,
            "max_depth": 3,
            "min_samples_leaf": 1,
            "class_weight": "balanced_subsample",
        }],
        "source_hashes": {
            "participant_features_sha256": sha256(feature_path.read_bytes()).hexdigest(),
            "split_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest(),
            "split_audit_sha256": sha256(audit_path.read_bytes()).hexdigest(),
        },
        "baseline_reference": {
            "config_id": "zone-a-phase11.1-baselines-v1",
            "metrics_sha256": sha256(baseline_path.read_bytes()).hexdigest(),
            "macro_f1": BASELINE_F1,
        },
    })
    return feature_path, manifest_path, audit_path, baseline_path, config_path

def _build(tmp_path, inputs):
    return build_phase_11_2_multimodal(
        feature_path=inputs[0],
        split_manifest_path=inputs[1],
        split_audit_path=inputs[2],
        baseline_metrics_path=inputs[3],
        config_path=inputs[4],
        metrics_path=tmp_path / "metrics.json",
        model_dir=tmp_path / "models",
        model_card_dir=tmp_path / "cards",
    )

def test_builds_three_development_only_early_fusion_candidates(tmp_path):
    report = _build(tmp_path, _fixture(tmp_path))

    assert report["status"] == "complete_development_only"
    assert report["development"]["row_count"] == 9
    assert report["external_test"]["evaluated"] is False
    assert report["external_test"]["row_count"] == 1
    assert set(report["multimodal_candidates"]) == {"camera_a1", "camera_a2", "camera_a1_a2"}
    a1_names = report["multimodal_candidates"]["camera_a1"]["feature_names"]
    a2_names = report["multimodal_candidates"]["camera_a2"]["feature_names"]
    combined_names = report["multimodal_candidates"]["camera_a1_a2"]["feature_names"]
    assert any(name.startswith("esp_a1") for name in a1_names)
    assert not any(name.startswith("esp_a2") for name in a1_names)
    assert any(name.startswith("esp_a2") for name in a2_names)
    assert not any(name.startswith("esp_a1") for name in a2_names)
    assert any(name.startswith("esp_a1") for name in combined_names)
    assert any(name.startswith("esp_a2") for name in combined_names)
    assert set(path.name for path in (tmp_path / "models").glob("*.joblib")) == {"camera_a1.joblib", "camera_a2.joblib", "camera_a1_a2.joblib"}
    assert joblib.load(tmp_path / "models/camera_a1.joblib") is not None
    assert "locked external test was not evaluated" in (tmp_path / "cards/camera_a1.md").read_text(encoding="utf-8")

def test_build_is_reproducible(tmp_path):
    inputs = _fixture(tmp_path)
    first = _build(tmp_path, inputs)
    first_metrics = (tmp_path / "metrics.json").read_bytes()
    first_hashes = {path.name: sha256(path.read_bytes()).hexdigest()for path in (tmp_path / "models").glob("*.joblib")}

    second = _build(tmp_path, inputs)

    assert second == first
    assert (tmp_path / "metrics.json").read_bytes() == first_metrics
    assert {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / "models").glob("*.joblib")} == first_hashes

def test_rejects_baseline_drift_before_training(tmp_path):
    inputs = _fixture(tmp_path)
    inputs[3].write_text(inputs[3].read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(MultimodalBuildError, match="baseline metrics differ"):
        _build(tmp_path, inputs)

def test_rejects_seed_change(tmp_path):
    inputs = _fixture(tmp_path)
    config = json.loads(inputs[4].read_text(encoding="utf-8"))
    config["random_seed"] = 1
    _write_json(inputs[4], config)

    with pytest.raises(MultimodalBuildError, match="seed must remain 3070"):
        _build(tmp_path, inputs)