"""phase 12.1 adapter around frozen offline feature calculations"""
from __future__ import annotations
from datetime import datetime, timedelta
import math
import numpy as np
from aria.fusion.window_builder import (
    ACTIVE_NODES,
    CAMERA_ID,
    DEFAULT_WINDOW_SECONDS,
    ESP_PACKET_INTERVAL_SECONDS,
    SCHEMA_VERSION,
    _camera_features,
    _sensor_features,
    _sgt_text,
    _window_start,
)
from aria.timebase import SGT

class InferencePreprocessingError(ValueError):
    """raised when live feature vector differs from the frozen model input"""

def _flatten_numeric(value, prefix, output):
    if isinstance(value, dict):
        for key in sorted(value):
            _flatten_numeric(value[key], f"{prefix}.{key}" if prefix else key, output)
    elif isinstance(value, bool):
        output[prefix] = float(value)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if not math.isfinite(numeric):
            raise InferencePreprocessingError(f"non-finite modelling feature encountered: {prefix}")
        output[prefix] = numeric
    elif value is None:
        output[prefix] = None
    else:
        raise InferencePreprocessingError(f"non-numeric modelling feature encountered: {prefix}")

def camera_feature_matrix(feature_vector, *, feature_roots, feature_names):
    """conv one schema-valid feature vector to frozen ordered model matrix"""
    if not isinstance(feature_vector, dict):
        raise InferencePreprocessingError("feature_vector must be an object")
    if not isinstance(feature_roots, (list, tuple)) or not feature_roots:
        raise InferencePreprocessingError("feature_roots must be a non-empty sequence")
    if not isinstance(feature_names, (list, tuple)) or not feature_names:
        raise InferencePreprocessingError("feature_names must be a non-empty sequence")
    if len(feature_names) != len(set(feature_names)):
        raise InferencePreprocessingError("feature_names contain duplicates")

    flattened = {}
    for root in feature_roots:
        if root not in feature_vector:
            raise InferencePreprocessingError(f"feature vector is missing frozen root: {root}")
        _flatten_numeric(feature_vector[root], root, flattened)
    actual_names = sorted(flattened)
    if actual_names != list(feature_names):
        missing = sorted(set(feature_names) - set(actual_names))
        unexpected = sorted(set(actual_names) - set(feature_names))
        raise InferencePreprocessingError(f"frozen feature fields differ: missing={missing}, unexpected={unexpected}")
    matrix = np.asarray(
        [[
            np.nan if flattened[name] is None else flattened[name]
            for name in feature_names
        ]],
        dtype=float,
    )
    return matrix

def build_track_feature_window(
    start,
    camera_records,
    sensor_records,
    *,
    local_track_id,
    keypoint_confidence=0.5,
):
    """build frozen two-second feature vector for one camera-local track"""
    if not isinstance(start, datetime) or start.tzinfo is None:
        raise ValueError("start must be a timezone-aware datetime")
    start = start.astimezone(SGT)
    if start != _window_start(start, DEFAULT_WINDOW_SECONDS):
        raise ValueError("start must align to a two-second window boundary")
    if local_track_id is None:
        if camera_records:
            raise ValueError("local_track_id may be null only without camera track records")
    elif (
        not isinstance(local_track_id, int)
        or isinstance(local_track_id, bool)
        or local_track_id < 0
    ):
        raise ValueError("local_track_id must be a non-negative integer or null")
    if (
        not isinstance(keypoint_confidence, (int, float))
        or isinstance(keypoint_confidence, bool)
        or not math.isfinite(keypoint_confidence)
        or not 0 <= keypoint_confidence <= 1
    ):
        raise ValueError("keypoint_confidence must be between zero and one")
    if not isinstance(sensor_records, dict) or set(sensor_records) != set(ACTIVE_NODES):
        raise ValueError("sensor_records must contain exactly ESP-A1 and ESP-A2")

    end = start + timedelta(seconds=DEFAULT_WINDOW_SECONDS)
    selected_camera_records = list(camera_records)
    for record in selected_camera_records:
        if record.get("camera_id") != CAMERA_ID or record.get("zone") != "A":
            raise ValueError("track feature records must come from Camera A in Zone A")
        if record.get("record_type") != "track":
            raise ValueError("track feature records must have record_type track")
        if record.get("local_track_id") != local_track_id:
            raise ValueError("cross-track camera aggregation is prohibited")
        timestamp = record.get("_timestamp")
        if not isinstance(timestamp, datetime) or not start <= timestamp < end:
            raise ValueError("camera record is outside the requested feature window")

    selected_sensor_records = {}
    for node_id in ACTIVE_NODES:
        records = list(sensor_records[node_id])
        for record in records:
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("node_id") != node_id:
                raise ValueError("sensor record is stored under the wrong active node")
            timestamp = record.get("_timestamp")
            if not isinstance(timestamp, datetime) or not start <= timestamp < end:
                raise ValueError("sensor record is outside the requested feature window")
        selected_sensor_records[node_id] = records

    camera = _camera_features(
        sorted(
            selected_camera_records,
            key=lambda record: (
                record["_timestamp"],
                record["frame_number"],
                record["local_track_id"],
            ),
        ),
        keypoint_confidence,
    )
    expected_packets = max(
        1,
        math.ceil(DEFAULT_WINDOW_SECONDS / ESP_PACKET_INTERVAL_SECONDS),
    )
    sensors = {
        node_id: _sensor_features(
            sorted(
                selected_sensor_records[node_id],
                key=lambda record: record["_timestamp"],
            ),
            node_id,
            expected_packets,
        )
        for node_id in ACTIVE_NODES
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "window_id": (
            f"zone_a_{int(start.timestamp() * 1000)}_"
            f"{int(DEFAULT_WINDOW_SECONDS * 1000)}"
        ),
        "zone": "A",
        "window_start_sgt": _sgt_text(start),
        "window_end_sgt": _sgt_text(end),
        "window_duration_ms": int(DEFAULT_WINDOW_SECONDS * 1000),
        "camera_available": camera["available"],
        "pose_available": camera["pose_available_count"] > 0,
        "a1_available": sensors["ESP-A1"]["available"],
        "a2_available": sensors["ESP-A2"]["available"],
        "camera": camera,
        "esp_a1": sensors["ESP-A1"],
        "esp_a2": sensors["ESP-A2"],
    }