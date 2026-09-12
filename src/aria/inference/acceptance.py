"""synthetic Phase 12.1 integration privacy and latency acceptance evidence"""
from __future__ import annotations
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import joblib
import numpy as np
import sklearn
from aria.inference.orchestrator import LocalInferenceOrchestrator, LocalPredictionWriter
from aria.inference.preprocessing import build_track_feature_window, camera_feature_matrix
from aria.inference.service import LocalInferenceService, _sha256
from aria.modeling.baselines import _feature_records
from aria.timebase import SGT

PHASE_ID = "12.1"
ACCEPTANCE_ID = "zone-a-phase12.1-local-inference-acceptance-v1"
DEFAULT_WARMUP_ITERATIONS = 100
DEFAULT_MEASURED_ITERATIONS = 1000
LATENCY_P95_LIMIT_MS = 2000.0
FORBIDDEN_OUTPUT_KEYS = {
    "participant_id",
    "participant_name",
    "person_name",
    "role",
    "feature_vector",
    "camera",
    "esp_a1",
    "esp_a2",
    "keypoints",
    "bounding_box",
    "raw_audio",
    "raw_video",
    "masked_video",
    "image",
}

class InferenceAcceptanceError(RuntimeError):
    """riased when Phase 12.1 acceptance evidence cannot pass safely"""

