import csv
import json
from datetime import datetime, timedelta, timezone
import pytest
from scripts.generate_integration_report import (
    TrialInterval,
    analyze_interval,
    analyze_node,
    build_report,
    load_intervals,
    load_packets,
)

SGT = timezone(timedelta(hours=8))
START = datetime(2026, 7, 30, 12, 0, tzinfo=SGT)

def payload(node_id, sequence, boot_id=100, **updates):
    packet = {
        "schema_version": 1,
        "firmware_version": "1.1.1",
        "sensor_config": (
            "A_PIR_US_MIC" if node_id == "ESP-A1" else "A_PIR_MIC"
        ),
        "boot_id": boot_id,
        "node_id": node_id,
        "zone": "A",
        "sequence": sequence,
        "timestamp_ms": sequence * 1000,
        "wifi_connected": True,
        "wifi_rssi_dbm": -60,
        "pir_motion": False,
        "pir_recent_activity": False,
        "audio_peak_to_peak": 20,
        "audio_activity": 3.0,
        "audio_rms": 4.0,
    }
    if node_id == "ESP-A1":
        packet.update({"distance_cm": 100.0, "distance_valid": True})
    packet.update(updates)
    return packet

def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for received_at, packet in rows:
            stream.write(
                json.dumps(
                    {
                        "received_at_sgt": received_at.isoformat(),
                        "source_ip": "127.0.0.1",
                        "source_port": 4210,
                        "payload": packet,
                    }
                )
                + "\n"
            )

def test_load_packets_filters_retired_nodes_and_formal_window(tmp_path):
    path = tmp_path / "packets.jsonl"
    retired = payload("ESP-A1", 1)
    retired.update({"node_id": "ESP-B", "zone": "B"})
    write_jsonl(
        path,
        [
            (START - timedelta(seconds=1), payload("ESP-A1", 0)),
            (START, payload("ESP-A1", 1)),
            (START, retired),
            (START + timedelta(seconds=1), payload("ESP-A2", 1)),
        ],
    )

    records, counters = load_packets(path, START, START + timedelta(seconds=2))

    assert [record.payload["node_id"] for record in records] == ["ESP-A1","ESP-A2",]
    assert counters["retired_or_unknown"] == 1
    assert counters["outside_window"] == 1


def test_node_analysis_is_per_boot_and_detects_duplicates(tmp_path):
    path = tmp_path / "packets.jsonl"
    write_jsonl(
        path,
        [
            (START, payload("ESP-A1", 1, boot_id=10)),
            (START + timedelta(seconds=1), payload("ESP-A1", 2, boot_id=10)),
            (START + timedelta(seconds=2), payload("ESP-A1", 2, boot_id=10)),
            (START + timedelta(seconds=3), payload("ESP-A1", 4, boot_id=10)),
            (START + timedelta(seconds=4), payload("ESP-A1", 0, boot_id=11)),
            (START + timedelta(seconds=5), payload("ESP-A1", 1, boot_id=11)),
        ],
    )
    records, _ = load_packets(path)

    result = analyze_node(records, "ESP-A1")

    assert result["unique_packets"] == 5
    assert result["expected_sequence_packets"] == 6
    assert result["duplicates"] == 1
    assert result["missing_sequence_packets"] == 1
    assert result["restart_count"] == 1
    assert result["delivery_percent"] == pytest.approx(5 / 6 * 100)

def test_ultrasonic_interval_applies_phase_2_acceptance_targets(tmp_path):
    path = tmp_path / "packets.jsonl"
    rows = [
        (
            START + timedelta(seconds=index),
            payload(
                "ESP-A1",
                index,
                distance_cm=100 + (index % 3) - 1,
                distance_valid=True,
            ),
        )
        for index in range(30)
    ]
    write_jsonl(path, rows)
    records, _ = load_packets(path)
    interval = TrialInterval(
        trial_id="u1",
        trial_type="ultrasonic",
        node_id="ESP-A1",
        start=START,
        end=START + timedelta(seconds=30),
        reference_distance_cm=100.0,
        expected_trigger=None,
        accepted=None,
        notes="",
    )

    result = analyze_interval(records, interval)

    assert result["status"] == "PASS"
    assert result["distance_valid_percent"] == 100.0
    assert result["distance_error_cm"] == 0.0
    assert result["distance_iqr_cm"] <= 10.0

def test_restart_requires_other_node_to_continue(tmp_path):
    path = tmp_path / "packets.jsonl"
    write_jsonl(
        path,
        [
            (START, payload("ESP-A1", 8, boot_id=10)),
            (START + timedelta(seconds=1), payload("ESP-A2", 4)),
            (START + timedelta(seconds=2), payload("ESP-A1", 0, boot_id=11)),
        ],
    )
    records, _ = load_packets(path)
    interval = TrialInterval(
        trial_id="restart",
        trial_type="restart",
        node_id="ESP-A1",
        start=START,
        end=START + timedelta(seconds=3),
        reference_distance_cm=None,
        expected_trigger=None,
        accepted=None,
        notes="",
    )

    assert analyze_interval(records, interval)["status"] == "PASS"

