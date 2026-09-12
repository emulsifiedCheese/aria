"""synthetic Phase 12.2 scenario and privacy acceptance"""
from __future__ import annotations
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from dash import dcc
from aria.dashboard.app import WARNING_TEXT, create_dashboard_app, render_dashboard_state
from aria.dashboard.state import DashboardStateAggregator
from aria.timebase import SGT

NOW = datetime(2026, 8, 24, 17, 0, 10, tzinfo=SGT)
EXPECTED_SCREENSHOTS = ("ready.png", "degraded.png", "blocked.png")
FORBIDDEN_OUTPUT_KEYS = {
    "session_id",
    "participant_id",
    "participant_name",
    "role",
    "role_attribution",
    "feature_vector",
    "raw_features",
    "raw_audio",
    "raw_video",
    "masked_video",
    "source_ip",
}

class DashboardAcceptanceError(RuntimeError):
    """raised when Phase 12.2 acceptance evidence cannot pass"""

def _sensor(node_id, sequence=1):
    return {"node_id": node_id, "sequence": sequence, "boot_id": 1202}

def _prediction(
    *,
    track_id=7,
    prediction_id="prediction_acceptance001",
    window_id="zone_a_1787562010000_1787562012000",
    emitted_at=NOW,
    available=True,
    reason=None,
    camera=True,
    pose=True,
    a1=True,
    a2=True,
):
    return {
        "schema_version": 3,
        "prediction_id": prediction_id,
        "session_id": "zone_a_20260824T170000SGT_synthetic1202",
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
            "camera_available": camera,
            "pose_available": pose,
            "esp_a1_available": a1,
            "esp_a2_available": a2,
        },
    }

def _aggregator(*, camera=True, sensors=("ESP-A1", "ESP-A2"), prediction=None):
    aggregator = DashboardStateAggregator()
    if camera:
        aggregator.update_camera(
            available=True,
            last_frame_at=NOW - timedelta(milliseconds=250),
            capture_fps=30.0,
            processing_fps=7.0,
        )
    received_at = (NOW - timedelta(milliseconds=250)).isoformat(
        timespec="milliseconds"
    )
    for node_id in sensors:
        aggregator.update_sensor(_sensor(node_id), received_at)
    if prediction is not False:
        aggregator.on_prediction(prediction or _prediction())
    return aggregator

def _warning_codes(state):
    return {warning["code"] for warning in state["warnings"]}

def _scenario_results():
    results = {}

    def record(name, state, condition):
        results[name] = {
            "passed": bool(condition),
            "overall_status": state["overall_status"],
            "warning_codes": sorted(_warning_codes(state)),
            "prediction_count": len(state["predictions"]),
        }

    single = _aggregator().snapshot(NOW)
    record("normal_single_track", single, single["overall_status"] == "ready")

    multiple_aggregator = _aggregator()
    multiple_aggregator.on_prediction(
        _prediction(track_id=8, prediction_id="prediction_acceptance002")
    )
    multiple = multiple_aggregator.snapshot(NOW)
    record(
        "normal_multiple_tracks",
        multiple,
        multiple["overall_status"] == "ready" and len(multiple["predictions"]) == 2,
    )

    camera_aggregator = _aggregator()
    camera_aggregator.update_camera(available=False)
    camera_state = camera_aggregator.snapshot(NOW)
    record(
        "camera_unavailable",
        camera_state,
        "camera_unavailable" in _warning_codes(camera_state),
    )

    pose_state = _aggregator(
        prediction=_prediction(pose=False)
    ).snapshot(NOW)
    record(
        "pose_unavailable",
        pose_state,
        "pose_unavailable" in _warning_codes(pose_state),
    )

    a1_state = _aggregator(
        sensors=("ESP-A2",), prediction=_prediction(a1=False)
    ).snapshot(NOW)
    record(
        "esp_a1_unavailable",
        a1_state,
        "esp_a1_unavailable" in _warning_codes(a1_state),
    )

    a2_state = _aggregator(
        sensors=("ESP-A1",), prediction=_prediction(a2=False)
    ).snapshot(NOW)
    record(
        "esp_a2_unavailable",
        a2_state,
        "esp_a2_unavailable" in _warning_codes(a2_state),
    )

    both_state = _aggregator(
        sensors=(), prediction=_prediction(a1=False, a2=False)
    ).snapshot(NOW)
    record(
        "both_sensors_unavailable",
        both_state,
        {"esp_a1_unavailable", "esp_a2_unavailable"}
        <= _warning_codes(both_state),
    )

    all_state = _aggregator(
        camera=False,
        sensors=(),
        prediction=_prediction(
            track_id=None,
            available=False,
            reason="missing_camera_track",
            camera=False,
            pose=False,
            a1=False,
            a2=False,
        ),
    ).snapshot(NOW)
    record(
        "all_modalities_unavailable",
        all_state,
        all_state["overall_status"] == "degraded"
        and all_state["predictions"][0]["prediction_available"] is False,
    )

    stale_prediction = _aggregator().snapshot(NOW + timedelta(seconds=6))
    record(
        "prediction_stale",
        stale_prediction,
        "prediction_stale" in _warning_codes(stale_prediction)
        and stale_prediction["predictions"][0]["stale"] is True,
    )
    record(
        "sensor_stale",
        stale_prediction,
        {"esp_a1_stale", "esp_a2_stale"} <= _warning_codes(stale_prediction),
    )

    loss_aggregator = _aggregator(sensors=(), prediction=False)
    received_at = NOW.isoformat(timespec="milliseconds")
    for sequence in [1, 4, *range(5, 53)]:
        loss_aggregator.update_sensor(_sensor("ESP-A1", sequence), received_at)
    loss_aggregator.update_sensor(_sensor("ESP-A2"), received_at)
    loss_aggregator.on_prediction(_prediction())
    loss_state = loss_aggregator.snapshot(NOW)
    record(
        "packet_loss_warning",
        loss_state,
        "esp_a1_packet_loss" in _warning_codes(loss_state),
    )

    mask_aggregator = _aggregator()
    mask_aggregator.set_mask_verified(False)
    mask_state = mask_aggregator.snapshot(NOW)
    record(
        "mask_unverified",
        mask_state,
        mask_state["overall_status"] == "blocked"
        and "mask_unverified" in _warning_codes(mask_state),
    )

    model_state = _aggregator(
        prediction=_prediction(available=False, reason="model_error")
    ).snapshot(NOW)
    record(
        "model_error",
        model_state,
        "model_error" in _warning_codes(model_state)
        and model_state["predictions"][0]["confidence"] is None,
    )

    retry_aggregator = _aggregator()
    retry = retry_aggregator.on_prediction(_prediction())
    retry_state = retry_aggregator.snapshot(NOW)
    record(
        "identical_prediction_retry",
        retry_state,
        retry is False and len(retry_state["predictions"]) == 1,
    )
    return results

