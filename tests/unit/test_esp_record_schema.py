import pytest
from aria.ingestion.record_schema import validate_esp_record

def packet(node_id="ESP-A1"):
    value = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC",
        "boot_id": 1234,
        "node_id": node_id,
        "zone": "A",
        "sequence": 10,
        "timestamp_ms": 10000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": False,
        "pir_recent_activity": False,
        "audio_peak_to_peak": 4,
        "audio_activity": 0.2,
        "audio_rms": 0.3,
    }
    if node_id == "ESP-A1":
        value.update(distance_cm=70.0, distance_valid=True)
    return value

def record(node_id="ESP-A1"):
    return {
        "received_at_sgt": "2026-08-01T11:22:33.123+08:00",
        "source_ip": "10.100.6.20",
        "source_port": 4210 if node_id == "ESP-A1" else 4211,
        "payload": packet(node_id),
    }

def test_stored_envelope_and_nested_packet_validate():
    assert validate_esp_record(record()) == record()
    assert validate_esp_record(record("ESP-A2")) == record("ESP-A2")

def test_envelope_requires_sgt_and_valid_nested_payload():
    wrong_time = record()
    wrong_time["received_at_sgt"] = "2026-08-01T10:22:33.123+07:00"
    with pytest.raises(ValueError, match="received_at_sgt"):
        validate_esp_record(wrong_time)

    wrong_payload = record("ESP-A2")
    wrong_payload["payload"]["distance_cm"] = 70.0
    with pytest.raises(ValueError, match="payload"):
        validate_esp_record(wrong_payload)

def test_envelope_rejects_uncontracted_receiver_metadata():
    value = record()
    value["participant_name"] = "must-not-be-stored"

    with pytest.raises(ValueError, match="Additional properties"):
        validate_esp_record(value)