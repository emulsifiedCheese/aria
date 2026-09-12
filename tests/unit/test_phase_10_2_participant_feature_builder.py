import json
from hashlib import sha256
from pathlib import Path
import pytest
from aria.dataset.participant_feature_builder import (
    ParticipantFeatureBuildError,
    build_participant_features,
)
from aria.dataset.dataset_audit import DatasetAuditError, audit_phase_10_2_dataset
PROJECT_ROOT = Path(__file__).resolve().parents[2]

def camera_record(timestamp, frame_number=1, track_id=7):
    return {
        "schema_version": 2,
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": frame_number,
        "frame_timestamp_sgt": timestamp,
        "frame_available": True,
        "pose_available": True,
        "local_track_id": track_id,
        "bounding_box": [10, 20, 110, 220],
        "detection_confidence": 0.8,
        "keypoints": [[float(i * 10), float(i * 5)] for i in range(17)],
        "keypoint_confidences": [0.9] * 17,
        "capture_latency_ms": 10.0,
        "detection_latency_ms": 20.0,
        "pose_latency_ms": 30.0,
        "total_latency_ms": 60.0,
        "mask_config_version": "batamfast-v2",
    }

def sensor_record(node_id, timestamp):
    payload = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC",
        "boot_id": 123,
        "node_id": node_id,
        "zone": "A",
        "sequence": 1,
        "timestamp_ms": 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": False,
        "pir_recent_activity": True,
        "audio_peak_to_peak": 11,
        "audio_activity": 3,
        "audio_rms": 5,
    }
    if node_id == "ESP-A1":
        payload.update(distance_cm=51, distance_valid=True)
    return {
        "received_at_sgt": timestamp,
        "source_ip": "127.0.0.1",
        "source_port": 4210 if node_id == "ESP-A1" else 4211,
        "payload": payload,
    }

def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

def _fixture(tmp_path, *, include_selected_track=True):
    session_id = "zone_a_20260820T100000SGT_test0001"
    raw = tmp_path / "raw"
    session_dir = raw / "sessions" / session_id
    cameras = [
        camera_record("2026-08-20T10:00:00.250+08:00", track_id=8),
    ]
    if include_selected_track:
        cameras.append(
            camera_record(
                "2026-08-20T10:00:00.500+08:00", frame_number=2, track_id=7
            )
        )
    _write_jsonl(session_dir / "camera_a_records.jsonl", cameras)
    _write_jsonl(session_dir / "esp_packets.jsonl", [
        sensor_record("ESP-A1", "2026-08-20T10:00:00.400+08:00"),
        sensor_record("ESP-A2", "2026-08-20T10:00:01.400+08:00"),
    ])
    manifest_path = raw / "manifests" / f"{session_id}.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n", encoding="utf-8")
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps({
        "review_status": "approved",
        "included_sessions": [{
            "session_id": session_id,
            "review_status": "approved",
            "manifest_relative_path": f"manifests/{session_id}.json",
            "manifest_sha256": "a" * 64,
            "configuration": {
                "collection_profile_id": "zone-a-collection-v7",
                "collection_profile_sha256": "b" * 64,
                "mask_config_version": "batamfast-v2",
                "schema_versions": {
                    "camera_track": 2,
                    "esp_packet": 1,
                    "feature_vector": 2
                }
            }
        }]
    }), encoding="utf-8")
    annotations_path = tmp_path / "annotations.jsonl"
    _write_jsonl(annotations_path, [{
        "schema_version": 1,
        "session_id": session_id,
        "participant_id": "P0001",
        "local_track_id": 7,
        "window_id": "zone_a_1787191200000_2000",
        "window_start_sgt": "2026-08-20T10:00:00.000+08:00",
        "window_end_sgt": "2026-08-20T10:00:02.000+08:00",
        "source_annotation_id": "annotation_test0001",
        "source_annotation_schema_version": 3,
        "source_activity": "Serving/Processing",
        "derived_activity": "Serving/Processing",
        "source_label_status": "labelled",
        "source_exclusion_reason": None,
        "track_present": True,
        "incident_affected": False,
        "usable_for_modelling": True,
        "phase_10_exclusion_reason": None,
    }])
    normalised_hash = sha256(annotations_path.read_bytes()).hexdigest()
    normalisation_report = tmp_path / "normalisation_report.json"
    normalisation_report.write_text(json.dumps({
        "status": "complete",
        "normalised_output_sha256": normalised_hash,
        "usable_windows": 1,
    }), encoding="utf-8")
    return raw, inventory_path, annotations_path, normalisation_report

