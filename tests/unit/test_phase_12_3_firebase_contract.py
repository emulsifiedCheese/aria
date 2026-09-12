import json
from hashlib import sha256
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_3_firebase.json"
CONFIG_SHA256 = "48e3cb907c7586e43dcf9bc956331408df557c739c2e1f581b55e30b2bbb2afb"

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def _validator():
    config = _config()
    schema = json.loads(
        (PROJECT_ROOT / config["inputs"]["firebase_prediction_schema_path"])
        .read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _available_record():
    return {
        "schema_version": 1,
        "prediction_id": "prediction_firebasecontract01",
        "emitted_at_sgt": "2026-08-24T18:00:00+08:00",
        "uploaded_at_sgt": "2026-08-24T18:00:01+08:00",
        "zone": "A",
        "model_version": "zone-a-camera-only-rf-v1",
        "preprocessing_version": "zone-a-phase12.1-single-track-window-v1",
        "prediction_available": True,
        "predicted_activity": "Serving/Processing",
        "confidence": 0.72,
        "availability": {
            "camera_available": True,
            "pose_available": True,
            "esp_a1_available": True,
            "esp_a2_available": True,
        },
    }

def test_phase_12_3_contract_is_frozen_and_required():
    config = _config()

    assert _sha256(CONFIG_PATH) == CONFIG_SHA256
    assert config["config_id"] == "zone-a-phase12.3-firebase-v1"
    assert config["status"] == "frozen_before_implementation"
    assert config["scope"] == {
        "zone": "A",
        "firebase_required_for_final_product": True,
        "participant_collection_allowed": False,
        "participant_upload_authorized": False,
        "accepted_development_input_scopes": ["synthetic", "non_research"],
        "cloud_retraining_allowed": False,
        "cloud_model_weight_updates_allowed": False,
    }

def test_contract_pins_database_and_existing_local_boundary():
    config = _config()
    firebase = config["firebase"]
    inputs = config["inputs"]

    assert firebase["product"] == "realtime_database"
    assert firebase["project_id"] == "aria-e906f"
    assert firebase["database_region"] == "asia-southeast1"
    assert firebase["database_url"] == ("https://aria-e906f-default-rtdb.asia-southeast1.firebasedatabase.app")
    assert firebase["root_path"] == "aria/schema_version_1"
    assert firebase["firestore_allowed"] is False
    assert firebase["storage_product_allowed"] is False

    for path_key, hash_key in (
        ("inference_contract_path", "inference_contract_sha256"),
        ("prediction_schema_path", "prediction_schema_sha256"),
        ("firebase_prediction_schema_path", "firebase_prediction_schema_sha256"),
        ("database_rules_path", "database_rules_sha256"),
    ):
        assert _sha256(PROJECT_ROOT / inputs[path_key]) == inputs[hash_key]

def test_firebase_schema_accepts_available_and_unavailable_summaries():
    validator = _validator()
    available = _available_record()
    validator.validate(available)

    unavailable = _available_record()
    unavailable["prediction_available"] = False
    unavailable.pop("predicted_activity")
    unavailable.pop("confidence")
    unavailable["unavailable_reason"] = "missing_camera_track"
    validator.validate(unavailable)

def test_firebase_schema_rejects_identifying_or_track_fields():
    validator = _validator()

    for field, value in (
        ("session_id", "zone_a_20260824T180000SGT_demo0001"),
        ("window_id", "zone_a_1787565600000_1787565602000"),
        ("local_track_id", 1),
        ("participant_id", "participant_demo"),
        ("feature_vector", [0.1, 0.2]),
        ("raw_video", "forbidden"),
    ):
        record = _available_record()
        record[field] = value
        with pytest.raises(ValidationError):
            validator.validate(record)

def test_contract_downscopes_credentials_and_keeps_secrets_out_of_config():
    authentication = _config()["authentication"]

    assert authentication == {
        "sdk": "firebase_admin_python",
        "credential_environment_variable": "ARIA_FIREBASE_CREDENTIALS",
        "credential_path_in_config_allowed": False,
        "credential_contents_in_logs_allowed": False,
        "credential_file_in_repository_allowed": False,
        "database_auth_variable_override": {"uid": "aria-phase12-3-sync"},
        "unrestricted_admin_access_allowed": False,
    }
    serialized = CONFIG_PATH.read_text(encoding="utf-8")
    assert "private_key" not in serialized
    assert "client_email" not in serialized

def test_contract_freezes_non_blocking_durable_delivery():
    delivery = _config()["delivery"]

    assert delivery["firebase_failure_blocks_inference"] is False
    assert delivery["firebase_failure_blocks_dashboard"] is False
    assert delivery["local_operation_without_firebase_required"] is True
    assert delivery["remote_key"] == "prediction_id"
    assert delivery["remote_records_immutable"] is True
    assert delivery["identical_retry_is_success"] is True
    assert delivery["conflicting_retry_is_error"] is True
    assert delivery["durable_local_outbox_required"] is True
    assert delivery["outbox_path"] == "outputs/firebase_outbox"
    assert delivery["maximum_backoff_seconds"] == 60

def test_acceptance_requires_rules_privacy_offline_and_live_synthetic_evidence():
    acceptance = _config()["acceptance"]

    assert acceptance["participant_data_allowed"] is False
    assert acceptance["external_test_access_allowed"] is False
    assert acceptance["rules_emulator_test_required"] is True
    assert acceptance["live_database_test_required"] is True
    assert acceptance["live_test_record_must_be_deleted"] is True
    assert set(acceptance["required_scenarios"]) == {
        "available_prediction_upload",
        "unavailable_prediction_upload",
        "forbidden_field_rejected_locally",
        "invalid_schema_rejected_locally",
        "identical_retry_is_idempotent",
        "conflicting_retry_is_rejected",
        "offline_write_is_queued",
        "queued_write_is_delivered_after_recovery",
        "inference_continues_during_firebase_failure",
        "dashboard_continues_during_firebase_failure",
        "unauthorized_database_access_is_denied",
        "synthetic_live_write_read_delete",
    }
