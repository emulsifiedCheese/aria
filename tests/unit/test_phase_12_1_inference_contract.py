import json
from hashlib import sha256
from pathlib import Path
import joblib
from aria.modeling.missing_modality import EXPECTED_POLICY

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_1_inference.json"
CONFIG_SHA256 = "68fa975e859a386c32d991557a88303b1f403f23b5886ff4dbf5093c49befba8"

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def test_phase_12_1_contract_is_frozen():
    config = _config()

    assert _sha256(CONFIG_PATH) == CONFIG_SHA256
    assert config["config_id"] == "zone-a-phase12.1-local-inference-v1"
    assert config["scope"] == {
        "zone": "A",
        "camera_id": "camera_a",
        "active_sensor_nodes": ["ESP-A1", "ESP-A2"],
        "prediction_granularity": "completed_two_second_window_per_local_track",
        "participant_collection_allowed": False,
    }

def test_contract_pins_the_frozen_camera_only_artifact_and_classes():
    model_config = _config()["model"]
    artifact_path = PROJECT_ROOT / model_config["artifact_path"]

    assert _sha256(artifact_path) == model_config["artifact_sha256"]
    assert model_config["name"] == "camera_only"
    assert model_config["class_labels"] == ["Serving/Processing","Idle/Waiting","Reaching/Handling",]
    assert model_config["fit_allowed"] is False
    assert model_config["calibration_allowed"] is False
    assert model_config["parameter_changes_allowed"] is False
    assert model_config["fallback_model_allowed"] is False
    assert model_config["confidence_method"] == "maximum_class_probability"
    assert model_config["confidence_threshold"] is None

    model = joblib.load(artifact_path)
    assert set(model.classes_) == set(model_config["class_labels"])
    assert model.n_features_in_ == len(_config()["preprocessing"]["feature_names"])

def test_contract_pins_schemas_and_single_track_preprocessing():
    preprocessing = _config()["preprocessing"]

    assert _sha256(PROJECT_ROOT / preprocessing["feature_schema_path"]) == (preprocessing["feature_schema_sha256"])
    assert _sha256(PROJECT_ROOT / preprocessing["prediction_schema_path"]) == (preprocessing["prediction_schema_sha256"])
    assert preprocessing["window_duration_ms"] == 2000
    assert preprocessing["keypoint_confidence_threshold"] == 0.5
    assert preprocessing["track_scope"] == "one_local_track_id"
    assert preprocessing["cross_track_aggregation_allowed"] is False
    assert preprocessing["feature_roots"] == ["camera_available","pose_available","camera",]
    assert len(preprocessing["feature_names"]) == 23
    assert preprocessing["feature_names"] == sorted(preprocessing["feature_names"])
    assert preprocessing["feature_order_changes_allowed"] is False

def test_contract_extends_the_frozen_missing_modality_policy_without_drift():
    policy = _config()["missing_modality_policy"]

    assert {key: policy[key] for key in EXPECTED_POLICY} == EXPECTED_POLICY
    assert policy["camera_available_pose_unavailable"] == ("use_camera_only_with_pose_unavailable")
    assert policy["reuse_stale_prediction"] is False

def test_contract_keeps_outputs_local_and_non_identifying():
    config = _config()

    assert config["output"]["local_only"] is True
    assert config["output"]["one_record_per_completed_window_and_local_track"] is True
    assert config["output"]["unavailable_activity"] is None
    assert config["output"]["unavailable_confidence"] is None
    assert config["privacy"] == {
        "participant_ids_allowed": False,
        "participant_names_allowed": False,
        "role_attribution_allowed": False,
        "raw_features_retained": False,
        "raw_audio_retained": False,
        "raw_or_masked_video_retained_by_inference": False,
        "firebase_required": False,
    }