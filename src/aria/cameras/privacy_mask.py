from dataclasses import dataclass, field
import cv2
import numpy as np

@dataclass
class MaskConfig:
    camera_id: str
    expected_width: int
    expected_height: int
    x: int
    y: int
    width: int
    height: int
    verified: bool
    excluded_polygons: list = field(default_factory=list)
    mask_config_version: str = "unversioned"

def _validate_excluded_polygons(polygons, frame_width, frame_height):
    if not isinstance(polygons, list):
        raise ValueError("Excluded polygons must be a list")

    for polygon_index, polygon in enumerate(polygons):
        if not isinstance(polygon, list) or len(polygon) < 3:
            raise ValueError(f"Excluded polygon {polygon_index} must have at least 3 points")

        for point in polygon:
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or any(
                    not isinstance(value, int) or isinstance(value, bool)
                    for value in point
                )
            ):
                raise ValueError(f"Excluded polygon {polygon_index} has an invalid point")

            x, y = point

            if not (0 <= x < frame_width and 0 <= y < frame_height):
                raise ValueError(f"Excluded polygon {polygon_index} extends outside the frame")

        contour = np.asarray(polygon, dtype=np.int32)

        if cv2.contourArea(contour) <= 0:
            raise ValueError(f"Excluded polygon {polygon_index} must have a non-zero area")

def _validate_mask_geometry(config, frame_width, frame_height, camera_id):
    if config is None:
        raise ValueError("Mask configuration is missing")

    if config.camera_id != camera_id:
        raise ValueError(f"Camera identity mismatch: expected {config.camera_id}, got {camera_id}")

    if frame_width != config.expected_width or frame_height != config.expected_height:
        raise ValueError("Frame resolution does not match the configured resolution")

    if config.width <= 0 or config.height <= 0:
        raise ValueError("Retained mask area must not be empty")

    if config.x < 0 or config.y < 0:
        raise ValueError("Mask coordinates must be inside the frame")

    if config.x + config.width > frame_width:
        raise ValueError("Mask extends beyond frame width")

    if config.y + config.height > frame_height:
        raise ValueError("Mask extends beyond frame height")

    _validate_excluded_polygons(
        polygons=config.excluded_polygons,
        frame_width=frame_width,
        frame_height=frame_height,
    )

def validate_mask_config(config, frame_width, frame_height, camera_id):
    _validate_mask_geometry(
        config=config,
        frame_width=frame_width,
        frame_height=frame_height,
        camera_id=camera_id,
    )

    if not config.verified:
        raise ValueError("Mask verification has not been completed")

def validate_draft_mask_config(config, frame_width, frame_height, camera_id):
        _validate_mask_geometry(
        config=config,
        frame_width=frame_width,
        frame_height=frame_height,
        camera_id=camera_id,
    )

def _apply_mask_geometry(frame, config):
    masked_frame = np.zeros_like(frame)
    x1 = config.x
    y1 = config.y
    x2 = config.x + config.width
    y2 = config.y + config.height
    masked_frame[y1:y2, x1:x2] = frame[y1:y2, x1:x2]

    for polygon in config.excluded_polygons:
        contour = np.asarray(polygon, dtype=np.int32)
        cv2.fillPoly(masked_frame, [contour], (0, 0, 0))

    return masked_frame

def apply_privacy_mask(frame, config, camera_id):
    if frame is None:
        raise ValueError("Frame is missing")

    frame_height, frame_width = frame.shape[:2]

    validate_mask_config(
        config=config,
        frame_width=frame_width,
        frame_height=frame_height,
        camera_id=camera_id,
    )

    return _apply_mask_geometry(frame=frame, config=config)

def is_point_in_retained_region(config, x, y):
    if not (config.x <= x < config.x + config.width and config.y <= y < config.y + config.height):
        return False

    point = (float(x), float(y))
    for polygon in config.excluded_polygons:
        contour = np.asarray(polygon, dtype=np.float32)
        if cv2.pointPolygonTest(contour, point, False) >= 0:
            return False

    return True

def apply_draft_privacy_mask(frame, config, camera_id):
    if frame is None:
        raise ValueError("Frame is missing")

    frame_height, frame_width = frame.shape[:2]

    validate_draft_mask_config(
        config=config,
        frame_width=frame_width,
        frame_height=frame_height,
        camera_id=camera_id,
    )

    return _apply_mask_geometry(frame=frame, config=config)

def draw_mask_preview(frame, config):
    preview = frame.copy()

    x1 = config.x
    y1 = config.y
    x2 = config.x + config.width
    y2 = config.y + config.height

    cv2.rectangle(preview, (x1, y1), (x2, y2), (255, 255, 255), 2)

    for polygon_index, polygon in enumerate(
        config.excluded_polygons,
        start=1,
    ):
        contour = np.asarray(polygon, dtype=np.int32)
        cv2.polylines(
            preview,
            [contour],
            isClosed=True,
            color=(0, 0, 255),
            thickness=2,
        )

        for point_index, point in enumerate(polygon, start=1):
            _draw_polygon_vertex_label(
                preview=preview,
                polygon_index=polygon_index,
                point_index=point_index,
                point=point,
            )

    return preview

def _draw_polygon_vertex_label(
    preview,
    polygon_index,
    point_index,
    point,
):
    x, y = point
    label = f"P{polygon_index}.{point_index} ({x},{y})"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.5
    thickness = 1
    padding = 3

    (text_width, text_height), baseline = cv2.getTextSize(
        label,
        font,
        font_scale,
        thickness,
    )
    frame_height, frame_width = preview.shape[:2]

    label_x = x + 8
    if label_x + text_width + padding > frame_width:
        label_x = x - text_width - 8
    label_x = max(padding,min(label_x, frame_width - text_width - padding),)

    label_y = y - 8
    if label_y - text_height - padding < 0:
        label_y = y + text_height + 10
    label_y = max(text_height + padding,min(label_y, frame_height - baseline - padding),)

    cv2.circle(preview, (x, y), 5, (0, 255, 255), -1)
    cv2.rectangle(
        preview,
        (label_x - padding, label_y - text_height - padding),
        (label_x + text_width + padding, label_y + baseline + padding),
        (0, 0, 0),
        -1,
    )
    cv2.putText(
        preview,
        label,
        (label_x, label_y),
        font,
        font_scale,
        (0, 255, 255),
        thickness,
        cv2.LINE_AA,
    )