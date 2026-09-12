import json
from pathlib import Path
import pytest
from aria.dataset.source_inventory import (
    InventoryError,
    apply_approval_decisions,
    scan_source_sessions,
)

def _write_jsonl(path: Path, count: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join('{"record": 1}\n' for _ in range(count)), encoding="utf-8")

def _write_manifest(root: Path, session_id: str, *, kind="participant", status="completed", annotations=2):
    outputs = []
    for output_kind, name, count in (
        ("annotations", "annotations.jsonl", annotations),
        ("camera_features", "camera.jsonl", 3),
        ("telemetry_features", "esp.jsonl", 4),
    ):
        relative = f"sessions/{session_id}/{name}"
        _write_jsonl(root / relative, count)
        outputs.append({
            "kind": output_kind,
            "relative_path": relative,
            "observed_record_count": count + 1,
            "written_record_count": count,
            "excluded_record_count": 1,
            "gap_count": 0,
            "longest_gap_seconds": 0,
        })
    manifest = {
        "schema_version": 8,
        "session_id": session_id,
        "session_kind": kind,
        "status": status,
        "participant_ids": ["P0001"],
        "incident_ids": [],
        "configuration": {
            "collection_profile_id": "zone-a-collection-v7",
            "collection_profile_sha256": "a" * 64,
            "mask_config_version": "batamfast-v2",
            "mask_verified": True,
            "schema_versions": {"session_manifest": 8},
        },
        "outputs": outputs,
    }
    path = root / "manifests" / f"{session_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")

def test_scan_selects_only_completed_participant_sessions_with_annotations(tmp_path):
    _write_manifest(tmp_path, "included")
    _write_manifest(tmp_path, "aborted", status="aborted")
    _write_manifest(tmp_path, "pilot", kind="pilot")
    _write_manifest(tmp_path, "dry", kind="non_research_dry_run")
    _write_manifest(tmp_path, "empty", annotations=0)
    result = scan_source_sessions(tmp_path)

    assert [item["session_id"] for item in result["included_sessions"]] == ["included"]
    assert result["included_sessions"][0]["review_status"] == ("pending_user_validation")
    reasons = {item["session_id"]: item["exclusion_reason"]for item in result["excluded_sessions"]}
    assert reasons == {
        "aborted": "status_aborted",
        "dry": "session_kind_non_research_dry_run",
        "empty": "no_annotations",
        "pilot": "session_kind_pilot",
    }

def test_scan_reports_declared_and_physical_accounting_without_approving_it(tmp_path):
    _write_manifest(tmp_path, "included")

    result = scan_source_sessions(tmp_path)
    outputs = result["included_sessions"][0]["outputs"]

    assert all(item["review_status"] == "pending_user_validation" for item in outputs)
    assert all(item["checks"]["physical_count_equals_written"] for item in outputs)
    assert all(
        item["checks"]["observed_equals_written_plus_excluded"]
        for item in outputs
    )
    assert all(item["sha256"] for item in outputs)
    assert result["included_sessions"][0]["manifest_sha256"]

def test_incident_log_counts_only_incidents_linked_by_the_manifest(tmp_path):
    _write_manifest(tmp_path, "included")
    manifest_path = tmp_path / "manifests" / "included.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["incident_ids"] = ["incident_one"]
    manifest["outputs"].append({
        "kind": "incident_log",
        "relative_path": "incidents",
        "observed_record_count": 1,
        "written_record_count": 1,
        "excluded_record_count": 0,
        "gap_count": 0,
        "longest_gap_seconds": 0,
    })
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    incident_dir = tmp_path / "incidents"
    incident_dir.mkdir()
    (incident_dir / "incident_one.json").write_text("{}\n", encoding="utf-8")
    (incident_dir / "unrelated.json").write_text("{}\n", encoding="utf-8")

    result = scan_source_sessions(tmp_path)
    incident = next(
        item
        for item in result["included_sessions"][0]["outputs"]
        if item["kind"] == "incident_log"
    )

    assert incident["physical_record_count"] == 1
    assert incident["checks"]["physical_count_equals_written"] is True

def test_scan_rejects_output_paths_outside_data_raw(tmp_path):
    _write_manifest(tmp_path, "unsafe")
    path = tmp_path / "manifests" / "unsafe.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["outputs"][0]["relative_path"] = "../outside.jsonl"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(InventoryError, match="escapes data/raw"):
        scan_source_sessions(tmp_path)

def test_explicit_approval_updates_only_included_sessions(tmp_path):
    _write_manifest(tmp_path, "included")
    inventory = scan_source_sessions(tmp_path)
    approval_path = tmp_path / "approvals.json"
    approval_path.write_text(json.dumps({
        "schema_version": 1,
        "phase": "10.1",
        "decision_date_sgt": "2026-08-20",
        "decision_authority": "project_owner",
        "decisions": [{
            "session_id": "included",
            "decision": "approved",
            "conditions": ["preserve_gaps"],
        }],
    }), encoding="utf-8")

    apply_approval_decisions(inventory, approval_path)

    assert inventory["review_status"] == "approved"
    session = inventory["included_sessions"][0]
    assert session["review_status"] == "approved"
    assert session["approval"]["conditions"] == ["preserve_gaps"]
    assert all(output["review_status"] == "approved" for output in session["outputs"])