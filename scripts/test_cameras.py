#!/usr/bin/env python3
"""measure camera a stream health without keeping any frames"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import time
import yaml

from aria.cameras.camera_manager import (
    DEFAULT_CAMERA_FPS,
    DEFAULT_CAMERA_HEIGHT,
    DEFAULT_CAMERA_WIDTH,
    CameraManager,
)

DEFAULT_CONFIG_PATH = "config/cameras.batamfast.yaml"


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight

@dataclass
class DiagnosticStats:
    reported_fps: float
    started_at: float
    successful_frames: int = 0
    read_failures: int = 0
    timing_inferred_drops: int = 0
    longest_frame_gap_ms: float = 0.0
    read_latencies_ms: list[float] = field(default_factory=list)
    previous_frame_at: float | None = None

    def record_read(
        self,
        success: bool,
        read_started_at: float,
        read_finished_at: float,
    ) -> None:
        self.read_latencies_ms.append(
            (read_finished_at - read_started_at) * 1000
        )

        if not success:
            self.read_failures += 1
            return

        self.successful_frames += 1

        if self.previous_frame_at is not None:
            gap_seconds = read_finished_at - self.previous_frame_at
            self.longest_frame_gap_ms = max(
                self.longest_frame_gap_ms,
                gap_seconds * 1000,
            )

            if self.reported_fps > 0:
                expected_intervals = max(1, round(gap_seconds * self.reported_fps))
                self.timing_inferred_drops += max(0, expected_intervals - 1)

        self.previous_frame_at = read_finished_at

    def result(self, ended_at: float) -> dict:
        elapsed_seconds = max(0.0, ended_at - self.started_at)
        measured_fps = (
            self.successful_frames / elapsed_seconds
            if elapsed_seconds > 0
            else 0.0
        )

        mean_latency = (
            sum(self.read_latencies_ms) / len(self.read_latencies_ms)
            if self.read_latencies_ms
            else 0.0
        )
        maximum_latency = max(self.read_latencies_ms, default=0.0)

        return {
            "duration_seconds": round(elapsed_seconds, 3),
            "reported_fps": round(self.reported_fps, 3),
            "measured_fps": round(measured_fps, 3),
            "successful_frames": self.successful_frames,
            "read_failures": self.read_failures,
            "estimated_dropped_frames": max(
                self.read_failures,
                self.timing_inferred_drops,
            ),
            "longest_frame_gap_ms": round(
                self.longest_frame_gap_ms,
                3,
            ),
            "read_latency_ms": {
                "mean": round(mean_latency, 3),
                "p95": round(percentile(self.read_latencies_ms, 0.95), 3),
                "maximum": round(maximum_latency, 3),
            },
        }


def normalise_source(source):
    if isinstance(source, int):
        return source
    if isinstance(source, str) and source.isdigit():
        return int(source)
    return source


def load_config(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)

def validate_deployment_cameras(cameras: list[dict]) -> None:
    cameras_by_id = {camera.get("camera_id"): camera for camera in cameras}

    if set(cameras_by_id) != {"camera_a"}:
        raise ValueError("Deployment camera configuration must contain only camera_a")

    camera_a = cameras_by_id["camera_a"]
    camera_a_source = normalise_source(camera_a.get("source"))

    if (
        camera_a.get("camera_model") != "DJI Osmo Action 5 Pro"
        or camera_a.get("transport") != "wireless_rtsp"
        or camera_a.get("zone") != "A"
        or not isinstance(camera_a_source, str)
        or not camera_a_source.startswith("rtsp://127.0.0.1:")
    ):
        raise ValueError(
            "camera_a must be the Zone A DJI Osmo Action 5 Pro local wireless "
            "RTSP stream; built-in and Continuity cameras are not allowed"
        )

def run_diagnostics(managers, duration_seconds: int) -> dict:
    started_at_sgt = datetime.now().astimezone().isoformat(
        timespec="milliseconds"
    )
    started_at = time.monotonic()
    diagnostics = {}

    try:
        for manager in managers:
            manager.open()
            print(manager.summary())
            diagnostics[manager.camera_id] = DiagnosticStats(
                reported_fps=manager.stats.actual_fps,
                started_at=started_at,
            )

        while time.monotonic() - started_at < duration_seconds:
            for manager in managers:
                read_started_at = time.monotonic()
                frame = manager.read()
                read_finished_at = time.monotonic()
                diagnostics[manager.camera_id].record_read(
                    success=frame is not None,
                    read_started_at=read_started_at,
                    read_finished_at=read_finished_at,
                )
    finally:
        for manager in managers:
            manager.close()

    ended_at = time.monotonic()
    ended_at_sgt = datetime.now().astimezone().isoformat(
        timespec="milliseconds"
    )

    return {
        "started_at_sgt": started_at_sgt,
        "ended_at_sgt": ended_at_sgt,
        "requested_duration_seconds": duration_seconds,
        "latency_definition": (
            "Local blocking duration of each OpenCV frame read; "
            "not camera-to-display latency."
        ),
        "drop_definition": (
            "Estimate based on failed reads and frame-arrival gaps relative "
            "to the stream-reported FPS."
        ),
        "raw_frames_retained": False,
        "cameras": {
            manager.camera_id: {
                "source": manager.source,
                "actual_width": manager.stats.actual_width,
                "actual_height": manager.stats.actual_height,
                "privacy_mask_status": manager.privacy_mask_status,
                **diagnostics[manager.camera_id].result(ended_at),
            }
            for manager in managers
        },
    }

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run ARIA camera diagnostics."
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to camera configuration file",
    )
    parser.add_argument(
        "--camera",
        help="Run one camera ID only, such as camera_a",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=15,
        help="Headless diagnostic duration in seconds",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON evidence output path",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    cameras = config.get("cameras", [])
    validate_deployment_cameras(cameras)

    if args.camera:
        cameras = [camera for camera in cameras if camera["camera_id"] == args.camera]

    if not cameras:
        raise SystemExit("No matching cameras found in the configuration")

    managers = [
        CameraManager(
            camera_id=camera["camera_id"],
            source=normalise_source(camera["source"]),
            width=camera.get("width", DEFAULT_CAMERA_WIDTH),
            height=camera.get("height", DEFAULT_CAMERA_HEIGHT),
            fps=camera.get("fps", DEFAULT_CAMERA_FPS),
            privacy_mask_status=camera.get(
                "privacy_mask_status",
                "not_configured",
            ),
        )
        for camera in cameras
    ]
    report = run_diagnostics(managers, duration_seconds=args.duration)
    rendered_report = json.dumps(report, indent=2)
    print(rendered_report)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            rendered_report + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
