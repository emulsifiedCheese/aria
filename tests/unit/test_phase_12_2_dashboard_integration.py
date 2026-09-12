from datetime import datetime, timedelta
import pytest
from aria.dashboard.integration import (
    DashboardIntegrationError,
    LocalDashboardIntegration,
    PrivacyGateError,
)
from aria.inference.service import LocalInferenceService
from aria.timebase import SGT
from scripts.run_local_dashboard import (
    _synthetic_camera_record,
    _synthetic_sensor_record,
)

START = datetime(2026, 8, 24, 16, 30, 0, tzinfo=SGT)
OBSERVED = START + timedelta(milliseconds=250)
EMITTED = START + timedelta(seconds=2)
SESSION_ID = "zone_a_20260824T163000SGT_synthetic1202"

@pytest.fixture(scope="module")
def service():
    return LocalInferenceService()

def _records():
    camera = _synthetic_camera_record(OBSERVED)
    sensors = {
        node_id: [_synthetic_sensor_record(node_id, OBSERVED)]
        for node_id in ("ESP-A1", "ESP-A2")
    }
    return camera, sensors

def _ready_integration(service):
    integration = LocalDashboardIntegration(service=service)
    camera, sensors = _records()
    integration.on_camera_record(camera, capture_fps=30.0, processing_fps=7.0)
    for records in sensors.values():
        integration.on_sensor_record(records[0])
    result = integration.process_completed_window(
        session_id=SESSION_ID,
        window_start=START,
        camera_records=[camera],
        sensor_records=sensors,
        emitted_at=EMITTED,
    )
    return integration, result

def test_real_model_prediction_and_health_reach_one_ready_snapshot(service):
    integration, result = _ready_integration(service)
    state = integration.snapshot(EMITTED)

    assert len(result["predictions"]) == 1
    assert result["predictions"][0]["prediction_available"] is True
    assert state["overall_status"] == "ready"
    assert state["camera"]["capture_fps"] == 30.0
    assert state["camera"]["processing_fps"] == 7.0
    assert state["sensors"]["ESP-A1"]["packets_received"] == 1
    assert state["sensors"]["ESP-A2"]["packets_received"] == 1
    assert state["predictions"][0]["local_track_id"] == 1
    assert state["predictions"][0]["confidence"] == pytest.approx(result["predictions"][0]["confidence"])

def test_integration_does_not_retain_raw_features_media_or_identifiers(service):
    integration, _ = _ready_integration(service)
    state = integration.snapshot(EMITTED)
    encoded = repr(state)
    retained = repr(
        {
            "camera": integration.aggregator._camera,
            "predictions": integration.aggregator._predictions,
            "sensors": integration.aggregator.node_monitor.nodes,
            "counters": integration.aggregator._sensor_counters,
        }
    )
    for forbidden in (
        "session_id",
        "source_ip",
        "audio_rms",
        "keypoints",
        "bounding_box",
        "raw_video",
        "raw_audio",
    ):
        assert forbidden not in encoded
        assert forbidden not in retained
    assert integration.orchestrator.writer is None

def test_new_camera_unavailable_window_replaces_current_activity(service):
    integration, first = _ready_integration(service)
    integration.on_camera_unavailable()
    second = integration.process_completed_window(
        session_id=SESSION_ID,
        window_start=START + timedelta(seconds=2),
        camera_records=[],
        sensor_records={"ESP-A1": [], "ESP-A2": []},
        emitted_at=EMITTED + timedelta(seconds=2),
    )
    state = integration.snapshot(EMITTED + timedelta(seconds=2))

    assert first["predictions"][0]["local_track_id"] == 1
    assert second["predictions"][0]["prediction_available"] is False
    assert second["predictions"][0]["unavailable_reason"] == "missing_camera_track"
    assert state["overall_status"] == "degraded"
    assert state["camera"]["available"] is False
    assert len(state["predictions"]) == 1
    assert state["predictions"][0]["local_track_id"] is None
    assert state["predictions"][0]["confidence"] is None

def test_unverified_mask_blocks_integrated_ready_state(service):
    integration, _ = _ready_integration(service)
    integration.set_mask_verified(False)
    state = integration.snapshot(EMITTED)

    assert state["overall_status"] == "blocked"
    assert state["privacy"]["privacy_ready"] is False
    assert "mask_unverified" in {item["code"] for item in state["warnings"]}
    with pytest.raises(PrivacyGateError, match="inference is paused"):
        integration.process_completed_window(
            session_id=SESSION_ID,
            window_start=START + timedelta(seconds=2),
            camera_records=[],
            sensor_records={"ESP-A1": [], "ESP-A2": []},
            emitted_at=EMITTED + timedelta(seconds=2),
        )

def test_integration_rejects_retired_or_invalid_producers(service):
    integration = LocalDashboardIntegration(service=service)
    camera, sensors = _records()
    retired = sensors["ESP-A2"][0]
    retired["payload"] = dict(retired["payload"], node_id="ESP-B")
    with pytest.raises(DashboardIntegrationError, match="invalid active ESP record"):
        integration.on_sensor_record(retired)
    invalid_camera = dict(camera, camera_id="camera_b")
    with pytest.raises(DashboardIntegrationError, match="invalid Camera A record"):
        integration.on_camera_record(invalid_camera, capture_fps=30.0, processing_fps=7.0)

def test_identical_completed_window_retry_is_safe_for_dashboard_state(service):
    integration, first = _ready_integration(service)
    camera, sensors = _records()
    second = integration.process_completed_window(
        session_id=SESSION_ID,
        window_start=START,
        camera_records=[camera],
        sensor_records=sensors,
        emitted_at=EMITTED,
    )
    assert second["predictions"] == first["predictions"]
    assert len(integration.snapshot(EMITTED)["predictions"]) == 1