def _build(tmp_path, **fixture_options):
    raw, inventory, annotations, report = _fixture(tmp_path, **fixture_options)
    output = tmp_path / "features.jsonl"
    result = build_participant_features(
        data_raw_dir=raw,
        inventory_path=inventory,
        normalised_annotations_path=annotations,
        normalisation_report_path=report,
        output_path=output,
        report_path=tmp_path / "feature_report.json",
        schema_path=PROJECT_ROOT / "schemas" / "phase_10_2_participant_feature.schema.json",
        feature_schema_path=PROJECT_ROOT / "schemas" / "feature_vector.schema.json",
    )
    return result, json.loads(output.read_text(encoding="utf-8"))

def test_builds_track_specific_camera_and_shared_sensor_features(tmp_path):
    report, row = _build(tmp_path)

    assert report["row_count"] == 1
    assert row["local_track_id"] == 7
    assert row["feature_vector"]["camera"]["track_record_count"] == 1
    assert row["feature_vector"]["camera"]["unique_track_count"] == 1
    assert row["feature_vector"]["esp_a1"]["packet_count"] == 1
    assert row["feature_vector"]["esp_a2"]["packet_count"] == 1
    assert "distance_cm_mean" not in row["feature_vector"]["esp_a2"]

def test_fails_closed_when_selected_track_is_absent(tmp_path):
    with pytest.raises(ParticipantFeatureBuildError, match="no selected-track"):
        _build(tmp_path, include_selected_track=False)

def test_fails_closed_when_normalised_hash_changes(tmp_path):
    raw, inventory, annotations, report = _fixture(tmp_path)
    annotations.write_text(annotations.read_text() + "\n", encoding="utf-8")

    with pytest.raises(ParticipantFeatureBuildError, match="hash mismatch"):
        build_participant_features(
            data_raw_dir=raw,
            inventory_path=inventory,
            normalised_annotations_path=annotations,
            normalisation_report_path=report,
            output_path=tmp_path / "features.jsonl",
            report_path=tmp_path / "feature_report.json",
        )

def _built_audit_fixture(tmp_path):
    raw, inventory, annotations, normalisation_report = _fixture(tmp_path)
    feature_path = tmp_path / "features.jsonl"
    build_report_path = tmp_path / "feature_report.json"
    build_participant_features(
        data_raw_dir=raw,
        inventory_path=inventory,
        normalised_annotations_path=annotations,
        normalisation_report_path=normalisation_report,
        output_path=feature_path,
        report_path=build_report_path,
    )
    normalisation = json.loads(normalisation_report.read_text(encoding="utf-8"))
    normalisation["total_windows"] = 1
    normalisation_report.write_text(json.dumps(normalisation), encoding="utf-8")
    return feature_path, build_report_path, annotations, normalisation_report

def _audit(tmp_path, feature_path, build_report, annotations, normalisation_report):
    return audit_phase_10_2_dataset(
        feature_path=feature_path,
        build_report_path=build_report,
        normalised_annotations_path=annotations,
        normalisation_report_path=normalisation_report,
        exclusion_ledger_path=tmp_path / "exclusions.jsonl",
        audit_report_path=tmp_path / "audit.json",
    )

def test_quality_and_privacy_audit_passes_schema_valid_dataset(tmp_path):
    inputs = _built_audit_fixture(tmp_path)

    report = _audit(tmp_path, *inputs)

    assert report["status"] == "pass"
    assert report["reconciliation"]["balances"] is True
    assert report["privacy_audit"]["passed"] is True

def test_audit_rejects_same_track_assigned_to_two_participants(tmp_path):
    feature_path, build_report_path, annotations, normalisation_report = (_built_audit_fixture(tmp_path))
    first = json.loads(feature_path.read_text(encoding="utf-8"))
    second = json.loads(json.dumps(first))
    second["participant_id"] = "P0002"
    second["episode_id"] = "episode_1111111111111111"
    _write_jsonl(feature_path, [first, second])
    build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
    build_report["row_count"] = 2
    build_report["participant_feature_output_sha256"] = sha256(feature_path.read_bytes()).hexdigest()
    build_report_path.write_text(json.dumps(build_report), encoding="utf-8")

    with pytest.raises(DatasetAuditError, match="conflicting participant/track"):
        _audit(
            tmp_path,
            feature_path,
            build_report_path,
            annotations,
            normalisation_report,
        )