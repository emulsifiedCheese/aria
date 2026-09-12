import json
import pytest
from jsonschema import ValidationError
from aria.vision.feature_writer import FeatureWriter

def valid_track_record():
    return {
        "schema_version": 2,
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": 1,
        "frame_timestamp_sgt": "2026-07-31T12:00:00.000+08:00",
        "frame_available": True,
        "pose_available": True,
        "local_track_id": 7,
        "bounding_box": [10, 20, 100, 200],
        "detection_confidence": 0.85,
        "keypoints": [[20.0, 30.0]],
        "keypoint_confidences": [0.9],
        "capture_latency_ms": 10.0,
        "detection_latency_ms": 20.0,
        "pose_latency_ms": 30.0,
        "total_latency_ms": 60.0,
        "mask_config_version": "batamfast-v1",
    }

def test_feature_writer_writes_schema_valid_record(tmp_path):
    output = tmp_path / "tracks.jsonl"
    writer = FeatureWriter(output)

    writer.write(valid_track_record())

    assert json.loads(output.read_text(encoding="utf-8")) == valid_track_record()

def test_feature_writer_rejects_wrong_camera_before_writing(tmp_path):
    output = tmp_path / "tracks.jsonl"
    writer = FeatureWriter(output)
    record = valid_track_record()
    record["camera_id"] = "camera_b"

    with pytest.raises(ValidationError):
        writer.write(record)

    assert not output.exists()

def test_feature_writer_requires_explicit_availability(tmp_path):
    writer = FeatureWriter(tmp_path / "tracks.jsonl")
    record = valid_track_record()
    del record["pose_available"]

    with pytest.raises(ValidationError):
        writer.write(record)

def test_feature_writer_accepts_experimental_stitched_association(tmp_path):
    output = tmp_path / "tracks.jsonl"
    writer = FeatureWriter(output)
    record = valid_track_record()
    record.update({
        "stitched_track_id": 2,
        "track_association_status": "stitched",
        "track_association_reason": "unique_spatiotemporal_match",
    })

    writer.write(record)

    assert json.loads(output.read_text(encoding="utf-8")) == record

def test_uncertain_association_requires_null_stitched_id(tmp_path):
    writer = FeatureWriter(tmp_path / "tracks.jsonl")
    record = valid_track_record()
    record.update({
        "stitched_track_id": 2,
        "track_association_status": "uncertain",
        "track_association_reason": "multiple_candidates",
    })

    with pytest.raises(ValidationError):
        writer.write(record)

def test_feature_writer_accepts_explicit_uncertain_association(tmp_path):
    output = tmp_path / "tracks.jsonl"
    writer = FeatureWriter(output)
    record = valid_track_record()
    record.update({
        "stitched_track_id": None,
        "track_association_status": "uncertain",
        "track_association_reason": "simultaneous_overlap",
    })

    writer.write(record)

    assert json.loads(output.read_text(encoding="utf-8")) == record