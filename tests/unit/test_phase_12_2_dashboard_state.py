from copy import deepcopy
from datetime import datetime, timedelta
import pytest
from aria.dashboard.state import DashboardStateAggregator, DashboardStateError
from aria.timebase import SGT

NOW = datetime(2026, 8, 24, 15, 0, 10, tzinfo=SGT)

def _sensor(node_id, sequence):
    return {"node_id": node_id, "sequence": sequence, "boot_id": 100}

def _prediction(
    *,
    track_id=7,
    window_id="zone_a_1787554808000_1787554810000",
    prediction_id="prediction_dashboard0001",
    emitted_at=NOW,
    available=True,
    reason=None,
    pose_available=True,
):
    return {
        "schema_version": 3,
        "prediction_id": prediction_id,
        "session_id": "zone_a_20260824T150000SGT_demo0001",
        "window_id": window_id,
        "zone": "A",
        "local_track_id": track_id,
        "emitted_at_sgt": emitted_at.isoformat(timespec="milliseconds"),
        "model_version": "zone-a-camera-only-rf-v1",
        "preprocessing_version": "zone-a-phase12.1-single-track-window-v1",
        "feature_schema_version": 2,
        "prediction_available": available,
        "predicted_activity": "Serving/Processing" if available else None,
        "confidence": 0.72 if available else None,
        "unavailable_reason": reason,
        "availability": {
            "camera_available": available,
            "pose_available": pose_available,
            "esp_a1_available": True,
            "esp_a2_available": True,
        },
    }

def _ready_aggregator():
    aggregator = DashboardStateAggregator()
    aggregator.update_camera(
        available=True,
        last_frame_at=NOW - timedelta(seconds=1),
        capture_fps=30,
        processing_fps=7,
    )
    received_at = (NOW - timedelta(seconds=1)).isoformat(timespec="milliseconds")
    aggregator.update_sensor(_sensor("ESP-A1", 1), received_at)
    aggregator.update_sensor(_sensor("ESP-A2", 1), received_at)
    aggregator.on_prediction(_prediction())
    return aggregator

def _warning_codes(state):
    return {warning["code"] for warning in state["warnings"]}

def test_ready_snapshot_is_schema_valid_local_and_non_identifying():
    state = _ready_aggregator().snapshot(NOW)

    assert state["overall_status"] == "ready"
    assert state["privacy"] == {
        "local_only": True,
        "mask_verified": True,
        "privacy_ready": True,
        "video_enabled": False,
    }
    assert state["warnings"] == []
    assert len(state["predictions"]) == 1
    assert state["predictions"][0]["local_track_id"] == 7
    assert state["predictions"][0]["confidence"] == 0.72
    assert "session_id" not in state["predictions"][0]
    assert "model_version" not in state["predictions"][0]
    assert "feature_vector" not in repr(state)

def test_multiple_tracks_share_only_the_current_window():
    aggregator = _ready_aggregator()
    aggregator.on_prediction(_prediction(track_id=8, prediction_id="prediction_dashboard0002"))

    state = aggregator.snapshot(NOW)
    assert [item["local_track_id"] for item in state["predictions"]] == [7, 8]

    next_window = _prediction(
        track_id=None,
        window_id="zone_a_1787554810000_1787554812000",
        prediction_id="prediction_dashboard0003",
        emitted_at=NOW + timedelta(seconds=2),
        available=False,
        reason="missing_camera_track",
        pose_available=False,
    )
    aggregator.on_prediction(next_window)
    state = aggregator.snapshot(NOW + timedelta(seconds=2))

    assert len(state["predictions"]) == 1
    assert state["predictions"][0]["local_track_id"] is None
    assert state["predictions"][0]["prediction_available"] is False
    assert state["overall_status"] == "degraded"
    assert "prediction_unavailable" in _warning_codes(state)

def test_identical_retry_is_noop_and_conflicting_retry_is_rejected():
    aggregator = _ready_aggregator()
    record = _prediction()

    assert aggregator.on_prediction(record) is False
    changed = deepcopy(record)
    changed["confidence"] = 0.5
    with pytest.raises(DashboardStateError, match="conflicting prediction retry"):
        aggregator.on_prediction(changed)

def test_older_prediction_cannot_replace_current_window():
    aggregator = _ready_aggregator()
    older = _prediction(
        track_id=3,
        window_id="zone_a_1787554806000_1787554808000",
        prediction_id="prediction_dashboard_old1",
        emitted_at=NOW - timedelta(seconds=2),
    )

    assert aggregator.on_prediction(older) is False
    assert [item["local_track_id"] for item in aggregator.snapshot(NOW)["predictions"]] == [7]

def test_stale_camera_sensor_and_prediction_are_explicitly_degraded():
    aggregator = _ready_aggregator()
    state = aggregator.snapshot(NOW + timedelta(seconds=6))

    assert state["overall_status"] == "degraded"
    assert state["camera"]["fresh"] is False
    assert state["sensors"]["ESP-A1"]["stale"] is True
    assert state["predictions"][0]["stale"] is True
    assert {"camera_stale", "esp_a1_stale", "esp_a2_stale", "prediction_stale"} <= _warning_codes(state)

def test_packet_loss_warning_uses_frozen_minimum_and_threshold():
    aggregator = DashboardStateAggregator()
    aggregator.update_camera(
        available=True,
        last_frame_at=NOW,
        capture_fps=30,
        processing_fps=7,
    )
    received_at = NOW.isoformat(timespec="milliseconds")
    sequences = [1, 4, *range(5, 53)]
    for sequence in sequences:
        aggregator.update_sensor(_sensor("ESP-A1", sequence), received_at)
    aggregator.update_sensor(_sensor("ESP-A2", 1), received_at)
    aggregator.on_prediction(_prediction())

    state = aggregator.snapshot(NOW)
    a1 = state["sensors"]["ESP-A1"]
    assert a1["packets_received"] == 50
    assert a1["packet_gap_events"] == 1
    assert a1["estimated_packets_lost"] == 2
    assert a1["packet_loss_percent"] == pytest.approx(3.846154)
    assert "esp_a1_packet_loss" in _warning_codes(state)
    assert state["overall_status"] == "degraded"

def test_unverified_mask_blocks_even_when_every_component_is_fresh():
    aggregator = _ready_aggregator()
    aggregator.set_mask_verified(False)

    state = aggregator.snapshot(NOW)
    assert state["overall_status"] == "blocked"
    assert state["privacy"]["privacy_ready"] is False
    assert state["camera"]["mask_verified"] is False
    assert "mask_unverified" in _warning_codes(state)

def test_initial_state_is_degraded_without_inventing_health_values():
    state = DashboardStateAggregator().snapshot(NOW)
    assert state["overall_status"] == "degraded"
    assert state["camera"]["last_frame_at_sgt"] is None
    assert state["sensors"]["ESP-A1"]["packet_loss_percent"] is None
    assert state["predictions"] == []
    assert {"camera_unavailable", "esp_a1_unavailable", "esp_a2_unavailable", "prediction_unavailable"} <= _warning_codes(state)

def test_dashboard_rejects_retired_node_and_invalid_prediction():
    aggregator = DashboardStateAggregator()
    with pytest.raises(DashboardStateError, match="only ESP-A1 and ESP-A2"):
        aggregator.update_sensor(_sensor("ESP-B", 1), NOW.isoformat())

    invalid = _prediction()
    invalid["participant_name"] = "not allowed"
    with pytest.raises(DashboardStateError, match="prediction schema failure"):
        aggregator.on_prediction(invalid)