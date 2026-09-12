import json
from copy import deepcopy
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "session_manifest.schema.json"

@pytest.fixture(scope="module")
def validator():
    with SCHEMA_PATH.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

@pytest.fixture
def planned_manifest():
    return {
        "schema_version": 8,
        "session_id": "zone_a_20260731T170000SGT_dryrun01",
        "zone": "A",
        "study_scope": "consenting_counter_agents",
        "session_kind": "non_research_dry_run",
        "status": "planned",
        "participant_ids": [],
        "participant_additions": [],
        "created_at_sgt": "2026-07-31T17:00:00+08:00",
        "started_at_sgt": None,
        "ended_at_sgt": None,
        "configuration": {
            "camera_id": "camera_a",
            "capture_width_px": 1920,
            "capture_height_px": 1080,
            "capture_fps": 30,
            "mask_config_version": "batamfast-v1",
            "mask_verified": True,
            "collection_profile_id": None,
            "collection_profile_sha256": None,
            "esp_nodes": ["ESP-A1", "ESP-A2"],
            "schema_versions": {
                "session_manifest": 8,
                "esp_packet": 1,
                "camera_track": 2,
                "feature_vector": 2,
                "annotation": 3,
                "prediction": 3,
                "incident": 5,
            },
        },
        "preflight": {
            "checked_at_sgt": None,
            "consent_and_acknowledgement_confirmed": False,
            "camera_identity_and_mode_confirmed": False,
            "privacy_mask_verified": False,
            "audio_capture_disabled": False,
            "esp_a1_fresh": False,
            "esp_a2_fresh": False,
            "storage_ready": False,
        },
        "outputs": [],
        "incident_ids": [],
    }

def assert_invalid(validator, manifest):
    with pytest.raises(ValidationError):
        validator.validate(manifest)

def test_planned_non_research_manifest_is_valid(validator, planned_manifest):
    validator.validate(planned_manifest)

def test_retired_manifest_version_one_is_rejected(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["schema_version"] = 1
    assert_invalid(validator, manifest)
    manifest = deepcopy(planned_manifest)
    manifest["configuration"]["schema_versions"]["session_manifest"] = 1
    assert_invalid(validator, manifest)

def test_running_manifest_requires_successful_preflight(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["status"] = "running"
    manifest["started_at_sgt"] = "2026-07-31T17:05:00+08:00"
    assert_invalid(validator, manifest)
    manifest["preflight"] = {key: True for key in manifest["preflight"] if key != "checked_at_sgt"} | {"checked_at_sgt": "2026-07-31T17:04:00+08:00"}
    validator.validate(manifest)

def test_participant_session_requires_pseudonymised_id(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["session_kind"] = "participant"
    manifest["participant_ids"] = ["Counter Agent Alice"]
    assert_invalid(validator, manifest)
    manifest["participant_ids"] = ["P0001"]
    manifest["configuration"]["collection_profile_id"] = "zone-a-collection-v7"
    manifest["configuration"]["collection_profile_sha256"] = "a" * 64
    validator.validate(manifest)

def test_manifest_records_only_consent_confirmed_participant_additions(
    validator, planned_manifest
):
    manifest = deepcopy(planned_manifest)
    manifest["session_kind"] = "participant"
    manifest["participant_ids"] = ["P0001", "P0002"]
    manifest["participant_additions"] = [{
        "participant_id": "P0002",
        "added_at_sgt": "2026-07-31T17:10:00+08:00",
        "consent_confirmed": True,
        "added_by_annotator_id": "A001",
    }]
    manifest["configuration"]["collection_profile_id"] = "zone-a-collection-v6"
    manifest["configuration"]["collection_profile_sha256"] = "a" * 64
    validator.validate(manifest)
    manifest["participant_additions"][0]["consent_confirmed"] = False
    assert_invalid(validator, manifest)

def test_formal_session_requires_frozen_collection_profile(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["session_kind"] = "pilot"
    manifest["participant_ids"] = ["P0001"]
    assert_invalid(validator, manifest)

@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("configuration", "camera_id"), "camera_b"),
        (("configuration", "mask_verified"), False),
        (("configuration", "esp_nodes"), ["ESP-A1", "ESP-B"]),
    ],
)
def test_retired_or_unverified_deployment_configuration_is_rejected(
    validator, planned_manifest, path, value
):
    manifest = deepcopy(planned_manifest)
    manifest[path[0]][path[1]] = value
    assert_invalid(validator, manifest)

def test_unknown_identity_field_is_rejected(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["participant_name"] = "Example Person"
    assert_invalid(validator, manifest)

def test_raw_media_output_kind_is_rejected(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["outputs"] = [{"kind": "raw_video", "relative_path": "data/raw/session.mp4"}]
    assert_invalid(validator, manifest)

def test_completed_manifest_requires_output_accounting(validator, planned_manifest):
    manifest = deepcopy(planned_manifest)
    manifest["status"] = "completed"
    manifest["started_at_sgt"] = "2026-07-31T17:05:00+08:00"
    manifest["ended_at_sgt"] = "2026-07-31T17:35:00+08:00"
    manifest["preflight"] = {key: True for key in manifest["preflight"] if key != "checked_at_sgt"} | {"checked_at_sgt": "2026-07-31T17:04:00+08:00"}
    assert_invalid(validator, manifest)

    manifest["outputs"] = [
        {
            "kind": "multimodal_windows",
            "relative_path": "windows/session.jsonl",
            "observed_record_count": 900,
            "written_record_count": 888,
            "excluded_record_count": 12,
            "gap_count": 2,
            "longest_gap_seconds": 1.25,
        }
    ]
    validator.validate(manifest)

def test_output_accounting_rejects_parent_paths_and_negative_counts(
    validator, planned_manifest
):
    output = {
        "kind": "predictions",
        "relative_path": "../predictions.jsonl",
        "observed_record_count": 5,
        "written_record_count": 5,
        "excluded_record_count": 0,
        "gap_count": 0,
        "longest_gap_seconds": 0,
    }
    manifest = deepcopy(planned_manifest)
    manifest["outputs"] = [output]
    assert_invalid(validator, manifest)

    manifest["outputs"][0]["relative_path"] = "predictions.jsonl"
    manifest["outputs"][0]["written_record_count"] = -1
    assert_invalid(validator, manifest)

@pytest.mark.parametrize("schema_name", ["annotation", "prediction", "incident"])
def test_collection_schema_versions_are_required_and_locked(validator, planned_manifest, schema_name):
    manifest = deepcopy(planned_manifest)
    del manifest["configuration"]["schema_versions"][schema_name]
    assert_invalid(validator, manifest)

    manifest = deepcopy(planned_manifest)
    current_version = manifest["configuration"]["schema_versions"][schema_name]
    manifest["configuration"]["schema_versions"][schema_name] = current_version + 1
    assert_invalid(validator, manifest)
