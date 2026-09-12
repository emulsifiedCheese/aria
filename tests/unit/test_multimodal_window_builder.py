import json
import pytest
from aria.fusion.window_builder import (
    build_windows,
    load_camera_records,
    load_sensor_records,
    validate_and_write_windows,
)
from aria.inference.preprocessing import build_track_feature_window
from scripts.build_multimodal_windows import load_excluded_window_ids, main

def camera_record(timestamp, frame_number=1, track_id=7, pose_available=True):
    keypoints = [[float(index * 10), float(index * 5)] for index in range(17)]
    return {
        "schema_version": 2,
        "record_type": "track",
        "camera_id": "camera_a",
        "zone": "A",
        "frame_number": frame_number,
        "frame_timestamp_sgt": timestamp,
        "frame_available": True,
        "pose_available": pose_available,
        "local_track_id": track_id,
        "bounding_box": [10, 20, 110, 220],
        "detection_confidence": 0.8,
        "keypoints": keypoints if pose_available else [],
        "keypoint_confidences": [0.9] * 17 if pose_available else [],
        "capture_latency_ms": 10.0,
        "detection_latency_ms": 20.0,
        "pose_latency_ms": 30.0,
        "total_latency_ms": 60.0,
        "mask_config_version": "batamfast-v1",
    }

def sensor_record(node_id, timestamp, sequence=1):
    payload = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": (
            "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC"
        ),
        "boot_id": 123,
        "node_id": node_id,
        "zone": "A",
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": sequence % 2 == 0,
        "pir_recent_activity": True,
        "audio_peak_to_peak": 10 + sequence,
        "audio_activity": 2 + sequence,
        "audio_rms": 4 + sequence,
    }
    if node_id == "ESP-A1":
        payload["distance_cm"] = 50 + sequence
        payload["distance_valid"] = True
    return {
        "received_at_sgt": timestamp,
        "source_ip": "127.0.0.1",
        "source_port": 4210 if node_id == "ESP-A1" else 4211,
        "payload": payload,
    }

def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )

def load_inputs(tmp_path, camera, sensors):
    camera_path = tmp_path / "camera.jsonl"
    sensor_path = tmp_path / "sensors.jsonl"
    write_jsonl(camera_path, camera)
    write_jsonl(sensor_path, sensors)
    return load_camera_records(camera_path), load_sensor_records(sensor_path)

def test_builds_epoch_aligned_window_and_normalises_sgt_to_sgt(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [camera_record("2026-07-31T16:00:00.250+08:00")],
        [
            sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00"),
            sensor_record("ESP-A2", "2026-07-31T16:00:01.400+08:00"),
        ],
    )

    windows = build_windows(camera, sensors)

    assert len(windows) == 1
    window = windows[0]
    assert window["window_start_sgt"] == "2026-07-31T16:00:00.000+08:00"
    assert window["window_end_sgt"] == "2026-07-31T16:00:02.000+08:00"
    assert window["camera_available"] is True
    assert window["a1_available"] is True
    assert window["a2_available"] is True
    assert window["esp_a1"]["packet_count"] == 1
    assert window["esp_a1"]["missing_packet_count"] == 1
    assert "distance_cm_mean" not in window["esp_a2"]

def test_preserves_missing_modalities_as_flags_and_nulls(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [camera_record("2026-07-31T16:00:00.250+08:00", pose_available=False)],
        [],
    )

    window = build_windows(camera, sensors)[0]

    assert window["camera_available"] is True
    assert window["pose_available"] is False
    assert window["a1_available"] is False
    assert window["a2_available"] is False
    assert window["esp_a1"]["packet_count"] == 0
    assert window["esp_a1"]["missing_packet_count"] == 2
    assert window["esp_a1"]["audio_rms_mean"] is None
    assert window["camera"]["pose_availability_ratio"] == 0.0
    assert window["camera"]["keypoint_confidence_mean"] is None

def test_emits_empty_windows_across_an_input_gap(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [
            camera_record("2026-07-31T16:00:00.250+08:00", frame_number=1),
            camera_record("2026-07-31T16:00:04.250+08:00", frame_number=2),
        ],
        [],
    )

    windows = build_windows(camera, sensors)

    assert len(windows) == 3
    missing = windows[1]
    assert missing["window_start_sgt"] == "2026-07-31T16:00:02.000+08:00"
    assert missing["camera_available"] is False
    assert missing["a1_available"] is False
    assert missing["a2_available"] is False
    assert missing["camera"]["frame_count"] == 0
    assert missing["esp_a1"]["missing_packet_count"] == 2

def test_windows_are_deterministic_for_reordered_inputs(tmp_path):
    camera_records = [
        camera_record("2026-07-31T16:00:01.250+08:00", frame_number=2),
        camera_record("2026-07-31T16:00:00.250+08:00", frame_number=1),
    ]
    sensor_records = [
        sensor_record("ESP-A1", "2026-07-31T16:00:01.400+08:00", sequence=2),
        sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00", sequence=1),
    ]
    camera, sensors = load_inputs(tmp_path, camera_records, sensor_records)

    forwards = build_windows(camera, sensors)
    backwards = build_windows(list(reversed(camera)), list(reversed(sensors)))

    assert forwards == backwards
    assert forwards[0]["camera"]["movement_speed_mean_px_per_second"] == 0.0
    assert forwards[0]["esp_a1"]["timing"]["mean_absolute_jitter_ms"] == 0.0

