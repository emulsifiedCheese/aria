import json
from hashlib import sha256
from pathlib import Path
import joblib
import pytest
from aria.modeling.baselines import BaselineBuildError, build_phase_11_1_baselines

SESSIONS = (
    "zone_a_20260805T122850SGT_69d79165",
    "zone_a_20260805T154439SGT_22e7eefd",
    "zone_a_20260805T165946SGT_0d343330",
)
EXTERNAL_SESSION = "zone_a_20260804T184322SGT_b12c640c"
LABELS = ("Serving/Processing", "Idle/Waiting", "Reaching/Handling")

def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),encoding="utf-8",)

def _sensor(value, a1):
    sensor = {
        "available": True,
        "packet_count": 2,
        "expected_packet_count": 2,
        "missing_packet_count": 0,
        "sequence_gap_count": 0,
        "pir_motion_ratio": value,
        "pir_recent_activity_ratio": value,
        "audio_peak_to_peak_mean": value * 10,
        "audio_activity_mean": value * 5,
        "audio_rms_mean": value * 3,
        "audio_rms_min": value * 2,
        "audio_rms_max": value * 4,
        "wifi_rssi_dbm_mean": -60 + value,
        "timing": {
            "interval_count": 1,
            "mean_interval_ms": 1000,
            "interval_std_ms": 0,
            "mean_absolute_jitter_ms": 0,
        },
    }
    if a1:
        sensor.update({
            "distance_valid_ratio": 1,
            "distance_cm_mean": 100 + value,
            "distance_cm_min": 99 + value,
            "distance_cm_max": 101 + value,
        })
    return sensor

def _camera(value):
    return {
        "available": True,
        "record_count": 10,
        "frame_count": 10,
        "available_frame_count": 10,
        "unavailable_frame_count": 0,
        "frame_number_gap_count": 0,
        "track_record_count": 10,
        "unique_track_count": 1,
        "pose_available_count": 10,
        "pose_missing_count": 0,
        "pose_availability_ratio": 1,
        "bbox_center_x_mean_px": 100 + value,
        "bbox_center_y_mean_px": 200 + value,
        "detection_confidence_mean": 0.8,
        "keypoint_confidence_mean": 0.7,
        "joint_angle_mean_degrees": 90 + value,
        "movement_speed_mean_px_per_second": value * 10,
        "timing": {
            "interval_count": 9,
            "mean_interval_ms": 100,
            "interval_std_ms": 1,
            "mean_absolute_jitter_ms": 1,
        },
    }

def _feature_row(session, participant, window, activity, value):
    return {
        "schema_version": 1,
        "dataset_version": "zone-a-phase10-features-v1",
        "episode_id": f"episode_{window:016x}",
        "session_id": session,
        "participant_id": participant,
        "local_track_id": 1,
        "source_annotation_id": f"annotation-{window}",
        "activity": activity,
        "provenance": {},
        "feature_vector": {
            "window_id": f"zone_a_{window}_2000",
            "camera_available": True,
            "pose_available": True,
            "a1_available": True,
            "a2_available": True,
            "camera": _camera(value),
            "esp_a1": _sensor(value, True),
            "esp_a2": _sensor(value, False),
        },
    }

def _fixture(tmp_path):
    rows = []
    assignments = []
    values = (
        (0, 0), (0, 1), (0, 2),
        (1, 0), (1, 1), (1, 2),
        (2, 0), (2, 1), (2, 2),
    )
    for index, (fold_index, label_index) in enumerate(values, 1):
        row = _feature_row(SESSIONS[fold_index], "P0001", 1000 + index, LABELS[label_index], label_index + 0.1,)
        rows.append(row)
        assignments.append({
            "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
            "partition": "development",
            "validation_fold_id": f"fold_{fold_index + 1:02d}",
            "session_id": row["session_id"],
            "participant_id": row["participant_id"],
            "window_id": row["feature_vector"]["window_id"],
        })
    external = _feature_row(EXTERNAL_SESSION, "P0009", 2000, LABELS[0], 9.9)
    rows.append(external)
    assignments.append({
        "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
        "partition": "external_test",
        "validation_fold_id": None,
        "session_id": external["session_id"],
        "participant_id": external["participant_id"],
        "window_id": external["feature_vector"]["window_id"],
    })

    feature_path = tmp_path / "features.jsonl"
    manifest_path = tmp_path / "manifest.jsonl"
    audit_path = tmp_path / "audit.json"
    config_path = tmp_path / "config.json"
    _write_jsonl(feature_path, rows)
    _write_jsonl(manifest_path, assignments)
    _write_json(audit_path, {"status": "pass"})
    _write_json(config_path, {
        "schema_version": 1,
        "config_id": "zone-a-phase11.1-baselines-v1",
        "split_policy_id": "zone-a-phase10.3-external-test-loso-v1",
        "random_seed": 3070,
        "selection_metric": "macro_f1",
        "class_labels": list(LABELS),
        "feature_sets": {
            "camera_only": ["camera_available", "pose_available", "camera"],
            "a1_only": ["a1_available", "esp_a1"],
            "a1_a2": ["a1_available", "a2_available", "esp_a1", "esp_a2"],
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
    })
    return feature_path, manifest_path, audit_path, config_path

def _build(tmp_path, inputs):
    return build_phase_11_1_baselines(
        feature_path=inputs[0],
        split_manifest_path=inputs[1],
        split_audit_path=inputs[2],
        config_path=inputs[3],
        metrics_path=tmp_path / "metrics.json",
        model_dir=tmp_path / "models",
        model_card_dir=tmp_path / "cards",
    )

def test_builds_four_development_only_baselines_and_artifacts(tmp_path):
    report = _build(tmp_path, _fixture(tmp_path))

    assert report["status"] == "complete_development_only"
    assert report["development"]["row_count"] == 9
    assert report["external_test"] == {
        "evaluated": False,
        "row_count": 1,
        "reason": "reserved for one final Phase 11 evaluation after model selection",
    }
    assert set(report["baselines"]) == {"majority", "camera_only", "a1_only", "a1_a2"}
    assert all(len(result["folds"]) == 3 for result in report["baselines"].values())
    assert not any(name.startswith("esp_a1") for name in report["baselines"]["camera_only"]["feature_names"])
    assert any(name.startswith("esp_a2") for name in report["baselines"]["a1_a2"]["feature_names"])
    assert set(path.name for path in (tmp_path / "models").glob("*.joblib")) == {"majority.joblib", "camera_only.joblib", "a1_only.joblib", "a1_a2.joblib"}
    assert joblib.load(tmp_path / "models/camera_only.joblib") is not None
    assert "locked external test was not evaluated" in (tmp_path / "cards/camera_only.md").read_text(encoding="utf-8")

def test_build_is_reproducible(tmp_path):
    inputs = _fixture(tmp_path)
    first = _build(tmp_path, inputs)
    first_metrics = (tmp_path / "metrics.json").read_bytes()
    first_models = {path.name: sha256(path.read_bytes()).hexdigest() for path in (tmp_path / "models").glob("*.joblib")}
    second = _build(tmp_path, inputs)
    assert second == first
    assert (tmp_path / "metrics.json").read_bytes() == first_metrics
    assert {path.name: sha256(path.read_bytes()).hexdigest() for path in (tmp_path / "models").glob("*.joblib")} == first_models

def test_rejects_source_drift_before_training(tmp_path):
    inputs = _fixture(tmp_path)
    inputs[0].write_text(inputs[0].read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(BaselineBuildError, match="source hashes differ"):
        _build(tmp_path, inputs)