#!/usr/bin/env python3
"""build the phase 2 telemetry report without reading or writing audio or video"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

ACTIVE_NODES = ("ESP-A1", "ESP-A2")
EXPECTED_CONFIGS = {
    "ESP-A1": "A_PIR_US_MIC",
    "ESP-A2": "A_PIR_MIC",
}
INTERVAL_TYPES = {
    "baseline",
    "pir_intended",
    "pir_cross",
    "ultrasonic",
    "audio_activity",
    "restart",
    # kept only so older evidence files still open
    "wifi_interrupt",
}
AUDIO_FIELDS = ("audio_peak_to_peak", "audio_activity", "audio_rms")

@dataclass(frozen=True)
class PacketRecord:
    received_at: datetime
    payload: dict[str, Any]

@dataclass(frozen=True)
class TrialInterval:
    trial_id: str
    trial_type: str
    node_id: str
    start: datetime
    end: datetime
    reference_distance_cm: float | None
    expected_trigger: bool | None
    accepted: bool | None
    notes: str


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"Timestamp must include an offset: {value}")
    return parsed

def percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight

def numeric_summary(values: Iterable[float]) -> dict[str, float | int | None]:
    cleaned = [float(value) for value in values if value is not None]
    return {
        "count": len(cleaned),
        "minimum": min(cleaned) if cleaned else None,
        "p25": percentile(cleaned, 0.25),
        "median": percentile(cleaned, 0.5),
        "p75": percentile(cleaned, 0.75),
        "p95": percentile(cleaned, 0.95),
        "maximum": max(cleaned) if cleaned else None,
    }


def parse_optional_bool(value: str, field: str, row_number: int) -> bool | None:
    """read true, false or a blank value from the interval csv"""
    normalised = value.strip().lower()
    if normalised in {"true", "yes", "1"}:
        return True
    if normalised in {"false", "no", "0"}:
        return False
    if not normalised:
        return None
    raise ValueError(f"Row {row_number}: {field} must be true, false or blank")


def load_packets(
    path: Path,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[PacketRecord], dict[str, int]]:
    records: list[PacketRecord] = []
    counters = {
        "input_lines": 0,
        "retired_or_unknown": 0,
        "malformed": 0,
        "outside_window": 0,
    }

    with path.open(encoding="utf-8") as stream:
        for line in stream:
            counters["input_lines"] += 1
            try:
                record = json.loads(line)
                payload = record["payload"]
                if not isinstance(payload, dict):
                    raise TypeError("payload must be an object")
                received_at = parse_timestamp(record["received_at_sgt"])
                node_id = payload["node_id"]
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                counters["malformed"] += 1
                continue

            if node_id not in ACTIVE_NODES:
                counters["retired_or_unknown"] += 1
                continue
            if start is not None and received_at < start:
                counters["outside_window"] += 1
                continue
            if end is not None and received_at > end:
                counters["outside_window"] += 1
                continue

            records.append(PacketRecord(received_at, payload))

    records.sort(key=lambda item: item.received_at)
    return records, counters

def load_intervals(path: Path | None) -> list[TrialInterval]:
    if path is None:
        return []

    intervals: list[TrialInterval] = []
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {
            "trial_id",
            "trial_type",
            "node_id",
            "start_sgt",
            "end_sgt",
            "reference_distance_cm",
            "expected_trigger",
            "accepted",
            "notes",
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(
                f"Interval CSV is missing columns: {', '.join(sorted(missing))}"
            )

        for row_number, row in enumerate(reader, start=2):
            trial_type = row["trial_type"].strip()
            node_id = row["node_id"].strip()
            if trial_type not in INTERVAL_TYPES:
                raise ValueError(
                    f"Row {row_number}: unsupported trial_type {trial_type!r}"
                )
            if node_id not in ACTIVE_NODES:
                raise ValueError(
                    f"Row {row_number}: node_id must be ESP-A1 or ESP-A2"
                )

            start = parse_timestamp(row["start_sgt"].strip())
            end = parse_timestamp(row["end_sgt"].strip())
            if end <= start:
                raise ValueError(f"Row {row_number}: end_sgt must follow start_sgt")

            reference_text = row["reference_distance_cm"].strip()
            reference = float(reference_text) if reference_text else None
            expected_trigger = parse_optional_bool(
                row["expected_trigger"], "expected_trigger", row_number
            )
            accepted = parse_optional_bool(row["accepted"], "accepted", row_number)

            if trial_type == "ultrasonic" and (
                node_id != "ESP-A1" or reference is None
            ):
                raise ValueError(
                    f"Row {row_number}: ultrasonic trials require ESP-A1 "
                    "and reference_distance_cm"
                )

            intervals.append(
                TrialInterval(
                    trial_id=row["trial_id"].strip() or f"row-{row_number}",
                    trial_type=trial_type,
                    node_id=node_id,
                    start=start,
                    end=end,
                    reference_distance_cm=reference,
                    expected_trigger=expected_trigger,
                    accepted=accepted,
                    notes=row["notes"].strip(),
                )
            )
    return intervals

def payload_issue(payload: dict[str, Any], node_id: str) -> str | None:
    if payload.get("zone") != "A":
        return "wrong zone"
    if payload.get("sensor_config") != EXPECTED_CONFIGS[node_id]:
        return "wrong sensor_config"
    if payload.get("firmware_version") != "1.1.1":
        return "unexpected firmware_version"
    required = {
        "boot_id",
        "sequence",
        "wifi_rssi_dbm",
        "pir_motion",
        *AUDIO_FIELDS,
    }
    if any(field not in payload for field in required):
        return "missing required field"
    has_distance = "distance_cm" in payload and "distance_valid" in payload
    if node_id == "ESP-A1" and not has_distance:
        return "ESP-A1 missing distance fields"
    if node_id == "ESP-A2" and (
        "distance_cm" in payload or "distance_valid" in payload
    ):
        return "ESP-A2 contains distance fields"
    return None

def analyze_node(records: list[PacketRecord], node_id: str) -> dict[str, Any]:
    node_records = [
        record for record in records if record.payload["node_id"] == node_id
    ]
    if not node_records:
        return {"node_id": node_id, "packets": 0}

    unique_keys: set[tuple[Any, Any]] = set()
    sequences_by_boot: dict[Any, set[int]] = defaultdict(set)
    boot_order: list[Any] = []
    out_of_order = 0
    previous_by_boot: dict[Any, int] = {}
    issues: dict[str, int] = defaultdict(int)

    for record in node_records:
        payload = record.payload
        boot_id = payload.get("boot_id")
        sequence = payload.get("sequence")
        if boot_id not in boot_order:
            boot_order.append(boot_id)
        if isinstance(sequence, int):
            key = (boot_id, sequence)
            unique_keys.add(key)
            sequences_by_boot[boot_id].add(sequence)
            previous = previous_by_boot.get(boot_id)
            if previous is not None and sequence < previous:
                out_of_order += 1
            previous_by_boot[boot_id] = sequence
        issue = payload_issue(payload, node_id)
        if issue:
            issues[issue] += 1

    expected = 0
    for sequences in sequences_by_boot.values():
        if sequences:
            expected += max(sequences) - min(sequences) + 1
    unique_packets = len(unique_keys)
    delivery = 100 * unique_packets / expected if expected else 0.0
    gaps = [
        (current.received_at - previous.received_at).total_seconds()
        for previous, current in zip(node_records, node_records[1:])
    ]
    rssi = numeric_summary(
        record.payload.get("wifi_rssi_dbm") for record in node_records
    )

    return {
        "node_id": node_id,
        "packets": len(node_records),
        "unique_packets": unique_packets,
        "duplicates": len(node_records) - unique_packets,
        "expected_sequence_packets": expected,
        "missing_sequence_packets": max(0, expected - unique_packets),
        "delivery_percent": delivery,
        "first_received": node_records[0].received_at,
        "last_received": node_records[-1].received_at,
        "duration_seconds": (
            node_records[-1].received_at - node_records[0].received_at
        ).total_seconds(),
        "longest_gap_seconds": max(gaps, default=0.0),
        "boot_ids": boot_order,
        "restart_count": max(0, len(boot_order) - 1),
        "out_of_order": out_of_order,
        "payload_issues": dict(issues),
        "rssi": rssi,
    }

def records_in_interval(
    records: list[PacketRecord],
    interval: TrialInterval,
    node_id: str | None = None,
) -> list[PacketRecord]:
    selected_node = node_id or interval.node_id
    return [
        record
        for record in records
        if record.payload["node_id"] == selected_node
        and interval.start <= record.received_at <= interval.end
    ]

def analyze_interval(
    records: list[PacketRecord],
    interval: TrialInterval,
) -> dict[str, Any]:
    selected = records_in_interval(records, interval)
    payloads = [record.payload for record in selected]
    result: dict[str, Any] = {
        "interval": interval,
        "samples": len(selected),
        "pir_detected": any(
            payload.get("pir_motion") is True for payload in payloads
        ),
        "audio": {
            field: numeric_summary(
                payload.get(field) for payload in payloads
            )
            for field in AUDIO_FIELDS
        },
        "status": "RECORDED",
        "detail": "",
    }

    if interval.trial_type in {"pir_intended", "pir_cross"}:
        expected = interval.expected_trigger
        if expected is None:
            expected = interval.trial_type == "pir_intended"
        detected = result["pir_detected"]
        result["status"] = "PASS" if detected == expected else "FAIL"
        result["detail"] = (
            f"PIR detected={str(detected).lower()}, "
            f"expected={str(expected).lower()}"
        )

    elif interval.trial_type == "ultrasonic":
        valid_values = [
            float(payload["distance_cm"])
            for payload in payloads
            if payload.get("distance_valid") is True
            and isinstance(payload.get("distance_cm"), (int, float))
            and payload["distance_cm"] >= 0
        ]
        distance = numeric_summary(valid_values)
        valid_percent = (
            100 * len(valid_values) / len(payloads) if payloads else 0.0
        )
        median = distance["median"]
        iqr = (
            distance["p75"] - distance["p25"]
            if distance["p75"] is not None and distance["p25"] is not None
            else None
        )
        reference = interval.reference_distance_cm
        error = abs(median - reference) if median is not None else None
        tolerance = max(10.0, reference * 0.10) if reference is not None else None
        passed = (
            len(payloads) >= 30
            and valid_percent >= 95.0
            and error is not None
            and tolerance is not None
            and error <= tolerance
            and iqr is not None
            and iqr <= 10.0
        )
        result.update(
            {
                "distance": distance,
                "distance_valid_percent": valid_percent,
                "distance_error_cm": error,
                "distance_iqr_cm": iqr,
                "status": "PASS" if passed else "FAIL",
                "detail": (
                    f"n={len(payloads)}, valid={valid_percent:.2f}%, "
                    f"median={format_number(median)} cm, "
                    f"error={format_number(error)} cm, "
                    f"IQR={format_number(iqr)} cm"
                ),
            }
        )

    elif interval.trial_type == "restart":
        boots = list(dict.fromkeys(payload.get("boot_id") for payload in payloads))
        other_node = "ESP-A2" if interval.node_id == "ESP-A1" else "ESP-A1"
        other_count = len(records_in_interval(records, interval, other_node))
        passed = len(boots) >= 2 and other_count > 0
        result["status"] = "PASS" if passed else "FAIL"
        result["detail"] = (
            f"boot IDs={boots}, {other_node} packets during interval={other_count}"
        )

    elif interval.trial_type == "wifi_interrupt":
        before = [
            record for record in records
            if record.payload["node_id"] == interval.node_id
            and interval.start - timedelta(seconds=30)
            <= record.received_at < interval.start
        ]
        after = [
            record for record in records
            if record.payload["node_id"] == interval.node_id
            and interval.end < record.received_at
            <= interval.end + timedelta(seconds=60)
        ]
        other_node = "ESP-A2" if interval.node_id == "ESP-A1" else "ESP-A1"
        other_count = len(records_in_interval(records, interval, other_node))
        packet_recovery = bool(before and after and other_count)
        passed = packet_recovery and interval.accepted is True
        result["status"] = "PASS" if passed else "FAIL"
        result["detail"] = (
            f"packets before={len(before)}, after={len(after)}, "
            f"{other_node} packets during interval={other_count}, "
            f"serial recovery accepted={interval.accepted}"
        )

    return result

def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"

def build_report(
    records: list[PacketRecord],
    counters: dict[str, int],
    intervals: list[TrialInterval],
    source: Path,
    formal_start: datetime | None,
    formal_end: datetime | None,
    minimum_minutes: float,
    minimum_delivery: float,
) -> str:
    endurance_records = [
        record
        for record in records
        if (formal_start is None or record.received_at >= formal_start)
        and (formal_end is None or record.received_at <= formal_end)
    ]
    node_results = {
        node_id: analyze_node(endurance_records, node_id)
        for node_id in ACTIVE_NODES
    }
    interval_results = [
        analyze_interval(records, interval) for interval in intervals
    ]

    baseline_nodes = {
        result["interval"].node_id
        for result in interval_results
        if result["interval"].trial_type == "baseline"
        and result["samples"] > 0
    }
    audio_activity_nodes = {
        result["interval"].node_id
        for result in interval_results
        if result["interval"].trial_type == "audio_activity"
        and result["samples"] > 0
        and result["interval"].accepted is True
    }
    pir_intended_counts = {
        node_id: sum(
            result["interval"].trial_type == "pir_intended"
            and result["interval"].node_id == node_id
            for result in interval_results
        )
        for node_id in ACTIVE_NODES
    }
    pir_cross_counts = {
        node_id: sum(
            result["interval"].trial_type == "pir_cross"
            and result["interval"].node_id == node_id
            for result in interval_results
        )
        for node_id in ACTIVE_NODES
    }
    ultrasonic_count = sum(
        result["interval"].trial_type == "ultrasonic"
        for result in interval_results
    )
    ultrasonic_pass = all(
        result["status"] == "PASS"
        for result in interval_results
        if result["interval"].trial_type == "ultrasonic"
    )
    pir_intended_detections = {
        node_id: sum(
            result["interval"].trial_type == "pir_intended"
            and result["interval"].node_id == node_id
            and result["pir_detected"]
            for result in interval_results
        )
        for node_id in ACTIVE_NODES
    }
    pir_cross_triggers = {
        node_id: sum(
            result["interval"].trial_type == "pir_cross"
            and result["interval"].node_id == node_id
            and result["pir_detected"]
            for result in interval_results
        )
        for node_id in ACTIVE_NODES
    }

    calibration_complete = (
        baseline_nodes == set(ACTIVE_NODES)
        and audio_activity_nodes == set(ACTIVE_NODES)
        and all(pir_intended_counts[node] >= 5 for node in ACTIVE_NODES)
        and all(pir_cross_counts[node] >= 5 for node in ACTIVE_NODES)
        and all(pir_intended_detections[node] >= 4 for node in ACTIVE_NODES)
        and all(pir_cross_triggers[node] <= 1 for node in ACTIVE_NODES)
        and ultrasonic_count >= 3
        and ultrasonic_pass
    )

    recovery_nodes = {
        result["interval"].node_id
        for result in interval_results
        if result["interval"].trial_type == "restart"
        and result["status"] == "PASS"
    }
    formal_window = formal_start is not None and formal_end is not None
    formal_duration_pass = (
        formal_window
        and (formal_end - formal_start).total_seconds() >= minimum_minutes * 60
    )
    boundary_tolerance = timedelta(seconds=5)
    endurance_nodes_pass = all(
        result["packets"] > 0
        and result["delivery_percent"] >= minimum_delivery
        and not result["payload_issues"]
        and formal_start is not None
        and formal_end is not None
        and result["first_received"] <= formal_start + boundary_tolerance
        and result["last_received"] >= formal_end - boundary_tolerance
        for result in node_results.values()
    )
    endurance_complete = (
        formal_duration_pass
        and endurance_nodes_pass
        and recovery_nodes == set(ACTIVE_NODES)
    )

    lines = [
        "# Zone A Phase 2 Telemetry Evidence Report",
        "",
        "## Scope",
        "",
        f"- Source: `{source}`",
        f"- Formal start: {formal_start.isoformat() if formal_start else 'not supplied'}",
        f"- Formal end: {formal_end.isoformat() if formal_end else 'not supplied'}",
        f"- Active packets available for labeled trials: {len(records)}",
        f"- Active packets in formal endurance window: {len(endurance_records)}",
        f"- Retired or unknown packets ignored: {counters['retired_or_unknown']}",
        f"- Malformed input lines ignored: {counters['malformed']}",
        "- Raw audio and video: not read or generated",
        "",
        "## Phase 2.3 calibration decision",
        "",
        f"Decision: **{'PASS' if calibration_complete else 'INCOMPLETE'}**",
        "",
        (
            "The decision requires per-node baseline and audio-activity intervals, "
            "five intended and five cross-placement PIR trials per node, and at "
            "least three passing ESP-A1 ultrasonic reference points."
        ),
        "",
        "| Node | Baseline | Accepted audio separation | PIR intended detected | PIR cross triggered |",
        "|---|---:|---:|---:|---:|",
    ]
    for node_id in ACTIVE_NODES:
        lines.append(
            f"| {node_id} | {'Yes' if node_id in baseline_nodes else 'No'} "
            f"| {'Yes' if node_id in audio_activity_nodes else 'No'} "
            f"| {pir_intended_detections[node_id]} / {pir_intended_counts[node_id]} "
            f"| {pir_cross_triggers[node_id]} / {pir_cross_counts[node_id]} |"
        )
    lines.extend(
        [
            f"| ESP-A1 ultrasonic reference points | {ultrasonic_count} |  |  |  |",
            "",
            "## Phase 2.4 endurance and recovery decision",
            "",
            f"Decision: **{'PASS' if endurance_complete else 'INCOMPLETE'}**",
            "",
            (
                f"Acceptance requires a supplied formal window of at least "
                f"{minimum_minutes:g} minutes per node, at least "
                f"{minimum_delivery:g}% sequence delivery per node, and one "
                "passing restart or power-cycle recovery trial per active node."
            ),
            "",
            "| Node | Duration (min) | Unique / expected | Delivery | Longest gap (s) | Boots | Payload issues |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for node_id in ACTIVE_NODES:
        result = node_results[node_id]
        if not result["packets"]:
            lines.append(f"| {node_id} | 0 | 0 / 0 | 0.00% | n/a | 0 | no packets |")
            continue
        issues = ", ".join(
            f"{name}: {count}"
            for name, count in result["payload_issues"].items()
        ) or "none"
        lines.append(
            f"| {node_id} | {result['duration_seconds'] / 60:.2f} "
            f"| {result['unique_packets']} / {result['expected_sequence_packets']} "
            f"| {result['delivery_percent']:.3f}% "
            f"| {result['longest_gap_seconds']:.3f} "
            f"| {len(result['boot_ids'])} | {issues} |"
        )

    lines.extend(["", "## Labeled trial results", ""])
    if not interval_results:
        lines.append(
            "No interval CSV was supplied. Calibration and recovery evidence "
            "cannot be accepted without controlled trial markers."
        )
    else:
        lines.extend(
            [
                "| Trial | Type | Node | Samples | Status | Detail |",
                "|---|---|---|---:|---|---|",
            ]
        )
        for result in interval_results:
            interval = result["interval"]
            detail = result["detail"] or "statistics recorded"
            lines.append(
                f"| {interval.trial_id} | {interval.trial_type} "
                f"| {interval.node_id} | {result['samples']} "
                f"| {result['status']} | {detail} |"
            )

    lines.extend(["", "## Numerical audio summaries", ""])
    audio_results = [
        result for result in interval_results
        if result["interval"].trial_type in {"baseline", "audio_activity"}
    ]
    if not audio_results:
        lines.append("No labeled baseline or audio-activity intervals were supplied.")
    else:
        lines.extend(
            [
                "| Trial | Node | Feature | n | Min | P25 | Median | P75 | P95 | Max |",
                "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for result in audio_results:
            interval = result["interval"]
            for field, summary in result["audio"].items():
                lines.append(
                    f"| {interval.trial_id} | {interval.node_id} | {field} "
                    f"| {summary['count']} | {format_number(summary['minimum'])} "
                    f"| {format_number(summary['p25'])} "
                    f"| {format_number(summary['median'])} "
                    f"| {format_number(summary['p75'])} "
                    f"| {format_number(summary['p95'])} "
                    f"| {format_number(summary['maximum'])} |"
                )

    lines.extend(
        [
            "",
            "## Interpretation limits",
            "",
            "- Sequence delivery is calculated independently within each boot ID.",
            "- A board-recovery trial passes only when the affected board returns with a new boot ID and the other active node continues sending packets during the interval.",
            "- Run board-recovery trials on the site's public network by restarting or power-cycling one board at a time; do not interrupt or replace the public access point.",
            "- Legacy `wifi_interrupt` rows remain readable as historical evidence but do not satisfy the current per-board recovery requirement.",
            "- An audio-activity interval counts toward acceptance only when `accepted=true` records the operator's evidence-based decision that at least one numerical feature has usable baseline/activity separation.",
            "- Numerical audio summaries contain features only. They do not establish or retain intelligible speech.",
            "- An incomplete report is not authority to begin participant collection.",
            "",
        ]
    )
    return "\n".join(lines)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 2.3/2.4 Zone A telemetry evidence."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw/esp_packets.jsonl"),
        help="Receiver JSONL input.",
    )
    parser.add_argument(
        "--intervals",
        type=Path,
        action="append",
        default=[],
        help="CSV containing controlled calibration and recovery intervals.",
    )
    parser.add_argument(
        "--start", type=parse_timestamp, help="Formal start time in ISO 8601 format."
    )
    parser.add_argument(
        "--end", type=parse_timestamp, help="Formal end time in ISO 8601 format."
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Markdown report path.",
    )
    parser.add_argument("--minimum-minutes", type=float, default=90.0)
    parser.add_argument("--minimum-delivery", type=float, default=98.0)
    return parser.parse_args()

def main() -> int:
    args = parse_args()
    if (args.start is None) != (args.end is None):
        raise SystemExit("--start and --end must be supplied together")
    if args.start is not None and args.end <= args.start:
        raise SystemExit("--end must be later than --start")
    if args.minimum_minutes <= 0:
        raise SystemExit("--minimum-minutes must be positive")
    if not 0 < args.minimum_delivery <= 100:
        raise SystemExit("--minimum-delivery must be in (0, 100]")

    records, counters = load_packets(args.input)
    intervals = [
        interval
        for path in args.intervals
        for interval in load_intervals(path)
    ]
    report = build_report(
        records=records,
        counters=counters,
        intervals=intervals,
        source=args.input,
        formal_start=args.start,
        formal_end=args.end,
        minimum_minutes=args.minimum_minutes,
        minimum_delivery=args.minimum_delivery,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
