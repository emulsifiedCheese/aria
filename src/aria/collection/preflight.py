"""fail-closed zone a preflight checks for collection-session startup"""
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
from typing import Callable, Mapping, Sequence
import yaml
from aria.cameras.camera_manager import CameraManager, FPS_TOLERANCE
from aria.cameras.privacy_mask import MaskConfig, validate_mask_config
from aria.ingestion.node_monitor import NodeMonitor, STALE_AFTER_SECONDS
from aria.ingestion.packet_parser import parse_packet
from aria.timebase import as_sgt, sgt_now as timebase_sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CAMERA_ID = "camera_a"
CAMERA_WIDTH = 1920
CAMERA_HEIGHT = 1080
CAMERA_FPS = 30
CAMERA_SOURCE = "rtsp://127.0.0.1:8554/live/camera_a"
ACTIVE_NODES = ("ESP-A1", "ESP-A2")
ACTIVE_FIRMWARE_VERSION = "1.1.1"
PARTICIPANT_ID_PATTERN = re.compile(r"^P[0-9]{4}$")
DEFAULT_CAMERA_CONFIG = PROJECT_ROOT / "config" / "cameras.batamfast.yaml"
DEFAULT_MASK_CONFIG = PROJECT_ROOT / "config" / "masks.batamfast.yaml"
DEFAULT_MEDIAMTX_CONFIG = PROJECT_ROOT / "config" / "mediamtx.local.yaml"
DEFAULT_COLLECTION_PROFILE = PROJECT_ROOT / "config" / "collection.zone_a.v7.yaml"
DEFAULT_OUTPUT_DIRECTORY = PROJECT_ROOT / "data" / "raw"
DEFAULT_MINIMUM_FREE_BYTES = 5 * 1024**3

REQUIRED_CHECKS = (
    "consent_and_acknowledgement_confirmed",
    "camera_identity_and_mode_confirmed",
    "privacy_mask_verified",
    "audio_capture_disabled",
    "esp_a1_fresh",
    "esp_a2_fresh",
    "storage_ready",
)

class PreflightError(RuntimeError):
    """raised when required preflight checks fails"""

@dataclass(frozen=True)
class SensorPacket:
    raw: bytes
    received_at_sgt: str

@dataclass(frozen=True)
class PreflightConfig:

    session_kind: str
    participant_ids: Sequence[str] = ()
    acknowledgement_confirmed: bool = False
    dji_recording_disabled: bool = False
    camera_config_path: Path = DEFAULT_CAMERA_CONFIG
    mask_config_path: Path = DEFAULT_MASK_CONFIG
    mediamtx_config_path: Path = DEFAULT_MEDIAMTX_CONFIG
    collection_profile_path: Path = DEFAULT_COLLECTION_PROFILE
    output_directory: Path = DEFAULT_OUTPUT_DIRECTORY
    minimum_free_bytes: int = DEFAULT_MINIMUM_FREE_BYTES
    approved_output_roots: Sequence[Path] = field(
        default_factory=lambda: (
            PROJECT_ROOT / "data",
            PROJECT_ROOT / "outputs",
        )
    )
    udp_host: str = "0.0.0.0"
    udp_port: int = 5005
    sensor_wait_seconds: float = 10.0

    def __post_init__(self):
        if self.minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must be non-negative")
        if self.sensor_wait_seconds <= 0:
            raise ValueError("sensor_wait_seconds must be positive")
        if not (1 <= self.udp_port <= 65535):
            raise ValueError("udp_port must be between 1 and 65535")


@dataclass(frozen=True)
class PreflightReport:

    checked_at_sgt: str
    checks: Mapping[str, bool]
    details: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.checked_at_sgt, str) or not self.checked_at_sgt.endswith("+08:00"):
            raise ValueError("checked_at_sgt must use the +08:00 SGT offset")
        try:
            checked_at = datetime.fromisoformat(self.checked_at_sgt)
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("checked_at_sgt must be an ISO 8601 timestamp") from error

        if checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError("checked_at_sgt must be timezone-aware")

        supplied = set(self.checks)
        required = set(REQUIRED_CHECKS)
        missing = sorted(required - supplied)
        unknown = sorted(supplied - required)
        if missing or unknown:
            details = []
            if missing:
                details.append(f"missing checks: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown checks: {', '.join(unknown)}")
            raise ValueError("Invalid preflight report; " + "; ".join(details))

        non_boolean = sorted(name for name, value in self.checks.items() if not isinstance(value, bool))
        if non_boolean:
            raise TypeError("Preflight checks must be boolean: " + ", ".join(non_boolean))

        unknown_details = sorted(set(self.details) - required)
        if unknown_details:
            raise ValueError("Unknown preflight detail keys: " + ", ".join(unknown_details))

    @property
    def passed(self):
        return all(self.checks[name] for name in REQUIRED_CHECKS)

    @property
    def failures(self):
        return tuple(name for name in REQUIRED_CHECKS if not self.checks[name])

    def to_manifest(self):
        return {
            "checked_at_sgt": self.checked_at_sgt,
            **{name: self.checks[name] for name in REQUIRED_CHECKS},
        }