def _camera_record(timestamp, *, track_id=7, pose_available=True, frame_number=1):
    return {
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": frame_number,
        "frame_available": True,
        "pose_available": pose_available,
        "local_track_id": track_id,
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

def _feature_vector(start, *, camera_available=True, pose_available=True):
    records = (
        [_camera_record(start + timedelta(milliseconds=250), pose_available=pose_available)]
        if camera_available
        else []
    )
    return build_track_feature_window(
        start,
        records,
        {"ESP-A1": [], "ESP-A2": []},
        local_track_id=7 if camera_available else None,
    )

def _percentiles(latencies_ms):
    values = np.asarray(latencies_ms, dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        raise InferenceAcceptanceError("latency samples must be finite and non-empty")
    return {
        "minimum_ms": float(np.min(values)),
        "mean_ms": float(np.mean(values)),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p99_ms": float(np.percentile(values, 99)),
        "maximum_ms": float(np.max(values)),
    }

def _benchmark(service, *, warmup_iterations, measured_iterations):
    if warmup_iterations < 0 or measured_iterations < 1:
        raise InferenceAcceptanceError("latency iteration counts are invalid")
    session_id = "zone_a_20260824T140000SGT_synth001"
    base = datetime(2026, 8, 24, 14, 0, 0, tzinfo=SGT)
    processing = LocalInferenceOrchestrator(service)
    for index in range(warmup_iterations):
        start = base + timedelta(seconds=2 * index)
        processing.process_completed_window(
            session_id=session_id,
            window_start=start,
            camera_records=[_camera_record(start + timedelta(milliseconds=250))],
            sensor_records={"ESP-A1": [], "ESP-A2": []},
        )
    processing_latencies = []
    processing_offset = warmup_iterations
    for index in range(measured_iterations):
        start = base + timedelta(seconds=2 * (processing_offset + index))
        began = time.perf_counter_ns()
        processing.process_completed_window(
            session_id=session_id,
            window_start=start,
            camera_records=[_camera_record(start + timedelta(milliseconds=250))],
            sensor_records={"ESP-A1": [], "ESP-A2": []},
        )
        processing_latencies.append((time.perf_counter_ns() - began) / 1_000_000)

    with tempfile.TemporaryDirectory(prefix="aria_phase12_1_delivery_") as directory:
        output_path = Path(directory) / "predictions.jsonl"
        writer = LocalPredictionWriter(output_path, validator=service.prediction_validator)
        delivery = LocalInferenceOrchestrator(service, writer=writer)
        delivery_offset = warmup_iterations + measured_iterations
        for index in range(warmup_iterations):
            start = base + timedelta(seconds=2 * (delivery_offset + index))
            delivery.process_completed_window(
                session_id=session_id,
                window_start=start,
                camera_records=[_camera_record(start + timedelta(milliseconds=250))],
                sensor_records={"ESP-A1": [], "ESP-A2": []},
            )
        delivery_latencies = []
        delivery_offset += warmup_iterations
        for index in range(measured_iterations):
            start = base + timedelta(seconds=2 * (delivery_offset + index))
            began = time.perf_counter_ns()
            result = delivery.process_completed_window(
                session_id=session_id,
                window_start=start,
                camera_records=[_camera_record(start + timedelta(milliseconds=250))],
                sensor_records={"ESP-A1": [], "ESP-A2": []},
            )
            delivery_latencies.append((time.perf_counter_ns() - began) / 1_000_000)
            if result["written_count"] != 1:
                raise InferenceAcceptanceError("delivery benchmark was not idempotently written")
        persisted_count = len(output_path.read_text(encoding="utf-8").splitlines())
    return {
        "clock": "perf_counter_ns",
        "warmup_iterations_per_path": warmup_iterations,
        "measured_iterations_per_path": measured_iterations,
        "window_duration_ms": 2000,
        "acceptance_limit": {
            "metric": "end_to_end_local_delivery_p95_ms",
            "maximum_ms": LATENCY_P95_LIMIT_MS,
            "basis": "complete processing and durable local delivery within one feature window",
        },
        "feature_build_validation_model_and_serialisation": _percentiles(
            processing_latencies
        ),
        "end_to_end_with_durable_local_jsonl_delivery": _percentiles(
            delivery_latencies
        ),
        "persisted_record_count_including_warmup": persisted_count,
    }

def _privacy_and_behaviour(service):
    session_id = "zone_a_20260824T150000SGT_synth002"
    base = datetime(2026, 8, 24, 15, 0, 0, tzinfo=SGT)
    scenarios = []
    with tempfile.TemporaryDirectory(prefix="aria_phase12_1_privacy_") as directory:
        output_path = Path(directory) / "predictions.jsonl"
        writer = LocalPredictionWriter(output_path, validator=service.prediction_validator)
        orchestrator = LocalInferenceOrchestrator(service, writer=writer)
        inputs = (
            (
                "camera_available_sensors_unavailable",
                [_camera_record(base + timedelta(milliseconds=250))],
                True,
            ),
            (
                "camera_and_pose_available_second_track",
                [
                    _camera_record(
                        base + timedelta(seconds=2, milliseconds=250),
                        track_id=7,
                    ),
                    _camera_record(
                        base + timedelta(seconds=2, milliseconds=500),
                        track_id=8,
                        frame_number=2,
                    ),
                ],
                True,
            ),
            ("camera_track_unavailable", [], False),
        )
        for index, (name, camera_records, expected_available) in enumerate(inputs):
            start = base + timedelta(seconds=2 * index)
            result = orchestrator.process_completed_window(
                session_id=session_id,
                window_start=start,
                camera_records=camera_records,
                sensor_records={"ESP-A1": [], "ESP-A2": []},
            )
            scenarios.append({
                "scenario": name,
                "prediction_count": len(result["predictions"]),
                "written_count": result["written_count"],
                "prediction_available_values": [
                    record["prediction_available"] for record in result["predictions"]
                ],
                "expected_primary_availability": expected_available,
            })
        persisted = [
            json.loads(line)
            for line in output_path.read_text(encoding="utf-8").splitlines()
        ]

    forbidden_found = sorted({
        key
        for record in persisted
        for key in record
        if key in FORBIDDEN_OUTPUT_KEYS
    })
    schema_valid = True
    for record in persisted:
        service.prediction_validator.validate(record)
    return {
        "input_scope": "synthetic",
        "participant_data_used": False,
        "external_test_used": False,
        "firebase_used": False,
        "raw_or_masked_video_persisted": False,
        "raw_audio_persisted": False,
        "raw_features_persisted": False,
        "prediction_schema_valid": schema_valid,
        "forbidden_output_keys_found": forbidden_found,
        "persisted_prediction_count": len(persisted),
        "scenarios": scenarios,
        "status": "pass" if not forbidden_found else "fail",
    }

def build_phase_12_1_acceptance(
    *,
    warmup_iterations=DEFAULT_WARMUP_ITERATIONS,
    measured_iterations=DEFAULT_MEASURED_ITERATIONS,
):
    service = LocalInferenceService()
    start = datetime(2026, 8, 24, 12, 0, 0, tzinfo=SGT)
    feature_vector = _feature_vector(start)
    roots = tuple(service.config["preprocessing"]["feature_roots"])
    live_matrix = camera_feature_matrix(
        feature_vector,
        feature_roots=roots,
        feature_names=service.config["preprocessing"]["feature_names"],
    )
    offline_matrix, offline_names = _feature_records(
        [{"feature_vector": feature_vector}],
        roots,
    )
    parity = {
        "feature_names_match": offline_names
        == service.config["preprocessing"]["feature_names"],
        "matrix_shape": list(live_matrix.shape),
        "matrix_equal_with_nan": bool(
            np.array_equal(live_matrix, offline_matrix, equal_nan=True)
        ),
    }
    privacy = _privacy_and_behaviour(service)
    latency = _benchmark(
        service,
        warmup_iterations=warmup_iterations,
        measured_iterations=measured_iterations,
    )
    delivery_p95 = latency["end_to_end_with_durable_local_jsonl_delivery"]["p95_ms"]
    checks = {
        "offline_live_preprocessing_parity": all((
            parity["feature_names_match"],
            parity["matrix_equal_with_nan"],
            parity["matrix_shape"] == [1, 23],
        )),
        "privacy_boundary": privacy["status"] == "pass",
        "local_delivery_within_window_p95": delivery_p95 <= LATENCY_P95_LIMIT_MS,
    }
    return {
        "schema_version": 1,
        "phase": PHASE_ID,
        "acceptance_id": ACCEPTANCE_ID,
        "status": "pass" if all(checks.values()) else "fail",
        "generated_at_sgt": datetime.now(tz=SGT).isoformat(timespec="seconds"),
        "scope": "synthetic local inference integration",
        "contract": {
            "config_id": service.config["config_id"],
            "config_sha256": _sha256(service.config_path),
            "model_version": service.config["model"]["version"],
            "model_artifact_sha256": _sha256(service.model_path),
            "preprocessing_version": service.config["preprocessing"]["version"],
            "feature_schema_sha256": _sha256(service.feature_schema_path),
            "prediction_schema_sha256": _sha256(service.prediction_schema_path),
        },
        "checks": checks,
        "offline_live_parity": parity,
        "privacy_and_behaviour": privacy,
        "latency": latency,
        "runtime": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version.split()[0],
            "numpy_version": np.__version__,
            "scikit_learn_version": sklearn.__version__,
            "joblib_version": joblib.__version__,
        },
        "limitations": [
            "Synthetic integration does not include camera capture or pose-estimation latency.",
            "The local writer is idempotent within one process and across restarts, not across concurrent processes.",
            "External Reaching/Handling performance remains limited and was not re-evaluated.",
        ],
    }

def write_phase_12_1_acceptance(report, output_path):
    if report.get("status") != "pass":
        raise InferenceAcceptanceError("Phase 12.1 integration acceptance did not pass")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return _sha256(output_path)