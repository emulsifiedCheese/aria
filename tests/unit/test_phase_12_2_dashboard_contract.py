import json
from hashlib import sha256
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_2_dashboard.json"
CONFIG_SHA256 = "1fcd1343f854691e2bce3fabb22b4f9b6f2b048a6d94e9406a7d31be1dcaca76"

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def _validator():
    config = _config()
    schema = json.loads((PROJECT_ROOT / config["inputs"]["dashboard_state_schema_path"]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _state():
    return {
        "schema_version": 1,
        "snapshot_id": "dashboard_0123456789abcdef",
        "dashboard_version": "zone-a-phase12.2-dashboard-v1",
        "generated_at_sgt": "2026-08-24T14:00:01+08:00",
        "zone": "A",
        "overall_status": "ready",
        "privacy": {
            "local_only": True,
            "mask_verified": True,
            "privacy_ready": True,
            "video_enabled": False,
        },
        "camera": {
            "camera_id": "camera_a",
            "available": True,
            "fresh": True,
            "last_frame_at_sgt": "2026-08-24T14:00:00+08:00",
            "age_seconds": 1.0,
            "capture_fps": 30.0,
            "processing_fps": 7.0,
            "mask_verified": True,
        },
        "sensors": {
            node_id: {
                "available": True,
                "fresh": True,
                "stale": False,
                "last_received_at_sgt": "2026-08-24T14:00:00+08:00",
                "age_seconds": 1.0,
                "packets_received": 60,
                "packet_gap_events": 0,
                "estimated_packets_lost": 0,
                "packet_loss_percent": 0.0,
            }
            for node_id in ("ESP-A1", "ESP-A2")
        },
        "predictions": [
            {
                "prediction_id": "prediction_0123456789abcdef",
                "window_id": "zone_a_1787551200000_1787551202000",
                "local_track_id": 1,
                "emitted_at_sgt": "2026-08-24T14:00:00+08:00",
                "age_seconds": 1.0,
                "stale": False,
                "prediction_available": True,
                "predicted_activity": "Serving/Processing",
                "confidence": 0.72,
                "unavailable_reason": None,
                "availability": {
                    "camera_available": True,
                    "pose_available": True,
                    "esp_a1_available": True,
                    "esp_a2_available": True,
                },
            }
        ],
        "warnings": [],
    }

def test_phase_12_2_dashboard_contract_is_frozen():
    config = _config()

    assert _sha256(CONFIG_PATH) == CONFIG_SHA256
    assert config["config_id"] == "zone-a-phase12.2-dashboard-v1"
    assert config["status"] == "frozen_before_implementation"
    assert config["scope"] == {
        "zone": "A",
        "camera_id": "camera_a",
        "active_sensor_nodes": ["ESP-A1", "ESP-A2"],
        "participant_collection_allowed": False,
        "accepted_input_scopes": ["synthetic", "non_research"],
    }

def test_contract_pins_dashboard_inputs_and_existing_inference_boundary():
    inputs = _config()["inputs"]

    for path_key, hash_key in (
        ("dashboard_state_schema_path", "dashboard_state_schema_sha256"),
        ("prediction_schema_path", "prediction_schema_sha256"),
        ("inference_contract_path", "inference_contract_sha256"),
        ("camera_config_path", "camera_config_sha256"),
        ("mask_config_path", "mask_config_sha256"),
    ):
        assert _sha256(PROJECT_ROOT / inputs[path_key]) == inputs[hash_key]

    assert inputs["prediction_schema_version"] == 3
    assert inputs["mask_config_version"] == "batamfast-v2"

def test_contract_freezes_local_server_and_health_policy():
    config = _config()

    assert config["server"] == {
        "host": "127.0.0.1",
        "port": 8050,
        "external_network_binding_allowed": False,
        "debug_mode_allowed": False,
        "refresh_interval_ms": 1000,
    }
    assert config["state_policy"] == {
        "dashboard_version": "zone-a-phase12.2-dashboard-v1",
        "latest_prediction_per_local_track": True,
        "cross_track_aggregation_allowed": False,
        "prediction_stale_after_seconds": 5.0,
        "camera_stale_after_seconds": 2.0,
        "sensor_stale_after_seconds": 5.0,
        "packet_loss_calculation": "cumulative_since_process_start",
        "packet_loss_warning_percent": 2.0,
        "packet_loss_warning_min_packets": 50,
        "prediction_persistence_allowed": False,
        "dashboard_snapshot_persistence_allowed": False,
        "reuse_stale_prediction_as_current": False,
    }

def test_contract_preserves_confidence_and_privacy_boundary():
    config = _config()
    presentation = config["presentation"]
    privacy = config["privacy"]

    assert presentation["confidence_transform"] == "none"
    assert presentation["confidence_threshold"] is None
    assert presentation["show_session_id"] is False
    assert presentation["video_component_allowed"] is False
    assert presentation["video_route_allowed"] is False
    assert privacy == {
        "local_only": True,
        "firebase_required": False,
        "firebase_output_allowed": False,
        "participant_identifiers_allowed": False,
        "participant_names_allowed": False,
        "role_attribution_allowed": False,
        "raw_features_allowed": False,
        "raw_audio_allowed": False,
        "raw_video_allowed": False,
        "masked_video_allowed": False,
        "arbitrary_warning_text_allowed": False,
    }

def test_dashboard_state_schema_accepts_only_non_identifying_summary_state():
    validator = _validator()
    state = _state()

    validator.validate(state)

    state["session_id"] = "zone_a_20260824T140000SGT_demo0001"
    with pytest.raises(ValidationError):
        validator.validate(state)

def test_dashboard_state_schema_rejects_video_and_invalid_available_prediction():
    validator = _validator()
    state = _state()

    state["privacy"]["video_enabled"] = True
    with pytest.raises(ValidationError):
        validator.validate(state)

    state = _state()
    state["predictions"][0]["confidence"] = None
    with pytest.raises(ValidationError):
        validator.validate(state)

def test_acceptance_matrix_covers_privacy_and_degraded_modes():
    acceptance = _config()["acceptance"]

    assert acceptance["participant_data_allowed"] is False
    assert acceptance["external_test_access_allowed"] is False
    assert acceptance["no_video_component_or_route_required"] is True
    assert set(acceptance["required_scenarios"]) == {
        "normal_single_track",
        "normal_multiple_tracks",
        "camera_unavailable",
        "pose_unavailable",
        "esp_a1_unavailable",
        "esp_a2_unavailable",
        "both_sensors_unavailable",
        "all_modalities_unavailable",
        "prediction_stale",
        "sensor_stale",
        "packet_loss_warning",
        "mask_unverified",
        "model_error",
        "identical_prediction_retry",
    }