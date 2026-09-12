import time
import numpy as np
import pytest
from aria.cameras.privacy_mask import MaskConfig
from aria.vision import pipeline as pipeline_module
from scripts.test_cv_pipeline import build_parser

def test_cli_requires_explicit_privacy_mask_configuration():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--source", "non_research_test.mp4"])

    arguments = parser.parse_args(
        [
            "--source",
            "non_research_test.mp4",
            "--mask-config",
            "config/masks.development.yaml",
        ]
    )

    assert arguments.mask_config == "config/masks.development.yaml"

class FakeCameraManager:
    frames = []
    instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.frames_to_read = list(self.frames)
        self.opened = False
        self.closed = False
        type(self).instance = self

    def open(self):
        self.opened = True

    def read(self):
        if self.frames_to_read:
            return self.frames_to_read.pop(0)
        return None

    def close(self):
        self.closed = True

class FakeModel:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.frames = []
        type(self).instances.append(self)

    def track(self, frame):
        self.frames.append(frame.copy())
        return object()

class FakePoseEstimator:
    instances = []
    outputs = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        type(self).instances.append(self)

    def estimate_many(self, frame, bounding_boxes):
        return list(type(self).outputs)

class FakeFeatureWriter:
    instance = None

    def __init__(self, output_path):
        self.output_path = output_path
        self.records = []
        self.closed = False
        type(self).instance = self

    def write(self, record):
        self.records.append(record)

    def close(self):
        self.closed = True

class FakeLatestMaskedFrameCapture:
    packets = []
    instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.remaining = list(self.packets)
        self.started = False
        self.stopped = False
        type(self).instance = self

    def start(self):
        self.started = True

    def get_latest(self):
        if self.remaining:
            return self.remaining.pop(0)
        return None

    def stop(self):
        self.stopped = True

    def summary(self, processed_frames, elapsed_seconds, processing_fps):
        return {
            "camera_id": "camera_a",
            "elapsed_seconds": elapsed_seconds,
            "processing_fps_target": processing_fps,
            "effective_processing_fps": (
                processed_frames / elapsed_seconds
            ),
            "capture_read_attempts": len(self.packets),
            "captured_frames": sum(
                packet.masked_frame is not None
                for packet in self.packets
            ),
            "processed_frames": processed_frames,
            "replaced_before_processing": 0,
            "read_failures": sum(
                packet.masked_frame is None
                for packet in self.packets
            ),
        }

def packet(frame, frame_number=1):
    return pipeline_module.CapturedFrame(
        frame_number=frame_number,
        frame_timestamp_sgt="2026-07-31T12:00:00.000+08:00",
        received_at_monotonic=time.perf_counter(),
        capture_latency_ms=2.0,
        masked_frame=frame,
    )

@pytest.fixture
def fake_pipeline_dependencies(monkeypatch):
    FakeModel.instances = []
    FakePoseEstimator.instances = []
    FakePoseEstimator.outputs = []
    monkeypatch.setattr(pipeline_module,"CameraManager",FakeCameraManager,)
    monkeypatch.setattr(pipeline_module,"LatestMaskedFrameCapture",FakeLatestMaskedFrameCapture,)
    monkeypatch.setattr(pipeline_module, "PersonDetector", FakeModel)
    monkeypatch.setattr(pipeline_module,"PoseEstimator",FakePoseEstimator,)
    monkeypatch.setattr(pipeline_module,"FeatureWriter",FakeFeatureWriter,)
    monkeypatch.setattr(pipeline_module.cv2,"destroyAllWindows",lambda: None,)

def mask_config():
    return MaskConfig(
        camera_id="camera_a",
        expected_width=4,
        expected_height=4,
        x=1,
        y=1,
        width=2,
        height=2,
        verified=True,
    )

def test_retired_or_unknown_camera_is_rejected():
    with pytest.raises(ValueError, match="only camera_a is active"):
        pipeline_module.CVPipeline(
            camera_id="camera_b",
            source="retired-stream",
            mask_config=mask_config(),
            output_path="unused.jsonl",
        )

@pytest.mark.parametrize(
    ("keyword", "value", "message"),
    [
        ("max_consecutive_dropped_frames", 0, "positive integer"),
        ("processing_fps", 0, "greater than 0"),
        ("processing_fps", 31, "at most 30"),
        ("inference_size", 0, "positive integer"),
        ("pose_inference_size", 0, "positive integer"),
        ("duration_seconds", 0, "greater than 0"),
    ],
)
def test_invalid_pipeline_limits_are_rejected(keyword, value, message):
    arguments = {
        "camera_id": "camera_a",
        "source": "test-stream",
        "mask_config": mask_config(),
        "output_path": "unused.jsonl",
        keyword: value,
    }

    with pytest.raises(ValueError, match=message):
        pipeline_module.CVPipeline(**arguments)