def test_report_accepts_one_restart_or_power_cycle_per_active_node():
    from scripts.generate_integration_report import PacketRecord

    records = []
    states = [
        (10, 0, 20, 0),
        (10, 1, 20, 1),
        (11, 0, 20, 2),
        (11, 1, 20, 3),
        (11, 2, 20, 4),
        (11, 3, 21, 0),
    ]
    for offset, state in enumerate(states):
        a1_boot, a1_sequence, a2_boot, a2_sequence = state
        received_at = START + timedelta(seconds=offset)
        records.extend(
            [
                PacketRecord(
                    received_at,
                    payload("ESP-A1", a1_sequence, boot_id=a1_boot),
                ),
                PacketRecord(
                    received_at,
                    payload("ESP-A2", a2_sequence, boot_id=a2_boot),
                ),
            ]
        )
    intervals = [
        TrialInterval(
            trial_id="board-recovery-a1",
            trial_type="restart",
            node_id="ESP-A1",
            start=START,
            end=START + timedelta(seconds=2),
            reference_distance_cm=None,
            expected_trigger=None,
            accepted=None,
            notes="Restarted ESP-A1 on the public network",
        ),
        TrialInterval(
            trial_id="board-recovery-a2",
            trial_type="restart",
            node_id="ESP-A2",
            start=START + timedelta(seconds=3),
            end=START + timedelta(seconds=5),
            reference_distance_cm=None,
            expected_trigger=None,
            accepted=None,
            notes="Power-cycled ESP-A2 on the public network",
        ),
    ]

    report = build_report(
        records=records,
        counters={
            "input_lines": len(records),
            "retired_or_unknown": 0,
            "malformed": 0,
            "outside_window": 0,
        },
        intervals=intervals,
        source="packets.jsonl",
        formal_start=START,
        formal_end=START + timedelta(seconds=5),
        minimum_minutes=5 / 60,
        minimum_delivery=98,
    )
    phase_2_4 = report.split(
        "## Phase 2.4 endurance and recovery decision", maxsplit=1
    )[1].split("## Labeled trial results", maxsplit=1)[0]

    assert "Decision: **PASS**" in phase_2_4
    assert "one passing restart or power-cycle recovery trial" in phase_2_4

def test_interval_csv_rejects_ultrasonic_for_esp_a2(tmp_path):
    path = tmp_path / "intervals.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "trial_id",
                "trial_type",
                "node_id",
                "start_sgt",
                "end_sgt",
                "reference_distance_cm",
                "expected_trigger",
                "accepted",
                "notes",
            ]
        )
        writer.writerow(
            [
                "bad",
                "ultrasonic",
                "ESP-A2",
                START.isoformat(),
                (START + timedelta(seconds=30)).isoformat(),
                "100",
                "",
                "",
                "",
            ]
        )

    with pytest.raises(ValueError, match="ultrasonic trials require ESP-A1"):
        load_intervals(path)

def test_report_keeps_calibration_packets_outside_formal_window(tmp_path):
    from scripts.generate_integration_report import PacketRecord

    calibration_time = START - timedelta(minutes=10)
    records = [
        PacketRecord(calibration_time, payload("ESP-A1", 1)),
        PacketRecord(START, payload("ESP-A1", 10)),
        PacketRecord(START, payload("ESP-A2", 10)),
        PacketRecord(START + timedelta(seconds=10), payload("ESP-A1", 20)),
        PacketRecord(START + timedelta(seconds=10), payload("ESP-A2", 20)),
    ]
    intervals = [
        TrialInterval(
            trial_id="baseline-a1",
            trial_type="baseline",
            node_id="ESP-A1",
            start=calibration_time - timedelta(seconds=1),
            end=calibration_time + timedelta(seconds=1),
            reference_distance_cm=None,
            expected_trigger=None,
            accepted=None,
            notes="",
        )
    ]

    report = build_report(
        records=records,
        counters={
            "input_lines": 5,
            "retired_or_unknown": 0,
            "malformed": 0,
            "outside_window": 0,
        },
        intervals=intervals,
        source=tmp_path / "packets.jsonl",
        formal_start=START,
        formal_end=START + timedelta(seconds=10),
        minimum_minutes=1,
        minimum_delivery=98,
    )

    assert "| baseline-a1 | baseline | ESP-A1 | 1 |" in report
    assert "Active packets in formal endurance window: 4" in report