import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "esp_packet.schema.json"

@pytest.fixture(scope="module")
def validator():
    with SCHEMA_PATH.open(encoding="utf-8") as file:
        schema = json.load(file)

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)

def assert_valid(validator, packet):
    errors = sorted(validator.iter_errors(packet), key=lambda error: error.path)
    assert errors == []

def common_packet(node_id, zone):
    sensor_configs = {"ESP-A1": "A_PIR_US_MIC", "ESP-A2": "A_PIR_MIC",}

    return {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": sensor_configs[node_id],
        "boot_id": 12319,
        "node_id": node_id,
        "zone": zone,
        "sequence": 10,
        "timestamp_ms": 10000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -61,
        "pir_motion": False,
        "pir_recent_activity": True,
    }

def test_esp_a1_packet_with_ultrasonic_is_valid(validator):
    packet = common_packet("ESP-A1", "A")
    packet.update(
        {
            "distance_cm": 206.16,
            "distance_valid": True,
            "audio_peak_to_peak": 52,
            "audio_activity": 7.31,
            "audio_rms": 9.21,
        }
    )
    assert_valid(validator, packet)

def test_esp_a2_packet_without_ultrasonic_is_valid(validator):
    packet = common_packet("ESP-A2", "A")
    packet.update(
        {
            "audio_peak_to_peak": 52,
            "audio_activity": 7.31,
            "audio_rms": 9.21,
        }
    )
    assert_valid(validator, packet)

def test_null_sensor_reading_is_valid(validator):
    packet = common_packet("ESP-A1", "A")
    packet.update(
        {
            "distance_cm": None,
            "distance_valid": False,
            "audio_peak_to_peak": None,
            "audio_activity": None,
            "audio_rms": None,
        }
    )
    assert_valid(validator, packet)

def test_negative_one_invalid_distance_sentinel_is_valid(validator):
    packet = common_packet("ESP-A1", "A")
    packet.update(
        {
            "distance_cm": -1.0,
            "distance_valid": False,
            "audio_peak_to_peak": 52,
            "audio_activity": 7.31,
            "audio_rms": 9.21,
        }
    )
    assert_valid(validator, packet)

def test_wrong_zone_is_invalid(validator):
    packet = common_packet("ESP-A2", "B")
    packet.update(
        {
            "audio_peak_to_peak": 44,
            "audio_activity": 6.2,
            "audio_rms": 8.4,
        }
    )
    assert list(validator.iter_errors(packet))

def test_esp_a_missing_audio_fields_is_invalid(validator):
    packet = common_packet("ESP-A1", "A")
    packet.update(
        {
            "distance_cm": 100.0,
            "distance_valid": True,
        }
    )
    assert list(validator.iter_errors(packet))

def test_wrong_sensor_config_is_invalid(validator):
    packet = common_packet("ESP-A2", "A")
    packet["sensor_config"] = "A_PIR_US_MIC"
    assert list(validator.iter_errors(packet))

def test_esp_a1_missing_ultrasonic_fields_is_invalid(validator):
    packet = common_packet("ESP-A1", "A")
    packet.update(
        {
            "audio_peak_to_peak": 52,
            "audio_activity": 7.31,
            "audio_rms": 9.21,
        }
    )
    assert list(validator.iter_errors(packet))

def test_esp_a2_with_ultrasonic_fields_is_invalid(validator):
    packet = common_packet("ESP-A2", "A")
    packet.update(
        {
            "distance_cm": 100.0,
            "distance_valid": True,
            "audio_peak_to_peak": 52,
            "audio_activity": 7.31,
            "audio_rms": 9.21,
        }
    )
    assert list(validator.iter_errors(packet))

def test_malformed_firmware_version_is_invalid(validator):
    packet = common_packet("ESP-A1", "A")
    packet["firmware_version"] = "version-one"
    assert list(validator.iter_errors(packet))

def test_boot_id_outside_uint32_range_is_invalid(validator):
    packet = common_packet("ESP-A1", "A")
    packet["boot_id"] = 4294967296
    assert list(validator.iter_errors(packet))

def test_negative_sequence_is_invalid(validator):
    packet = common_packet("ESP-A1", "A")
    packet["sequence"] = -1
    assert list(validator.iter_errors(packet))

@pytest.mark.parametrize("node_id", ["ESP-A", "ESP-B", "ESP-T"])
def test_retired_or_legacy_node_is_invalid(validator, node_id):
    packet = common_packet("ESP-A1", "A")
    packet["node_id"] = node_id
    assert list(validator.iter_errors(packet))