def test_pipeline_skips_inference_and_counts_exclusion_while_paused(
    fake_pipeline_dependencies,
    monkeypatch,
):
    class ControlledWriter(FakeFeatureWriter):
        def __init__(self):
            super().__init__("unused.jsonl")
            self.excluded = 0

        def record_excluded(self):
            self.excluded += 1

    controlled_writer = ControlledWriter()
    FakeLatestMaskedFrameCapture.packets = [packet(np.full((4, 4, 3), 255, dtype=np.uint8))]
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        writer=controlled_writer,
        pause_requested=lambda: True,
        display=False,
    )

    pipeline.run()

    assert controlled_writer.excluded == 1
    assert controlled_writer.records == []
    assert FakeModel.instances[0].frames == []

def test_latest_capture_masks_before_publishing_and_replaces_backlog(
    monkeypatch,
):
    first = np.full((4, 4, 3), 128, dtype=np.uint8)
    second = np.full((4, 4, 3), 255, dtype=np.uint8)
    FakeCameraManager.frames = [first, second, None]
    camera = FakeCameraManager()
    capture = pipeline_module.LatestMaskedFrameCapture(
        camera=camera,
        mask_config=mask_config(),
        camera_id="camera_a",
        max_consecutive_dropped_frames=1,
    )

    capture.start()
    capture._thread.join(timeout=1)
    latest = capture.get_latest()
    dropped = capture.get_latest()
    capture.stop()

    assert latest.frame_number == 2
    assert latest.masked_frame[0, 0].tolist() == [0, 0, 0]
    assert latest.masked_frame[1, 1].tolist() == [255, 255, 255]
    assert dropped.masked_frame is None
    assert capture.replaced_frames == 1
    assert camera.closed is True

def test_latest_capture_fails_closed_when_masking_fails(monkeypatch):
    FakeCameraManager.frames = [np.full((4, 4, 3), 255, dtype=np.uint8)]
    camera = FakeCameraManager()

    def fail_masking(*args, **kwargs):
        raise RuntimeError("masking failed")

    monkeypatch.setattr(pipeline_module,"apply_privacy_mask",fail_masking,)
    capture = pipeline_module.LatestMaskedFrameCapture(
        camera=camera,
        mask_config=mask_config(),
        camera_id="camera_a",
        max_consecutive_dropped_frames=1,
    )

    capture.start()
    capture._thread.join(timeout=1)

    with pytest.raises(RuntimeError, match="masking failed"):
        capture.get_latest()

    capture.stop()

def test_full_pipeline_uses_detector_ids_and_attaches_pose(
    fake_pipeline_dependencies,
    monkeypatch,
):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [packet(frame)]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [
            {
                "local_track_id": 7,
                "bounding_box": [0, 0, 2, 2],
                "detection_confidence": 0.8,
            }
        ],
    )
    FakePoseEstimator.outputs = [([[1.0, 1.0]] * 5, [0.9] * 5),]

    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
        processing_fps=30,
    )
    summary = pipeline.run()

    record = FakeFeatureWriter.instance.records[0]
    assert record["zone"] == "A"
    assert record["camera_id"] == "camera_a"
    assert record["schema_version"] == 2
    assert record["record_type"] == "track"
    assert record["frame_available"] is True
    assert record["pose_available"] is True
    assert record["frame_timestamp_sgt"].endswith("+08:00")
    assert record["mask_config_version"] == "unversioned"
    assert "capture_latency_ms" in record
    assert "detection_latency_ms" in record
    assert record["pose_latency_ms"] >= 0.0
    assert record["local_track_id"] == 7
    assert FakeModel.instances[0].kwargs["inference_size"] == 640
    assert FakePoseEstimator.instances[0].kwargs["inference_size"] == 384
    assert "total_latency_ms" in record
    assert FakeFeatureWriter.instance.closed is True
    assert FakeLatestMaskedFrameCapture.instance.stopped is True
    assert summary["processed_frames"] == 1
    assert summary["inference_latency_ms"]["maximum"] >= 0
    assert summary["frame_age_ms"]["maximum"] >= 0

