#!/usr/bin/env python3
"""run Phase 12.2 dashboard on its frozen localhost boundary"""
from __future__ import annotations
import argparse
from datetime import timedelta
from threading import Event, Thread
import time
from aria.dashboard.app import create_dashboard_app
from aria.dashboard.integration import LocalDashboardIntegration
from aria.dashboard.state import DashboardStateAggregator
from aria.fusion.window_builder import DEFAULT_WINDOW_SECONDS, _window_start
from aria.timebase import sgt_now

def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the local-only ARIA Zone A activity dashboard."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="seed the in-memory dashboard with safe preview data",
    )
    parser.add_argument(
        "--input-scope",
        choices=("synthetic", "non_research"),
        help="required provenance declaration for --demo",
    )
    parser.add_argument(
        "--demo-state",
        choices=("ready", "degraded", "blocked"),
        help="synthetic dashboard state to present; valid only with --demo",
    )
    return parser

def seed_safe_preview(aggregator, *, now=None):
    """seed non-identifying in-memory state for local ui inspection"""
    now = now or sgt_now()
    observed_at = (now - timedelta(milliseconds=250)).isoformat(timespec="milliseconds")
    aggregator.update_camera(
        available=True,
        last_frame_at=observed_at,
        capture_fps=30.0,
        processing_fps=7.0,
    )
    for node_id in ("ESP-A1", "ESP-A2"):
        aggregator.update_sensor(
            {"node_id": node_id, "sequence": 1, "boot_id": 1202},
            observed_at,
        )
    aggregator.on_prediction(
        {
            "schema_version": 3,
            "prediction_id": "prediction_preview1202",
            "session_id": "zone_a_20260824T000000SGT_synthetic1202",
            "window_id": "zone_a_1787500800000_1787500802000",
            "zone": "A",
            "local_track_id": 1,
            "emitted_at_sgt": observed_at,
            "model_version": "zone-a-camera-only-rf-v1",
            "preprocessing_version": "zone-a-phase12.1-single-track-window-v1",
            "feature_schema_version": 2,
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
    )
    return aggregator

def _synthetic_camera_record(timestamp):
    return {
        "schema_version": 2,
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": 1,
        "frame_timestamp_sgt": timestamp.isoformat(timespec="milliseconds"),
        "frame_available": True,
        "pose_available": True,
        "local_track_id": 1,
        "bounding_box": [10, 20, 110, 220],
        "detection_confidence": 0.8,
        "keypoints": [[float(index * 10), float(index * 5)] for index in range(17)],
        "keypoint_confidences": [0.9] * 17,
        "capture_latency_ms": 10.0,
        "detection_latency_ms": 20.0,
        "pose_latency_ms": 30.0,
        "total_latency_ms": 60.0,
        "mask_config_version": "batamfast-v2",
        "_timestamp": timestamp,
    }

def _synthetic_sensor_record(node_id, timestamp):
    payload = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC",
        "boot_id": 1202,
        "node_id": node_id,
        "zone": "A",
        "sequence": 1,
        "timestamp_ms": 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": False,
        "pir_recent_activity": True,
        "audio_peak_to_peak": 12,
        "audio_activity": 3,
        "audio_rms": 5,
    }
    if node_id == "ESP-A1":
        payload.update({"distance_cm": 51, "distance_valid": True})
    return {
        "received_at_sgt": timestamp.isoformat(timespec="milliseconds"),
        "source_ip": "127.0.0.1",
        "source_port": 4210 if node_id == "ESP-A1" else 4211,
        "payload": payload,
        "_timestamp": timestamp,
    }

def seed_safe_integration_preview(integration, *, now=None):
    """exercise sensor, camera, inference and dashboard boundaries in memory"""
    now = now or sgt_now()
    observed_at = now - timedelta(milliseconds=250)
    camera = _synthetic_camera_record(observed_at)
    sensors = {
        node_id: [_synthetic_sensor_record(node_id, observed_at)]
        for node_id in ("ESP-A1", "ESP-A2")
    }
    integration.on_camera_record(camera, capture_fps=30.0, processing_fps=7.0)
    for records in sensors.values():
        integration.on_sensor_record(records[0])
    integration.process_completed_window(
        session_id="zone_a_20260824T000000SGT_synthetic1202",
        window_start=_window_start(observed_at, DEFAULT_WINDOW_SECONDS),
        camera_records=[camera],
        sensor_records=sensors,
        emitted_at=now,
    )
    return integration

def _apply_demo_state(integration, state):
    if state == "degraded":
        integration.on_camera_unavailable()
    elif state == "blocked":
        integration.set_mask_verified(False)

def start_safe_preview_heartbeat(integration, state="ready"):
    """keep synthetic evidence fresh without changing production state policy"""
    stop_requested = Event()

    def update():
        last_window = _window_start(
            sgt_now() - timedelta(milliseconds=250), DEFAULT_WINDOW_SECONDS
        )
        while not stop_requested.is_set():
            now = sgt_now()
            window = _window_start(now - timedelta(milliseconds=250), DEFAULT_WINDOW_SECONDS)
            if window != last_window:
                seed_safe_integration_preview(integration, now=now)
                _apply_demo_state(integration, state)
                last_window = window
            time.sleep(0.1)

    thread = Thread(target=update, name="phase12.2-safe-preview", daemon=True)
    thread.start()
    return stop_requested

def run_dashboard(app):
    config = app.aria_aggregator.config["server"]
    app.run(
        host=config["host"],
        port=config["port"],
        debug=config["debug_mode_allowed"],
    )

def main(argv=None, *, app_factory=create_dashboard_app, run=True):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo and args.input_scope is None:
        parser.error("--demo requires --input-scope synthetic or non_research")
    if args.input_scope is not None and not args.demo:
        parser.error("--input-scope is only valid with --demo")
    if args.demo_state is not None and not args.demo:
        parser.error("--demo-state is only valid with --demo")

    aggregator = DashboardStateAggregator()
    integration = LocalDashboardIntegration(aggregator=aggregator)
    if args.demo:
        seed_safe_integration_preview(integration)
        _apply_demo_state(integration, args.demo_state or "ready")
    app = app_factory(aggregator)
    app.aria_integration = integration
    if run:
        stop_preview = (
            start_safe_preview_heartbeat(integration, args.demo_state or "ready")
            if args.demo
            else None
        )
        try:
            run_dashboard(app)
        finally:
            if stop_preview is not None:
                stop_preview.set()
    return app

if __name__ == "__main__":
    main()