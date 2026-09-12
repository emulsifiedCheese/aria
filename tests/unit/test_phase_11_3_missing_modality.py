import json
from pathlib import Path
import pytest
from aria.modeling.missing_modality import (
    EXPECTED_POLICY,
    MissingModalityError,
    apply_missing_modality_policy,
    build_missing_modality_evidence,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def test_frozen_contract_matches_runtime_policy():
    contract = json.loads((PROJECT_ROOT / "config/phase_11_3_evaluation.json").read_text(encoding="utf-8"))
    assert contract["missing_modality_policy"] == EXPECTED_POLICY

def test_sensor_loss_uses_camera_only_prediction():
    calls = []

    def predict_camera():
        calls.append(True)
        return "Idle/Waiting", 0.6

    for a1_available, a2_available in ((False, True), (True, False), (False, False)):
        result = apply_missing_modality_policy(
            EXPECTED_POLICY,
            camera_available=True,
            a1_available=a1_available,
            a2_available=a2_available,
            predict_camera=predict_camera,
        )
        assert result["prediction_available"] is True
        assert result["predicted_activity"] == "Idle/Waiting"
        assert result["model_invoked"] is True
    assert len(calls) == 3

def test_camera_loss_clears_prediction_without_invoking_model():
    def fail_if_called():
        raise AssertionError("camera model was invoked without Camera A")

    for a1_available, a2_available in ((True, True), (False, False)):
        result = apply_missing_modality_policy(
            EXPECTED_POLICY,
            camera_available=False,
            a1_available=a1_available,
            a2_available=a2_available,
            predict_camera=fail_if_called,
        )
        assert result == {
            "prediction_available": False,
            "predicted_activity": None,
            "confidence": None,
            "unavailable_reason": "missing_camera_track",
            "model_invoked": False,
        }

def test_valid_to_camera_loss_transition_does_not_reuse_stale_output():
    available = apply_missing_modality_policy(
        EXPECTED_POLICY,
        camera_available=True,
        a1_available=True,
        a2_available=True,
        predict_camera=lambda: ("Serving/Processing", 0.9),
    )
    unavailable = apply_missing_modality_policy(
        EXPECTED_POLICY,
        camera_available=False,
        a1_available=True,
        a2_available=True,
        predict_camera=lambda: available,
    )
    assert available["predicted_activity"] == "Serving/Processing"
    assert unavailable["predicted_activity"] is None
    assert unavailable["confidence"] is None

def test_evidence_covers_every_frozen_outcome():
    report = build_missing_modality_evidence(EXPECTED_POLICY)
    assert report["status"] == "pass"
    assert report["scenario_count"] == 6
    assert report["camera_model_invocation_count"] == 4
    assert report["participant_data_used"] is False
    assert report["external_evaluation_repeated"] is False
    assert all(not row["stale_prediction_reused"] for row in report["scenarios"])

def test_policy_drift_and_non_boolean_availability_are_rejected():
    changed = dict(EXPECTED_POLICY, reuse_stale_prediction=True)
    with pytest.raises(MissingModalityError, match="frozen contract"):
        build_missing_modality_evidence(changed)
    with pytest.raises(MissingModalityError, match="booleans"):
        apply_missing_modality_policy(
            EXPECTED_POLICY,
            camera_available=1,
            a1_available=True,
            a2_available=True,
            predict_camera=lambda: ("Idle/Waiting", 0.5),
        )