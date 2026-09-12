import cv2
import pytest
from aria.cameras.camera_manager import CameraManager

class FakeCapture:
    def __init__(self, width=1920, height=1080, fps=30, opened=True):
        self.values = {
            cv2.CAP_PROP_FRAME_WIDTH: width,
            cv2.CAP_PROP_FRAME_HEIGHT: height,
            cv2.CAP_PROP_FPS: fps,
        }
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def set(self, property_id, value):
        self.values[property_id] = value
        return True

    def get(self, property_id):
        return self.values[property_id]

    def release(self):
        self.released = True

def test_default_capture_mode_is_1080p_at_30_fps(monkeypatch):
    capture = FakeCapture()
    monkeypatch.setattr(cv2, "VideoCapture", lambda source: capture)

    manager = CameraManager(camera_id="camera_a", source=0)
    manager.open()

    assert manager.stats.requested_width == 1920
    assert manager.stats.requested_height == 1080
    assert manager.stats.requested_fps == 30
    assert manager.stats.actual_width == 1920
    assert manager.stats.actual_height == 1080
    assert manager.stats.actual_fps == 30

def test_unsupported_capture_mode_is_rejected(monkeypatch):
    capture = FakeCapture(width=640, height=480, fps=30)

    def ignore_mode_request(property_id, value):
        return False

    capture.set = ignore_mode_request
    monkeypatch.setattr(cv2, "VideoCapture", lambda source: capture)

    manager = CameraManager(camera_id="camera_a", source=1)

    with pytest.raises(RuntimeError, match="required capture mode"):
        manager.open()

    assert capture.released is True
    assert manager.capture is None

def test_prerecorded_source_can_keep_its_native_mode(monkeypatch):
    capture = FakeCapture(width=640, height=480, fps=25)

    def ignore_mode_request(property_id, value):
        return False

    capture.set = ignore_mode_request
    monkeypatch.setattr(cv2, "VideoCapture", lambda source: capture)

    manager = CameraManager(camera_id="camera_a",source="test-video.mp4",enforce_capture_mode=False,)
    manager.open()

    assert manager.stats.actual_width == 640
    assert manager.stats.actual_height == 480
    assert manager.stats.actual_fps == 25