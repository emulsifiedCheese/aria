import json
from queue import Queue
from threading import Event
import numpy as np
import pytest
from aria.acceptance.equipment_runtime import EquipmentCheck, camera_health_loop
from aria.acceptance.live_runtime import main
from aria.acceptance.synthetic_runtime import sensor_record
from aria.cameras.privacy_mask import MaskConfig
from aria.collection.preflight import PreflightError, PreflightReport, REQUIRED_CHECKS
from aria.timebase import sgt_now

def test_equipment_cli_routes_away_from_inference_and_recording(monkeypatch):
    from aria.acceptance import equipment_runtime, live_runtime
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    def forbidden(*args, **kwargs):
        raise AssertionError("recording/inference path invoked")
    monkeypatch.setattr(live_runtime, "run_hardware", forbidden)
    monkeypatch.setattr(live_runtime, "RunEvidence", forbidden)
    monkeypatch.setattr(live_runtime, "SandboxFirebase", forbidden)
    monkeypatch.setattr(equipment_runtime, "run_equipment", lambda: 7)
    assert main(["--input-scope", "non_research", "--equipment-only",
                 "--approved-staff-present", "--mask-alignment-confirmed",
                 "--dji-recording-disabled"]) == 7

@pytest.mark.parametrize("arguments", [
    ["--input-scope", "non_research", "--approved-staff-present"],
    ["--input-scope", "non_research", "--equipment-only"],
    ["--input-scope", "synthetic", "--equipment-only"],
    ["--input-scope", "participant", "--equipment-only"],
])

def test_equipment_cli_rejects_unsafe_combinations(arguments):
    with pytest.raises(SystemExit):
        main(arguments)

def test_camera_health_masks_and_discards_pixels_without_recognition(monkeypatch):
    from aria.acceptance import equipment_runtime
    stop, ready, queue = Event(), Event(), Queue()
    masked_calls = []
    actual_mask = equipment_runtime.apply_privacy_mask
    def mask_frame(frame, mask, camera_id):
        result = actual_mask(frame, mask, camera_id)
        assert not result[:, :2].any()
        masked_calls.append(True)
        return result
    monkeypatch.setattr(equipment_runtime, "apply_privacy_mask", mask_frame)
    class Camera:
        closed = False
        count = 0
        def __init__(self, **kwargs):
            assert kwargs["enforce_capture_mode"] is True
        def open(self):
            pass
        def read(self):
            self.count += 1
            if self.count == 3:
                stop.set()
            return np.ones((8, 8, 3), dtype=np.uint8)
        def close(self):
            Camera.closed = True
    mask = MaskConfig("camera_a", 8, 8, 2, 0, 6, 8, True)
    times = iter((0., 1., 2.))
    camera_health_loop(queue, stop, ready, mask, camera_factory=Camera, clock=lambda: next(times))
    assert ready.is_set() and Camera.closed and len(masked_calls) == 2
    assert queue.qsize() == 2
    for _ in range(2):
        message = queue.get_nowait()
        assert set(message) == {"kind", "frames", "last_frame_at", "capture_fps"}
        json.dumps(message)  #no image arrays, tracks, poses or activity records

def test_camera_health_fails_closed_on_invalid_mask():
    class Camera:
        closed = False
        def __init__(self, **kwargs):
            pass
        def open(self):
            pass
        def read(self):
            return np.ones((8, 8, 3), dtype=np.uint8)
        def close(self):
            Camera.closed = True
    queue = Queue()
    with pytest.raises(ValueError):
        camera_health_loop(queue, Event(), Event(), None, camera_factory=Camera)
    assert Camera.closed and queue.empty()

class CameraStub:
    def __init__(self, mask, *, equipment_only):
        assert equipment_only is True
        self.process = self
        self.failed = Event()
        self.messages = []
        self.alive = False
    def start(self):
        self.alive = True
    def is_alive(self):
        return self.alive
    def poll(self):
        messages, self.messages = self.messages, []
        return iter(messages)
    def stop(self):
        self.alive = False
        return {"stopped": True, "forced": False}

class SocketStub:
    def __init__(self, *args):
        self.messages = []
        self.closed = False
    def bind(self, address):
        assert address == ("0.0.0.0", 5005)
    def setblocking(self, value):
        assert value is False
    def recvfrom(self, size):
        if not self.messages:
            raise BlockingIOError
        return self.messages.pop(0), ("127.0.0.1", 4210)
    def close(self):
        self.closed = True

def report(passed):
    return PreflightReport(sgt_now().isoformat(), {name: passed for name in REQUIRED_CHECKS})

def test_equipment_health_only_no_model_cloud_or_output_files(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("model or cloud instantiated")
    monkeypatch.setattr("aria.inference.service.LocalInferenceService.__init__", forbidden)
    monkeypatch.setattr("aria.acceptance.runtime_io.SandboxFirebase.__init__", forbidden)
    monkeypatch.chdir(tmp_path)
    check = EquipmentCheck(camera_factory=CameraStub, socket_factory=SocketStub, preflight_runner=lambda config: report(True))
    check.start()
    sock, camera = check.udp, check.camera
    for node in ("ESP-A1", "ESP-A2"):
        sock.messages.append(json.dumps(sensor_record(sgt_now(), node)["payload"]).encode())
    camera.messages.append({"kind": "equipment_health", "frames": 30, "last_frame_at": sgt_now().isoformat(), "capture_fps": 30.})
    check.poll()
    status = check.status()
    assert status["camera"]["fresh"]
    assert all(value["fresh"] for value in status["sensors"].values())
    assert all(value["packets_received"] == 1 for value in status["sensors"].values())
    assert status["activity_inference"] is False and status["recording"] is False
    assert "audio" not in json.dumps(status) and "predictions" not in status
    check.pause()
    assert not camera.alive and sock.closed
    assert not check.status()["camera"]["mask_verified"]
    assert list(tmp_path.iterdir()) == []

def test_equipment_failed_preflight_opens_no_producers():
    def forbidden(*args, **kwargs):
        raise AssertionError("producer opened")
    check = EquipmentCheck(camera_factory=forbidden, socket_factory=forbidden,
                           preflight_runner=lambda config: report(False))
    with pytest.raises(PreflightError):
        check.start()
    assert check.state == "paused" and check.camera is None and check.udp is None

def test_equipment_rejects_track_records():
    check = EquipmentCheck(camera_factory=CameraStub, socket_factory=SocketStub,
                           preflight_runner=lambda config: report(True))
    check.start()
    try:
        check.camera.messages.append({"kind": "frame", "records": [{"record_type": "track"}]})
        with pytest.raises(RuntimeError, match="unexpected_camera_payload"):
            check.poll()
    finally:
        check.pause()