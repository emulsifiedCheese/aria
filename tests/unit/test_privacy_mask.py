import cv2
import numpy as np
import pytest
from aria.cameras.privacy_mask import (
    MaskConfig,
    apply_draft_privacy_mask,
    apply_privacy_mask,
    draw_mask_preview,
    validate_draft_mask_config,
    validate_mask_config,
)

def valid_config():
    return MaskConfig(
        camera_id="camera_a",
        expected_width=640,
        expected_height=480,
        x=100,
        y=100,
        width=300,
        height=200,
        verified=True,
    )

def test_valid_mask_configuration():
    config = valid_config()
    validate_mask_config(
        config=config,
        frame_width=640,
        frame_height=480,
        camera_id="camera_a",
    )

def test_missing_configuration_is_rejected():
    with pytest.raises(ValueError, match="missing"):
        validate_mask_config(
            config=None,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )

def test_wrong_resolution_is_rejected():
    config = valid_config()
    with pytest.raises(ValueError, match="resolution"):
        validate_mask_config(
            config=config,
            frame_width=1280,
            frame_height=720,
            camera_id="camera_a",
        )

def test_wrong_camera_identity_is_rejected():
    config = valid_config()
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="unknown_camera",
        )

def test_unverified_mask_is_rejected():
    config = valid_config()
    config.verified = False
    with pytest.raises(ValueError, match="verification"):
        validate_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )

def test_unverified_draft_mask_is_accepted_for_calibration():
    config = valid_config()
    config.verified = False
    validate_draft_mask_config(
        config=config,
        frame_width=640,
        frame_height=480,
        camera_id="camera_a",
    )

def test_draft_mask_still_rejects_invalid_geometry():
    config = valid_config()
    config.verified = False
    config.x = 600
    with pytest.raises(ValueError, match="beyond frame width"):
        validate_draft_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )

def test_empty_mask_is_rejected():
    config = valid_config()
    config.width = 0
    with pytest.raises(ValueError, match="must not be empty"):
        validate_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )

def test_out_of_bounds_mask_is_rejected():
    config = valid_config()
    config.x = 500
    config.width = 200
    with pytest.raises(ValueError, match="beyond frame width"):
        validate_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )

def test_apply_privacy_mask_keeps_only_retained_region():
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    config = valid_config()
    masked = apply_privacy_mask(
        frame=frame,
        config=config,
        camera_id="camera_a",
    )
    assert masked[150, 150].tolist() == [255, 255, 255]
    assert masked[20, 20].tolist() == [0, 0, 0]

def test_apply_draft_privacy_mask_keeps_only_retained_region():
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    config = valid_config()
    config.verified = False
    masked = apply_draft_privacy_mask(
        frame=frame,
        config=config,
        camera_id="camera_a",
    )
    assert masked[150, 150].tolist() == [255, 255, 255]
    assert masked[20, 20].tolist() == [0, 0, 0]

def test_apply_privacy_mask_blacks_excluded_polygon():
    frame = np.full((480, 640, 3), 255, dtype=np.uint8)
    config = valid_config()
    config.excluded_polygons = [[[150, 150], [250, 150], [200, 250]],]
    masked = apply_privacy_mask(
        frame=frame,
        config=config,
        camera_id="camera_a",
    )
    assert masked[180, 200].tolist() == [0, 0, 0]
    assert masked[120, 120].tolist() == [255, 255, 255]

def test_mask_preview_labels_every_polygon_vertex(monkeypatch):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    config = valid_config()
    config.excluded_polygons = [
        [[0, 0], [200, 0], [100, 100]],
        [[500, 300], [639, 300], [639, 479]],
    ]
    labels = []

    def capture_label(image, text, *args, **kwargs):
        labels.append(text)
        return image

    monkeypatch.setattr(cv2, "putText", capture_label)

    draw_mask_preview(frame, config)

    assert labels == [
        "P1.1 (0,0)",
        "P1.2 (200,0)",
        "P1.3 (100,100)",
        "P2.1 (500,300)",
        "P2.2 (639,300)",
        "P2.3 (639,479)",
    ]

@pytest.mark.parametrize(
    "polygon, error",
    [
        ([[100, 100], [200, 200]], "at least 3 points"),
        ([[100, 100], [200, 100], [640, 200]], "outside the frame"),
        ([[100, 100], [200, 100], [300, 100]], "non-zero area"),
    ],
)
def test_invalid_excluded_polygon_is_rejected(polygon, error):
    config = valid_config()
    config.excluded_polygons = [polygon]

    with pytest.raises(ValueError, match=error):
        validate_mask_config(
            config=config,
            frame_width=640,
            frame_height=480,
            camera_id="camera_a",
        )