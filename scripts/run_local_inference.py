#!/usr/bin/env python3
"""run Phase 12.1 local inference on synthetic or non-research record streams"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from aria.fusion.window_builder import (
    ACTIVE_NODES,
    DEFAULT_WINDOW_SECONDS,
    _window_start,
    load_camera_records,
    load_sensor_records,
)
from aria.inference.orchestrator import LocalInferenceOrchestrator, LocalPredictionWriter
from aria.inference.service import LocalInferenceService

def _parser():
    parser = argparse.ArgumentParser(
        description="Run frozen local inference on non-participant numerical/track records",
    )
    parser.add_argument("--camera-input", type=Path, required=True)
    parser.add_argument("--sensor-input", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--input-scope",
        choices=("synthetic", "non_research"),
        required=True,
        help="Participant and pilot inputs are prohibited",
    )
    return parser

def main(argv=None):
    args = _parser().parse_args(argv)
    camera_records = load_camera_records(args.camera_input)
    sensors = load_sensor_records(args.sensor_input)
    camera_by_start = defaultdict(list)
    sensors_by_node_and_start = {
        node_id: defaultdict(list) for node_id in ACTIVE_NODES
    }
    occupied = set()
    for record in camera_records:
        start = _window_start(record["_timestamp"], DEFAULT_WINDOW_SECONDS)
        occupied.add(start)
        camera_by_start[start].append(record)
    for record in sensors:
        start = _window_start(record["_timestamp"], DEFAULT_WINDOW_SECONDS)
        occupied.add(start)
        sensors_by_node_and_start[record["payload"]["node_id"]][start].append(record)
    if not occupied:
        raise SystemExit("No input records were found")

    starts = []
    current = min(occupied)
    while current <= max(occupied):
        starts.append(current)
        current += timedelta(seconds=DEFAULT_WINDOW_SECONDS)

    service = LocalInferenceService()
    writer = LocalPredictionWriter(args.output, validator=service.prediction_validator)
    orchestrator = LocalInferenceOrchestrator(service, writer=writer)
    predicted = 0
    written = 0
    for start in starts:
        result = orchestrator.process_completed_window(
            session_id=args.session_id,
            window_start=start,
            camera_records=camera_by_start[start],
            sensor_records={
                node_id: sensors_by_node_and_start[node_id][start]
                for node_id in ACTIVE_NODES
            },
        )
        predicted += len(result["predictions"])
        written += result["written_count"]
    print(
        f"Local inference complete: windows={len(starts)}, "
        f"predictions={predicted}, newly_written={written}"
    )

if __name__ == "__main__":
    main()