"""Invented numerical fixtures only; never open a camera or a participant file."""
from datetime import timedelta
from pathlib import Path
from aria.dashboard.integration import LocalDashboardIntegration
from aria.fusion.window_builder import _window_start
from aria.timebase import sgt_now
from .runtime import NODES, WindowRuntime
from .runtime_io import SandboxFirebase

def camera_record(at, track=1, frame=1):
    return {
        "schema_version": 2, "record_type": "track", "camera_id": "camera_a", "zone": "A",
        "frame_number": frame, "frame_timestamp_sgt": at.isoformat(timespec="milliseconds"),
        "frame_available": True, "pose_available": True, "local_track_id": track,
        "bounding_box": [10 + track * 120, 20, 110 + track * 120, 220],
        "detection_confidence": .8,
        "keypoints": [[float(i * 10 + track * 120), float(i * 5)] for i in range(17)],
        "keypoint_confidences": [.9] * 17, "capture_latency_ms": 10.,
        "detection_latency_ms": 20., "pose_latency_ms": 30., "total_latency_ms": 60.,
        "mask_config_version": "batamfast-v2",
    }

def sensor_record(at, node, sequence=1):
    payload = {
        "schema_version": 1, "firmware_version": "1.1.1",
        "sensor_config": "A_PIR_US_MIC" if node == "ESP-A1" else "A_PIR_MIC",
        "boot_id": 1301, "node_id": node, "zone": "A", "sequence": sequence,
        "timestamp_ms": sequence * 1000, "wifi_connected": True, "wifi_rssi_dbm": -60,
        "pir_motion": False, "pir_recent_activity": True,
        "audio_peak_to_peak": 12, "audio_activity": 3, "audio_rms": 5,
    }
    if node == "ESP-A1":
        payload.update(distance_cm=51, distance_valid=True)
    return {
        "received_at_sgt": at.isoformat(timespec="milliseconds"), "source_ip": "127.0.0.1",
        "source_port": 4210 if node == "ESP-A1" else 4211, "payload": payload,
    }

def run_synthetic(*, now=None):
    current = [_window_start(now or sgt_now(), 2)]
    cloud = SandboxFirebase(now=lambda: current[0])
    outbox_path = Path(cloud.directory.name)
    integration = LocalDashboardIntegration(firebase_sync=cloud)
    runtime = WindowRuntime(integration=integration, now=current[0])
    checks = {}
    frame = 0

    def step(*, camera=True, nodes=NODES):
        nonlocal frame
        frame += 1
        start = runtime.next_window
        observed = start + timedelta(seconds=1.75)
        current[0] = observed
        for node in nodes:
            runtime.sensor_record(sensor_record(observed, node, frame), now=observed)
        if camera:
            runtime.camera_batch(
                [camera_record(observed, track, frame) for track in (1, 2)],
                capture_fps=30., processing_fps=7., now=observed,
            )
        current[0] = start + timedelta(seconds=3)
        runtime.tick(current[0])
        return integration.snapshot(current[0])

    try:
        runtime.resume(verified=True, now=current[0])
        state = step()
        checks["real_model_multiple_tracks"] = (
            state["overall_status"] == "ready" and len(state["predictions"]) == 2
            and all(p["prediction_available"] for p in state["predictions"])
        )
        checks["projector_outbox_simulated_delivery"] = cloud.flush(current[0])["delivered"] == 2
        cloud.set_offline(True)
        state = step()
        checks["offline_local_continuity"] = (
            state["overall_status"] == "ready"
            and cloud.flush(current[0])["failure"] == "unavailable"
            and cloud.summary()["pending"] == 2
        )
        state = step(nodes=("ESP-A2",))
        checks["a1_loss_camera_inference"] = all(
            p["prediction_available"] and not p["availability"]["esp_a1_available"]
            for p in state["predictions"]
        )
        state = step(nodes=("ESP-A1",))
        checks["a2_loss_camera_inference"] = all(
            p["prediction_available"] and not p["availability"]["esp_a2_available"]
            for p in state["predictions"]
        )
        cloud.set_offline(False)
        checks["queued_delivery_after_recovery"] = (
            cloud.flush(current[0])["failure"] is None and cloud.summary()["pending"] == 0
        )
        state = step(camera=False)
        checks["camera_loss_clears_activity"] = (
            len(state["predictions"]) == 1
            and state["predictions"][0]["predicted_activity"] is None
            and state["predictions"][0]["confidence"] is None
        )
        count_before = runtime.counts["predictions"]
        runtime.pause()
        cloud.purge()
        step()
        checks["privacy_pause_no_inference_or_stale_activity"] = (
            runtime.counts["predictions"] == count_before
            and integration.snapshot(current[0])["predictions"] == []
            and runtime.buffered_records == 0
            and cloud.summary()["pending"] == 0
        )
        runtime.resume(verified=True, now=current[0])
        state = step()
        checks["fresh_resume"] = len(state["predictions"]) == 2
        runtime.stop()
        checks["clean_stop_counts"] = (
            runtime.summary()["record_accounting_balanced"]
            and runtime.buffered_records == 0
            and not integration.snapshot(current[0])["predictions"]
        )
        checks["no_feature_or_prediction_files"] = not list(outbox_path.glob("*.jsonl"))
        summary = runtime.summary()
    finally:
        runtime.stop()
        cloud.close()
    checks["temporary_outbox_removed"] = not outbox_path.exists()
    return {
        "input_scope": "synthetic", "live_hardware_used": False,
        "live_firebase_accessed": False, "participant_data_used": False,
        "external_test_accessed": False, "phase_13_1_complete": False,
        "checks": checks, "runtime": summary,
    }
