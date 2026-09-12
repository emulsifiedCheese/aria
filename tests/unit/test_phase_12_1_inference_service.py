from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pytest
from aria.inference.preprocessing import (
    InferencePreprocessingError,
    build_track_feature_window,
    camera_feature_matrix,
)
from aria.inference.service import (
    InferenceInputError,
    InferenceStartupError,
    LocalInferenceService,
)
from aria.timebase import SGT
import aria.inference.service as service_module

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SESSION_ID = "zone_a_20260824T120000SGT_demo0001"

def _camera_record(timestamp, *, pose_available=True):
    return {
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": 1,
        "frame_available": True,
        "pose_available": pose_available,
        "local_track_id": 7,
        "bounding_box": [10, 20, 110, 220],
        "detection_confidence": 0.8,
        "keypoints": (
            [[float(index * 10), float(index * 5)] for index in range(17)]
            if pose_available
            else []
        ),
        "keypoint_confidences": [0.9] * 17 if pose_available else [],
        "_timestamp": timestamp,
    }

def _feature_vector(*, camera_available=True, pose_available=True):
    start = datetime(2026, 8, 24, 12, 0, 0, tzinfo=SGT)
    camera = (
        [_camera_record(start + timedelta(milliseconds=250), pose_available=pose_available)]
        if camera_available
        else []
    )
    return build_track_feature_window(
        start,
        camera,
        {"ESP-A1": [], "ESP-A2": []},
        local_track_id=7,
    )

@pytest.fixture(scope="module")
def inference_service():
    return LocalInferenceService()

def test_startup_loads_only_the_frozen_model_and_contract(inference_service):
    assert inference_service.model_path == (PROJECT_ROOT / "models" / "phase_11_1" / "camera_only.joblib")
    assert inference_service.model.n_features_in_ == 23
    assert set(inference_service.model.classes_) == {"Serving/Processing","Idle/Waiting","Reaching/Handling",}

def test_startup_rejects_contract_byte_drift(tmp_path):
    changed = tmp_path / "phase_12_1_inference.json"
    changed.write_bytes((PROJECT_ROOT / "config" / "phase_12_1_inference.json").read_bytes() + b"\n")
    with pytest.raises(InferenceStartupError, match="contract hash mismatch"):
        LocalInferenceService(changed)

def test_startup_rejects_model_artifact_hash_drift(monkeypatch):
    original = service_module._sha256

    def changed_model_hash(path):
        if Path(path).name == "camera_only.joblib":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(service_module, "_sha256", changed_model_hash)
    with pytest.raises(InferenceStartupError, match="model artifact hash mismatch"):
        LocalInferenceService()

def test_matrix_uses_the_exact_frozen_feature_order(inference_service):
    vector = _feature_vector()
    preprocessing = inference_service.config["preprocessing"]

    matrix = camera_feature_matrix(
        vector,
        feature_roots=preprocessing["feature_roots"],
        feature_names=preprocessing["feature_names"],
    )

    assert matrix.shape == (1, 23)
    assert matrix[0, preprocessing["feature_names"].index("camera_available")] == 1.0
    assert matrix[0, preprocessing["feature_names"].index("pose_available")] == 1.0

def test_matrix_rejects_frozen_feature_drift(inference_service):
    vector = _feature_vector()
    del vector["camera"]["movement_speed_mean_px_per_second"]
    preprocessing = inference_service.config["preprocessing"]

    with pytest.raises(InferencePreprocessingError, match="frozen feature fields differ"):
        camera_feature_matrix(
            vector,
            feature_roots=preprocessing["feature_roots"],
            feature_names=preprocessing["feature_names"],
        )

def test_camera_prediction_is_schema_valid_and_uses_max_probability(inference_service):
    prediction = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=_feature_vector(),
        emitted_at=datetime(2026, 8, 24, 12, 0, 2, tzinfo=SGT),
    )

    assert prediction["prediction_available"] is True
    assert prediction["predicted_activity"] in inference_service.config["model"]["class_labels"]
    assert 0 <= prediction["confidence"] <= 1
    assert prediction["unavailable_reason"] is None
    assert prediction["availability"] == {
        "camera_available": True,
        "pose_available": True,
        "esp_a1_available": False,
        "esp_a2_available": False,
    }
    inference_service.prediction_validator.validate(prediction)

def test_pose_loss_continues_with_explicit_availability(inference_service):
    prediction = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=_feature_vector(pose_available=False),
    )

    assert prediction["prediction_available"] is True
    assert prediction["availability"]["pose_available"] is False

def test_camera_loss_clears_current_output_without_invoking_model(inference_service):
    class FailIfInvoked:
        def predict(self, _):
            raise AssertionError("model invoked without camera")

        def predict_proba(self, _):
            raise AssertionError("model invoked without camera")

    original_model = inference_service.model
    inference_service.model = FailIfInvoked()
    try:
        prediction = inference_service.predict(
            session_id=SESSION_ID,
            local_track_id=7,
            feature_vector=_feature_vector(camera_available=False),
        )
    finally:
        inference_service.model = original_model

    assert prediction["prediction_available"] is False
    assert prediction["predicted_activity"] is None
    assert prediction["confidence"] is None
    assert prediction["unavailable_reason"] == "missing_camera_track"

def test_model_failure_emits_model_error_without_stale_values(inference_service):
    available = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=_feature_vector(),
    )

    class FailingModel:
        classes_ = np.asarray([
            "Idle/Waiting",
            "Reaching/Handling",
            "Serving/Processing",
        ])

        def predict(self, _):
            raise RuntimeError("synthetic model failure")

        def predict_proba(self, _):
            raise RuntimeError("synthetic model failure")

    original_model = inference_service.model
    inference_service.model = FailingModel()
    try:
        failed = inference_service.predict(
            session_id=SESSION_ID,
            local_track_id=7,
            feature_vector=_feature_vector(),
        )
    finally:
        inference_service.model = original_model

    assert available["prediction_available"] is True
    assert failed["prediction_available"] is False
    assert failed["predicted_activity"] is None
    assert failed["confidence"] is None
    assert failed["unavailable_reason"] == "model_error"

def test_prediction_id_is_stable_for_the_same_window_and_track(inference_service):
    first = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=_feature_vector(),
        emitted_at=datetime(2026, 8, 24, 12, 0, 2, tzinfo=SGT),
    )
    second = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=deepcopy(_feature_vector()),
        emitted_at=datetime(2026, 8, 24, 12, 0, 3, tzinfo=SGT),
    )

    assert first["prediction_id"] == second["prediction_id"]

def test_prediction_id_and_output_are_independent_between_tracks(inference_service):
    first = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=7,
        feature_vector=_feature_vector(),
    )
    second = inference_service.predict(
        session_id=SESSION_ID,
        local_track_id=8,
        feature_vector=_feature_vector(),
    )

    assert first["prediction_id"] != second["prediction_id"]
    assert first["local_track_id"] == 7
    assert second["local_track_id"] == 8

def test_invalid_session_cannot_emit_a_prediction(inference_service):
    with pytest.raises(InferenceInputError, match="prediction schema failure"):
        inference_service.predict(
            session_id="participant_name",
            local_track_id=7,
            feature_vector=_feature_vector(),
        )