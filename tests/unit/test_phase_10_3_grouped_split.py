import json
from hashlib import sha256
from pathlib import Path
import pytest
from aria.dataset.grouped_split import (
    GroupedSplitError,
    audit_phase_10_3_splits,
    build_phase_10_3_splits,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_SESSION = "zone_a_20260804T184322SGT_b12c640c"
DEVELOPMENT_SESSION_1 = "zone_a_20260805T122850SGT_69d79165"
DEVELOPMENT_SESSION_2 = "zone_a_20260805T154439SGT_22e7eefd"

def _write_jsonl(path, rows):
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )

def _row(session_id, participant_id, window_number, episode_number, activity):
    return {
        "schema_version": 1,
        "dataset_version": "zone-a-phase10-features-v1",
        "episode_id": f"episode_{episode_number:016x}",
        "session_id": session_id,
        "participant_id": participant_id,
        "local_track_id": 1,
        "source_annotation_id": f"annotation-{session_id}-{participant_id}",
        "activity": activity,
        "provenance": {},
        "feature_vector": {
            "window_id": f"zone_a_{window_number}_2000",
            "camera_available": True,
            "pose_available": True,
            "a1_available": True,
            "a2_available": True,
        },
    }

def _fixture(tmp_path, external_participant_in_development=False):
    rows = [
        _row(EXTERNAL_SESSION, "P0009", 1000, 1, "Idle/Waiting"),
        _row(
            DEVELOPMENT_SESSION_1,
            "P0009" if external_participant_in_development else "P0001",
            2000,
            2,
            "Serving/Processing",
        ),
        _row(
            DEVELOPMENT_SESSION_2,
            "P0001",
            3000,
            3,
            "Reaching/Handling",
        ),
    ]
    feature_path = tmp_path / "features.jsonl"
    _write_jsonl(feature_path, rows)
    feature_hash = sha256(feature_path.read_bytes()).hexdigest()
    dataset_audit_path = tmp_path / "dataset_audit.json"
    dataset_audit_path.write_text(json.dumps({
        "status": "pass",
        "participant_feature_sha256": feature_hash,
        "quality_audit": {"row_count": len(rows)},
    }, sort_keys=True), encoding="utf-8")
    audit_hash = sha256(dataset_audit_path.read_bytes()).hexdigest()
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps({
        "schema_version": 1,
        "policy_id": "zone-a-phase10.3-external-test-loso-v1",
        "dataset_version": "zone-a-phase10-features-v1",
        "expected_source_dataset_sha256": feature_hash,
        "expected_source_audit_sha256": audit_hash,
        "external_test": {
            "session_ids": [EXTERNAL_SESSION],
            "participant_ids": ["P0009"],
            "access_rule": "final_evaluation_only",
            "selection_rule": "predeclared_disconnected_participant_session_component",
        },
        "development_validation": {
            "method": "leave_one_session_out",
            "fold_sessions": {
                "fold_01": DEVELOPMENT_SESSION_1,
                "fold_02": DEVELOPMENT_SESSION_2,
            },
        },
        "grouping_rules": {
            "external_participant_isolation": True,
            "external_session_isolation": True,
            "episode_integrity": True,
            "temporal_window_integrity": True,
            "development_validation_session_isolation": True,
            "development_validation_participant_isolation": False,
        },
    }, sort_keys=True), encoding="utf-8")
    return feature_path, dataset_audit_path, policy_path

def _build(tmp_path, inputs):
    manifest_path = tmp_path / "manifest.jsonl"
    build_report_path = tmp_path / "build_report.json"
    report = build_phase_10_3_splits(
        feature_path=inputs[0],
        dataset_audit_path=inputs[1],
        policy_path=inputs[2],
        manifest_path=manifest_path,
        build_report_path=build_report_path,
        schema_path=PROJECT_ROOT / "schemas" / "phase_10_3_split_assignment.schema.json",
    )
    return report, manifest_path, build_report_path

def test_builds_locked_external_test_and_loso_development_folds(tmp_path):
    inputs = _fixture(tmp_path)
    report, manifest_path, build_report_path = _build(tmp_path, inputs)

    assert report["row_count"] == 3
    assert report["partition_summary"]["development"]["row_count"] == 2
    assert report["partition_summary"]["external_test"]["row_count"] == 1
    assert report["development_cross_validation"]["fold_count"] == 2

    audit = audit_phase_10_3_splits(
        feature_path=inputs[0],
        dataset_audit_path=inputs[1],
        policy_path=inputs[2],
        manifest_path=manifest_path,
        build_report_path=build_report_path,
        audit_report_path=tmp_path / "split_audit.json",
    )

    assert audit["status"] == "pass"
    assert all(audit["leakage_checks"].values())
    assert audit["reconciliation"]["balances"] is True

def test_build_is_deterministic(tmp_path):
    inputs = _fixture(tmp_path)
    _, manifest_path, _ = _build(tmp_path, inputs)
    first_hash = sha256(manifest_path.read_bytes()).hexdigest()
    _, manifest_path, _ = _build(tmp_path, inputs)
    assert sha256(manifest_path.read_bytes()).hexdigest() == first_hash

def test_rejects_external_participant_in_development(tmp_path):
    inputs = _fixture(tmp_path, external_participant_in_development=True)

    with pytest.raises(GroupedSplitError, match="participant appears in development"):
        _build(tmp_path, inputs)

def test_rejects_source_dataset_drift(tmp_path):
    inputs = _fixture(tmp_path)
    inputs[0].write_text(inputs[0].read_text() + "\n", encoding="utf-8")

    with pytest.raises(GroupedSplitError, match="feature hash differs"):
        _build(tmp_path, inputs)

def test_audit_rejects_fold_assignment_drift(tmp_path):
    inputs = _fixture(tmp_path)
    _, manifest_path, build_report_path = _build(tmp_path, inputs)
    assignments = [
        json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()
    ]
    for assignment in assignments:
        if assignment["validation_fold_id"] == "fold_01":
            assignment["validation_fold_id"] = "fold_02"
    _write_jsonl(manifest_path, assignments)
    build_report = json.loads(build_report_path.read_text(encoding="utf-8"))
    build_report["manifest_sha256"] = sha256(manifest_path.read_bytes()).hexdigest()
    build_report_path.write_text(
        json.dumps(build_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    with pytest.raises(GroupedSplitError, match="leakage audit failed"):
        audit_phase_10_3_splits(
            feature_path=inputs[0],
            dataset_audit_path=inputs[1],
            policy_path=inputs[2],
            manifest_path=manifest_path,
            build_report_path=build_report_path,
            audit_report_path=tmp_path / "split_audit.json",
        )