"""supervised equipment health only; no recognition, files or cloud client"""
from __future__ import annotations
import json
from queue import Full
import select
import socket
import sys
import time
from aria.cameras.camera_manager import CameraManager
from aria.cameras.privacy_mask import apply_privacy_mask
from aria.collection.preflight import (PreflightConfig, load_and_validate_mask, load_camera_config, require_ready,run_preflight,)
from aria.dashboard.state import DashboardStateAggregator
from aria.ingestion.packet_parser import parse_packet
from aria.timebase import sgt_now
from .runtime_io import CameraProcess, ROOT, verify_assets

def camera_health_loop(queue, stop, ready, mask, *, camera_factory=CameraManager,
                       clock=time.monotonic):
    """mask then discard frames; only equipment timing crosses IPC."""
    camera = camera_factory(camera_id="camera_a", source="rtsp://127.0.0.1:8554/live/camera_a",
                            enforce_capture_mode=True)
    began = clock()
    last_report = began
    frames = 0
    try:
        camera.open()
        ready.set()
        while not stop.is_set():
            frame = camera.read()
            if stop.is_set():
                break
            if frame is None:
                raise RuntimeError("camera_frame_unavailable")
            #no detector, pose model, writer, preview or feature extractor
            try:
                masked = apply_privacy_mask(frame, mask, "camera_a")
            finally:
                del frame
            del masked
            frames += 1
            now = clock()
            if now - last_report >= 1:
                try:
                    queue.put_nowait({"kind": "equipment_health", "frames": frames,
                                      "last_frame_at": sgt_now().isoformat(),
                                      "capture_fps": frames / max(now - began, .001)})
                except Full:
                    pass  #replaceable health summaries, never recorded frames
                last_report = now
    finally:
        camera.close()

class EquipmentCheck:
    def __init__(self, *, camera_factory=CameraProcess, socket_factory=socket.socket,
                 preflight_runner=run_preflight):
        self.camera_factory, self.socket_factory = camera_factory, socket_factory
        self.preflight_runner = preflight_runner
        self.config = PreflightConfig("non_research_dry_run", dji_recording_disabled=True,
                                      output_directory=ROOT / "outputs")
        self.health = DashboardStateAggregator()
        self.health.set_mask_verified(False)
        self.camera = self.udp = None
        self.invalid_packets = 0
        self.state = "paused"
        self.shutdown_clean = True
        self.assets = None

    def start(self):
        if self.state != "paused":
            raise RuntimeError("pause_before_resume")
        self.assets = verify_assets()
        report = self.preflight_runner(self.config)
        for name, passed in report.checks.items():
            print(("PASS " if passed else "FAIL ") + name, flush=True)
        require_ready(report)
        mask = load_and_validate_mask(self.config.mask_config_path,
                                      load_camera_config(self.config.camera_config_path))
        try:
            self.udp = self.socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(("0.0.0.0", 5005))
            self.udp.setblocking(False)
            self.camera = self.camera_factory(mask, equipment_only=True)
            self.camera.start()
            self.last_message = time.monotonic()
            self.saw_camera = False
            self.health.set_mask_verified(True)
            self.state = "running"
        except BaseException:
            self.pause()
            raise

    def poll(self):
        if self.state != "running":
            return
        for _ in range(64):
            try:
                data, _ = self.udp.recvfrom(65535)
            except BlockingIOError:
                break
            try:
                packet = parse_packet(data)
                if packet["firmware_version"] != "1.1.1":
                    raise ValueError("firmware_mismatch")
                self.health.update_sensor(packet, sgt_now().isoformat())
            except (ValueError, TypeError):
                self.invalid_packets += 1
        for message in self.camera.poll():
            if message.get("kind") != "equipment_health" or set(message) != {
                "kind", "frames", "last_frame_at", "capture_fps"
            }:
                raise RuntimeError("unexpected_camera_payload")
            self.health.update_camera(available=True, last_frame_at=message["last_frame_at"],
                                      capture_fps=message["capture_fps"], processing_fps=None)
            self.last_message = time.monotonic()
            self.saw_camera = True
        if self.camera.failed.is_set() or not self.camera.process.is_alive():
            raise RuntimeError("camera_failed")
        if time.monotonic() - self.last_message > (5 if self.saw_camera else 45):
            raise RuntimeError("camera_timeout")

    def pause(self):
        self.state = "paused"
        self.health.set_mask_verified(False)
        if self.udp is not None:
            self.udp.close()
            self.udp = None
        if self.camera is not None:
            result = self.camera.stop()
            self.shutdown_clean &= result["stopped"] and not result["forced"]
            if not result["stopped"]:
                raise RuntimeError("camera_did_not_stop")
            self.camera = None

    def status(self):
        snapshot = self.health.snapshot()
        return {"mode": "equipment_only", "state": self.state,
                "camera": snapshot["camera"], "sensors": snapshot["sensors"],
                "invalid_packets": self.invalid_packets,
                "activity_inference": False, "recording": False, "cloud": False,
                "phase_13_1_complete": False}

def run_equipment():
    check = EquipmentCheck()
    clean = False
    try:
        check.start()
        print("EQUIPMENT ONLY: approved staff may remain. No detection, pose, activity inference, files or cloud.", flush=True)
        print("No dashboard in this mode. Commands: status | pause | resume-verified | stop", flush=True)
        print("Pause before non-approved people enter the retained region or if the camera moves.", flush=True)
        print("resume-verified reconfirms approved staff only, aligned privacy mask and DJI recording disabled.", flush=True)
        next_check = time.monotonic()
        deadline = next_check + 5400
        while time.monotonic() < deadline:
            try:
                if check.state == "running" and time.monotonic() >= next_check:
                    verify_assets()
                    next_check = time.monotonic() + 1
                readable, _, _ = select.select([sys.stdin], [], [], .05)
                if readable:
                    line = sys.stdin.readline()
                    command = line.strip()
                    if not line or command in ("stop", "abort"):
                        clean = command != "abort"
                        break
                    if command in ("pause", "privacy-failure"):
                        check.pause()
                        print("Paused; camera and UDP stopped.", flush=True)
                    elif command == "resume-verified":
                        check.start()
                    elif command == "status":
                        print(json.dumps(check.status(), sort_keys=True), flush=True)
                    else:
                        print("Use status, pause, resume-verified or stop.", flush=True)
                check.poll()
            except Exception:
                check.pause()
                print("Equipment check paused: health/privacy check failed. Recheck before resuming.", flush=True)
        else:
            clean = True
    except KeyboardInterrupt:
        clean = True
    except Exception:
        print("Equipment startup failed; no recording started.", flush=True)
    finally:
        check.pause()
        print("Stopped. No recording or evidence files created; Phase 13.1 is not marked complete.", flush=True)
    return 0 if clean and check.shutdown_clean else 1