class PauseStopController:

    def __init__(self):
        self._paused = threading.Event()
        self._stopped = threading.Event()

    @property
    def ready(self):
        return not self._stopped.is_set()

    @property
    def paused(self):
        return self._paused.is_set()

    @property
    def stopped(self):
        return self._stopped.is_set()

    def pause(self):
        self._paused.set()

    def resume(self):
        self._paused.clear()

    def stop(self):
        self._stopped.set()

def sgt_now():
    return timebase_sgt_now()

def _aware_sgt_timestamp(value):
    if not isinstance(value, datetime):
        raise TypeError("clock must return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return as_sgt(value)

def _load_yaml_mapping(path, label):
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"{label} does not exist")
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a mapping")
    return value

def validate_participant_scope(config):
    if config.session_kind not in {"non_research_dry_run", "pilot", "participant"}:
        raise ValueError("Unsupported session_kind")

    participant_ids = tuple(config.participant_ids)
    if len(set(participant_ids)) != len(participant_ids):
        raise ValueError("Participant IDs must be unique")
    if any(PARTICIPANT_ID_PATTERN.fullmatch(value) is None for value in participant_ids):
        raise ValueError("Participant IDs must be pseudonymised P0000-style codes")

    if config.session_kind == "non_research_dry_run":
        if participant_ids:
            raise ValueError("Non-research dry runs must not include participant IDs")
        return "non-research scope confirmed; no participant IDs"

    if not participant_ids:
        raise ValueError("Pilot and participant sessions require participant IDs")
    if config.acknowledgement_confirmed is not True:
        raise ValueError("Ethics Pack acknowledgement has not been confirmed")
    return f"approved participant scope confirmed for {len(participant_ids)} code(s)"

def load_camera_config(path):
    document = _load_yaml_mapping(path, "camera configuration")
    cameras = document.get("cameras")
    if not isinstance(cameras, list) or len(cameras) != 1:
        raise ValueError("Camera configuration must contain exactly camera_a")
    camera = cameras[0]
    if not isinstance(camera, dict):
        raise ValueError("camera_a configuration must be a mapping")
    if camera.get("camera_id") != CAMERA_ID:
        raise ValueError("Only camera_a is accepted")
    if camera.get("zone") != "A":
        raise ValueError("camera_a must belong to Zone A")
    if camera.get("source") != CAMERA_SOURCE:
        raise ValueError("camera_a must use the approved local RTSP source")
    if camera.get("width") != CAMERA_WIDTH or camera.get("height") != CAMERA_HEIGHT:
        raise ValueError("camera_a must be configured for 1920x1080")
    fps = camera.get("fps")
    if (
        not isinstance(fps, (int, float))
        or isinstance(fps, bool)
        or abs(float(fps) - CAMERA_FPS) > FPS_TOLERANCE
    ):
        raise ValueError("camera_a must report approximately 30 FPS")
    return camera

def probe_camera(camera):
    manager = CameraManager(
        camera_id=camera["camera_id"],
        source=camera["source"],
        width=camera["width"],
        height=camera["height"],
        fps=camera["fps"],
        privacy_mask_status=camera.get("privacy_mask_status", "not_configured"),
    )
    try:
        manager.open()
        if manager.stats.actual_width != CAMERA_WIDTH:
            raise ValueError("Live camera width is not 1920")
        if manager.stats.actual_height != CAMERA_HEIGHT:
            raise ValueError("Live camera height is not 1080")
        if abs(manager.stats.actual_fps - CAMERA_FPS) > FPS_TOLERANCE:
            raise ValueError("Live camera FPS is outside the accepted tolerance")
    finally:
        manager.close()

