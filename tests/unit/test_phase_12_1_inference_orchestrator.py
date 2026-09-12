import json
from datetime import datetime, timedelta
import pytest
from aria.inference.orchestrator import (
    LocalInferenceOrchestrator,
    LocalPredictionWriter,
    PredictionDeliveryError,
)
from aria.inference.service import LocalInferenceService
from aria.timebase import SGT
from scripts.run_local_inference import main

SESSION_ID = "zone_a_20260824T130000SGT_demo0002"

def _camera_record(timestamp, *, frame_number=1, track_id=7):
    return {
        "schema_version": 2,
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": frame_number,
        "frame_timestamp_sgt": timestamp.isoformat(timespec="milliseconds"),
        "frame_available": True,
        "pose_available": True,
        "local_track_id": track_id,
        "bounding_box": [10, 20, 110, 220],
        "detection_confidence": 0.8,
        "keypoints": [[float(index * 10), float(index * 5)] for index in range(17)],
        "keypoint_confidences": [0.9] * 17,
        "capture_latency_ms": 10.0,
        "detection_latency_ms": 20.0,
        "pose_latency_ms": 30.0,
        "total_latency_ms": 60.0,
        "mask_config_version": "synthetic-v1",
        "_timestamp": timestamp,
    }

@pytest.fixture(scope="module")
def service():
    return LocalInferenceService()

def _orchestrator(tmp_path, service, callback=None):
    writer = LocalPredictionWriter(tmp_path / "predictions.jsonl",validator=service.prediction_validator,)
    return LocalInferenceOrchestrator(service,writer=writer,on_prediction=callback,)

def test_completed_window_isolates_tracks_and_writes_once(tmp_path, service):
    start = datetime(2026, 8, 24, 13, 0, 0, tzinfo=SGT)
    callbacks = []
    orchestrator = _orchestrator(tmp_path, service, callbacks.append)
    camera = [
        _camera_record(start + timedelta(milliseconds=250), track_id=8),
        _camera_record(
            start + timedelta(milliseconds=500),
            frame_number=2,
            track_id=7,
        ),
    ]

    first = orchestrator.process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=camera,
        sensor_records={"ESP-A1": [], "ESP-A2": []},
    )
    second = orchestrator.process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=list(reversed(camera)),
        sensor_records={"ESP-A1": [], "ESP-A2": []},
    )

    assert [record["local_track_id"] for record in first["predictions"]] == [7, 8]
    assert len({record["prediction_id"] for record in first["predictions"]}) == 2
    assert first["written_count"] == 2
    assert second["written_count"] == 0
    assert len(callbacks) == 2
    assert len((tmp_path / "predictions.jsonl").read_text().splitlines()) == 2

def test_no_camera_track_emits_one_explicit_null_track_record(tmp_path, service):
    start = datetime(2026, 8, 24, 13, 0, 2, tzinfo=SGT)
    orchestrator = _orchestrator(tmp_path, service)

    result = orchestrator.process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=[],
        sensor_records={"ESP-A1": [], "ESP-A2": []},
    )

    assert result["written_count"] == 1
    prediction = result["predictions"][0]
    assert prediction["local_track_id"] is None
    assert prediction["prediction_available"] is False
    assert prediction["predicted_activity"] is None
    assert prediction["confidence"] is None
    assert prediction["unavailable_reason"] == "missing_camera_track"

def test_writer_rejects_conflicting_retry(tmp_path, service):
    output = tmp_path / "predictions.jsonl"
    writer = LocalPredictionWriter(output, validator=service.prediction_validator)
    start = datetime(2026, 8, 24, 13, 0, 4, tzinfo=SGT)
    record = LocalInferenceOrchestrator(service).process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=[_camera_record(start + timedelta(milliseconds=250))],
        sensor_records={"ESP-A1": [], "ESP-A2": []},
    )["predictions"][0]

    assert writer.append(record) is True
    changed = dict(record, emitted_at_sgt="2026-08-24T13:00:07.000+08:00")
    with pytest.raises(PredictionDeliveryError, match="conflicting prediction retry"):
        writer.append(changed)

def test_writer_rejects_invalid_existing_log(tmp_path, service):
    output = tmp_path / "predictions.jsonl"
    output.write_text('{"participant_name":"not allowed"}\n', encoding="utf-8")
    with pytest.raises(PredictionDeliveryError, match="invalid existing prediction"):
        LocalPredictionWriter(output, validator=service.prediction_validator)

def test_writer_restart_preserves_idempotency(tmp_path, service):
    output = tmp_path / "predictions.jsonl"
    start = datetime(2026, 8, 24, 13, 0, 6, tzinfo=SGT)
    first_writer = LocalPredictionWriter(output, validator=service.prediction_validator)
    orchestrator = LocalInferenceOrchestrator(service, writer=first_writer)
    result = orchestrator.process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=[_camera_record(start + timedelta(milliseconds=250))],
        sensor_records={"ESP-A1": [], "ESP-A2": []},
    )
    restarted = LocalPredictionWriter(output, validator=service.prediction_validator)
    assert result["written_count"] == 1
    assert restarted.append(result["predictions"][0]) is False
    assert len(output.read_text().splitlines()) == 1

def test_cli_processes_only_declared_non_research_records(tmp_path):
    start = datetime(2026, 8, 24, 13, 1, 0, tzinfo=SGT)
    camera_path = tmp_path / "camera.jsonl"
    sensor_path = tmp_path / "sensors.jsonl"
    output_path = tmp_path / "predictions.jsonl"
    camera = _camera_record(start + timedelta(milliseconds=250))
    camera.pop("_timestamp")
    camera_path.write_text(json.dumps(camera) + "\n", encoding="utf-8")
    sensor_path.write_text("", encoding="utf-8")

    main([
        "--camera-input", str(camera_path),
        "--sensor-input", str(sensor_path),
        "--session-id", SESSION_ID,
        "--output", str(output_path),
        "--input-scope", "synthetic",
    ])

    records = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["local_track_id"] == 7
    assert records[0]["prediction_available"] is True
    assert "participant_id" not in records[0]
    assert "feature_vector" not in records[0]

def test_cli_requires_an_explicit_safe_input_scope(tmp_path):
    with pytest.raises(SystemExit):
        main([
            "--camera-input", str(tmp_path / "camera.jsonl"),
            "--sensor-input", str(tmp_path / "sensors.jsonl"),
            "--session-id", SESSION_ID,
            "--output", str(tmp_path / "predictions.jsonl"),
        ])