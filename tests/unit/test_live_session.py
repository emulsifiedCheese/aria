import json
import socket
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import time
import pytest
from aria.collection.live_session import (
    CameraSessionWriter,
    ControlledCameraFeatureWriter,
    TelemetrySessionWriter,
    build_parser,
    current_window_id,
    validate_cli_args,
)
from aria.collection.preflight import PauseStopController
from aria.timebase import SGT

def context(tmp_path):
    return SimpleNamespace(
        session_id="zone_a_20260801T111129SGT_test0001",
        manifest_path=tmp_path / "manifests" / "session.json",
        pause_stop_controller=PauseStopController(),
    )

def packet(node_id, sequence):
    value = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC",
        "boot_id": 10,
        "node_id": node_id,
        "zone": "A",
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -55,
        "pir_motion": False,
        "pir_recent_activity": False,
        "audio_peak_to_peak": 4,
        "audio_activity": 1.0,
        "audio_rms": 1.0,
    }
    if node_id == "ESP-A1":
        value["distance_cm"] = 100.0
        value["distance_valid"] = True
    return json.dumps(value).encode()

class FakeSocket:
    def __init__(self, packets):
        self.packets = list(packets)
        self.closed = False

    def bind(self, address):
        self.address = address

    def settimeout(self, timeout):
        self.timeout = timeout

    def recvfrom(self, size):
        if self.closed:
            raise OSError("closed")
        if self.packets:
            return self.packets.pop(0), ("10.0.0.2", 4210)
        time.sleep(0.001)
        raise socket.timeout()

    def close(self):
        self.closed = True

def wait_for_count(writer, count):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if writer.session_summary()["written_record_count"] >= count:
            return
        time.sleep(0.005)
    raise AssertionError("writer did not receive expected records")

def test_telemetry_writer_owns_valid_session_output(tmp_path):
    fake_socket = FakeSocket(
        [
            packet("ESP-A1", 1),
            packet("ESP-A2", 1),
            packet("ESP-A1", 3),
        ]
    )
    writer = TelemetrySessionWriter(
        context(tmp_path),
        socket_factory=lambda *args: fake_socket,
    )
    wait_for_count(writer, 3)
    writer.close()

    summary = writer.session_summary()
    assert summary["observed_record_count"] == 3
    assert summary["written_record_count"] == 3
    assert summary["gap_count"] == 1
    assert summary["relative_path"].startswith("sessions/")
    records = [
        json.loads(line)
        for line in writer.output_path.read_text().splitlines()
    ]
    assert {record["payload"]["node_id"] for record in records} == {"ESP-A1","ESP-A2",}

def test_telemetry_writer_excludes_packets_while_paused(tmp_path):
    writer_context = context(tmp_path)
    writer_context.pause_stop_controller.pause()
    fake_socket = FakeSocket([packet("ESP-A1", 1), packet("ESP-A2", 1)])
    writer = TelemetrySessionWriter(
        writer_context,
        socket_factory=lambda *args: fake_socket,
    )
    deadline = time.monotonic() + 1
    while (
        writer.session_summary()["excluded_record_count"] < 2
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)
    writer.close()

    assert writer.session_summary()["observed_record_count"] == 2
    assert writer.session_summary()["written_record_count"] == 0
    assert writer.session_summary()["excluded_record_count"] == 2
    assert writer.output_path.read_text() == ""

def camera_record(
    frame_number=1,
    timestamp="2026-08-01T11:11:29.000+08:00",
):
    return {
        "schema_version": 2,
        "record_type": "frame_status",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": frame_number,
        "frame_timestamp_sgt": timestamp,
        "frame_available": True,
        "pose_available": False,
        "local_track_id": None,
        "bounding_box": None,
        "detection_confidence": None,
        "keypoints": [],
        "keypoint_confidences": [],
        "capture_latency_ms": 1.0,
        "detection_latency_ms": 1.0,
        "pose_latency_ms": 0.0,
        "total_latency_ms": 2.0,
        "mask_config_version": "batamfast-v1",
    }

def test_camera_feature_writer_obeys_shared_pause(tmp_path):
    writer_context = context(tmp_path)
    writer = ControlledCameraFeatureWriter(writer_context)
    writer.write(camera_record(1))
    writer_context.pause_stop_controller.pause()
    writer.write(camera_record(2))
    writer.close()

    summary = writer.session_summary()
    assert summary["observed_record_count"] == 2
    assert summary["written_record_count"] == 1
    assert summary["excluded_record_count"] == 1
    assert len(writer.output_path.read_text().splitlines()) == 1

def test_camera_exclusion_deletes_written_rows_and_blocks_later_rows(tmp_path):
    writer = ControlledCameraFeatureWriter(context(tmp_path))
    excluded_timestamp = "2026-08-01T11:11:29.000+08:00"
    retained_timestamp = "2026-08-01T11:11:31.000+08:00"
    excluded_window = current_window_id(datetime.fromisoformat(excluded_timestamp))

    writer.write(camera_record(1, excluded_timestamp))
    writer.write(camera_record(2, retained_timestamp))
    assert writer.exclude_windows([excluded_window]) == 1
    assert writer.verify_excluded_windows([excluded_window]) is True

    writer.write(camera_record(3, excluded_timestamp))
    writer.close()

    records = [json.loads(line) for line in writer.output_path.read_text().splitlines()]
    assert [record["frame_number"] for record in records] == [2]
    assert writer.session_summary() == {
        "kind": "camera_features",
        "relative_path": writer.relative_path,
        "observed_record_count": 3,
        "written_record_count": 1,
        "excluded_record_count": 2,
        "gap_count": 0,
        "longest_gap_seconds": 2.0,
    }

