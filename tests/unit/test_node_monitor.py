from datetime import datetime, timedelta
import pytest
from aria.timebase import SGT
from aria.ingestion.node_monitor import NodeMonitor

def packet(node_id="ESP-A1", sequence=1, boot_id=100):
    return {
        "node_id": node_id,
        "sequence": sequence,
        "boot_id": boot_id,
    }

def now_iso():
    return datetime.now(SGT).isoformat(timespec="milliseconds")

def test_first_packet_has_no_warning():
    monitor = NodeMonitor()
    assert monitor.update(packet(sequence=1), now_iso()) == []

def test_duplicate_packet_is_detected():
    monitor = NodeMonitor()
    monitor.update(packet(sequence=5), now_iso())
    messages = monitor.update(packet(sequence=5), now_iso())
    assert len(messages) == 1
    assert "duplicate packet" in messages[0]

def test_skipped_packets_are_detected():
    monitor = NodeMonitor()
    monitor.update(packet(sequence=5), now_iso())
    messages = monitor.update(packet(sequence=8), now_iso())
    assert len(messages) == 1
    assert "skipped 2 packet(s)" in messages[0]

def test_lower_sequence_is_detected():
    monitor = NodeMonitor()
    monitor.update(packet(sequence=8), now_iso())
    messages = monitor.update(packet(sequence=1), now_iso())
    assert len(messages) == 1
    assert "out-of-order packet" in messages[0]

def test_changed_boot_id_is_detected_as_restart():
    monitor = NodeMonitor()
    monitor.update(packet(sequence=8, boot_id=100), now_iso())
    messages = monitor.update(packet(sequence=1, boot_id=101), now_iso())
    assert len(messages) == 1
    assert "ESP-A1 restarted" in messages[0]
    assert "boot_id 100 -> 101" in messages[0]

def test_stale_node_is_reported_once():
    monitor = NodeMonitor()
    old_time = (
        datetime.now(SGT) - timedelta(seconds=10)
    ).isoformat(timespec="milliseconds")
    monitor.update(packet(), old_time)
    first_messages = monitor.check_stale_nodes()
    second_messages = monitor.check_stale_nodes()
    assert len(first_messages) == 1
    assert "ESP-A1 is stale" in first_messages[0]
    assert second_messages == []

def test_new_packet_clears_stale_state():
    monitor = NodeMonitor()
    old_time = (datetime.now(SGT) - timedelta(seconds=10)).isoformat(timespec="milliseconds")
    monitor.update(packet(sequence=1), old_time)
    monitor.check_stale_nodes()
    monitor.update(packet(sequence=2), now_iso())
    assert monitor.nodes["ESP-A1"]["stale"] is False

def test_non_sgt_timestamp_is_rejected():
    monitor = NodeMonitor()
    now = datetime.now(SGT)
    with pytest.raises(ValueError, match="SGT"):
        monitor.update(packet(), now.isoformat().replace("+08:00", "+07:00"))
