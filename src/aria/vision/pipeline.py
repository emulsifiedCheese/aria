from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import json
import math
import threading
import time
import cv2
from aria.cameras.camera_manager import CameraManager
from aria.cameras.privacy_mask import (
    apply_privacy_mask,
    is_point_in_retained_region,
)
from aria.vision.detector import PersonDetector
from aria.vision.feature_writer import FeatureWriter
from aria.vision.pose_estimator import PoseEstimator
from aria.vision.track_stitcher import AnonymousTrackStitcher
from aria.vision.tracker import extract_tracks
from aria.timebase import sgt_now

ACTIVE_CAMERA_ZONES = {
    "camera_a": "A",
}
DEFAULT_MAX_CONSECUTIVE_DROPPED_FRAMES = 30
DEFAULT_PROCESSING_FPS = 15.0
DEFAULT_INFERENCE_SIZE = 640
DEFAULT_POSE_INFERENCE_SIZE = 384
DEFAULT_KEYPOINT_CONFIDENCE = 0.5
DEFAULT_MIN_CONFIDENT_KEYPOINTS = 5
MIN_DUPLICATE_SHARED_KEYPOINTS = 6
MAX_DUPLICATE_POSE_DISTANCE = 0.15
MIN_DUPLICATE_BOX_IOU = 0.4
PERFORMANCE_SMOOTHING_ALPHA = 0.2
COCO_SKELETON_CONNECTIONS = (
    (0, 1),
    (0, 2),
    (1, 3),
    (2, 4),
    (3, 5),
    (4, 6),
    (5, 6),
    (5, 7),
    (6, 8),
    (7, 9),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (12, 14),
    (13, 15),
    (14, 16),
)

@dataclass
class CapturedFrame:
    frame_number: int
    frame_timestamp_sgt: str
    received_at_monotonic: float
    capture_latency_ms: float
    masked_frame: object | None

class LatestMaskedFrameCapture:

    def __init__(
        self,
        camera,
        mask_config,
        camera_id,
        max_consecutive_dropped_frames,
    ):
        self.camera = camera
        self.mask_config = mask_config
        self.camera_id = camera_id
        self.max_consecutive_dropped_frames = (max_consecutive_dropped_frames)
        self._condition = threading.Condition()
        self._latest = None
        self._terminal_status = None
        self._error = None
        self._finished = False
        self._stop_requested = threading.Event()
        self._thread = None
        self.total_read_attempts = 0
        self.successful_frames = 0
        self.read_failures = 0
        self.replaced_frames = 0

    def start(self):
        self.camera.open()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name=f"{self.camera_id}-masked-capture",
            daemon=True,
        )
        self._thread.start()

    def _capture_loop(self):
        consecutive_dropped_frames = 0

        try:
            while not self._stop_requested.is_set():
                read_started_at = time.perf_counter()
                frame = self.camera.read()
                received_at = time.perf_counter()
                capture_latency_ms = (received_at - read_started_at) * 1000
                self.total_read_attempts += 1
                frame_number = self.total_read_attempts
                frame_timestamp = sgt_now().isoformat(timespec="milliseconds")

                if self._stop_requested.is_set():
                    break

                if frame is None:
                    self.read_failures += 1
                    consecutive_dropped_frames += 1
                    if (consecutive_dropped_frames>= self.max_consecutive_dropped_frames):
                        with self._condition:
                            self._terminal_status = CapturedFrame(
                                frame_number=frame_number,
                                frame_timestamp_sgt=frame_timestamp,
                                received_at_monotonic=received_at,
                                capture_latency_ms=capture_latency_ms,
                                masked_frame=None,
                            )
                        break
                    continue

                consecutive_dropped_frames = 0
                masked_frame = apply_privacy_mask(frame=frame,config=self.mask_config,camera_id=self.camera_id,)
                packet = CapturedFrame(
                    frame_number=frame_number,
                    frame_timestamp_sgt=frame_timestamp,
                    received_at_monotonic=received_at,
                    capture_latency_ms=capture_latency_ms,
                    masked_frame=masked_frame,
                )
                self.successful_frames += 1

                with self._condition:
                    self._terminal_status = None
                    if self._latest is not None:
                        self.replaced_frames += 1
                    self._latest = packet
                    self._condition.notify_all()
        except Exception as error:
            with self._condition:
                self._latest = None
                self._error = error
                self._condition.notify_all()
        finally:
            with self._condition:
                self._finished = True
                self._condition.notify_all()

    def get_latest(self):
        with self._condition:
            while (
                self._latest is None
                and not self._finished
                and self._error is None
            ):
                self._condition.wait(timeout=0.1)

            if self._error is not None:
                raise self._error

            if self._latest is not None:
                packet = self._latest
                self._latest = None
                return packet

            if self._terminal_status is not None:
                packet = self._terminal_status
                self._terminal_status = None
                return packet

            return None

    def stop(self):
        self._stop_requested.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self.camera.close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def summary(self, processed_frames, elapsed_seconds, processing_fps):
        return {
            "camera_id": self.camera_id,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "processing_fps_target": processing_fps,
            "effective_processing_fps": round(
                (
                    processed_frames / elapsed_seconds
                    if elapsed_seconds > 0
                    else 0.0
                ),
                3,
            ),
            "capture_read_attempts": self.total_read_attempts,
            "captured_frames": self.successful_frames,
            "processed_frames": processed_frames,
            "replaced_before_processing": self.replaced_frames,
            "read_failures": self.read_failures,
        }

