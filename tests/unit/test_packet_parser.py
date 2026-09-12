import json
import pytest
from aria.ingestion.packet_parser import parse_packet

def make_packet(node_id="ESP-A1", zone="A"):
    sensor_configs = {
        "ESP-A1": "A_PIR_US_MIC",
        "ESP-A2": "A_PIR_MIC",
    }

    packet = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": sensor_configs.get(node_id, "A_PIR_US_MIC"),
        "boot_id": 12319,
        "node_id": node_id,
        "zone": zone,
        "sequence": 1,
        "timestamp_ms": 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": False,
        "pir_recent_activity": True,
        "audio_peak_to_peak": 52,
        "audio_activity": 7.31,
        "audio_rms": 9.21,
    }

    if node_id == "ESP-A1":
        packet.update(
            {
                "distance_cm": 206.16,
                "distance_valid": True,
            }
        )

    return packet

def encode(packet):
    return json.dumps(packet).encode("utf-8")

def test_valid_packet_is_returned():
    packet = make_packet()

    assert parse_packet(encode(packet)) == packet

def test_valid_esp_a2_packet_without_distance_is_returned():
    packet = make_packet(node_id="ESP-A2")

    assert parse_packet(encode(packet)) == packet

def test_invalid_json_is_rejected():
    with pytest.raises(ValueError, match="Invalid JSON"):
        parse_packet(b'{"node_id":')

def test_non_object_json_is_rejected():
    with pytest.raises(ValueError, match="JSON object"):
        parse_packet(b'["ESP-A1"]')

def test_missing_required_field_is_rejected():
    packet = make_packet()
    del packet["sequence"]

    with pytest.raises(ValueError, match="Missing field: sequence"):
        parse_packet(encode(packet))

def test_missing_firmware_version_is_rejected():
    packet = make_packet()
    del packet["firmware_version"]

    with pytest.raises(ValueError, match="Missing field: firmware_version"):
        parse_packet(encode(packet))

def test_missing_boot_id_is_rejected():
    packet = make_packet()
    del packet["boot_id"]

    with pytest.raises(ValueError, match="Missing field: boot_id"):
        parse_packet(encode(packet))

def test_unknown_node_is_rejected():
    packet = make_packet(node_id="ESP-X", zone="X")

    with pytest.raises(ValueError, match="Unknown node_id"):
        parse_packet(encode(packet))

def test_wrong_zone_is_rejected():
    packet = make_packet(node_id="ESP-A2", zone="B")

    with pytest.raises(ValueError, match="Wrong zone"):
        parse_packet(encode(packet))

@pytest.mark.parametrize("node_id", ["ESP-B", "ESP-T", "ESP-A"])
def test_retired_or_legacy_node_is_rejected(node_id):
    packet = make_packet(node_id=node_id, zone="A")

    with pytest.raises(ValueError, match="Unknown node_id"):
        parse_packet(encode(packet))

def test_non_integer_sequence_is_rejected():
    packet = make_packet()
    packet["sequence"] = "1"

    with pytest.raises(ValueError, match="sequence must be an integer"):
        parse_packet(encode(packet))

def test_wrong_sensor_config_is_rejected():
    packet = make_packet(node_id="ESP-A2")
    packet["sensor_config"] = "A_PIR_US_MIC"

    with pytest.raises(ValueError, match="schema validation"):
        parse_packet(encode(packet))

def test_esp_a1_without_distance_fields_is_rejected():
    packet = make_packet()
    del packet["distance_cm"]
    del packet["distance_valid"]

    with pytest.raises(ValueError, match="schema validation"):
        parse_packet(encode(packet))

def test_esp_a2_with_distance_fields_is_rejected():
    packet = make_packet(node_id="ESP-A2")
    packet["distance_cm"] = 100.0
    packet["distance_valid"] = True

    with pytest.raises(ValueError, match="schema validation"):
        parse_packet(encode(packet))

def test_missing_audio_field_is_rejected():
    packet = make_packet()
    del packet["audio_rms"]

    with pytest.raises(ValueError, match="schema validation"):
        parse_packet(encode(packet))

def test_wrong_schema_version_is_rejected():
    packet = make_packet()
    packet["schema_version"] = 2

    with pytest.raises(ValueError, match="schema validation"):
        parse_packet(encode(packet))