def test_same_pipeline_preview_receives_track_id_overlay(
    fake_pipeline_dependencies,
    monkeypatch,
):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [packet(frame)]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [
            {
                "local_track_id": 23,
                "bounding_box": [0, 0, 2, 2],
                "detection_confidence": 0.8,
            }
        ],
    )
    FakePoseEstimator.outputs = [([[1.0, 1.0]] * 5, [0.9] * 5),]
    drawn_ids = []
    original_draw = pipeline_module.CVPipeline._draw_track

    def capture_draw(masked_frame, record):
        drawn_ids.append(record["local_track_id"])
        return original_draw(masked_frame, record)

    monkeypatch.setattr(pipeline_module.CVPipeline,"_draw_track",staticmethod(capture_draw),)
    preview_frames = []
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
        processing_fps=30,
        preview_callback=preview_frames.append,
    )

    pipeline.run()

    assert drawn_ids == [23]
    assert len(preview_frames) == 1
    assert FakeFeatureWriter.instance.records[0]["local_track_id"] == 23

def test_experimental_stitching_preserves_raw_id_and_writes_anonymous_id(
    fake_pipeline_dependencies,
    monkeypatch,
):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [packet(frame)]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [
            {
                "local_track_id": 23,
                "bounding_box": [0, 0, 2, 2],
                "detection_confidence": 0.8,
            }
        ],
    )
    FakePoseEstimator.outputs = [([[1.0, 1.0]] * 5, [0.9] * 5),]
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
        processing_fps=30,
        experimental_track_stitching=True,
    )

    summary = pipeline.run()

    record = FakeFeatureWriter.instance.records[0]
    assert record["local_track_id"] == 23
    assert record["stitched_track_id"] == 1
    assert record["track_association_status"] == "new"
    assert record["track_association_reason"] == "new_track"
    assert summary["anonymous_track_stitching"]["enabled"] is True

def test_full_pipeline_rejects_excluded_and_implausible_tracks(
    fake_pipeline_dependencies,
    monkeypatch,
):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [packet(frame)]
    config = mask_config()
    config.excluded_polygons = [
        [[2, 1], [3, 1], [3, 3], [2, 3]],
    ]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [
            {
                "local_track_id": 1378,
                "bounding_box": [2, 1, 4, 4],
                "detection_confidence": 0.4,
            },
            {
                "local_track_id": 1365,
                "bounding_box": [0, 0, 2, 2],
                "detection_confidence": 0.4,
            },
        ],
    )
    FakePoseEstimator.outputs = [([[1.0, 1.0]] * 4, [0.9] * 4),]

    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=config,
        output_path="unused.jsonl",
        display=False,
        processing_fps=30,
    )
    summary = pipeline.run()

    records = FakeFeatureWriter.instance.records
    assert len(records) == 1
    assert records[0]["record_type"] == "frame_status"
    assert summary["rejected_excluded_zone_tracks"] == 1
    assert summary["rejected_implausible_pose_tracks"] == 1

def test_confirmed_detector_track_survives_temporary_pose_failure(
    fake_pipeline_dependencies,
):
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
    )
    strong = {
        "local_track_id": 12,
        "bounding_box": [0, 0, 2, 2],
        "detection_confidence": 0.3,
        "keypoints": [[1.0, 1.0]] * 5,
        "keypoint_confidences": [0.9] * 5,
    }
    missing_pose = {
        "local_track_id": 12,
        "bounding_box": [0, 0, 2, 2],
        "detection_confidence": 0.3,
        "keypoints": [],
        "keypoint_confidences": [],
    }

    confirmed = pipeline._filter_tracks([strong])
    retained = pipeline._filter_tracks([missing_pose])

    assert confirmed[0]["local_track_id"] == 12
    assert len(confirmed[0]["keypoints"]) == 5
    assert retained[0]["local_track_id"] == 12
    assert retained[0]["keypoints"] == []

def test_same_frame_duplicate_is_suppressed_without_persistent_alias(
    fake_pipeline_dependencies,
):
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
    )
    common = {
        "bounding_box": [0, 0, 2, 2],
        "detection_confidence": 0.8,
        "keypoints": [[1.0, 1.0]] * 10,
        "keypoint_confidences": [0.9] * 10,
    }

    simultaneous = pipeline._filter_tracks(
        [
            {"local_track_id": 53, **common},
            {
                "local_track_id": 61,
                **common,
                "detection_confidence": 0.9,
            },
        ]
    )
    duplicate_alone = pipeline._filter_tracks([{"local_track_id": 61, **common}])

    assert [track["local_track_id"] for track in simultaneous] == [53]
    assert [track["local_track_id"] for track in duplicate_alone] == [61]
    assert pipeline.suppressed_frame_duplicate_tracks == 1

