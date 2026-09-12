#!/usr/bin/env python3
"""combine camera a and sensor records into fixed zone a time windows"""

import argparse
import json
from pathlib import Path

from aria.fusion.window_builder import (
    DEFAULT_WINDOW_SECONDS,
    build_windows,
    load_camera_records,
    load_sensor_records,
    validate_and_write_windows,
)

def load_excluded_window_ids(incident_paths: list[Path]) -> list[str]:
    """return every window marked as affected by an incident"""
    excluded_window_ids: set[str] = set()
    for incident_path in incident_paths:
        path = Path(incident_path)
        with path.open(encoding="utf-8") as stream:
            incident = json.load(stream)
        affected = incident.get("affected_window_ids")
        if not isinstance(affected, list) or any(
            not isinstance(window_id, str) or not window_id
            for window_id in affected
        ):
            raise ValueError(
                f"{path}: affected_window_ids must be a list of non-empty strings"
            )
        excluded_window_ids.update(affected)
    return sorted(excluded_window_ids)

def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-input", required=True, help="Camera A JSONL input")
    parser.add_argument("--sensor-input", required=True, help="ESP-A1/A2 JSONL input")
    parser.add_argument("--output", required=True, help="Feature-window JSONL output")
    parser.add_argument(
        "--window-seconds",
        type=float,
        default=DEFAULT_WINDOW_SECONDS,
    )
    parser.add_argument(
        "--keypoint-confidence",
        type=float,
        default=0.5,
    )
    parser.add_argument(
        "--incident",
        action="append",
        type=Path,
        default=[],
        help=(
            "Lifecycle incident record whose affected_window_ids must be "
            "excluded; repeat for each incident"
        ),
    )
    return parser.parse_args(argv)

def main(argv=None) -> None:
    args = parse_args(argv)
    excluded_window_ids = load_excluded_window_ids(args.incident)
    windows = build_windows(
        load_camera_records(
            args.camera_input,
            excluded_window_ids=excluded_window_ids,
            window_seconds=args.window_seconds,
        ),
        load_sensor_records(
            args.sensor_input,
            excluded_window_ids=excluded_window_ids,
            window_seconds=args.window_seconds,
        ),
        window_seconds=args.window_seconds,
        keypoint_confidence=args.keypoint_confidence,
        excluded_window_ids=excluded_window_ids,
    )
    validate_and_write_windows(
        windows,
        args.output,
        excluded_window_ids=excluded_window_ids,
    )
    print(f"Wrote {len(windows)} multimodal windows to {args.output}")


if __name__ == "__main__":
    main()
