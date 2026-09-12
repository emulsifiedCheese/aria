import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from aria.timebase import SGT
import yaml
from aria.collection.preflight import (
    CAMERA_SOURCE,
    PreflightConfig,
    SensorPacket,
    evaluate_sensor_packets,
    load_and_validate_mask,
    load_camera_config,
    load_session_mask,
    probe_stream,
    run_preflight,
    validate_local_storage,
    validate_mediamtx_config,
    validate_participant_scope,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMERA_CONFIG = PROJECT_ROOT / "config" / "cameras.batamfast.yaml"
MASK_CONFIG = PROJECT_ROOT / "config" / "masks.batamfast.yaml"
MEDIAMTX_CONFIG = PROJECT_ROOT / "config" / "mediamtx.local.yaml"
NOW = datetime(2026, 7, 31, 21, 45, tzinfo=SGT)

def telemetry_packet(node_id):
    packet = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": {
            "ESP-A1": "A_PIR_US_MIC",
            "ESP-A2": "A_PIR_MIC",
        }[node_id],
        "boot_id": 12319,
        "node_id": node_id,
        "zone": "A",
        "sequence": 10,
        "timestamp_ms": 10000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -61,
        "pir_motion": False,
        "pir_recent_activity": True,
        "audio_peak_to_peak": 52,
        "audio_activity": 7.31,
        "audio_rms": 9.21,
    }
    if node_id == "ESP-A1":
        packet.update(distance_cm=206.16, distance_valid=True)
    return packet

def sensor_packets(received_at=NOW):
    timestamp = received_at.isoformat()
    return [
        SensorPacket(json.dumps(telemetry_packet(node_id)).encode(), timestamp)
        for node_id in ("ESP-A1", "ESP-A2")
    ]

def base_config(tmp_path):
    return PreflightConfig(
        session_kind="non_research_dry_run",
        dji_recording_disabled=True,
        camera_config_path=CAMERA_CONFIG,
        mask_config_path=MASK_CONFIG,
        mediamtx_config_path=MEDIAMTX_CONFIG,
        output_directory=tmp_path,
        minimum_free_bytes=100,
        approved_output_roots=(tmp_path,),
    )

def run_with_fakes(config, **overrides):
    options = {
        "clock": lambda: NOW,
        "camera_probe": lambda camera: None,
        "stream_probe": lambda source: [
            {"codec_name": "h264", "codec_type": "video"}
        ],
        "sensor_probe": lambda supplied: sensor_packets(),
        "disk_usage": lambda path: SimpleNamespace(free=10**12),
        "pause_stop_factory": lambda: SimpleNamespace(ready=True),
    }
    options.update(overrides)
    return run_preflight(config, **options)

def write_yaml(tmp_path, name, document):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    return path

def test_complete_non_research_preflight_passes(tmp_path):
    report = run_with_fakes(base_config(tmp_path))
    assert report.passed
    assert all(report.checks.values())

def test_participant_and_pilot_require_pseudonyms_and_acknowledgement(tmp_path):
    valid = replace(
        base_config(tmp_path),session_kind="participant",participant_ids=("P0001",),acknowledgement_confirmed=True,)
    validate_participant_scope(valid)

    with pytest.raises(ValueError, match="acknowledgement"):
        validate_participant_scope(replace(valid, acknowledgement_confirmed=False))
    with pytest.raises(ValueError, match="pseudonymised"):
        validate_participant_scope(replace(valid, participant_ids=("not-a-pseudonym",)))

def test_non_research_dry_run_rejects_participant_ids(tmp_path):
    config = replace(base_config(tmp_path), participant_ids=("P0001",))
    with pytest.raises(ValueError, match="must not include"):
        validate_participant_scope(config)

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("camera_id", "camera_b", "camera_a"),
        ("width", 1280, "1920x1080"),
        ("height", 720, "1920x1080"),
        ("fps", 25, "30 FPS"),
        ("source", "rtsp://127.0.0.1:8554/live/camera_b", "approved local RTSP"),
    ],
)
def test_camera_configuration_is_locked(tmp_path, field, value, message):
    document = yaml.safe_load(CAMERA_CONFIG.read_text())
    document["cameras"][0][field] = value
    path = write_yaml(tmp_path, "camera.yaml", document)
    with pytest.raises(ValueError, match=message):
        load_camera_config(path)