def test_single_track_builder_matches_existing_window_preprocessing(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [
            camera_record("2026-07-31T16:00:00.250+08:00", frame_number=1),
            camera_record("2026-07-31T16:00:01.250+08:00", frame_number=2),
        ],
        [
            sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00"),
            sensor_record("ESP-A2", "2026-07-31T16:00:01.400+08:00"),
        ],
    )
    offline = build_windows(camera, sensors)[0]

    track_window = build_track_feature_window(
        camera[0]["_timestamp"].replace(microsecond=0),
        list(reversed(camera)),
        {
            "ESP-A1": [record for record in sensors if record["payload"]["node_id"] == "ESP-A1"],
            "ESP-A2": [record for record in sensors if record["payload"]["node_id"] == "ESP-A2"],
        },
        local_track_id=7,
    )

    assert track_window == offline

def test_single_track_builder_rejects_cross_track_aggregation(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [
            camera_record("2026-07-31T16:00:00.250+08:00", track_id=7),
            camera_record(
                "2026-07-31T16:00:00.500+08:00",
                frame_number=2,
                track_id=8,
            ),
        ],
        [],
    )

    with pytest.raises(ValueError, match="cross-track"):
        build_track_feature_window(
            camera[0]["_timestamp"].replace(microsecond=0),
            camera,
            {"ESP-A1": [], "ESP-A2": []},
            local_track_id=7,
        )

def test_single_track_builder_emits_explicit_camera_unavailability(tmp_path):
    _, sensors = load_inputs(
        tmp_path,
        [],
        [sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00")],
    )

    window = build_track_feature_window(
        sensors[0]["_timestamp"].replace(microsecond=0),
        [],
        {"ESP-A1": sensors, "ESP-A2": []},
        local_track_id=7,
    )

    assert window["camera_available"] is False
    assert window["pose_available"] is False
    assert window["a1_available"] is True
    assert window["camera"]["track_record_count"] == 0

def test_rejects_naive_timestamp(tmp_path):
    camera_path = tmp_path / "camera.jsonl"
    write_jsonl(
        camera_path,
        [camera_record("2026-07-31T08:00:00.250")],
    )

    with pytest.raises(ValueError, match="must use the \\+08:00 SGT offset"):
        load_camera_records(camera_path)

def test_rejects_retired_sensor_node(tmp_path):
    sensor_path = tmp_path / "sensors.jsonl"
    record = sensor_record("ESP-A2", "2026-07-31T16:00:00.400+08:00")
    record["payload"]["node_id"] = "ESP-B"
    write_jsonl(sensor_path, [record])

    with pytest.raises(ValueError, match="inactive node"):
        load_sensor_records(sensor_path)

def test_rejects_synthetic_distance_on_esp_a2(tmp_path):
    sensor_path = tmp_path / "sensors.jsonl"
    record = sensor_record("ESP-A2", "2026-07-31T16:00:00.400+08:00")
    record["payload"]["distance_cm"] = 0
    record["payload"]["distance_valid"] = False
    write_jsonl(sensor_path, [record])

    with pytest.raises(ValueError, match="ESP-A2 must omit distance"):
        load_sensor_records(sensor_path)

def test_validates_and_writes_versioned_schema(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [camera_record("2026-07-31T16:00:00.250+08:00")],
        [sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00")],
    )
    windows = build_windows(camera, sensors)
    output = tmp_path / "windows.jsonl"

    validate_and_write_windows(windows, output)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["schema_version"] == 2
    assert written["zone"] == "A"
    assert written["esp_a1"]["distance_cm_mean"] == 51

def test_excluded_window_is_not_built_or_written(tmp_path):
    camera, sensors = load_inputs(
        tmp_path,
        [camera_record("2026-07-31T16:00:00.250+08:00")],
        [sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00")],
    )
    excluded_window = "zone_a_1785484800000_2000"

    assert build_windows(
        camera,
        sensors,
        excluded_window_ids=[excluded_window],
    ) == []

    window = build_windows(camera, sensors)[0]
    with pytest.raises(ValueError, match="Excluded windows"):
        validate_and_write_windows(
            [window],
            tmp_path / "windows.jsonl",
            excluded_window_ids=[window["window_id"]],
        )

def test_cli_rebuild_excludes_incident_linked_window(tmp_path):
    camera_path = tmp_path / "camera.jsonl"
    sensor_path = tmp_path / "sensors.jsonl"
    output_path = tmp_path / "windows.jsonl"
    incident_path = tmp_path / "incident.json"
    timestamp = "2026-07-31T16:00:00.250+08:00"
    write_jsonl(camera_path, [camera_record(timestamp)])
    write_jsonl(
        sensor_path,
        [sensor_record("ESP-A1", "2026-07-31T16:00:00.400+08:00")],
    )
    incident_path.write_text(
        json.dumps({
            "affected_window_ids": ["zone_a_1785484800000_2000"],
        }),
        encoding="utf-8",
    )

    main([
        "--camera-input", str(camera_path),
        "--sensor-input", str(sensor_path),
        "--output", str(output_path),
        "--incident", str(incident_path),
    ])

    assert output_path.read_text(encoding="utf-8") == ""

def test_incident_window_ids_are_merged_and_validated(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    invalid = tmp_path / "invalid.json"
    first.write_text(json.dumps({"affected_window_ids": ["window_b", "window_a"]}),encoding="utf-8",)
    second.write_text(json.dumps({"affected_window_ids": ["window_b", "window_c"]}),encoding="utf-8",)
    invalid.write_text(json.dumps({"affected_window_ids": "window_a"}),encoding="utf-8",)

    assert load_excluded_window_ids([first, second]) == ["window_a", "window_b", "window_c",]
    with pytest.raises(ValueError, match="affected_window_ids"):
        load_excluded_window_ids([invalid])