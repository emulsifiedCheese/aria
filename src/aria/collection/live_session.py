"""lifecycle owned live zone a writers and interactive dry-run runner"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import shlex
import socket
import threading
import time
import tempfile
from aria.ingestion.packet_parser import parse_packet
from aria.ingestion.record_schema import validate_esp_record
from aria.vision.feature_writer import FeatureWriter
from aria.vision.pipeline import CVPipeline
from aria.timebase import SGT, sgt_now
from .live_annotation import ANNOTATOR_ID_PATTERN, LiveAnnotationWriter
from .collection_profile import (
    CollectionProfileError,
    DEFAULT_COLLECTION_PROFILE,
    enforce_live_settings,
)
from .preflight import (
    PreflightConfig,
    load_and_validate_mask,
    load_camera_config,
)
from .masked_preview import DEFAULT_PREVIEW_PORT, MaskedTrackPreviewServer
from .run_session import prepare_session, start_prepared_session

DEFAULT_CAMERA_SOURCE = "rtsp://127.0.0.1:8554/live/camera_a"
DEFAULT_WINDOW_SECONDS = 2.0

def _sgt_now():
    return sgt_now()

def _timestamp_window_id(value, window_seconds=DEFAULT_WINDOW_SECONDS):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("record timestamp must be timezone-aware")
    return current_window_id(value, window_seconds=window_seconds)

def _rewrite_jsonl_excluding(output_path, window_ids, timestamp_field):
    output_path = Path(output_path)
    window_ids = set(window_ids)
    removed = 0
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as destination:
            temporary_path = Path(destination.name)
            if output_path.exists():
                with output_path.open(encoding="utf-8") as source:
                    for line_number, line in enumerate(source, start=1):
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            window_id = _timestamp_window_id(record[timestamp_field])
                        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                            raise ValueError(f"Cannot verify {output_path}:{line_number} for exclusion") from error
                        if window_id in window_ids:
                            removed += 1
                        else:
                            destination.write(json.dumps(record) + "\n")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return removed

def _jsonl_has_windows(output_path, window_ids, timestamp_field):
    output_path = Path(output_path)
    if not output_path.exists():
        return False
    window_ids = set(window_ids)
    with output_path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            if _timestamp_window_id(record[timestamp_field]) in window_ids:
                return True
    return False

def _session_output(context, filename):
    output_root = context.manifest_path.parent.parent.resolve()
    output_path = output_root / "sessions" / context.session_id / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    relative_path = output_path.relative_to(output_root).as_posix()
    return output_root, output_path, relative_path

class TelemetrySessionWriter:
    def __init__(
        self,
        context,
        *,
        udp_host="0.0.0.0",
        udp_port=5005,
        socket_factory=socket.socket,
        clock=_sgt_now,
    ):
        self.context = context
        self.controller = context.pause_stop_controller
        self.clock = clock
        self.output_root, self.output_path, self.relative_path = _session_output(
            context,
            "esp_packets.jsonl",
        )
        self._stream = self.output_path.open("x", encoding="utf-8")
        self._lock = threading.Lock()
        self._stop_requested = threading.Event()
        self._error = None
        self._observed_record_count = 0
        self._written_record_count = 0
        self._excluded_record_count = 0
        self._gap_count = 0
        self._longest_gap_seconds = 0.0
        self._previous_by_node = {}
        self._excluded_window_ids = set()
        self._socket = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._socket.bind((udp_host, udp_port))
            self._socket.settimeout(0.25)
        except Exception:
            self._socket.close()
            self._stream.close()
            raise
        self._thread = threading.Thread(
            target=self._receive_loop,
            name=f"{context.session_id}-telemetry",
            daemon=True,
        )
        self._thread.start()

    def _receive_loop(self):
        try:
            while not self._stop_requested.is_set() and not self.controller.stopped:
                try:
                    raw, address = self._socket.recvfrom(65535)
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop_requested.is_set() or self.controller.stopped:
                        break
                    raise

                received_at = self.clock()
                if received_at.tzinfo is None or received_at.utcoffset() is None:
                    raise ValueError("Telemetry clock must be timezone-aware")
                try:
                    payload = parse_packet(raw)
                except (TypeError, ValueError):
                    with self._lock:
                        self._observed_record_count += 1
                        self._excluded_record_count += 1
                    continue

                with self._lock:
                    self._observed_record_count += 1
                    if self.controller.paused or self.controller.stopped:
                        self._excluded_record_count += 1
                        continue
                    self._update_quality(payload, received_at)
                    record = {
                        "received_at_sgt": received_at.astimezone(SGT).isoformat(
                            timespec="milliseconds"
                        ),
                        "source_ip": address[0],
                        "source_port": address[1],
                        "payload": payload,
                    }
                    validate_esp_record(record)
                    if _timestamp_window_id(record["received_at_sgt"]) in self._excluded_window_ids:
                        self._excluded_record_count += 1
                        continue
                    self._stream.write(json.dumps(record) + "\n")
                    self._stream.flush()
                    self._written_record_count += 1
        except Exception as error:
            self._error = error

    def _update_quality(self, payload, received_at):
        node_id = payload["node_id"]
        current = {
            "boot_id": payload["boot_id"],
            "sequence": payload["sequence"],
            "received_at": received_at,
        }
        previous = self._previous_by_node.get(node_id)
        if previous is not None:
            interval = (received_at - previous["received_at"]).total_seconds()
            self._longest_gap_seconds = max(
                self._longest_gap_seconds,
                max(0.0, interval),
            )
            if current["boot_id"] == previous["boot_id"]:
                self._gap_count += max(
                    0,
                    current["sequence"] - previous["sequence"] - 1,
                )
        self._previous_by_node[node_id] = current

    def pause(self):
        return None

    def resume(self):
        if self._error is not None:
            raise self._error

    def exclude_windows(self, window_ids):
        with self._lock:
            self._excluded_window_ids.update(window_ids)
            self._stream.flush()
            self._stream.close()
            try:
                removed = _rewrite_jsonl_excluding(
                    self.output_path,
                    window_ids,
                    "received_at_sgt",
                )
            finally:
                self._stream = self.output_path.open("a", encoding="utf-8")
            self._written_record_count -= removed
            self._excluded_record_count += removed
            return removed

    def verify_excluded_windows(self, window_ids):
        with self._lock:
            self._stream.flush()
            return not _jsonl_has_windows(
                self.output_path,
                window_ids,
                "received_at_sgt",
            )

    def close(self):
        self._stop_requested.set()
        try:
            self._socket.close()
        except OSError:
            pass
        self._thread.join(timeout=2.0)
        with self._lock:
            if not self._stream.closed:
                self._stream.close()
        if self._thread.is_alive():
            raise RuntimeError("Telemetry writer did not stop")
        if self._error is not None:
            raise self._error

    def session_summary(self):
        with self._lock:
            return {
                "kind": "telemetry_features",
                "relative_path": self.relative_path,
                "observed_record_count": self._observed_record_count,
                "written_record_count": self._written_record_count,
                "excluded_record_count": self._excluded_record_count,
                "gap_count": self._gap_count,
                "longest_gap_seconds": round(self._longest_gap_seconds, 6),
            }

    def status(self):
        return self.session_summary()

class ControlledCameraFeatureWriter:
    def __init__(self, context, *, record_observer=None):
        if record_observer is not None and not callable(record_observer):
            raise TypeError("record_observer must be callable")
        self.context = context
        self.controller = context.pause_stop_controller
        self.record_observer = record_observer
        self.output_root, self.output_path, self.relative_path = _session_output(context,"camera_a_records.jsonl",)
        self._writer = FeatureWriter(self.output_path)
        self._lock = threading.Lock()
        self._observed_record_count = 0
        self._written_record_count = 0
        self._excluded_record_count = 0
        self._gap_count = 0
        self._longest_gap_seconds = 0.0
        self._last_frame_number = None
        self._last_frame_timestamp = None
        self._excluded_window_ids = set()

    def write(self, record):
        with self._lock:
            self._observed_record_count += 1
            if self.controller.paused or self.controller.stopped:
                self._excluded_record_count += 1
                return
            window_id = _timestamp_window_id(record["frame_timestamp_sgt"])
            if window_id in self._excluded_window_ids:
                self._excluded_record_count += 1
                return
            if self.record_observer is not None:
                self.record_observer(record)
            self._writer.write(record)
            self._written_record_count += 1
            frame_number = record["frame_number"]
            timestamp = datetime.fromisoformat(record["frame_timestamp_sgt"])
            if (self._last_frame_number is not None and frame_number > self._last_frame_number):
                self._gap_count += max(0,frame_number - self._last_frame_number - 1,)
                interval = (timestamp - self._last_frame_timestamp).total_seconds()
                self._longest_gap_seconds = max(self._longest_gap_seconds,max(0.0, interval),)
            if self._last_frame_number != frame_number:
                self._last_frame_number = frame_number
                self._last_frame_timestamp = timestamp

    def record_excluded(self):
        with self._lock:
            self._observed_record_count += 1
            self._excluded_record_count += 1

    def exclude_windows(self, window_ids):
        with self._lock:
            self._excluded_window_ids.update(window_ids)
            self._writer.close()
            removed = _rewrite_jsonl_excluding(
                self.output_path,
                window_ids,
                "frame_timestamp_sgt",
            )
            self._written_record_count -= removed
            self._excluded_record_count += removed
            return removed

    def verify_excluded_windows(self, window_ids):
        with self._lock:
            self._writer.close()
            return not _jsonl_has_windows(
                self.output_path,
                window_ids,
                "frame_timestamp_sgt",)

    def close(self):
        with self._lock:
            self._writer.close()
            self.output_path.touch(exist_ok=True)

    def session_summary(self):
        with self._lock:
            return {
                "kind": "camera_features",
                "relative_path": self.relative_path,
                "observed_record_count": self._observed_record_count,
                "written_record_count": self._written_record_count,
                "excluded_record_count": self._excluded_record_count,
                "gap_count": self._gap_count,
                "longest_gap_seconds": round(self._longest_gap_seconds, 6),
            }

class CameraSessionWriter:
    def __init__(
        self,
        context,
        *,
        source,
        mask_config,
        pipeline_factory=CVPipeline,
        startup_timeout=15.0,
        pipeline_options=None,
        preview_enabled=False,
        preview_port=DEFAULT_PREVIEW_PORT,
        annotation_writer=None,
        preview_server_factory=MaskedTrackPreviewServer,
    ):
        self.context = context
        self.controller = context.pause_stop_controller
        self.source = source
        self.mask_config = mask_config
        self.pipeline_factory = pipeline_factory
        self.startup_timeout = startup_timeout
        self.pipeline_options = dict(pipeline_options or {})
        self.annotation_writer = annotation_writer
        self.preview = None
        try:
            if preview_enabled:
                preview_options = {"port": preview_port}
                if annotation_writer is not None:
                    preview_options["annotation_writer"] = annotation_writer
                self.preview = preview_server_factory(**preview_options)
                self.preview.start()
            self.feature_writer = ControlledCameraFeatureWriter(
                context,
                record_observer=(
                    self.preview.observe_record
                    if self.preview is not None
                    and callable(getattr(self.preview, "observe_record", None))
                    else None
                ),
            )
        except Exception:
            if self.preview is not None:
                self.preview.stop()
            raise
        self._stop_requested = threading.Event()
        self._thread = None
        self._error = None
        self._pipeline = None
        self._excluded_window_ids = set()
        self._start_pipeline()

    def _start_pipeline(self):
        started = threading.Event()
        self._error = None
        self._stop_requested.clear()
        try:
            self._pipeline = self.pipeline_factory(
                camera_id="camera_a",
                source=self.source,
                mask_config=self.mask_config,
                output_path=self.feature_writer.output_path,
                display=False,
                writer=self.feature_writer,
                stop_requested=lambda: (self._stop_requested.is_set() or self.controller.stopped),
                pause_requested=lambda: self.controller.paused,
                started_callback=started.set,
                preview_callback=(self.preview.publish if self.preview is not None else None),
                **self.pipeline_options,
            )
        except Exception:
            self.feature_writer.close()
            if self.preview is not None:
                self.preview.stop()
            raise

        def run_pipeline():
            try:
                self._pipeline.run()
            except Exception as error:
                self._error = error
            finally:
                started.set()

        self._thread = threading.Thread(
            target=run_pipeline,
            name=f"{self.context.session_id}-camera",
            daemon=True,
        )
        self._thread.start()
        if not started.wait(timeout=self.startup_timeout):
            self._stop_requested.set()
            self._thread.join(timeout=2.0)
            self.feature_writer.close()
            raise RuntimeError("Camera writer startup timed out")
        if self._error is not None:
            self._stop_requested.set()
            self._thread.join(timeout=2.0)
            self.feature_writer.close()
            raise self._error
        if not self._thread.is_alive():
            self.feature_writer.close()
            raise RuntimeError("Camera writer ended during startup")

    def pause(self):
        if self.preview is not None:
            self.preview.pause()
        return None

    def resume(self):
        if self._thread is not None and self._thread.is_alive():
            if self._error is not None:
                raise self._error
        else:
            self._start_pipeline()
        if self.preview is not None:
            self.preview.resume()

    def exclude_windows(self, window_ids):
        self._excluded_window_ids.update(window_ids)
        return self.feature_writer.exclude_windows(window_ids)

    def verify_excluded_windows(self, window_ids):
        return self.feature_writer.verify_excluded_windows(window_ids)

    def close(self):
        self._stop_requested.set()
        try:
            if self.annotation_writer is not None:
                self.annotation_writer.close()
            if self._thread is not None:
                self._thread.join(timeout=15.0)
                if self._thread.is_alive():
                    raise RuntimeError("Camera writer did not stop")
            self.feature_writer.close()
            if self._error is not None:
                raise self._error
        finally:
            if self.preview is not None:
                self.preview.stop()

    def session_summary(self):
        return self.feature_writer.session_summary()

    def status(self):
        summary = self.session_summary()
        summary["running"] = bool(self._thread and self._thread.is_alive())
        summary["error"] = None if self._error is None else str(self._error)
        if self.preview is not None:
            summary["masked_track_preview"] = self.preview.status()
        return summary

def current_window_id(now=None, window_seconds=DEFAULT_WINDOW_SECONDS):
    now = now or _sgt_now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Window clock must be timezone-aware")
    window_ms = int(round(window_seconds * 1000))
    start_ms = math.floor(now.timestamp() * 1000 / window_ms) * window_ms
    return f"zone_a_{start_ms}_{window_ms}"

def _print_status(started):
    with started.context.manifest_path.open(encoding="utf-8") as stream:
        manifest = json.load(stream)
    print(f"session_id={started.context.session_id} status={manifest['status']}")
    for handle in started.writer_handles:
        status = getattr(handle, "status", None)
        if callable(status):
            print(json.dumps(status(), sort_keys=True))

def interactive_session(started, input_fn=input):
    print("Commands: status, pause TYPE, resume ACTION... [--deletion-completed], stop, abort")
    while True:
        try:
            parts = shlex.split(input_fn("aria> "))
        except (EOFError, KeyboardInterrupt):
            print("\nInput ended; aborting the live session safely.")
            return started.abort()
        if not parts:
            continue
        command, *arguments = parts
        try:
            if command == "status" and not arguments:
                _print_status(started)
                continue
            if command == "pause" and len(arguments) == 1:
                window_id = current_window_id()
                incident = started.pause(
                    arguments[0],
                    affected_window_ids=[window_id],
                )
                print(
                    f"paused incident_id={incident['incident_id']} "
                    f"window_id={window_id}"
                )
                continue
            if command == "resume" and arguments:
                deletion_completed = "--deletion-completed" in arguments
                actions = [
                    value
                    for value in arguments
                    if value != "--deletion-completed"
                ]
                incident = started.resume(actions,deletion_completed=deletion_completed,)
                print(f"resumed incident_id={incident['incident_id']}")
                continue
            if command == "stop" and not arguments:
                completed = started.stop()
                print(f"completed manifest={started.context.manifest_path}")
                return completed
            if command == "abort" and not arguments:
                aborted = started.abort()
                print(f"aborted manifest={started.context.manifest_path}")
                return aborted
            print("Invalid command or arguments")
        except Exception as error:
            print(f"ERROR: {error}")
            with started.context.manifest_path.open(encoding="utf-8") as stream:
                manifest = json.load(stream)
            if manifest["status"] in {"completed", "aborted"}:
                return manifest

def build_parser():
    parser = argparse.ArgumentParser(description="Run one lifecycle-owned Zone A collection session.")
    parser.add_argument(
        "--session-kind",
        choices=["non_research_dry_run", "pilot", "participant"],
        default="non_research_dry_run",
    )
    parser.add_argument(
        "--participant-id",
        action="append",
        default=[],
        help="Pseudonymised P0000-style participant ID; repeat as needed",
    )
    parser.add_argument(
        "--acknowledgement-confirmed",
        action="store_true",
        help="Confirm required Ethics Pack acknowledgement for pilot/participant sessions",
    )
    parser.add_argument("--dji-recording-disabled", action="store_true")
    parser.add_argument(
        "--camera-config",
        type=Path,
        default=Path("config/cameras.batamfast.yaml"),
    )
    parser.add_argument(
        "--mask-config",
        type=Path,
        default=Path("config/masks.batamfast.yaml"),
    )
    parser.add_argument(
        "--mediamtx-config",
        type=Path,
        default=Path("config/mediamtx.local.yaml"),
    )
    parser.add_argument(
        "--collection-profile",
        type=Path,
        default=DEFAULT_COLLECTION_PROFILE,
        help="Frozen Phase 9.2 settings used by pilot/participant sessions",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=Path("data/raw"),
    )
    parser.add_argument("--minimum-free-gib", type=float, default=5.0)
    parser.add_argument("--udp-host", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--sensor-wait-seconds", type=float, default=10.0)
    parser.add_argument(
        "--masked-track-preview",
        action="store_true",
        help="Serve the same pipeline's masked track-ID view on localhost only",
    )
    parser.add_argument(
        "--preview-port",
        type=int,
        default=DEFAULT_PREVIEW_PORT,
    )
    parser.add_argument(
        "--annotator-id",
        default="A001",
        help="Pseudonymised A000-style annotator ID for pilot/participant sessions",
    )
    parser.add_argument("--processing-fps", type=float, default=15.0)
    parser.add_argument(
        "--experimental-track-stitching",
        action="store_true",
        help=(
            "Add non-biometric anonymous stitched IDs for non-research "
            "validation only"
        ),
    )
    parser.add_argument("--inference-size", type=int, default=768)
    parser.add_argument("--pose-inference-size", type=int, default=384)
    parser.add_argument(
        "--detector-model",
        type=Path,
        default=Path("yolov8n.pt"),
    )
    parser.add_argument(
        "--pose-model",
        type=Path,
        default=Path("yolov8n-pose.pt"),
    )
    parser.add_argument("--detector-confidence", type=float, default=0.10)
    parser.add_argument("--detector-iou", type=float, default=0.70)
    parser.add_argument("--pose-confidence", type=float, default=0.15)
    parser.add_argument("--keypoint-confidence", type=float, default=0.5)
    parser.add_argument("--min-confident-keypoints", type=int, default=4)
    parser.add_argument(
        "--tracker-config",
        default="config/bytetrack.zone_a.persistence.yaml",
    )
    parser.add_argument("--device")
    return parser

def validate_cli_args(args):
    if not args.dji_recording_disabled:
        raise SystemExit("--dji-recording-disabled confirmation is required")
    if not 1 <= args.preview_port <= 65535:
        raise SystemExit("--preview-port must be between 1 and 65535")
    if ANNOTATOR_ID_PATTERN.fullmatch(args.annotator_id) is None:
        raise SystemExit("--annotator-id must use A000 format")
    if not 0 < args.detector_iou <= 1:
        raise SystemExit("--detector-iou must be greater than zero and at most one")
    if not args.detector_model.is_file():
        raise SystemExit(
            f"--detector-model must be an existing local file: "
            f"{args.detector_model}"
        )
    if not args.pose_model.is_file():
        raise SystemExit(f"--pose-model must be an existing local file: {args.pose_model}")
    if args.session_kind in {"pilot", "participant"} and not args.masked_track_preview:
        raise SystemExit("--masked-track-preview is required for pilot/participant annotation")
    if (args.experimental_track_stitching and args.session_kind != "non_research_dry_run"):
        raise SystemExit("--experimental-track-stitching is restricted to non_research_dry_run sessions pending S1-S4 validation")
    if args.session_kind in {"pilot", "participant"}:
        try:
            enforce_live_settings(args, args.collection_profile)
        except CollectionProfileError as error:
            raise SystemExit(str(error)) from error

def main(argv=None):
    args = build_parser().parse_args(argv)
    validate_cli_args(args)
    preflight_config = PreflightConfig(
        session_kind=args.session_kind,
        participant_ids=tuple(args.participant_id),
        acknowledgement_confirmed=args.acknowledgement_confirmed,
        dji_recording_disabled=True,
        camera_config_path=args.camera_config,
        mask_config_path=args.mask_config,
        mediamtx_config_path=args.mediamtx_config,
        collection_profile_path=args.collection_profile,
        output_directory=args.output_directory,
        minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        sensor_wait_seconds=args.sensor_wait_seconds,
    )
    camera = load_camera_config(args.camera_config)
    mask = load_and_validate_mask(args.mask_config, camera)
    prepared = prepare_session(preflight_config)
    pipeline_options = {
        "detector_model": str(args.detector_model),
        "pose_model": str(args.pose_model),
        "detector_confidence": args.detector_confidence,
        "detector_iou": args.detector_iou,
        "pose_confidence": args.pose_confidence,
        "tracker_config": args.tracker_config,
        "processing_fps": args.processing_fps,
        "inference_size": args.inference_size,
        "pose_inference_size": args.pose_inference_size,
        "device": args.device,
        "keypoint_confidence": args.keypoint_confidence,
        "min_confident_keypoints": args.min_confident_keypoints,
        "experimental_track_stitching": (
            args.experimental_track_stitching
        ),
    }
    annotation_handle = {}
    writer_factories = [
        lambda context: TelemetrySessionWriter(
            context,
            udp_host=args.udp_host,
            udp_port=args.udp_port,
        )
    ]
    if args.session_kind in {"pilot", "participant"}:
        def annotation_factory(context):
            writer = LiveAnnotationWriter(
                context,
                annotator_id=args.annotator_id,
            )
            annotation_handle["writer"] = writer
            return writer

        writer_factories.append(annotation_factory)
    writer_factories.append(
        lambda context: CameraSessionWriter(
            context,
            source=camera["source"],
            mask_config=mask,
            pipeline_options=pipeline_options,
            preview_enabled=args.masked_track_preview,
            preview_port=args.preview_port,
            annotation_writer=annotation_handle.get("writer"),
        )
    )
    started = start_prepared_session(prepared, writer_factories)
    if "writer" in annotation_handle:
        annotation_handle["writer"].set_participant_registrar(started.add_participant)
    print(f"Live session started: {started.context.session_id}")
    print(f"Manifest: {started.context.manifest_path}")
    for handle in started.writer_handles:
        preview = getattr(handle, "preview", None)
        if preview is not None:
            print(f"Masked track preview: {preview.url}")
    try:
        interactive_session(started)
    except Exception:
        with started.context.manifest_path.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        if manifest["status"] in {"running", "paused"}:
            started.abort()
        raise
    return 0

if __name__ == "__main__":
    raise SystemExit(main())