class CVPipeline:
    def __init__(
        self,
        camera_id,
        source,
        mask_config,
        output_path,
        display=True,
        detector_model="yolov8n.pt",
        detector_confidence=0.5,
        detector_iou=0.7,
        pose_model="yolov8n-pose.pt",
        pose_confidence=0.25,
        tracker_config="config/bytetrack.zone_a.yaml",
        max_consecutive_dropped_frames=(DEFAULT_MAX_CONSECUTIVE_DROPPED_FRAMES),
        tracking_only=False,
        processing_fps=DEFAULT_PROCESSING_FPS,
        inference_size=DEFAULT_INFERENCE_SIZE,
        pose_inference_size=DEFAULT_POSE_INFERENCE_SIZE,
        device=None,
        duration_seconds=None,
        keypoint_confidence=DEFAULT_KEYPOINT_CONFIDENCE,
        min_confident_keypoints=DEFAULT_MIN_CONFIDENT_KEYPOINTS,
        experimental_track_stitching=False,
        writer=None,
        stop_requested=None,
        pause_requested=None,
        started_callback=None,
        preview_callback=None,
    ):
        if camera_id not in ACTIVE_CAMERA_ZONES:
            raise ValueError(
                f"Unsupported camera_id: {camera_id}; "
                "only camera_a is active"
            )

        if (
            not isinstance(max_consecutive_dropped_frames, int)
            or isinstance(max_consecutive_dropped_frames, bool)
            or max_consecutive_dropped_frames <= 0
        ):
            raise ValueError("max_consecutive_dropped_frames must be a positive integer")
        if (
            not isinstance(processing_fps, (int, float))
            or isinstance(processing_fps, bool)
            or processing_fps <= 0
            or processing_fps > 30
        ):
            raise ValueError("processing_fps must be greater than 0 and at most 30")
        if (
            not isinstance(inference_size, int)
            or isinstance(inference_size, bool)
            or inference_size <= 0
        ):
            raise ValueError("inference_size must be a positive integer")
        if (
            not isinstance(pose_inference_size, int)
            or isinstance(pose_inference_size, bool)
            or pose_inference_size <= 0
        ):
            raise ValueError("pose_inference_size must be a positive integer")
        if (
            duration_seconds is not None
            and (
                not isinstance(duration_seconds, (int, float))
                or isinstance(duration_seconds, bool)
                or duration_seconds <= 0
            )
        ):
            raise ValueError("duration_seconds must be greater than 0 when provided")
        if not 0 <= keypoint_confidence <= 1:
            raise ValueError("keypoint_confidence must be between 0 and 1")
        if (
            not isinstance(min_confident_keypoints, int)
            or isinstance(min_confident_keypoints, bool)
            or min_confident_keypoints < 1
            or min_confident_keypoints > 17
        ):
            raise ValueError("min_confident_keypoints must be an integer from 1 to 17")
        if not isinstance(experimental_track_stitching, bool):
            raise TypeError("experimental_track_stitching must be a boolean")

        self.camera_id = camera_id
        self.zone = ACTIVE_CAMERA_ZONES[camera_id]
        self.source = source
        self.mask_config = mask_config
        self.display = display
        self.max_consecutive_dropped_frames = (max_consecutive_dropped_frames)
        self.tracking_only = tracking_only
        self.processing_fps = float(processing_fps)
        self.duration_seconds = duration_seconds
        self.keypoint_confidence = float(keypoint_confidence)
        self.min_confident_keypoints = min_confident_keypoints
        self.track_stitcher = (AnonymousTrackStitcher() if experimental_track_stitching else None)
        self.stop_requested = stop_requested or (lambda: False)
        self.pause_requested = pause_requested or (lambda: False)
        self.started_callback = started_callback
        self.preview_callback = preview_callback
        for callback, name in (
            (self.stop_requested, "stop_requested"),
            (self.pause_requested, "pause_requested"),
        ):
            if not callable(callback):
                raise TypeError(f"{name} must be callable")
        if started_callback is not None and not callable(started_callback):
            raise TypeError("started_callback must be callable")
        if preview_callback is not None and not callable(preview_callback):
            raise TypeError("preview_callback must be callable")
        self.inference_latencies_ms = []
        self.frame_ages_ms = []
        self._last_processed_at = None
        self._rolling_processing_fps = 0.0
        self._rolling_inference_latency_ms = 0.0
        self.rejected_excluded_zone_tracks = 0
        self.rejected_implausible_pose_tracks = 0
        self.suppressed_frame_duplicate_tracks = 0
        self._confirmed_pose_track_ids = set()

        self.model = PersonDetector(
            model_name=detector_model,
            confidence=detector_confidence,
            iou=detector_iou,
            tracker_config=tracker_config,
            inference_size=inference_size,
            device=device,
        )
        self.pose_estimator = None
        if not tracking_only:
            self.pose_estimator = PoseEstimator(
                model_name=pose_model,
                confidence=pose_confidence,
                inference_size=pose_inference_size,
                device=device,
            )
        self.writer = writer if writer is not None else FeatureWriter(output_path)

    def run(self):
        camera = CameraManager(
            camera_id=self.camera_id,
            source=self.source,
            enforce_capture_mode=isinstance(self.source, int),
        )
        capture = LatestMaskedFrameCapture(
            camera=camera,
            mask_config=self.mask_config,
            camera_id=self.camera_id,
            max_consecutive_dropped_frames=(
                self.max_consecutive_dropped_frames
            ),
        )
        processed_frames = 0
        processing_interval = 1.0 / self.processing_fps
        next_process_at = time.monotonic()

        capture.start()
        if self.started_callback is not None:
            self.started_callback()
        started_at = time.monotonic()

        try:
            while True:
                if self.stop_requested():
                    break
                if (
                    self.duration_seconds is not None
                    and time.monotonic() - started_at
                    >= self.duration_seconds
                ):
                    break

                wait_seconds = next_process_at - time.monotonic()
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                if self.stop_requested():
                    break

                packet = capture.get_latest()
                if packet is None:
                    break

                if self.pause_requested():
                    record_excluded = getattr(
                        self.writer,
                        "record_excluded",
                        None,
                    )
                    if callable(record_excluded):
                        record_excluded()
                    next_process_at = max(
                        next_process_at + processing_interval,
                        time.monotonic(),
                    )
                    continue

                if packet.masked_frame is None:
                    self.writer.write(
                        self._frame_status_record(
                            frame_number=packet.frame_number,
                            frame_timestamp=(
                                packet.frame_timestamp_sgt
                            ),
                            frame_available=False,
                            capture_latency_ms=(
                                packet.capture_latency_ms
                            ),
                            total_latency_ms=(
                                time.perf_counter()
                                - packet.received_at_monotonic
                            )
                            * 1000,
                        )
                    )
                    continue

                processed_frames += 1
                should_stop = self._process_frame(packet)
                if should_stop:
                    break

                next_process_at = max(
                    next_process_at + processing_interval,
                    time.monotonic(),
                )
        finally:
            capture.stop()
            if hasattr(self.writer, "close"):
                self.writer.close()
            cv2.destroyAllWindows()

        elapsed_seconds = time.monotonic() - started_at
        summary = capture.summary(
            processed_frames=processed_frames,
            elapsed_seconds=elapsed_seconds,
            processing_fps=self.processing_fps,
        )
        summary["inference_latency_ms"] = self._metric_summary(self.inference_latencies_ms)
        summary["frame_age_ms"] = self._metric_summary(self.frame_ages_ms)
        summary["rejected_excluded_zone_tracks"] = (self.rejected_excluded_zone_tracks)
        summary["rejected_implausible_pose_tracks"] = (self.rejected_implausible_pose_tracks)
        summary["suppressed_frame_duplicate_tracks"] = (self.suppressed_frame_duplicate_tracks)
        summary["anonymous_track_stitching"] = (
            self.track_stitcher.summary()
            if self.track_stitcher is not None
            else {"enabled": False}
        )
        print("CV pipeline summary:")
        print(json.dumps(summary, indent=2))
        return summary

    def _process_frame(self, packet):
        detection_started_at = time.perf_counter()
        result = self.model.track(packet.masked_frame)
        detection_latency_ms = (time.perf_counter() - detection_started_at) * 1000
        tracks = extract_tracks(result)
        tracks = self._filter_tracks_to_retained_region(tracks)

        pose_latency_ms = 0.0
        if not self.tracking_only and tracks:
            pose_started_at = time.perf_counter()
            poses = self.pose_estimator.estimate_many(packet.masked_frame,[track["bounding_box"] for track in tracks],)
            pose_latency_ms = (time.perf_counter() - pose_started_at) * 1000
            for track, (keypoints, confidences) in zip(tracks, poses):
                track["keypoints"] = keypoints
                track["keypoint_confidences"] = confidences

        tracks = self._filter_tracks(tracks)
        if self.track_stitcher is not None:
            tracks = self.track_stitcher.associate(tracks,packet.received_at_monotonic,)
        inference_latency_ms = detection_latency_ms + pose_latency_ms
        self.inference_latencies_ms.append(inference_latency_ms)
        self._update_performance_metrics(inference_latency_ms)

        if not tracks:
            self.writer.write(
                self._frame_status_record(
                    frame_number=packet.frame_number,
                    frame_timestamp=packet.frame_timestamp_sgt,
                    frame_available=True,
                    capture_latency_ms=packet.capture_latency_ms,
                    detection_latency_ms=detection_latency_ms,
                    total_latency_ms=(time.perf_counter() - packet.received_at_monotonic) * 1000,
                )
            )

        for track in tracks:
            keypoints = track.get("keypoints", [])
            keypoint_confidences = track.get(
                "keypoint_confidences",
                [],
            )
            total_latency_ms = (time.perf_counter() - packet.received_at_monotonic) * 1000
            record = {
                "schema_version": 2,
                "record_type": "track",
                "camera_id": self.camera_id,
                "zone": self.zone,
                "frame_number": packet.frame_number,
                "frame_timestamp_sgt": (
                    packet.frame_timestamp_sgt
                ),
                "frame_available": True,
                "pose_available": bool(keypoints),
                "local_track_id": track["local_track_id"],
                "bounding_box": track["bounding_box"],
                "detection_confidence": track[
                    "detection_confidence"
                ],
                "keypoints": keypoints,
                "keypoint_confidences": keypoint_confidences,
                "capture_latency_ms": round(
                    packet.capture_latency_ms,
                    2,
                ),
                "detection_latency_ms": round(
                    detection_latency_ms,
                    2,
                ),
                "pose_latency_ms": round(pose_latency_ms, 2),
                "total_latency_ms": round(total_latency_ms, 2),
                "mask_config_version": (
                    self.mask_config.mask_config_version
                ),
            }
            for field_name in (
                "stitched_track_id",
                "track_association_status",
                "track_association_reason",
            ):
                if field_name in track:
                    record[field_name] = track[field_name]
            self.writer.write(record)

            if self.display or self.preview_callback is not None:
                self._draw_track(packet.masked_frame, record)

        self.frame_ages_ms.append(
            (time.perf_counter() - packet.received_at_monotonic) * 1000)

        if not self.display and self.preview_callback is None:
            return False

        self._draw_performance_overlay(packet.masked_frame)
        if self.preview_callback is not None:
            self.preview_callback(packet.masked_frame)
        if not self.display:
            return False
        cv2.imshow(f"ARIA CV Pipeline - {self.camera_id}",packet.masked_frame,)
        return cv2.waitKey(1) & 0xFF == ord("q")

    def _update_performance_metrics(self, inference_latency_ms):
        processed_at = time.perf_counter()
        if self._last_processed_at is not None:
            interval_seconds = processed_at - self._last_processed_at
            if interval_seconds > 0:
                instantaneous_fps = 1.0 / interval_seconds
                if self._rolling_processing_fps == 0.0:
                    self._rolling_processing_fps = instantaneous_fps
                else:
                    alpha = PERFORMANCE_SMOOTHING_ALPHA
                    self._rolling_processing_fps = (alpha * instantaneous_fps + (1 - alpha) * self._rolling_processing_fps)
        self._last_processed_at = processed_at

        if self._rolling_inference_latency_ms == 0.0:
            self._rolling_inference_latency_ms = inference_latency_ms
        else:
            alpha = PERFORMANCE_SMOOTHING_ALPHA
            self._rolling_inference_latency_ms = (alpha * inference_latency_ms + (1 - alpha) * self._rolling_inference_latency_ms)

    def _filter_tracks(self, tracks):
        accepted = []

        for track in tracks:
            if not self.tracking_only:
                confident_keypoints = sum(
                    confidence is not None
                    and confidence >= self.keypoint_confidence
                    for confidence in track.get(
                        "keypoint_confidences",
                        [],
                    )
                )
                if confident_keypoints < self.min_confident_keypoints:
                    self.rejected_implausible_pose_tracks += 1
                    if (
                        track["local_track_id"]
                        not in self._confirmed_pose_track_ids
                    ):
                        continue
                    track = dict(track)
                    track["keypoints"] = []
                    track["keypoint_confidences"] = []
                else:
                    self._confirmed_pose_track_ids.add(track["local_track_id"])

            accepted.append(track)

        if self.tracking_only:
            return accepted

        return self._suppress_frame_duplicates(accepted)

    def _filter_tracks_to_retained_region(self, tracks):
        accepted = []
        for track in tracks:
            x1, _y1, x2, y2 = track["bounding_box"]
            anchor_x = (x1 + x2) / 2
            anchor_y = y2 - 1
            if not is_point_in_retained_region(
                self.mask_config,
                anchor_x,
                anchor_y,
            ):
                self.rejected_excluded_zone_tracks += 1
                continue
            accepted.append(track)
        return accepted

    def _suppress_frame_duplicates(self, tracks):
        retained = []
        for candidate in sorted(
            tracks,
            key=lambda track: track["local_track_id"],
        ):
            if any(
                self._are_same_frame_duplicates(candidate, existing)
                for existing in retained
            ):
                self.suppressed_frame_duplicate_tracks += 1
                continue
            retained.append(candidate)
        return retained

    def _are_same_frame_duplicates(self, first, second):
        if self._box_iou(
            first["bounding_box"],
            second["bounding_box"],
        ) < MIN_DUPLICATE_BOX_IOU:
            return False

        first_box = first["bounding_box"]
        second_box = second["bounding_box"]
        scale = max(
            first_box[2] - first_box[0],
            first_box[3] - first_box[1],
            second_box[2] - second_box[0],
            second_box[3] - second_box[1],
            1,
        )
        distances = []
        for (
            first_point,
            first_confidence,
            second_point,
            second_confidence,
        ) in zip(
            first.get("keypoints", []),
            first.get("keypoint_confidences", []),
            second.get("keypoints", []),
            second.get("keypoint_confidences", []),
        ):
            if (
                first_confidence is None
                or second_confidence is None
                or first_confidence < self.keypoint_confidence
                or second_confidence < self.keypoint_confidence
            ):
                continue
            distances.append(
                math.hypot(first_point[0] - second_point[0],first_point[1] - second_point[1],) / scale)

        return (
            len(distances) >= MIN_DUPLICATE_SHARED_KEYPOINTS
            and sum(distances) / len(distances)
            <= MAX_DUPLICATE_POSE_DISTANCE
        )

    @staticmethod
    def _box_iou(first, second):
        intersection_width = max(0,min(first[2], second[2]) - max(first[0], second[0]),)
        intersection_height = max(0,min(first[3], second[3]) - max(first[1], second[1]),)
        intersection = intersection_width * intersection_height
        first_area = max(0, first[2] - first[0]) * max(0,first[3] - first[1],)
        second_area = max(0, second[2] - second[0]) * max(0,second[3] - second[1],)
        union = first_area + second_area - intersection
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _metric_summary(values):
        if not values:
            return {
                "mean": 0.0,
                "p95": 0.0,
                "maximum": 0.0,
            }

        ordered = sorted(values)
        position = (len(ordered) - 1) * 0.95
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        p95 = (ordered[lower] * (1 - weight)
            + ordered[upper] * weight
        )
        return {
            "mean": round(sum(values) / len(values), 3),
            "p95": round(p95, 3),
            "maximum": round(max(values), 3),
        }

    def _frame_status_record(
        self,
        frame_number,
        frame_timestamp,
        frame_available,
        capture_latency_ms,
        total_latency_ms,
        detection_latency_ms=0.0,
    ):
        return {
            "schema_version": 2,
            "record_type": "frame_status",
            "camera_id": self.camera_id,
            "zone": self.zone,
            "frame_number": frame_number,
            "frame_timestamp_sgt": frame_timestamp,
            "frame_available": frame_available,
            "pose_available": False,
            "local_track_id": None,
            "bounding_box": None,
            "detection_confidence": None,
            "keypoints": [],
            "keypoint_confidences": [],
            "capture_latency_ms": round(capture_latency_ms, 2),
            "detection_latency_ms": round(
                detection_latency_ms,
                2,
            ),
            "pose_latency_ms": 0.0,
            "total_latency_ms": round(total_latency_ms, 2),
            "mask_config_version": self.mask_config.mask_config_version,
        }

    @staticmethod
    def _draw_track(frame, record):
        x1, y1, x2, y2 = record["bounding_box"]

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (255, 255, 255),
            2,
        )
        stitched_id = record.get("stitched_track_id")
        label = f"ID {record['local_track_id']}"
        if "track_association_status" in record:
            stitched_label = "?" if stitched_id is None else stitched_id
            label = f"R{record['local_track_id']} / S{stitched_label}"
        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2,
        )

        keypoints = record["keypoints"]
        confidences = record["keypoint_confidences"]

        for first_index, second_index in COCO_SKELETON_CONNECTIONS:
            if (
                first_index >= len(keypoints)
                or second_index >= len(keypoints)
                or first_index >= len(confidences)
                or second_index >= len(confidences)
            ):
                continue

            first_confidence = confidences[first_index]
            second_confidence = confidences[second_index]
            if (
                first_confidence is not None and first_confidence < 0.25
            ) or (
                second_confidence is not None and second_confidence < 0.25
            ):
                continue

            first_point = tuple(
                int(value) for value in keypoints[first_index]
            )
            second_point = tuple(
                int(value) for value in keypoints[second_index]
            )
            cv2.line(
                frame,
                first_point,
                second_point,
                (255, 255, 255),
                2,
            )

        for keypoint, confidence in zip(
            keypoints,
            confidences,
        ):
            if confidence is not None and confidence < 0.25:
                continue

            x, y = [int(value) for value in keypoint]
            cv2.circle(frame, (x, y), 3, (0, 255, 0), -1)

    def _draw_performance_overlay(self, frame):
        cv2.rectangle(
            frame,
            (10, 10),
            (360, 78),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            frame,
            f"Processing FPS: {self._rolling_processing_fps:.1f}",
            (20, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            (
                "Vision inference: "
                f"{self._rolling_inference_latency_ms:.1f} ms"
            ),
            (20, 68),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
        )