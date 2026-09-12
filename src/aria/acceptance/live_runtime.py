"""op-controlled non-research diagnostics; recording modes stay separate"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import select
import socket
import sys
from threading import Thread
import time
from uuid import uuid4
from aria.collection.preflight import (
    PreflightConfig, load_and_validate_mask, load_camera_config,
    require_ready, run_preflight,
)
from aria.dashboard.app import create_dashboard_app
from aria.dashboard.integration import LocalDashboardIntegration
from aria.ingestion.packet_parser import parse_packet
from aria.timebase import sgt_now
from .runtime import RuntimeSafetyError, WindowRuntime
from .runtime_io import CameraProcess, ROOT, SandboxFirebase, file_hash, verify_assets

OUTPUT_ROOT = ROOT / "outputs/acceptance/phase_13"
RUNTIME_FILES = (
    "src/aria/acceptance/runtime.py", "src/aria/acceptance/runtime_io.py",
    "src/aria/acceptance/live_runtime.py", "src/aria/acceptance/synthetic_runtime.py",
    "src/aria/acceptance/aggregate_report.py",
    "src/aria/acceptance/stability_report.py",
    "src/aria/dashboard/state.py", "src/aria/dashboard/integration.py",
    "src/aria/inference/service.py", "src/aria/inference/orchestrator.py",
    "src/aria/inference/preprocessing.py", "src/aria/cloud/firebase_sync.py",
    "scripts/run_phase_13.py",
)

class RunEvidence:
    """own a new aggregate-only run manifest and fixed-code event journal"""

    def __init__(self, scope, *, root=OUTPUT_ROOT):
        self.path = Path(root) / (sgt_now().strftime("run_%Y%m%dT%H%M%S_") + uuid4().hex[:8])
        self.path.mkdir(parents=True, exist_ok=False)
        self.stream = (self.path / "events.jsonl").open("x", encoding="utf-8")
        self.event_count = 0
        self.manifest = {
            "schema_version": 1, "kind": "phase13_runtime_diagnostics",
            "input_scope": scope, "status": "starting",
            "participant_data_used": False, "external_test_accessed": False,
            "live_firebase_accessed": False, "phase_13_1_complete": False,
            "started_at_sgt": sgt_now().isoformat(),
            "artifacts": {name: file_hash(ROOT / name) for name in RUNTIME_FILES},
            "deployment_assets": verify_assets(),
        }
        self.save()

    def event(self, code, metrics=None):
        #caller-supplied commands and exception messages are never logged
        self.stream.write(json.dumps({
            "at_sgt": sgt_now().isoformat(), "event": code,
            "metrics": metrics or {},
        }, sort_keys=True, allow_nan=False) + "\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.event_count += 1

    def save(self):
        temporary = self.path / "manifest.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.manifest, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path / "manifest.json")

    def finish(self, *, clean, summary):
        try:
            unchanged = all(file_hash(ROOT / name) == digest
                            for name, digest in self.manifest["artifacts"].items())
            verify_assets()
        except Exception:
            unchanged = False
        self.event("stopped" if clean else "aborted", summary)
        self.stream.close()
        self.manifest.update(
            status="completed" if clean and unchanged else "aborted",
            ended_at_sgt=sgt_now().isoformat(), event_count=self.event_count,
            artifacts_unchanged=unchanged, summary=summary,
            events_sha256=file_hash(self.path / "events.jsonl"),
        )
        self.save()

class HardwareRun:
    def __init__(self, runtime, cloud, config, evidence, *,
                 camera_factory=CameraProcess, socket_factory=socket.socket,
                 preflight_runner=run_preflight, clock=sgt_now, live_display_only=False):
        if live_display_only and (
            cloud is not None or evidence is not None
            or runtime.integration.firebase_sync is not None
            or runtime.integration.orchestrator.writer is not None
        ):
            raise RuntimeSafetyError("live_display_requires_no_recording_or_cloud")
        self.live_display_only = live_display_only
        self.runtime, self.cloud, self.config, self.evidence = runtime, cloud, config, evidence
        self.camera_factory, self.socket_factory = camera_factory, socket_factory
        self.preflight_runner, self.clock = preflight_runner, clock
        self.camera = self.udp = None
        self.camera_started_at = None
        self.last_frame_at = None
        self.invalid_packets = 0
        self.camera_shutdowns = []
        self.last_running_health = None
        self.last_pause_reason = None
        self.stability_report = None

    def preflight(self):
        verify_assets()
        report = self.preflight_runner(self.config)
        #store booleans only; no arbitrary error text or device addresses
        if self.evidence is not None:
            self.evidence.event("preflight", dict(report.checks))
        require_ready(report)
        return load_and_validate_mask(self.config.mask_config_path, load_camera_config(self.config.camera_config_path))

    def start(self, mask):
        try:
            self.udp = self.socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(("0.0.0.0", 5005))
            self.udp.setblocking(False)
            self.camera = self.camera_factory(mask)
            self.camera.start()
            self.camera_started_at = time.monotonic()
            self.last_frame_at = None
            self.runtime.resume(verified=True, now=self.clock())
            if self.evidence is not None:
                self.evidence.event("running_empty_region")
        except BaseException:
            self.pause("startup_failed")
            raise

    def pause(self, reason="privacy_pause"):
        #close inference/display gate before stopping vision process
        self.runtime.pause()
        if self.stability_report is not None and reason != "shutdown_privacy_gate":
            self.stability_report.pause()
        self.last_pause_reason = reason
        if self.udp is not None:
            self.udp.close()
            self.udp = None
        if self.camera is not None:
            result = self.camera.stop()
            self.camera_shutdowns.append(result)
            if not result["stopped"]:
                raise RuntimeSafetyError("camera_did_not_stop")
            self.camera = None
        if self.cloud is not None:
            self.cloud.purge()
        if self.evidence is not None:
            self.evidence.event(reason)

    def resume(self):
        if self.runtime.state != "paused":
            raise RuntimeSafetyError("resume_requires_paused_state")
        mask = self.preflight()
        self.start(mask)

    def poll(self):
        if self.runtime.state != "running":
            return
        now = self.clock()
        for _ in range(64):
            try:
                data, address = self.udp.recvfrom(65535)
            except BlockingIOError:
                break
            try:
                packet = parse_packet(data)
            except (ValueError, TypeError):
                self.invalid_packets += 1
                continue
            if self.stability_report is not None:
                self.stability_report.packet(packet['node_id'], packet['sequence'], packet['boot_id'])
            self.runtime.sensor_record({
                "received_at_sgt": now.isoformat(),
                "source_ip": address[0], "source_port": address[1], "payload": packet,
            }, now=now)
        for message in self.camera.poll():
            if not self.live_display_only and any(
                record.get("record_type") == "track" for record in message["records"]
            ):
                self.pause("person_detected_empty_region_required")
                return
            self.runtime.camera_batch(
                message["records"], capture_fps=message["capture_fps"],
                processing_fps=message["processing_fps"], now=now,
            )
            if self.stability_report is not None:
                self.stability_report.frame(message['capture_fps'], message['processing_fps'])
            self.last_frame_at = time.monotonic()
        if self.camera.failed.is_set() or not self.camera.process.is_alive():
            self.pause("camera_failure")
            return
        if (self.last_frame_at is None and time.monotonic() - self.camera_started_at > 45
                or self.last_frame_at is not None and time.monotonic() - self.last_frame_at > 5):
            self.pause("camera_timeout")
            return
        self.runtime.tick(now)
        state = self.runtime.integration.snapshot(now)
        if self.stability_report is not None:
            self.stability_report.observe(state)
        self.last_running_health = {
            "overall_status": state["overall_status"],
            "camera": state["camera"], "sensors": state["sensors"],
        }

    def summary(self):
        state = self.runtime.integration.snapshot(self.clock())
        return {
            **self.runtime.summary(),
            "mode": "live_display_only" if self.live_display_only else "empty_region",
            "recording": False if self.live_display_only else "aggregate_diagnostics",
            "cloud": self.cloud.summary() if self.cloud is not None else False,
            "phase_13_1_complete": False,
            "invalid_udp_packets": self.invalid_packets,
            "camera_shutdowns": list(self.camera_shutdowns),
            "last_running_health": self.last_running_health,
            "health": {"overall_status": state["overall_status"],
                       "camera": state["camera"], "sensors": state["sensors"]},
            "capture_fps_definition": "frame_attempt_index_delta_over_capture_timestamp_delta",
            "processing_fps_definition": "processed_frame_timestamp_interval_reciprocal",
        }

    def close(self):
        self.pause("shutdown_privacy_gate")
        self.runtime.stop()

def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-scope", required=True, choices=("synthetic", "non_research"))
    parser.add_argument("--confirm-empty-retained-region", action="store_true")
    parser.add_argument("--equipment-only", action="store_true", help="health only: no detection, inference, recording or cloud")
    parser.add_argument("--live-display-only", action="store_true", help="approved staff: in-memory activity display; no staff records or cloud")
    parser.add_argument("--save-aggregate-report", action="store_true", help="opt in to one restricted results/counts/shutdown report")
    parser.add_argument("--stability-check", action="store_true", help="opt in to 90-minute aggregate metrics; requires live display and aggregate report")
    parser.add_argument("--clean-boot-confirmed", action="store_true", help="operator attests the clean boot; requires aggregate reporting")
    parser.add_argument("--approved-staff-present", action="store_true")
    parser.add_argument("--mask-alignment-confirmed", action="store_true")
    parser.add_argument("--dji-recording-disabled", action="store_true")
    return parser

def run_hardware(args, *, output_root=OUTPUT_ROOT):
    from werkzeug.serving import make_server
    live_display_only = getattr(args, "live_display_only", False)
    save_aggregate = getattr(args, "save_aggregate_report", False)
    stability_check = getattr(args, "stability_check", False)
    if stability_check and not (save_aggregate and live_display_only):
        raise RuntimeSafetyError("stability_requires_display_and_aggregate_report")
    if save_aggregate and not live_display_only:
        raise RuntimeSafetyError("aggregate_report_requires_live_display")
    if live_display_only and not all((args.input_scope == "non_research", args.approved_staff_present, args.mask_alignment_confirmed, args.dji_recording_disabled)):
        raise RuntimeSafetyError("live_display_confirmations_required")
    deployment_assets = verify_assets()
    config = PreflightConfig(session_kind="non_research_dry_run", dji_recording_disabled=True, camera_config_path=ROOT / "config/cameras.batamfast.yaml", mask_config_path=ROOT / "config/masks.batamfast.yaml", mediamtx_config_path=ROOT / "config/mediamtx.local.yaml", output_directory=ROOT / "outputs",)
    #no cam process, socket owner, dashboard or persistent run directory is started unless every fresh hardware preflight check passes
    report = run_preflight(config)
    for name, passed in report.checks.items():
        print(("PASS " if passed else "FAIL ") + name, flush=True)
    require_ready(report)
    mask = load_and_validate_mask(config.mask_config_path, load_camera_config(config.camera_config_path))
    cloud = None if live_display_only else SandboxFirebase()
    server = server_thread = hardware = evidence = aggregate_report = None
    clean = False
    started = False
    summary = {}
    try:
        integration = LocalDashboardIntegration(firebase_sync=cloud)
        runtime = WindowRuntime(integration=integration)
        if save_aggregate:
            from .aggregate_report import AggregateRunReport
            report_class = AggregateRunReport
            report_options = {}
            if stability_check:
                from .stability_report import StabilityRunReport
                report_class = StabilityRunReport
                report_options['storage_root'] = ROOT / 'outputs'
            aggregate_report = report_class(
                root=output_root, preflight=report.checks,
                clean_boot_confirmed=getattr(args, "clean_boot_confirmed", False),
                source_files=RUNTIME_FILES,
                **report_options,
            )
        if not live_display_only:
            evidence = RunEvidence("non_research", root=output_root)
            evidence.event("preflight", dict(report.checks))
        hardware = HardwareRun(runtime, cloud, config, evidence,
                               live_display_only=live_display_only)
        if stability_check:
            hardware.stability_report = aggregate_report
            runtime.latency_observer = aggregate_report.latency
        app = create_dashboard_app(integration.aggregator)
        if live_display_only:
            disable_dashboard_caching(app)
        server = make_server("127.0.0.1", 8050, app.server, threaded=True)
        server_thread = Thread(target=server.serve_forever, name="aria-phase13-dashboard", daemon=True)
        server_thread.start()
        if cloud is not None:
            cloud.start()
        hardware.start(mask)
        started = True
        if evidence is not None:
            evidence.manifest["status"] = "running"
            evidence.save()
        print("Dashboard: http://127.0.0.1:8050/ (no video)", flush=True)
        if live_display_only:
            if aggregate_report is not None:
                print("LIVE DISPLAY: aggregate reporting enabled; no staff records, recordings, outbox or cloud client.", flush=True)
                print("Aggregate report (incomplete until verified shutdown): " + str(aggregate_report.path), flush=True)
            else:
                print("LIVE DISPLAY ONLY: no recordings, saved records, evidence files, outbox or cloud client.", flush=True)
            print("Commands: status | pause | privacy-failure | resume-verified | stop | abort", flush=True)
            print("Pause BEFORE non-approved people enter the retained region or the camera moves.", flush=True)
            print("resume-verified confirms approved staff only, rechecked mask alignment and DJI recording disabled.", flush=True)
            if stability_check:
                print("STABILITY: waiting up to 60 seconds for fresh camera and both ESPs; aggregate-only checkpoints every 60 seconds. Pauses invalidate an uninterrupted run.", flush=True)
        else:
            print("Cloud is LOCAL SIMULATION; no Firebase network access.", flush=True)
            print("Commands: status | pause | privacy-failure | resume-verified | cloud-offline | cloud-online | stop | abort", flush=True)
            print("resume-verified confirms empty region, rechecked mask alignment and DJI recording disabled.", flush=True)
        deadline = time.monotonic() + 5400
        next_asset_check = time.monotonic()
        while (not aggregate_report.due() if stability_check else time.monotonic() < deadline):
            if time.monotonic() >= next_asset_check:
                for name in ("config/masks.batamfast.yaml", "config/cameras.batamfast.yaml", "config/mediamtx.local.yaml"):
                    if file_hash(ROOT / name) != deployment_assets[name]:
                        hardware.pause("configuration_changed")
                        break
                next_asset_check = time.monotonic() + 1
            readable, _, _ = select.select([sys.stdin], [], [], .05)
            if readable:
                line = sys.stdin.readline()
                command = line.strip()
                if not line or command in ("stop", "abort"):
                    clean = command != "abort"
                    break
                if command in ("pause", "privacy-failure"):
                    hardware.pause()
                elif command == "resume-verified":
                    try:
                        hardware.resume()
                    except Exception:
                        hardware.pause("resume_failed")
                        print("Resume refused; preflight or producer startup failed.", flush=True)
                elif command in ("cloud-offline", "cloud-online"):
                    if cloud is None:
                        print("Cloud is disabled in live-display-only mode.", flush=True)
                    else:
                        cloud.set_offline(command == "cloud-offline")
                        evidence.event("simulated_cloud_offline" if command == "cloud-offline" else "simulated_cloud_online")
                elif command == "status":
                    value = hardware.summary()
                    if stability_check:
                        value['stability'] = aggregate_report.snapshot()
                    if evidence is not None:
                        evidence.event("status", value)
                    print(json.dumps(value, sort_keys=True), flush=True)
                else:
                    print("Unknown command; use status, pause, resume-verified, cloud-offline, cloud-online, stop or abort.", flush=True)
            try:
                previous_state = runtime.state
                hardware.poll()
                if previous_state == "running" and runtime.state == "paused":
                    print("Paused: " + hardware.last_pause_reason, flush=True)
            except Exception:
                hardware.pause("runtime_failure")
                print("Runtime paused safely. Inspect status; do not resume until cause is resolved.", flush=True)
        else:
            clean = True
            if stability_check:
                print("Stability measurement ended; results require assessment, not an automatic pass.", flush=True)
    except KeyboardInterrupt:
        clean = True
    finally:
        clean = clean and started
        try:
            if hardware is not None:
                try:
                    if stability_check and aggregate_report is not None:
                        aggregate_report.end_measurement()
                finally:
                    hardware.close()
                summary = hardware.summary()
                clean = clean and summary["record_accounting_balanced"]
                clean = clean and all(
                    item["stopped"] and not item["forced"] and not item.get("failed", False)
                    and item.get("exit_code", 0) == 0 for item in hardware.camera_shutdowns
                )
        except Exception:
            clean = False
            summary["cleanup_failed"] = True
        finally:
            try:
                if cloud is not None:
                    cloud.close()
                    summary["temporary_outbox_removed"] = not Path(cloud.directory.name).exists()
            except Exception:
                clean = False
                summary["temporary_outbox_removed"] = False
            finally:
                dashboard_stopped = False
                try:
                    if server_thread is not None:
                        server.shutdown()
                        server_thread.join(timeout=3)
                        clean = clean and not server_thread.is_alive()
                    if server is not None:
                        server.server_close()
                    dashboard_stopped = server_thread is None or not server_thread.is_alive()
                except Exception:
                    clean = False
                    summary["cleanup_failed"] = True
                if evidence is not None:
                    evidence.finish(clean=clean, summary=summary)
                    clean = clean and evidence.manifest["status"] == "completed"
                    print("Aggregate evidence: " + str(evidence.path), flush=True)
                elif live_display_only:
                    if aggregate_report is not None:
                        try:
                            clean = aggregate_report.finish(
                                summary=summary, requested_clean=clean, started=started,
                                udp_closed=hardware is not None and hardware.udp is None,
                                dashboard_stopped=dashboard_stopped,
                            )
                            print("Aggregate report: " + str(aggregate_report.path), flush=True)
                            print("Clean shutdown verified: " + str(clean).lower(), flush=True)
                        except Exception:
                            clean = False
                            print("Aggregate report could not be finalised; do not claim a pass.", flush=True)
                        phase = '13.2' if stability_check else '13.1'
                        print(f"No staff records saved. Close the dashboard tab; Phase {phase} still requires assessment.", flush=True)
                    else:
                        print("Stopped. No recording/evidence files created. Close the dashboard tab; Phase 13.1 remains unassessed.", flush=True)
    return 0 if clean else 1

def disable_dashboard_caching(app):
    """keep live-display HTTP responses out of ordinary browser caches"""
    @app.server.after_request
    def no_store(response):
        response.headers["Cache-Control"] = "no-store, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stability_check and not (args.live_display_only and args.save_aggregate_report):
        parser.error("stability-check requires live-display-only and save-aggregate-report")
    if args.save_aggregate_report and not args.live_display_only:
        parser.error("save-aggregate-report requires live-display-only")
    if args.clean_boot_confirmed and not args.save_aggregate_report:
        parser.error("clean-boot-confirmed requires save-aggregate-report")
    if args.live_display_only:
        if args.input_scope != "non_research" or args.equipment_only or args.confirm_empty_retained_region:
            parser.error("live-display-only requires non_research and cannot combine other hardware modes")
        if not all((args.approved_staff_present, args.mask_alignment_confirmed, args.dji_recording_disabled)):
            parser.error("live-display-only requires approved-staff, mask-alignment and recording-disabled confirmations")
        if not sys.stdin.isatty():
            parser.error("live-display-only requires an interactive terminal")
        return run_hardware(args)
    if args.equipment_only:
        if args.input_scope != "non_research":
            parser.error("equipment-only requires non_research scope")
        if not all((args.approved_staff_present, args.mask_alignment_confirmed,
                    args.dji_recording_disabled)):
            parser.error("equipment-only requires approved-staff, mask-alignment and recording-disabled confirmations")
        if args.confirm_empty_retained_region:
            parser.error("equipment-only does not use the empty-region confirmation")
        if not sys.stdin.isatty():
            parser.error("equipment-only requires an interactive terminal")
        from .equipment_runtime import run_equipment
        return run_equipment()
    if args.approved_staff_present:
        parser.error("approved-staff-present requires equipment-only or live-display-only")
    if args.input_scope == "synthetic":
        from .synthetic_runtime import run_synthetic
        evidence = RunEvidence("synthetic")
        try:
            report = run_synthetic()
        except BaseException:
            evidence.finish(clean=False, summary={"synthetic_run_failed": True})
            raise
        evidence.finish(clean=all(report["checks"].values()), summary=report)
        print(json.dumps(report, indent=2))
        print("Aggregate evidence: " + str(evidence.path))
        return 0 if evidence.manifest["status"] == "completed" else 1
    if not all((args.confirm_empty_retained_region, args.mask_alignment_confirmed, args.dji_recording_disabled)):
        parser.error("live hardware requires empty retained region, mask-alignment and recording-disabled confirmations")
    if not sys.stdin.isatty():
        parser.error("live hardware requires an interactive terminal for pause/stop controls")
    return run_hardware(args)