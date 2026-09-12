"""apply the frozen phase 11.3 missing-modality policy"""
from __future__ import annotations

EXPECTED_POLICY = {
    "camera_unavailable": "prediction_unavailable",
    "camera_available_a1_unavailable": "use_camera_only",
    "camera_available_a2_unavailable": "use_camera_only",
    "camera_available_both_sensors_unavailable": "use_camera_only",
    "all_modalities_unavailable": "prediction_unavailable",
    "reuse_stale_prediction": False,
}

class MissingModalityError(ValueError):
    """raised when availability cannot follow the frozen policy"""

def validate_missing_modality_policy(policy: dict) -> None:
    if policy != EXPECTED_POLICY:
        raise MissingModalityError("missing-modality policy differs from the frozen contract")

def apply_missing_modality_policy(
    policy: dict,
    *,
    camera_available: bool,
    a1_available: bool,
    a2_available: bool,
    predict_camera,
) -> dict:
    """return a current prediction result without retaining earlier output"""
    validate_missing_modality_policy(policy)
    availability = (camera_available, a1_available, a2_available)
    if not all(isinstance(value, bool) for value in availability):
        raise MissingModalityError("modality availability values must be booleans")
    if not camera_available:
        return {
            "prediction_available": False,
            "predicted_activity": None,
            "confidence": None,
            "unavailable_reason": "missing_camera_track",
            "model_invoked": False,
        }
    predicted_activity, confidence = predict_camera()
    return {
        "prediction_available": True,
        "predicted_activity": predicted_activity,
        "confidence": confidence,
        "unavailable_reason": None,
        "model_invoked": True,
    }

def build_missing_modality_evidence(policy: dict) -> dict:
    """exercise the frozen policy with privacy-safe synthetic states"""
    scenarios = (
        ("all_available", True, True, True, "use_camera_only"),
        ("a1_unavailable", True, False, True, "use_camera_only"),
        ("a2_unavailable", True, True, False, "use_camera_only"),
        ("both_sensors_unavailable", True, False, False, "use_camera_only"),
        ("camera_unavailable", False, True, True, "prediction_unavailable"),
        ("all_modalities_unavailable", False, False, False, "prediction_unavailable"),
    )
    calls = 0

    def predict_camera():
        nonlocal calls
        calls += 1
        return "synthetic_test_activity", 0.75

    results = []
    previous_result = None
    for name, camera, a1, a2, expected_action in scenarios:
        result = apply_missing_modality_policy(
            policy,
            camera_available=camera,
            a1_available=a1,
            a2_available=a2,
            predict_camera=predict_camera,
        )
        actual_action = (
            "use_camera_only" if result["prediction_available"] else "prediction_unavailable"
        )
        stale_prediction_reused = (
            not result["prediction_available"]
            and result["predicted_activity"] is not None
            and previous_result is not None
            and result["predicted_activity"] == previous_result.get("predicted_activity")
        )
        results.append({
            "scenario": name,
            "availability": {
                "camera_a": camera,
                "esp_a1": a1,
                "esp_a2": a2,
            },
            "expected_action": expected_action,
            "actual_action": actual_action,
            "model_invoked": result["model_invoked"],
            "prediction_cleared": result["predicted_activity"] is None,
            "confidence_cleared": result["confidence"] is None,
            "stale_prediction_reused": stale_prediction_reused,
            "status": "pass"
            if actual_action == expected_action and not stale_prediction_reused
            else "fail",
        })
        previous_result = result
    return {
        "phase": "11.3",
        "scope": "synthetic missing-modality control-flow test",
        "participant_data_used": False,
        "external_evaluation_repeated": False,
        "scenario_count": len(results),
        "camera_model_invocation_count": calls,
        "status": "pass" if all(row["status"] == "pass" for row in results) else "fail",
        "scenarios": results,
    }