def test_camera_probe_must_open_live_rtsp_stream(tmp_path):
    def fail_to_open(camera):
        raise RuntimeError("stream unavailable")

    report = run_with_fakes(base_config(tmp_path), camera_probe=fail_to_open)
    assert report.checks["camera_identity_and_mode_confirmed"] is False
    assert "stream unavailable" in report.details["camera_identity_and_mode_confirmed"]

@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda mask: mask.update(verified=False), "verification"),
        (lambda mask: mask.update(camera_id="camera_b"), "identity"),
        (lambda mask: mask.update(expected_width=1280), "width"),
        (lambda mask: mask.update(width=0), "must not be empty"),
        (
            lambda mask: mask.update(excluded_polygons=[[[0, 0], [1, 1]]]),
            "at least 3 points",
        ),
    ],
)
def test_mask_must_be_verified_and_geometry_valid(tmp_path, mutation, message):
    camera = load_camera_config(CAMERA_CONFIG)
    document = yaml.safe_load(MASK_CONFIG.read_text())
    mutation(document["masks"]["camera_a"])
    path = write_yaml(tmp_path, "mask.yaml", document)
    with pytest.raises(ValueError, match=message):
        load_and_validate_mask(path, camera)

def test_current_mediamtx_config_disables_recording_and_audio():
    validate_mediamtx_config(MEDIAMTX_CONFIG)

def test_development_mask_is_limited_to_non_research_sessions(tmp_path):
    camera = load_camera_config(CAMERA_CONFIG)
    development = PROJECT_ROOT / "config" / "masks.development.yaml"

    non_research = replace(base_config(tmp_path), mask_config_path=development)
    assert load_session_mask(non_research, camera).mask_config_version == "development-v1"

    participant = replace(non_research,session_kind="participant",participant_ids=("P0001",),acknowledgement_confirmed=True,)
    with pytest.raises(ValueError, match="exact approved"):
        load_session_mask(participant, camera)

def test_mediamtx_recording_or_missing_audio_removal_is_rejected(tmp_path):
    document = yaml.safe_load(MEDIAMTX_CONFIG.read_text())
    document["paths"]["live/camera_a"]["record"] = True
    path = write_yaml(tmp_path, "mediamtx-recording.yaml", document)
    with pytest.raises(ValueError, match="recording"):
        validate_mediamtx_config(path)

    document = yaml.safe_load(MEDIAMTX_CONFIG.read_text())
    document["paths"]["ingest/camera_a"]["runOnAvailable"] = "ffmpeg -c:v copy"
    path = write_yaml(tmp_path, "mediamtx-audio.yaml", document)
    with pytest.raises(ValueError, match="remove all audio"):
        validate_mediamtx_config(path)

def test_live_stream_must_have_one_h264_track_and_no_audio(tmp_path):
    def audio_present(source):
        assert source == CAMERA_SOURCE
        return [
            {"codec_name": "h264", "codec_type": "video"},
            {"codec_name": "aac", "codec_type": "audio"},
        ]

    report = run_with_fakes(base_config(tmp_path), stream_probe=audio_present)
    assert report.checks["audio_capture_disabled"] is False

def test_ffprobe_adapter_reads_json_stream_description(monkeypatch):
    completed = SimpleNamespace(
        stdout=json.dumps(
            {"streams": [{"codec_name": "h264", "codec_type": "video"}]}
        )
    )
    monkeypatch.setattr("aria.collection.preflight.shutil.which", lambda name: "/ffprobe")
    monkeypatch.setattr("aria.collection.preflight.subprocess.run", lambda *args, **kwargs: completed)
    assert probe_stream() == [{"codec_name": "h264", "codec_type": "video"}]