def test_close_people_with_different_poses_remain_separate(
    fake_pipeline_dependencies,
):
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
    )
    first = {
        "local_track_id": 10,
        "bounding_box": [0, 0, 2, 2],
        "detection_confidence": 0.8,
        "keypoints": [[0.5, 0.5]] * 10,
        "keypoint_confidences": [0.9] * 10,
    }
    second = {
        "local_track_id": 11,
        "bounding_box": [0, 0, 2, 2],
        "detection_confidence": 0.8,
        "keypoints": [[1.5, 1.5]] * 10,
        "keypoint_confidences": [0.9] * 10,
    }

    tracks = pipeline._filter_tracks([first, second])

    assert [track["local_track_id"] for track in tracks] == [10, 11]

def test_tracking_only_skips_pose_and_emits_track_without_keypoints(
    fake_pipeline_dependencies,
    monkeypatch,
):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [packet(frame)]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [
            {
                "local_track_id": 9,
                "bounding_box": [0, 0, 2, 2],
                "detection_confidence": 0.7,
            }
        ],
    )

    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
        tracking_only=True,
        processing_fps=30,
        inference_size=960,
    )
    pipeline.run()

    record = FakeFeatureWriter.instance.records[0]
    assert record["pose_available"] is False
    assert record["keypoints"] == []
    assert record["keypoint_confidences"] == []
    assert FakeModel.instances[0].kwargs["inference_size"] == 960

def test_draw_track_connects_only_confident_skeleton_keypoints(monkeypatch):
    lines = []
    circles = []
    monkeypatch.setattr(
        pipeline_module.cv2,
        "line",
        lambda frame, start, end, color, thickness: lines.append(
            (start, end, color, thickness)
        ),
    )
    monkeypatch.setattr(pipeline_module.cv2, "rectangle", lambda *args: None)
    monkeypatch.setattr(pipeline_module.cv2, "putText", lambda *args: None)
    monkeypatch.setattr(
        pipeline_module.cv2,
        "circle",
        lambda frame, center, radius, color, thickness: circles.append(
            (center, radius, color, thickness)
        ),
    )
    keypoints = [[float(index), float(index + 1)] for index in range(17)]
    confidences = [0.9] * 17
    confidences[1] = 0.1

    pipeline_module.CVPipeline._draw_track(
        np.zeros((20, 20, 3), dtype=np.uint8),
        {
            "bounding_box": [0, 0, 19, 19],
            "local_track_id": 1,
            "keypoints": keypoints,
            "keypoint_confidences": confidences,
        },
    )

    connected_pairs = {(start[0], end[0]) for start, end, _, _ in lines}
    assert (0, 2) in connected_pairs
    assert (0, 1) not in connected_pairs
    assert (1, 3) not in connected_pairs
    assert all(color == (255, 255, 255) for _, _, color, _ in lines)
    assert all(color == (0, 255, 0) for _, _, color, _ in circles)

def test_performance_overlay_displays_fps_and_inference_latency(
    fake_pipeline_dependencies,
    monkeypatch,
):
    labels = []
    monkeypatch.setattr(pipeline_module.cv2, "rectangle", lambda *args: None)
    monkeypatch.setattr(
        pipeline_module.cv2,
        "putText",
        lambda frame, text, *args: labels.append(text),
    )
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
    )
    pipeline._rolling_processing_fps = 7.04
    pipeline._rolling_inference_latency_ms = 84.26

    pipeline._draw_performance_overlay(np.zeros((100, 400, 3), dtype=np.uint8))

    assert labels == ["Processing FPS: 7.0","Vision inference: 84.3 ms",]

def test_performance_metrics_use_smoothed_measured_values(fake_pipeline_dependencies,monkeypatch,):
    times = iter([10.0, 10.2])
    monkeypatch.setattr(
        pipeline_module.time,
        "perf_counter",
        lambda: next(times),
    )
    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
    )

    pipeline._update_performance_metrics(10.0)
    pipeline._update_performance_metrics(20.0)

    assert pipeline._rolling_processing_fps == pytest.approx(5.0)
    assert pipeline._rolling_inference_latency_ms == pytest.approx(12.0)

def test_pipeline_writes_explicit_frame_availability(fake_pipeline_dependencies,monkeypatch,):
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    FakeLatestMaskedFrameCapture.packets = [
        packet(frame),
        packet(None, frame_number=2),
    ]
    monkeypatch.setattr(
        pipeline_module,
        "extract_tracks",
        lambda result: [],
    )

    pipeline = pipeline_module.CVPipeline(
        camera_id="camera_a",
        source="test-stream",
        mask_config=mask_config(),
        output_path="unused.jsonl",
        display=False,
        processing_fps=30,
    )
    pipeline.run()

    available, dropped = FakeFeatureWriter.instance.records
    assert available["frame_available"] is True
    assert available["pose_available"] is False
    assert dropped["frame_available"] is False
    assert dropped["pose_available"] is False