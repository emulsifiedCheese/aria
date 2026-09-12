import json
import hashlib
from aria.ingestion import udp_receiver

def packet(node_id):
    return {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": (
            "A_PIR_US_MIC"
            if node_id == "ESP-A1"
            else "A_PIR_MIC"
        ),
        "boot_id": 12319,
        "node_id": node_id,
        "zone": "A",
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

def test_receiver_has_logs_for_active_nodes_only():
    assert set(udp_receiver.NODE_LOG_FILES) == {"ESP-A1", "ESP-A2"}

def test_packets_are_written_to_separate_node_logs(
    tmp_path,
    monkeypatch,
):
    log_files = {"ESP-A1": tmp_path / "esp_a1.log", "ESP-A2": tmp_path / "esp_a2.log"}
    monkeypatch.setattr(udp_receiver, "NODE_LOG_FILES", log_files)

    for node_id in log_files:
        udp_receiver.write_node_output(
            node_id=node_id,
            received_at="2026-07-29T12:00:00.000+08:00",
            source_ip="127.0.0.1",
            source_port=4210 if node_id == "ESP-A1" else 4211,
            payload=packet(node_id),
        )

    esp_a1_output = log_files["ESP-A1"].read_text(encoding="utf-8")
    esp_a2_output = log_files["ESP-A2"].read_text(encoding="utf-8")

    assert json.loads(
        esp_a1_output[esp_a1_output.index("{"):]
    )["node_id"] == "ESP-A1"
    assert json.loads(
        esp_a2_output[esp_a2_output.index("{"):]
    )["node_id"] == "ESP-A2"
    assert "ESP-A2" not in esp_a1_output
    assert "ESP-A1" not in esp_a2_output

def test_retired_node_has_no_dedicated_log(tmp_path, monkeypatch):
    log_files = {"ESP-A1": tmp_path / "esp_a1.log","ESP-A2": tmp_path / "esp_a2.log",}
    monkeypatch.setattr(udp_receiver, "NODE_LOG_FILES", log_files)

    udp_receiver.write_node_output(
        node_id="ESP-B",
        received_at="2026-07-29T12:00:00.000+08:00",
        source_ip="127.0.0.1",
        source_port=4211,
        payload={"node_id": "ESP-B"},
    )

    assert not any(tmp_path.iterdir())

def test_invalid_packet_diagnostic_does_not_retain_packet_contents():
    raw_packet = b'{"participant_name":"must-not-be-retained"}'

    record = udp_receiver.build_invalid_record(
        received_at="2026-07-29T12:00:00.000+08:00",
        source_ip="192.0.2.10",
        source_port=4210,
        error_message="invalid packet",
        data=raw_packet,
    )

    assert "raw_packet" not in record
    assert record["raw_packet_size_bytes"] == len(raw_packet)
    assert record["raw_packet_sha256"] == hashlib.sha256(raw_packet).hexdigest()
    assert "must-not-be-retained" not in json.dumps(record)