def test_dji_recording_disabled_confirmation_is_required(tmp_path):
    report = run_with_fakes(replace(base_config(tmp_path), dji_recording_disabled=False))
    assert report.checks["audio_capture_disabled"] is False

def test_only_schema_valid_fresh_a1_and_a2_pass():
    assert evaluate_sensor_packets(sensor_packets(), NOW) == {"ESP-A1": True, "ESP-A2": True,}
    missing_a2 = evaluate_sensor_packets(sensor_packets()[:1], NOW)
    assert missing_a2 == {"ESP-A1": True, "ESP-A2": False}

def test_stale_invalid_or_retired_sensor_packets_fail():
    stale = evaluate_sensor_packets(sensor_packets(received_at=NOW - timedelta(seconds=6)), NOW)
    assert stale == {"ESP-A1": False, "ESP-A2": False}

    invalid_packet = telemetry_packet("ESP-A2")
    invalid_packet["sensor_config"] = "A_PIR_US_MIC"
    packets = sensor_packets()[:1] + [
        SensorPacket(json.dumps(invalid_packet).encode(),NOW.isoformat(),)
    ]
    assert evaluate_sensor_packets(packets, NOW) == {
        "ESP-A1": False,
        "ESP-A2": False,
    }

    wrong_firmware = telemetry_packet("ESP-A2")
    wrong_firmware["firmware_version"] = "1.1.0"
    packets = sensor_packets()[:1] + [
        SensorPacket(json.dumps(wrong_firmware).encode(), NOW.isoformat())
    ]
    assert evaluate_sensor_packets(packets, NOW) == {"ESP-A1": False,"ESP-A2": False,}

    retired = telemetry_packet("ESP-A2")
    retired["node_id"] = "ESP-T"
    packets = sensor_packets() + [
        SensorPacket(
            json.dumps(retired).encode(),
            NOW.isoformat(),
        )
    ]
    assert evaluate_sensor_packets(packets, NOW) == {"ESP-A1": False,"ESP-A2": False,}

def test_storage_must_be_approved_writable_and_have_free_space(tmp_path, monkeypatch):
    config = base_config(tmp_path)
    validate_local_storage(config, disk_usage=lambda path: SimpleNamespace(free=10**12))

    outside = replace(config, approved_output_roots=(tmp_path / "approved",))
    with pytest.raises(ValueError, match="approved local roots"):
        validate_local_storage(outside, disk_usage=lambda path: SimpleNamespace(free=10**12))

    with pytest.raises(ValueError, match="Insufficient"):
        validate_local_storage(config, disk_usage=lambda path: SimpleNamespace(free=0))

    monkeypatch.setattr("aria.collection.preflight.os.access", lambda path, mode: False)
    with pytest.raises(ValueError, match="not writable"):
        validate_local_storage(config, disk_usage=lambda path: SimpleNamespace(free=10**12))

def test_timezone_aware_clock_and_pause_stop_interface_are_required(tmp_path):
    naive_report = run_with_fakes(base_config(tmp_path), clock=lambda: datetime(2026, 7, 31, 13, 45))
    assert naive_report.checks["storage_ready"] is False

    pause_failure = run_with_fakes(base_config(tmp_path),pause_stop_factory=lambda: SimpleNamespace(ready=False),)
    assert pause_failure.checks["storage_ready"] is False

def test_preflight_collects_failures_without_starting_any_writer(tmp_path):
    config = replace(base_config(tmp_path),participant_ids=("P0001",),dji_recording_disabled=False,)
    report = run_with_fakes(
        config,
        camera_probe=lambda camera: (_ for _ in ()).throw(RuntimeError("offline")),
        sensor_probe=lambda supplied: [],
        disk_usage=lambda path: SimpleNamespace(free=0),
    )
    assert report.passed is False
    assert set(report.failures) == {
        "consent_and_acknowledgement_confirmed",
        "camera_identity_and_mode_confirmed",
        "audio_capture_disabled",
        "esp_a1_fresh",
        "esp_a2_fresh",
        "storage_ready",
    }
    assert report.checks["privacy_mask_verified"] is True