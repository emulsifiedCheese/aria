import json
from pathlib import Path
import pytest
from aria.dataset.annotation_normalizer import (
    AnnotationNormalisationError,
    normalise_approved_annotations,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

def _fixture(tmp_path, *, duplicate=False, conflicting_participant=False):
    session_id = "zone_a_20260820T100000SGT_test0001"
    window_ids = ["zone_a_1787191200000_2000", "zone_a_1787191202000_2000"]
    annotation = {
        "schema_version": 2,
        "annotation_id": "annotation_test0001",
        "session_id": session_id,
        "zone": "A",
        "participant_id": "P0001",
        "local_track_id": 7,
        "window_ids": window_ids,
        "interval_start_sgt": "2026-08-20T10:00:00+08:00",
        "interval_end_sgt": "2026-08-20T10:00:04+08:00",
        "label_status": "labelled",
        "activity": "Typing/Processing",
        "exclusion_reason": None,
        "usable_for_modelling": True,
        "annotator_id": "A001",
        "created_at_sgt": "2026-08-20T10:00:04+08:00",
    }
    annotations = [annotation]
    if duplicate:
        second = dict(annotation)
        second["annotation_id"] = "annotation_test0002"
        annotations.append(second)
    if conflicting_participant:
        second = dict(annotation)
        second["annotation_id"] = "annotation_test0003"
        second["participant_id"] = "P0002"
        annotations.append(second)
    session_dir = tmp_path / "raw" / "sessions" / session_id
    _write_jsonl(session_dir / "annotations.jsonl", annotations)
    camera_records = [{
        "record_type": "track",
        "frame_timestamp_sgt": "2026-08-20T10:00:00.500+08:00",
        "local_track_id": 7,
    }]
    if conflicting_participant:
        camera_records.append({
            "record_type": "track",
            "frame_timestamp_sgt": "2026-08-20T10:00:02.500+08:00",
            "local_track_id": 7,
        })
    _write_jsonl(session_dir / "camera_a_records.jsonl", camera_records)
    manifest_path = tmp_path / "raw" / "manifests" / f"{session_id}.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps({
        "session_id": session_id,
        "participant_ids": ["P0001", "P0002"],
        "started_at_sgt": "2026-08-20T10:00:00+08:00",
        "ended_at_sgt": "2026-08-20T10:01:00+08:00",
    }), encoding="utf-8")
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps({
        "review_status": "approved",
        "included_sessions": [{
            "session_id": session_id,
            "review_status": "approved",
            "manifest_relative_path": f"manifests/{session_id}.json",
            "incident_ids": [],
        }],
    }), encoding="utf-8")
    return inventory_path

def test_normalises_historical_label_and_excludes_absent_track_window(tmp_path):
    inventory = _fixture(tmp_path)
    output = tmp_path / "normalised.jsonl"
    report = normalise_approved_annotations(
        data_raw_dir=tmp_path / "raw",
        inventory_path=inventory,
        output_path=output,
        report_path=tmp_path / "report.json",
        schema_dir=PROJECT_ROOT / "schemas",
    )

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert records[0]["derived_activity"] == "Serving/Processing"
    assert records[0]["usable_for_modelling"] is True
    assert records[1]["phase_10_exclusion_reason"] == "selected_track_absent"
    assert records[1]["usable_for_modelling"] is False
    assert report["usable_windows"] == 1
    assert report["newly_excluded_track_absent_windows"] == 1
    assert report["source_annotation_schema_counts"] == {"2": 1}

def test_rejects_overlapping_annotations_for_same_participant_window(tmp_path):
    inventory = _fixture(tmp_path, duplicate=True)

    with pytest.raises(AnnotationNormalisationError, match="overlapping"):
        normalise_approved_annotations(
            data_raw_dir=tmp_path / "raw",
            inventory_path=inventory,
            output_path=tmp_path / "normalised.jsonl",
            report_path=tmp_path / "report.json",
            schema_dir=PROJECT_ROOT / "schemas",
        )

def test_excludes_both_participants_when_one_track_is_assigned_to_both(tmp_path):
    inventory = _fixture(tmp_path, conflicting_participant=True)
    output = tmp_path / "normalised.jsonl"

    report = normalise_approved_annotations(
        data_raw_dir=tmp_path / "raw",
        inventory_path=inventory,
        output_path=output,
        report_path=tmp_path / "report.json",
        schema_dir=PROJECT_ROOT / "schemas",
    )

    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert all(record["usable_for_modelling"] is False for record in records)
    assert all(
        record["phase_10_exclusion_reason"] == "conflicting_track_assignment"
        for record in records
    )
    assert report["conflicting_track_assignment_group_count"] == 2
    assert report["newly_excluded_conflicting_track_assignment_windows"] == 4