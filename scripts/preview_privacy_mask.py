#!/usr/bin/env python3
"""preview and edit the camera a mask without showing an unmasked frame"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import cv2
import numpy as np
import yaml

from aria.cameras.privacy_mask import (
    MaskConfig,
    apply_draft_privacy_mask,
    draw_mask_preview,
)

CAMERA_ID = "camera_a"
LOCAL_CAMERA_SOURCE = "rtsp://127.0.0.1:8554/live/camera_a"
WINDOW_NAME = "ARIA Camera A - unverified mask calibration preview"
EDITOR_VERTEX_RADIUS = 18


def validate_source(source: str) -> None:
    if source != LOCAL_CAMERA_SOURCE:
        raise ValueError("Draft preview accepts only the local camera_a RTSP source")

def load_draft_mask(path: str | Path) -> MaskConfig:
    with Path(path).open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)

    masks = document.get("masks") if isinstance(document, dict) else None
    if not isinstance(masks, dict) or set(masks) != {CAMERA_ID}:
        raise ValueError("Mask configuration must contain only the active camera_a mask")

    mask = masks[CAMERA_ID]
    if not isinstance(mask, dict):
        raise ValueError("camera_a mask configuration must be a mapping")

    try:
        return MaskConfig(
            camera_id=mask["camera_id"],
            expected_width=mask["expected_width"],
            expected_height=mask["expected_height"],
            x=mask["x"],
            y=mask["y"],
            width=mask["width"],
            height=mask["height"],
            verified=mask["verified"],
            excluded_polygons=mask.get("excluded_polygons", []),
            mask_config_version=mask.get("mask_config_version", "unversioned"),
        )
    except KeyError as error:
        raise ValueError(
            f"camera_a mask is missing required field {error.args[0]!r}"
        ) from error

def save_draft_mask(path: str | Path, config: MaskConfig) -> None:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)

    mask = document["masks"][CAMERA_ID]
    mask["excluded_polygons"] = config.excluded_polygons
    mask["verified"] = False

    rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=False)
    path.write_text(rendered, encoding="utf-8")

def _point_to_segment_distance_squared(point, start, end):
    point = np.asarray(point, dtype=float)
    start = np.asarray(start, dtype=float)
    end = np.asarray(end, dtype=float)
    segment = end - start
    length_squared = float(np.dot(segment, segment))

    if length_squared == 0:
        return float(np.dot(point - start, point - start))

    proportion = float(np.dot(point - start, segment)) / length_squared
    proportion = max(0.0, min(1.0, proportion))
    projection = start + proportion * segment
    difference = point - projection
    return float(np.dot(difference, difference))

class InteractiveMaskEditor:
    """edit exclusion polygons on an already masked preview"""

    def __init__(self, config, config_path, display_scale=0.8):
        if not 0 < display_scale <= 1:
            raise ValueError("display_scale must be greater than 0 and at most 1")
        if not config.excluded_polygons:
            raise ValueError("Interactive editing requires at least one exclusion polygon")

        self.config = config
        self.config_path = Path(config_path)
        self.display_scale = display_scale
        self.active_polygon_index = 0
        self.history = []
        self.dragging_vertex_index = None
        self.pending_polygon = None
        self.dirty = False

    @property
    def active_polygon(self):
        return self.config.excluded_polygons[self.active_polygon_index]

    def _frame_point(self, display_x, display_y):
        x = round(display_x / self.display_scale)
        y = round(display_y / self.display_scale)
        return [
            max(0, min(x, self.config.expected_width - 1)),
            max(0, min(y, self.config.expected_height - 1)),
        ]

    def _remember(self):
        self.history.append(deepcopy(self.config.excluded_polygons))
        self.history = self.history[-100:]

    def select_polygon(self, polygon_number):
        if self.pending_polygon is not None:
            return False
        polygon_index = polygon_number - 1
        if 0 <= polygon_index < len(self.config.excluded_polygons):
            self.active_polygon_index = polygon_index
            return True
        return False

    def cycle_polygon(self, direction):
        if self.pending_polygon is not None:
            return False
        polygon_count = len(self.config.excluded_polygons)
        self.active_polygon_index = (self.active_polygon_index + direction) % polygon_count
        return True

    def start_new_polygon(self):
        if self.pending_polygon is not None:
            return False
        self.dragging_vertex_index = None
        self.pending_polygon = []
        return True

    def append_pending_vertex(self, point):
        if self.pending_polygon is None:
            return False
        self.pending_polygon.append(point)
        return True

    def commit_pending_polygon(self):
        if self.pending_polygon is None or len(self.pending_polygon) < 3:
            return False
        self._remember()
        self.config.excluded_polygons.append(self.pending_polygon)
        self.active_polygon_index = len(self.config.excluded_polygons) - 1
        self.pending_polygon = None
        self.dirty = True
        return True

    def cancel_pending_polygon(self):
        if self.pending_polygon is None:
            return False
        self.pending_polygon = None
        return True

    def insert_vertex_on_nearest_edge(self, point):
        polygon = self.active_polygon
        edge_index = min(
            range(len(polygon)),
            key=lambda index: _point_to_segment_distance_squared(
                point,
                polygon[index],
                polygon[(index + 1) % len(polygon)],
            ),
        )
        self._remember()
        polygon.insert(edge_index + 1, point)
        self.dirty = True
        return edge_index + 1

    def nearest_vertex_index(self, point):
        distances = [
            (vertex[0] - point[0]) ** 2 + (vertex[1] - point[1]) ** 2
            for vertex in self.active_polygon
        ]
        vertex_index = min(range(len(distances)), key=distances.__getitem__)
        if distances[vertex_index] <= EDITOR_VERTEX_RADIUS**2:
            return vertex_index
        return None

    def undo(self):
        if self.pending_polygon is not None:
            if not self.pending_polygon:
                return False
            self.pending_polygon.pop()
            return True
        if not self.history:
            return False
        self.config.excluded_polygons = self.history.pop()
        self.dirty = True
        self.dragging_vertex_index = None
        return True

    def save(self):
        if self.pending_polygon is not None:
            raise ValueError("Finish or cancel the new polygon before saving")
        save_draft_mask(self.config_path, self.config)
        self.config.verified = False
        self.dirty = False

    def handle_key(self, key):
        """apply one keyboard command and return a message when needed"""
        if ord("1") <= key <= ord("9"):
            self.select_polygon(key - ord("0"))
        elif key == ord("["):
            self.cycle_polygon(-1)
        elif key == ord("]"):
            self.cycle_polygon(1)
        elif key == ord("n"):
            self.start_new_polygon()
        elif key in (10, 13) and not self.commit_pending_polygon():
            return "A new polygon requires at least three points"
        elif key == 27:
            self.cancel_pending_polygon()
        elif key == ord("u"):
            self.undo()
        elif key == ord("s"):
            try:
                self.save()
            except ValueError as error:
                return str(error)
            return f"Saved unverified draft mask to {self.config_path}"
        return None

    def mouse_callback(self, event, display_x, display_y, flags, parameter):
        point = self._frame_point(display_x, display_y)

        if event == cv2.EVENT_LBUTTONDBLCLK:
            self.dragging_vertex_index = None
            if self.pending_polygon is None:
                self.insert_vertex_on_nearest_edge(point)
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            if self.pending_polygon is not None:
                self.append_pending_vertex(point)
                return
            vertex_index = self.nearest_vertex_index(point)
            if vertex_index is not None:
                self._remember()
                self.dragging_vertex_index = vertex_index
            return

        if (
            event == cv2.EVENT_MOUSEMOVE
            and self.dragging_vertex_index is not None
            and flags & cv2.EVENT_FLAG_LBUTTON
        ):
            self.active_polygon[self.dragging_vertex_index] = point
            self.dirty = True
            return

        if event == cv2.EVENT_LBUTTONUP:
            self.dragging_vertex_index = None

    def draw_overlay(self, preview):
        if self.pending_polygon is None:
            contour = np.asarray(self.active_polygon, dtype=np.int32)
            cv2.polylines(
                preview,
                [contour],
                isClosed=True,
                color=(255, 255, 0),
                thickness=3,
            )
            state = "*" if self.dirty else ""
            instructions = (
                f"EDIT P{self.active_polygon_index + 1}{state} | "
                "double-click edge: add | drag: move | n: new | "
                "1-9/[ ]: select | u: undo | s: save | q: quit"
            )
        else:
            if self.pending_polygon:
                contour = np.asarray(
                    self.pending_polygon,
                    dtype=np.int32,
                )
                cv2.polylines(
                    preview,
                    [contour],
                    isClosed=False,
                    color=(255, 0, 255),
                    thickness=3,
                )
                for point_index, point in enumerate(
                    self.pending_polygon,
                    start=1,
                ):
                    cv2.circle(
                        preview,
                        tuple(point),
                        5,
                        (255, 0, 255),
                        -1,
                    )
                    cv2.putText(
                        preview,
                        f"N{point_index} ({point[0]},{point[1]})",
                        (
                            min(point[0] + 8, preview.shape[1] - 180),
                            max(18, min(point[1] - 8, preview.shape[0] - 50)),
                        ),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 0, 255),
                        1,
                        cv2.LINE_AA,
                    )
            instructions = (
                f"NEW P{len(self.config.excluded_polygons) + 1} "
                f"({len(self.pending_polygon)} points) | "
                "single-click: add | Enter: close | "
                "u: remove last | Esc: cancel"
            )
        cv2.rectangle(
            preview,
            (12, preview.shape[0] - 42),
            (preview.shape[1] - 12, preview.shape[0] - 8),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            preview,
            instructions,
            (22, preview.shape[0] - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )

def render_preview_frame(frame, config: MaskConfig, editor=None):
    masked_frame = apply_draft_privacy_mask(
        frame=frame,
        config=config,
        camera_id=CAMERA_ID,
    )
    preview = draw_mask_preview(masked_frame, config)
    cv2.putText(
        preview,
        "CALIBRATION PREVIEW - MASK UNVERIFIED",
        (24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )
    if editor is not None:
        editor.draw_overlay(preview)
    return preview

def run_preview(
    source,
    config,
    config_path=None,
    interactive=False,
    display_scale=0.8,
):
    validate_source(source)
    editor = None
    if interactive:
        if config_path is None:
            raise ValueError("Interactive mode requires a mask config path")
        editor = InteractiveMaskEditor(
            config=config,
            config_path=config_path,
            display_scale=display_scale,
        )

    capture = cv2.VideoCapture(source)
    window_created = False

    try:
        if not capture.isOpened():
            raise RuntimeError("Could not open the local camera_a RTSP stream")

        while True:
            success, frame = capture.read()
            if not success or frame is None:
                raise RuntimeError(
                    "Camera A frame read failed; preview stopped closed"
                )

            preview = render_preview_frame(
                frame=frame,
                config=config,
                editor=editor,
            )
            if editor is not None and display_scale != 1:
                preview = cv2.resize(
                    preview,
                    None,
                    fx=display_scale,
                    fy=display_scale,
                    interpolation=cv2.INTER_AREA,
                )

            if not window_created:
                window_mode = (
                    cv2.WINDOW_AUTOSIZE
                    if editor is not None
                    else cv2.WINDOW_NORMAL
                )
                cv2.namedWindow(WINDOW_NAME, window_mode)
                if editor is not None:
                    cv2.setMouseCallback(
                        WINDOW_NAME,
                        editor.mouse_callback,
                    )
                window_created = True

            cv2.imshow(WINDOW_NAME, preview)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if editor is not None:
                message = editor.handle_key(key)
                if message:
                    print(message)
    finally:
        capture.release()
        if window_created:
            cv2.destroyWindow(WINDOW_NAME)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Display a local masked-only Camera A calibration preview. "
            "No frames are written and no detection pipeline is run."
        )
    )
    parser.add_argument(
        "--source",
        default=LOCAL_CAMERA_SOURCE,
        help="Local Camera A RTSP source; other sources are rejected",
    )
    parser.add_argument(
        "--mask-config",
        default="config/masks.batamfast.yaml",
        help="Draft Camera A mask configuration",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable safe masked-only polygon vertex editing",
    )
    parser.add_argument(
        "--display-scale",
        type=float,
        default=0.8,
        help="Interactive display scale from greater than 0 through 1",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    config = load_draft_mask(args.mask_config)
    run_preview(
        source=args.source,
        config=config,
        config_path=args.mask_config,
        interactive=args.interactive,
        display_scale=args.display_scale,
    )


if __name__ == "__main__":
    main()
