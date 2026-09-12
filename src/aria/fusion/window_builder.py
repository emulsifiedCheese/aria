"""deterministic zone a multimodal feature-window construction"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from statistics import fmean, pstdev
from jsonschema import Draft202012Validator, FormatChecker
from aria.timebase import SGT

ACTIVE_NODES = ("ESP-A1", "ESP-A2")
CAMERA_ID = "camera_a"
DEFAULT_WINDOW_SECONDS = 2.0
ESP_PACKET_INTERVAL_SECONDS = 1.0
SCHEMA_VERSION = 2
DEFAULT_SCHEMA_PATH = (Path(__file__).resolve().parents[3] / "schemas" / "feature_vector.schema.json")

def parse_aware_timestamp(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    if not value.endswith("+08:00"):
        raise ValueError(f"{field_name} must use the +08:00 SGT offset")
    candidate = value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError(f"Invalid {field_name}: {value}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a SGT offset")
    return parsed.astimezone(SGT)

def _sgt_text(value: datetime) -> str:
    return value.astimezone(SGT).isoformat(timespec="milliseconds")

def _window_start(value: datetime, duration_seconds: float) -> datetime:
    epoch_seconds = value.timestamp()
    start_seconds = math.floor(epoch_seconds / duration_seconds) * duration_seconds
    return datetime.fromtimestamp(start_seconds, tz=SGT)

def _mean(values):
    return fmean(values) if values else None

def _minimum(values):
    return min(values) if values else None

def _maximum(values):
    return max(values) if values else None

def _ratio(numerator: int, denominator: int):
    return numerator / denominator if denominator else None

def _gap_count(values):
    ordered = sorted(set(values))
    return sum(max(0, current - previous - 1) for previous, current in zip(ordered, ordered[1:]))

def _interval_quality(timestamps, expected_interval_ms=None):
    ordered = sorted(set(timestamps))
    intervals = [
        (current - previous).total_seconds() * 1000
        for previous, current in zip(ordered, ordered[1:])
    ]
    mean_ms = _mean(intervals)
    return {
        "interval_count": len(intervals),
        "mean_interval_ms": mean_ms,
        "interval_std_ms": pstdev(intervals) if len(intervals) > 1 else (
            0.0 if intervals else None
        ),
        "mean_absolute_jitter_ms": (
            _mean([abs(value - expected_interval_ms) for value in intervals])
            if expected_interval_ms is not None
            else None
        ),
    }

def _angle_degrees(first, vertex, third):
    a = (first[0] - vertex[0], first[1] - vertex[1])
    b = (third[0] - vertex[0], third[1] - vertex[1])
    magnitude = math.hypot(*a) * math.hypot(*b)
    if magnitude == 0:
        return None
    cosine = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / magnitude))
    return math.degrees(math.acos(cosine))

def _pose_measurements(record, confidence_threshold):
    keypoints = record.get("keypoints", [])
    confidences = record.get("keypoint_confidences", [])
    confident = [
        point
        for point, confidence in zip(keypoints, confidences)
        if confidence is not None and confidence >= confidence_threshold
    ]
    centroid = None
    if confident:
        centroid = (
            fmean(point[0] for point in confident),
            fmean(point[1] for point in confident),
        )
    angle_triplets = (
        (5, 7, 9),
        (6, 8, 10),
        (11, 13, 15),
        (12, 14, 16),
    )
    angles = []
    for first, vertex, third in angle_triplets:
        if max(first, vertex, third) >= len(keypoints):
            continue
        selected_confidences = (
            confidences[first],
            confidences[vertex],
            confidences[third],
        )
        if any(
            confidence is None or confidence < confidence_threshold
            for confidence in selected_confidences
        ):
            continue
        angle = _angle_degrees(
            keypoints[first],
            keypoints[vertex],
            keypoints[third],
        )
        if angle is not None:
            angles.append(angle)

    return centroid, angles, [
        confidence for confidence in confidences if confidence is not None
    ]

def _camera_features(records, confidence_threshold):
    frame_numbers = {record["frame_number"] for record in records}
    available_frames = {
        record["frame_number"]
        for record in records
        if record["frame_available"]
    }
    unavailable_frames = {
        record["frame_number"]
        for record in records
        if not record["frame_available"]
    }
    track_records = [record for record in records if record["record_type"] == "track"]
    pose_records = [record for record in track_records if record["pose_available"]]

    centers_x = []
    centers_y = []
    detection_confidences = []
    pose_confidences = []
    joint_angles = []
    centroids_by_track = defaultdict(list)

    for record in track_records:
        box = record.get("bounding_box")
        if box is not None:
            centers_x.append((box[0] + box[2]) / 2)
            centers_y.append((box[1] + box[3]) / 2)
        confidence = record.get("detection_confidence")
        if confidence is not None:
            detection_confidences.append(confidence)
        if not record["pose_available"]:
            continue
        centroid, angles, confidences = _pose_measurements(
            record,
            confidence_threshold,
        )
        joint_angles.extend(angles)
        pose_confidences.extend(confidences)
        if centroid is not None:
            centroids_by_track[record["local_track_id"]].append((record["_timestamp"], centroid))

    movement_speeds = []
    for observations in centroids_by_track.values():
        observations.sort(key=lambda item: item[0])
        for (previous_time, previous), (current_time, current) in zip(
            observations, observations[1:]
        ):
            elapsed = (current_time - previous_time).total_seconds()
            if elapsed > 0:
                movement_speeds.append(
                    math.hypot(
                        current[0] - previous[0],
                        current[1] - previous[1],
                    ) / elapsed
                )

    timestamps = [
        record["_timestamp"]
        for frame_number in frame_numbers
        for record in records
        if record["frame_number"] == frame_number
    ]
    timestamps = sorted(set(timestamps))
    return {
        "available": bool(available_frames),
        "record_count": len(records),
        "frame_count": len(frame_numbers),
        "available_frame_count": len(available_frames),
        "unavailable_frame_count": len(unavailable_frames),
        "frame_number_gap_count": _gap_count(frame_numbers),
        "track_record_count": len(track_records),
        "unique_track_count": len({
            record["local_track_id"] for record in track_records
        }),
        "pose_available_count": len(pose_records),
        "pose_missing_count": len(track_records) - len(pose_records),
        "pose_availability_ratio": _ratio(len(pose_records), len(track_records)),
        "bbox_center_x_mean_px": _mean(centers_x),
        "bbox_center_y_mean_px": _mean(centers_y),
        "detection_confidence_mean": _mean(detection_confidences),
        "keypoint_confidence_mean": _mean(pose_confidences),
        "joint_angle_mean_degrees": _mean(joint_angles),
        "movement_speed_mean_px_per_second": _mean(movement_speeds),
        "timing": _interval_quality(timestamps),
    }

def _sensor_features(records, node_id, expected_packets):
    payloads = [record["payload"] for record in records]
    pir_motion = [payload["pir_motion"] for payload in payloads]
    pir_recent = [payload["pir_recent_activity"] for payload in payloads]
    audio_peak = [
        payload["audio_peak_to_peak"]
        for payload in payloads
        if payload["audio_peak_to_peak"] is not None
    ]
    audio_activity = [
        payload["audio_activity"]
        for payload in payloads
        if payload["audio_activity"] is not None
    ]
    audio_rms = [
        payload["audio_rms"]
        for payload in payloads
        if payload["audio_rms"] is not None
    ]
    result = {
        "available": bool(records),
        "packet_count": len(records),
        "expected_packet_count": expected_packets,
        "missing_packet_count": max(0, expected_packets - len(records)),
        "sequence_gap_count": _gap_count(
            payload["sequence"] for payload in payloads
        ),
        "pir_motion_ratio": _ratio(sum(pir_motion), len(pir_motion)),
        "pir_recent_activity_ratio": _ratio(sum(pir_recent), len(pir_recent)),
        "audio_peak_to_peak_mean": _mean(audio_peak),
        "audio_activity_mean": _mean(audio_activity),
        "audio_rms_mean": _mean(audio_rms),
        "audio_rms_min": _minimum(audio_rms),
        "audio_rms_max": _maximum(audio_rms),
        "wifi_rssi_dbm_mean": _mean([
            payload["wifi_rssi_dbm"] for payload in payloads
        ]),
        "timing": _interval_quality(
            [record["_timestamp"] for record in records],
            expected_interval_ms=ESP_PACKET_INTERVAL_SECONDS * 1000,
        ),
    }
    if node_id == "ESP-A1":
        valid_distances = [
            payload["distance_cm"]
            for payload in payloads
            if payload["distance_valid"]
            and payload["distance_cm"] is not None
            and payload["distance_cm"] >= 0
        ]
        result["distance_valid_ratio"] = _ratio(sum(payload["distance_valid"] for payload in payloads),len(payloads),)
        result["distance_cm_mean"] = _mean(valid_distances)
        result["distance_cm_min"] = _minimum(valid_distances)
        result["distance_cm_max"] = _maximum(valid_distances)
    return result

def _load_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {error}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            record["_line_number"] = line_number
            records.append(record)
    return records

def _remove_excluded_records(records, excluded_window_ids, window_seconds):
    excluded_window_ids = set(excluded_window_ids)
    if not excluded_window_ids:
        return records
    duration_ms = int(round(window_seconds * 1000))
    retained = []
    for record in records:
        start = _window_start(record["_timestamp"], window_seconds)
        window_id = f"zone_a_{int(start.timestamp() * 1000)}_{duration_ms}"
        if window_id not in excluded_window_ids:
            retained.append(record)
    return retained

def load_camera_records(
    path,
    *,
    excluded_window_ids=(),
    window_seconds=DEFAULT_WINDOW_SECONDS,
):
    records = _load_jsonl(path)
    for record in records:
        if record.get("camera_id") != CAMERA_ID:
            raise ValueError(f"{path}:{record['_line_number']}: only camera_a is active")
        record["_timestamp"] = parse_aware_timestamp(record.get("frame_timestamp_sgt"),"frame_timestamp_sgt",)
    return _remove_excluded_records(records, excluded_window_ids, window_seconds)

def load_sensor_records(
    path,
    *,
    excluded_window_ids=(),
    window_seconds=DEFAULT_WINDOW_SECONDS,
):
    records = _load_jsonl(path)
    for record in records:
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{record['_line_number']}: payload must be an object")
        node_id = payload.get("node_id")
        if node_id not in ACTIVE_NODES:
            raise ValueError(f"{path}:{record['_line_number']}: inactive node {node_id!r}")
        if payload.get("zone") != "A":
            raise ValueError(f"{path}:{record['_line_number']}: active nodes must use Zone A")
        if node_id == "ESP-A1":
            if "distance_cm" not in payload or "distance_valid" not in payload:
                raise ValueError(f"{path}:{record['_line_number']}: ESP-A1 distance fields required")
        elif "distance_cm" in payload or "distance_valid" in payload:
            raise ValueError(f"{path}:{record['_line_number']}: ESP-A2 must omit distance fields")
        record["_timestamp"] = parse_aware_timestamp(record.get("received_at_sgt"),"received_at_sgt",)
    return _remove_excluded_records(records, excluded_window_ids, window_seconds)

def build_windows(
    camera_records,
    sensor_records,
    window_seconds=DEFAULT_WINDOW_SECONDS,
    keypoint_confidence=0.5,
    excluded_window_ids=(),
):
    if (
        not isinstance(window_seconds, (int, float))
        or isinstance(window_seconds, bool)
        or not math.isfinite(window_seconds)
        or window_seconds <= 0
    ):
        raise ValueError("window_seconds must be a finite number greater than zero")
    if not 0 <= keypoint_confidence <= 1:
        raise ValueError("keypoint_confidence must be between zero and one")

    all_records = list(camera_records) + list(sensor_records)
    if not all_records:
        return []
    grouped_camera = defaultdict(list)
    grouped_sensors = {node_id: defaultdict(list) for node_id in ACTIVE_NODES}
    occupied_starts = set()
    for record in camera_records:
        start = _window_start(record["_timestamp"], window_seconds)
        occupied_starts.add(start)
        grouped_camera[start].append(record)
    for record in sensor_records:
        start = _window_start(record["_timestamp"], window_seconds)
        occupied_starts.add(start)
        grouped_sensors[record["payload"]["node_id"]][start].append(record)

    expected_packets = max(1,math.ceil(window_seconds / ESP_PACKET_INTERVAL_SECONDS),)
    first_start = min(occupied_starts)
    last_start = max(occupied_starts)
    starts = []
    start = first_start
    while start <= last_start:
        starts.append(start)
        start += timedelta(seconds=window_seconds)
    excluded_window_ids = set(excluded_window_ids)
    windows = []
    for start in starts:
        end = start + timedelta(seconds=window_seconds)
        window_id = (f"zone_a_{int(start.timestamp() * 1000)}_"f"{int(window_seconds * 1000)}")
        if window_id in excluded_window_ids:
            continue
        camera = _camera_features(
            sorted(
                grouped_camera[start],
                key=lambda record: (
                    record["_timestamp"],
                    record["frame_number"],
                    record.get("local_track_id") or -1,
                ),
            ),
            keypoint_confidence,
        )
        a1 = _sensor_features(
            sorted(
                grouped_sensors["ESP-A1"][start],
                key=lambda record: record["_timestamp"],
            ),
            "ESP-A1",
            expected_packets,
        )
        a2 = _sensor_features(
            sorted(
                grouped_sensors["ESP-A2"][start],
                key=lambda record: record["_timestamp"],
            ),
            "ESP-A2",
            expected_packets,
        )
        windows.append({
            "schema_version": SCHEMA_VERSION,
            "window_id": window_id,
            "zone": "A",
            "window_start_sgt": _sgt_text(start),
            "window_end_sgt": _sgt_text(end),
            "window_duration_ms": int(round(window_seconds * 1000)),
            "camera_available": camera["available"],
            "pose_available": camera["pose_available_count"] > 0,
            "a1_available": a1["available"],
            "a2_available": a2["available"],
            "camera": camera,
            "esp_a1": a1,
            "esp_a2": a2,
        })
    return windows

def validate_and_write_windows(
    windows,
    output_path,
    schema_path=DEFAULT_SCHEMA_PATH,
    excluded_window_ids=(),
):
    with Path(schema_path).open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    excluded_window_ids = set(excluded_window_ids)
    with output.open("w", encoding="utf-8") as stream:
        for window in windows:
            if window.get("window_id") in excluded_window_ids:
                raise ValueError("Excluded windows cannot be written")
            validator.validate(window)
            stream.write(json.dumps(window, sort_keys=True) + "\n")