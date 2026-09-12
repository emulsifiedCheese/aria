import pytest
from aria.vision import detector as detector_module

class FakeModel:
    def __init__(self, model_name):
        self.model_name = model_name
        self.calls = []

    def track(self, **kwargs):
        self.calls.append(kwargs)
        return ["result"]

def test_detector_uses_zone_a_bytetrack_configuration(monkeypatch):
    monkeypatch.setattr(detector_module, "YOLO", FakeModel)
    detector = detector_module.PersonDetector(
        model_name="test.pt",
        confidence=0.6,
        iou=0.35,
        tracker_config="config/bytetrack.zone_a.yaml",
    )

    result = detector.track("masked-frame")

    assert result == "result"
    assert detector.model.calls == [
        {
            "source": "masked-frame",
            "persist": True,
            "tracker": "config/bytetrack.zone_a.yaml",
            "classes": [0],
            "conf": 0.6,
            "iou": 0.35,
            "imgsz": 640,
            "verbose": False,
        }
    ]

def test_pose_tracker_uses_one_pose_model_call(monkeypatch):
    monkeypatch.setattr(detector_module, "YOLO", FakeModel)
    tracker = detector_module.PoseTracker(
        model_name="pose-test.pt",
        inference_size=960,
        device="cpu",
    )

    result = tracker.track("masked-frame")

    assert result == "result"
    assert tracker.model.model_name == "pose-test.pt"
    assert tracker.model.calls[0]["imgsz"] == 960
    assert tracker.model.calls[0]["device"] == "cpu"

def test_detector_rejects_invalid_nms_iou_before_loading_model(monkeypatch):
    monkeypatch.setattr(detector_module, "YOLO", FakeModel)

    with pytest.raises(ValueError, match="iou"):
        detector_module.PersonDetector(iou=0)