def load_and_validate_mask(path, camera):
    document = _load_yaml_mapping(path, "privacy-mask configuration")
    masks = document.get("masks")
    if not isinstance(masks, dict) or set(masks) != {CAMERA_ID}:
        raise ValueError("Mask configuration must contain camera_a only")
    value = masks[CAMERA_ID]
    if not isinstance(value, dict):
        raise ValueError("camera_a mask must be a mapping")

    required = {
        "camera_id",
        "mask_config_version",
        "expected_width",
        "expected_height",
        "x",
        "y",
        "width",
        "height",
        "verified",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError("Mask configuration is missing: " + ", ".join(missing))

    mask = MaskConfig(
        camera_id=value["camera_id"],
        expected_width=value["expected_width"],
        expected_height=value["expected_height"],
        x=value["x"],
        y=value["y"],
        width=value["width"],
        height=value["height"],
        verified=value["verified"],
        excluded_polygons=value.get("excluded_polygons", []),
        mask_config_version=value["mask_config_version"],
    )
    if mask.expected_width != camera["width"]:
        raise ValueError("Mask width does not match camera configuration")
    if mask.expected_height != camera["height"]:
        raise ValueError("Mask height does not match camera configuration")
    if not mask.mask_config_version.strip():
        raise ValueError("Mask configuration version must not be empty")
    validate_mask_config(mask, camera["width"], camera["height"], camera["camera_id"])
    return mask

def load_session_mask(config, camera):

    mask = load_and_validate_mask(config.mask_config_path, camera)
    if config.session_kind in {"pilot", "participant"}:
        approved = load_and_validate_mask(DEFAULT_MASK_CONFIG, camera)
        if mask != approved:
            raise ValueError("Pilot and participant sessions require the exact approved Camera A deployment mask")
    return mask

def validate_mediamtx_config(path):
    document = _load_yaml_mapping(path, "MediaMTX configuration")
    paths = document.get("paths")
    if not isinstance(paths, dict) or set(paths) != {
        "ingest/camera_a",
        "live/camera_a",
    }:
        raise ValueError("MediaMTX must expose only ingest/camera_a and live/camera_a")

    ingest = paths["ingest/camera_a"]
    live = paths["live/camera_a"]
    if ingest.get("record") is not False or live.get("record") is not False:
        raise ValueError("MediaMTX recording must be disabled on both camera paths")
    command = ingest.get("runOnAvailable")
    if not isinstance(command, str):
        raise ValueError("MediaMTX audio-removal relay is not configured")
    required_tokens = (
        "-map 0:v:0",
        "-c:v copy",
        "-an",
        CAMERA_SOURCE,
    )
    if any(token not in command for token in required_tokens):
        raise ValueError("MediaMTX relay must copy H264 video and remove all audio")
    if document.get("playback") is not False:
        raise ValueError("MediaMTX playback must remain disabled")

def probe_stream(source=CAMERA_SOURCE, ffprobe_path=None):
    executable = ffprobe_path or shutil.which("ffprobe")
    if executable is None:
        raise RuntimeError("ffprobe is required to inspect the ARIA-facing stream")
    result = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            source,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    document = json.loads(result.stdout)
    streams = document.get("streams")
    if streams != [{"codec_name": "h264", "codec_type": "video"}]:
        raise ValueError("ARIA-facing stream must contain one H264 video track only")
    return streams

def validate_audio_boundary(config, stream_probe):
    if config.dji_recording_disabled is not True:
        raise ValueError("DJI recording-disabled confirmation is required")
    validate_mediamtx_config(config.mediamtx_config_path)
    streams = stream_probe(CAMERA_SOURCE)
    if list(streams) != [{"codec_name": "h264", "codec_type": "video"}]:
        raise ValueError("ARIA-facing stream must contain one H264 video track only")

def collect_sensor_packets(config):
    deadline = time.monotonic() + config.sensor_wait_seconds
    packets = []
    observed = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
        receiver.bind((config.udp_host, config.udp_port))
        while time.monotonic() < deadline and observed != set(ACTIVE_NODES):
            remaining = deadline - time.monotonic()
            receiver.settimeout(max(0.01, min(0.25, remaining)))
            try:
                raw, _ = receiver.recvfrom(65535)
            except socket.timeout:
                continue
            received_at = sgt_now().isoformat()
            packets.append(SensorPacket(raw=raw, received_at_sgt=received_at))
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                observed.add(value.get("node_id"))
    return packets

def evaluate_sensor_packets(packets, now):
    monitor = NodeMonitor()
    invalid_packet = False
    observed = set()
    for packet in packets:
        try:
            payload = parse_packet(packet.raw)
            if payload["firmware_version"] != ACTIVE_FIRMWARE_VERSION:
                raise ValueError(f"{payload['node_id']} firmware must be {ACTIVE_FIRMWARE_VERSION}")
            received_at = datetime.fromisoformat(packet.received_at_sgt)
            if received_at.tzinfo is None or received_at.utcoffset() is None:
                raise ValueError("Sensor receive timestamp must be timezone-aware")
            monitor.update(payload, received_at.isoformat())
            observed.add(payload["node_id"])
        except (TypeError, ValueError):
            invalid_packet = True

    monitor.check_stale_nodes(now=now)
    statuses = {
        node_id: (
            not invalid_packet
            and node_id in observed
            and node_id in monitor.nodes
            and not monitor.nodes[node_id]["stale"]
        )
        for node_id in ACTIVE_NODES
    }
    return statuses

def _path_is_within(path, root):
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False

def validate_local_storage(config, disk_usage=shutil.disk_usage):
    output_directory = Path(config.output_directory).resolve()
    approved_roots = tuple(Path(root).resolve() for root in config.approved_output_roots)
    if not approved_roots or not any(_path_is_within(output_directory, root) for root in approved_roots):
        raise ValueError("Output directory is outside the approved local roots")
    if not output_directory.is_dir():
        raise ValueError("Output directory must already exist")
    if not os.access(output_directory, os.W_OK):
        raise ValueError("Output directory is not writable")
    usage = disk_usage(output_directory)
    if usage.free < config.minimum_free_bytes:
        raise ValueError("Insufficient free storage for the configured minimum")

def require_ready(report):

    if not isinstance(report, PreflightReport):
        raise TypeError("report must be a PreflightReport")
    if not report.passed:
        raise PreflightError("Session preflight failed: " + ", ".join(report.failures))
    return report

def _record_check(checks, details, name, operation):
    try:
        detail = operation()
        checks[name] = True
        details[name] = str(detail or "passed")
    except Exception as error:
        checks[name] = False
        details[name] = str(error)

def run_preflight(
    config,
    *,
    clock: Callable[[], datetime] = sgt_now,
    camera_probe: Callable[[Mapping], None] = probe_camera,
    stream_probe: Callable[[str], Sequence[Mapping]] = probe_stream,
    sensor_probe: Callable[[PreflightConfig], Sequence[SensorPacket]] = collect_sensor_packets,
    disk_usage: Callable = shutil.disk_usage,
    pause_stop_factory: Callable[[], PauseStopController] = PauseStopController,
):

    if not isinstance(config, PreflightConfig):
        raise TypeError("config must be a PreflightConfig")

    checks = {name: False for name in REQUIRED_CHECKS}
    details = {}

    try:
        now = clock()
        checked_at_sgt = _aware_sgt_timestamp(now)
        clock_ready = True
        clock_detail = "timezone-aware SGT clock ready"
    except Exception as error:
        now = sgt_now()
        checked_at_sgt = _aware_sgt_timestamp(now)
        clock_ready = False
        clock_detail = str(error)

    _record_check(
        checks,
        details,
        "consent_and_acknowledgement_confirmed",
        lambda: validate_participant_scope(config),
    )

    camera = None
    try:
        camera = load_camera_config(config.camera_config_path)
        camera_probe(camera)
        checks["camera_identity_and_mode_confirmed"] = True
        details["camera_identity_and_mode_confirmed"] = ("camera_a opened at 1920x1080 and approximately 30 FPS")
    except Exception as error:
        checks["camera_identity_and_mode_confirmed"] = False
        details["camera_identity_and_mode_confirmed"] = str(error)

    if camera is None:
        checks["privacy_mask_verified"] = False
        details["privacy_mask_verified"] = "camera configuration is not valid"
    else:
        _record_check(
            checks,
            details,
            "privacy_mask_verified",
            lambda: (
                load_session_mask(config, camera)
                and "verified camera_a mask geometry accepted"
            ),
        )

    _record_check(
        checks,
        details,
        "audio_capture_disabled",
        lambda: (
            validate_audio_boundary(config, stream_probe)
            or "recording disabled; one H264 video track; no audio track"
        ),
    )

    try:
        sensor_packets = sensor_probe(config)
        sensor_statuses = evaluate_sensor_packets(sensor_packets, now=clock())
    except Exception as error:
        sensor_statuses = {node_id: False for node_id in ACTIVE_NODES}
        sensor_error = str(error)
    else:
        sensor_error = None

    for node_id, check_name in (("ESP-A1", "esp_a1_fresh"), ("ESP-A2", "esp_a2_fresh")):
        checks[check_name] = sensor_statuses[node_id]
        details[check_name] = (
            f"{node_id} schema-valid and fresh within {STALE_AFTER_SECONDS} seconds"
            if sensor_statuses[node_id]
            else sensor_error or f"{node_id} missing, invalid or stale"
        )

    try:
        validate_local_storage(config, disk_usage=disk_usage)
        controller = pause_stop_factory()
        if not getattr(controller, "ready", False):
            raise ValueError("Pause/stop interface did not initialise")
        if not clock_ready:
            raise ValueError(clock_detail)
        checks["storage_ready"] = True
        details["storage_ready"] = ("SGT clock, approved writable storage and pause/stop interface ready")
    except Exception as error:
        checks["storage_ready"] = False
        details["storage_ready"] = str(error)

    return PreflightReport(
        checked_at_sgt=checked_at_sgt,
        checks=checks,
        details=details,
    )