def test_camera_session_writer_starts_and_stops_pipeline(tmp_path):
    class FakePreview:
        instance = None

        def __init__(self, port):
            self.port = port
            self.url = f"http://127.0.0.1:{port}/"
            self.frames = []
            self.paused = False
            self.stopped = False
            FakePreview.instance = self

        def start(self):
            return self.url

        def publish(self, frame):
            self.frames.append(frame)

        def pause(self):
            self.paused = True

        def resume(self):
            self.paused = False

        def stop(self):
            self.stopped = True

        def status(self):
            return {
                "url": self.url,
                "paused": self.paused,
                "stopped": self.stopped,
            }

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            self.kwargs["started_callback"]()
            self.kwargs["preview_callback"]("masked-frame")
            self.kwargs["writer"].write(camera_record())
            while not self.kwargs["stop_requested"]():
                time.sleep(0.001)
            self.kwargs["writer"].close()

    writer = CameraSessionWriter(
        context(tmp_path),
        source="test-stream",
        mask_config=object(),
        pipeline_factory=FakePipeline,
        preview_enabled=True,
        preview_port=9876,
        preview_server_factory=FakePreview,
    )
    writer.pause()
    assert FakePreview.instance.paused is True
    writer.resume()
    assert FakePreview.instance.paused is False
    writer.close()

    summary = writer.session_summary()
    assert summary["kind"] == "camera_features"
    assert summary["written_record_count"] == 1
    assert writer.status()["running"] is False
    assert FakePreview.instance.frames == ["masked-frame"]
    assert FakePreview.instance.stopped is True

def test_current_window_id_uses_two_second_epoch_boundary():
    from datetime import datetime, timezone

    value = current_window_id(datetime(2026, 8, 1, 11, 11, 29, 999000, tzinfo=SGT))
    assert value == "zone_a_1785553888000_2000"

def test_live_session_defaults_to_accepted_phase_5_4_profile():
    args = build_parser().parse_args([])

    assert args.session_kind == "non_research_dry_run"
    assert args.participant_id == []
    assert args.acknowledgement_confirmed is False
    assert args.tracker_config == "config/bytetrack.zone_a.persistence.yaml"
    assert args.detector_model == Path("yolov8n.pt")
    assert args.detector_confidence == 0.10
    assert args.detector_iou == 0.70
    assert args.pose_confidence == 0.15
    assert args.keypoint_confidence == 0.5
    assert args.min_confident_keypoints == 4
    assert args.processing_fps == 15.0
    assert args.experimental_track_stitching is False
    assert args.inference_size == 768
    assert args.pose_inference_size == 384
    assert args.masked_track_preview is False
    assert args.preview_port == 8765
    assert args.annotator_id == "A001"

def test_live_session_accepts_pilot_identity_and_acknowledgement_flags():
    args = build_parser().parse_args(
        [
            "--session-kind",
            "pilot",
            "--participant-id",
            "P0001",
            "--participant-id",
            "P0002",
            "--acknowledgement-confirmed",
            "--masked-track-preview",
            "--preview-port",
            "9876",
        ]
    )

    assert args.session_kind == "pilot"
    assert args.participant_id == ["P0001", "P0002"]
    assert args.acknowledgement_confirmed is True
    assert args.masked_track_preview is True
    assert args.preview_port == 9876

def test_pilot_requires_masked_track_preview_before_preflight():
    args = build_parser().parse_args(
        [
            "--session-kind",
            "pilot",
            "--participant-id",
            "P0001",
            "--acknowledgement-confirmed",
            "--dji-recording-disabled",
        ]
    )

    with pytest.raises(SystemExit, match="masked-track-preview"):
        validate_cli_args(args)

def test_preview_port_is_validated_before_preflight():
    args = build_parser().parse_args(
        [
            "--dji-recording-disabled",
            "--preview-port",
            "0",
        ]
    )

    with pytest.raises(SystemExit, match="preview-port"):
        validate_cli_args(args)

def test_annotator_id_is_validated_before_preflight():
    args = build_parser().parse_args(
        [
            "--dji-recording-disabled",
            "--annotator-id",
            "operator-name",
        ]
    )

    with pytest.raises(SystemExit, match="A000"):
        validate_cli_args(args)

def test_detector_iou_is_validated_before_preflight():
    args = build_parser().parse_args(
        [
            "--dji-recording-disabled",
            "--detector-iou",
            "0",
        ]
    )

    with pytest.raises(SystemExit, match="detector-iou"):
        validate_cli_args(args)

def test_detector_model_must_exist_before_preflight(tmp_path):
    args = build_parser().parse_args(
        [
            "--dji-recording-disabled",
            "--detector-model",
            str(tmp_path / "missing.pt"),
        ]
    )

    with pytest.raises(SystemExit, match="existing local file"):
        validate_cli_args(args)

def test_pose_model_must_exist_before_preflight(tmp_path):
    args = build_parser().parse_args(
        [
            "--dji-recording-disabled",
            "--pose-model",
            str(tmp_path / "missing-pose.pt"),
        ]
    )

    with pytest.raises(SystemExit, match="pose-model"):
        validate_cli_args(args)

def test_experimental_track_stitching_is_rejected_for_pilot():
    args = build_parser().parse_args(
        [
            "--session-kind",
            "pilot",
            "--participant-id",
            "P0001",
            "--acknowledgement-confirmed",
            "--dji-recording-disabled",
            "--masked-track-preview",
            "--experimental-track-stitching",
        ]
    )

    with pytest.raises(SystemExit, match="non_research_dry_run"):
        validate_cli_args(args)