def _walk(value):
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)
        return
    yield value
    children = getattr(value, "children", None)
    if children is not None:
        yield from _walk(children)

def _collect_keys(value):
    keys = set()
    if isinstance(value, dict):
        keys.update(value)
        for item in value.values():
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys

def _privacy_results():
    state = _aggregator().snapshot(NOW)
    app = create_dashboard_app(_aggregator())
    components = render_dashboard_state(state)
    component_names = {type(item).__name__ for item in _walk(components)}
    routes = {rule.rule for rule in app.server.url_map.iter_rules()}
    config = app.aria_aggregator.config
    checks = {
        "emitted_state_has_no_forbidden_keys": not (
            _collect_keys(state) & FORBIDDEN_OUTPUT_KEYS
        ),
        "no_image_or_video_component": not ({"Img", "Video"} & component_names),
        "no_media_or_video_route": not any(
            "media" in route.lower() or "video" in route.lower() for route in routes
        ),
        "fixed_warning_dictionary_is_complete": set(WARNING_TEXT)
        == {
            "mask_unverified",
            "camera_unavailable",
            "camera_stale",
            "esp_a1_unavailable",
            "esp_a1_stale",
            "esp_a1_packet_loss",
            "esp_a2_unavailable",
            "esp_a2_stale",
            "esp_a2_packet_loss",
            "pose_unavailable",
            "prediction_unavailable",
            "prediction_stale",
            "model_error",
        },
        "localhost_only": config["server"]["host"] == "127.0.0.1"
        and config["server"]["external_network_binding_allowed"] is False,
        "debug_disabled": config["server"]["debug_mode_allowed"] is False,
        "dashboard_persistence_disabled": config["state_policy"][
            "dashboard_snapshot_persistence_allowed"
        ]
        is False,
        "one_second_refresh": any(
            isinstance(item, dcc.Interval) and item.interval == 1000
            for item in _walk(app.layout)
        ),
    }
    return {name: {"passed": passed} for name, passed in checks.items()}

def _screenshot_results(screenshot_dir):
    directory = Path(screenshot_dir)
    results = {}
    for name in EXPECTED_SCREENSHOTS:
        path = directory / name
        data = path.read_bytes() if path.is_file() else b""
        passed = data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 10_000
        results[name.removesuffix(".png")] = {
            "passed": passed,
            "path": str(path),
            "size_bytes": len(data),
            "sha256": sha256(data).hexdigest() if data else None,
        }
    return results

def run_acceptance(screenshot_dir):
    config = DashboardStateAggregator().config
    scenarios = _scenario_results()
    privacy = _privacy_results()
    screenshots = _screenshot_results(screenshot_dir)
    required = set(config["acceptance"]["required_scenarios"])
    scenario_names_match = set(scenarios) == required
    passed = (
        scenario_names_match
        and all(item["passed"] for item in scenarios.values())
        and all(item["passed"] for item in privacy.values())
        and all(item["passed"] for item in screenshots.values())
    )
    report = {
        "acceptance_id": "zone-a-phase12.2-dashboard-acceptance-v1",
        "generated_at_sgt": NOW.isoformat(timespec="milliseconds"),
        "input_scope": "synthetic",
        "participant_data_used": False,
        "external_test_accessed": False,
        "firebase_used": False,
        "scenario_names_match_contract": scenario_names_match,
        "scenarios": scenarios,
        "privacy": privacy,
        "screenshots": screenshots,
        "passed": passed,
    }
    if not passed:
        raise DashboardAcceptanceError("Phase 12.2 dashboard acceptance failed")
    return report