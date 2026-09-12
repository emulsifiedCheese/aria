import numpy as np
import pytest
from aria.cameras.privacy_mask import MaskConfig
from scripts import preview_privacy_mask

def draft_config():
    return MaskConfig(
        camera_id="camera_a",
        expected_width=4,
        expected_height=4,
        x=1,
        y=1,
        width=2,
        height=2,
        verified=False,
    )

class FakeCapture:
    def __init__(self, frames=None, opened=True):
        self.frames = list(frames or [])
        self.opened = opened
        self.released = False

    def isOpened(self):
        return self.opened

    def read(self):
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self):
        self.released = True

def test_validate_source_rejects_any_non_local_camera_a_source():
    with pytest.raises(ValueError, match="only the local camera_a"):
        preview_privacy_mask.validate_source("rtsp://example.test/camera_a")

def test_load_draft_mask_requires_only_camera_a(tmp_path):
    path = tmp_path / "masks.yaml"
    path.write_text(
        """
masks:
  camera_a:
    camera_id: camera_a
    expected_width: 4
    expected_height: 4
    x: 1
    y: 1
    width: 2
    height: 2
    verified: false
  camera_b:
    camera_id: camera_b
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="only the active camera_a"):
        preview_privacy_mask.load_draft_mask(path)

def test_load_draft_unverified_camera_a_mask(tmp_path):
    path = tmp_path / "masks.yaml"
    path.write_text(
        """
masks:
  camera_a:
    camera_id: camera_a
    expected_width: 4
    expected_height: 4
    x: 1
    y: 1
    width: 2
    height: 2
    verified: false
""",
        encoding="utf-8",
    )

    config = preview_privacy_mask.load_draft_mask(path)

    assert config == draft_config()

def test_run_preview_displays_only_masked_frames(monkeypatch):
    frame = np.full((4, 4, 3), 255, dtype=np.uint8)
    capture = FakeCapture(frames=[frame])
    displayed = []
    events = []

    monkeypatch.setattr(preview_privacy_mask.cv2,"VideoCapture",lambda source: capture,)
    monkeypatch.setattr(preview_privacy_mask,"draw_mask_preview",lambda masked, config: masked.copy(),)
    monkeypatch.setattr(preview_privacy_mask.cv2,"putText",lambda image, *args, **kwargs: image,)
    monkeypatch.setattr(preview_privacy_mask.cv2,"namedWindow",lambda *args: events.append("window"),)

    def capture_display(name, image):
        events.append("display")
        displayed.append(image.copy())

    monkeypatch.setattr(preview_privacy_mask.cv2, "imshow", capture_display)
    monkeypatch.setattr(preview_privacy_mask.cv2,"waitKey",lambda delay: ord("q"),)
    monkeypatch.setattr(preview_privacy_mask.cv2,"destroyWindow",lambda name: events.append("destroy"),)
    monkeypatch.setattr(preview_privacy_mask.cv2,"imwrite",lambda *args, **kwargs: pytest.fail("Preview must not write frames"),)

    preview_privacy_mask.run_preview(source=preview_privacy_mask.LOCAL_CAMERA_SOURCE,config=draft_config(),)

    assert events == ["window", "display", "destroy"]
    assert len(displayed) == 1
    assert displayed[0][0, 0].tolist() == [0, 0, 0]
    assert displayed[0][1, 1].tolist() == [255, 255, 255]
    assert capture.released


def test_failed_frame_read_stops_closed_without_opening_window(monkeypatch):
    capture = FakeCapture()
    monkeypatch.setattr(preview_privacy_mask.cv2,"VideoCapture",lambda source: capture,)
    monkeypatch.setattr(preview_privacy_mask.cv2,"namedWindow",lambda *args: pytest.fail("Window must not open before a masked frame"),)
    monkeypatch.setattr(preview_privacy_mask.cv2,"imshow",lambda *args: pytest.fail("No frame should be displayed"),)

    with pytest.raises(RuntimeError, match="stopped closed"):
        preview_privacy_mask.run_preview(source=preview_privacy_mask.LOCAL_CAMERA_SOURCE,config=draft_config(),)

    assert capture.released

def test_invalid_source_is_rejected_before_capture_is_opened(monkeypatch):
    monkeypatch.setattr(preview_privacy_mask.cv2,"VideoCapture",lambda source: pytest.fail("Invalid source must not be opened"),)

    with pytest.raises(ValueError, match="only the local camera_a"):
        preview_privacy_mask.run_preview(source="rtsp://127.0.0.1:8554/live/other_camera",config=draft_config(),)

def editor_config():
    config = MaskConfig(
        camera_id="camera_a",
        expected_width=100,
        expected_height=100,
        x=0,
        y=0,
        width=100,
        height=100,
        verified=False,
        excluded_polygons=[
            [[10, 10], [90, 10], [90, 90], [10, 90]],
            [[20, 20], [30, 20], [25, 30]],
        ],
    )
    return config

def test_interactive_double_click_inserts_on_nearest_edge(tmp_path):
    editor = preview_privacy_mask.InteractiveMaskEditor(config=editor_config(),config_path=tmp_path / "mask.yaml",display_scale=0.5,)

    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONDBLCLK,
        25,
        5,
        0,
        None,
    )

    assert editor.active_polygon == [
        [10, 10],
        [50, 10],
        [90, 10],
        [90, 90],
        [10, 90],
    ]
    assert editor.dirty is True

def test_interactive_drag_moves_vertex_and_undo_restores_it(tmp_path):
    editor = preview_privacy_mask.InteractiveMaskEditor(config=editor_config(),config_path=tmp_path / "mask.yaml",display_scale=0.5,)

    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONDOWN,
        5,
        5,
        0,
        None,
    )
    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_MOUSEMOVE,
        15,
        20,
        preview_privacy_mask.cv2.EVENT_FLAG_LBUTTON,
        None,
    )
    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONUP,
        15,
        20,
        0,
        None,
    )

    assert editor.active_polygon[0] == [30, 40]
    assert editor.undo() is True
    assert editor.active_polygon[0] == [10, 10]

def test_interactive_save_forces_unverified_and_preserves_polygons(tmp_path):
    path = tmp_path / "mask.yaml"
    path.write_text(
        """
masks:
  camera_a:
    camera_id: camera_a
    mask_config_version: draft-v1
    expected_width: 100
    expected_height: 100
    x: 0
    y: 0
    width: 100
    height: 100
    excluded_polygons:
      - [[10, 10], [90, 10], [90, 90], [10, 90]]
    verified: true
""",
        encoding="utf-8",
    )
    config = editor_config()
    editor = preview_privacy_mask.InteractiveMaskEditor(config=config,config_path=path,display_scale=1,)

    editor.save()

    saved = preview_privacy_mask.yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["masks"]["camera_a"]["excluded_polygons"] == (config.excluded_polygons)
    assert saved["masks"]["camera_a"]["verified"] is False

def test_interactive_polygon_selection_is_bounded(tmp_path):
    editor = preview_privacy_mask.InteractiveMaskEditor(config=editor_config(),config_path=tmp_path / "mask.yaml",)

    assert editor.select_polygon(2) is True
    assert editor.active_polygon_index == 1
    assert editor.select_polygon(3) is False
    assert editor.active_polygon_index == 1

def test_interactive_new_polygon_stays_separate(tmp_path):
    editor = preview_privacy_mask.InteractiveMaskEditor(config=editor_config(),config_path=tmp_path / "mask.yaml",display_scale=1,)

    assert editor.start_new_polygon() is True
    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONDOWN,
        40,
        40,
        0,
        None,
    )
    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONDOWN,
        60,
        40,
        0,
        None,
    )
    editor.mouse_callback(
        preview_privacy_mask.cv2.EVENT_LBUTTONDOWN,
        50,
        60,
        0,
        None,
    )

    assert len(editor.config.excluded_polygons) == 2
    assert editor.commit_pending_polygon() is True
    assert editor.config.excluded_polygons == [
        [[10, 10], [90, 10], [90, 90], [10, 90]],
        [[20, 20], [30, 20], [25, 30]],
        [[40, 40], [60, 40], [50, 60]],
    ]
    assert editor.active_polygon_index == 2
    assert editor.dirty is True

def test_interactive_new_polygon_requires_three_points(tmp_path):
    editor = preview_privacy_mask.InteractiveMaskEditor(config=editor_config(),config_path=tmp_path / "mask.yaml",)
    editor.start_new_polygon()
    editor.append_pending_vertex([40, 40])
    editor.append_pending_vertex([60, 40])

    assert editor.commit_pending_polygon() is False
    assert len(editor.config.excluded_polygons) == 2
    assert editor.cancel_pending_polygon() is True

def test_interactive_can_cycle_more_than_nine_polygons(tmp_path):
    config = editor_config()
    config.excluded_polygons = [
        [[index, 0], [index + 1, 0], [index, 1]]
        for index in range(10)
    ]
    editor = preview_privacy_mask.InteractiveMaskEditor(config=config,config_path=tmp_path / "mask.yaml",)

    editor.active_polygon_index = 8
    assert editor.cycle_polygon(1) is True
    assert editor.active_polygon_index == 9
    assert editor.cycle_polygon(1) is True
    assert editor.active_polygon_index == 0