import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from .manifest import (
    build_initial_manifest,
    generate_session_id,
    validate_manifest,
    write_manifest_atomic,
)
from .lifecycle import SessionLifecycle
from .preflight import (
    PauseStopController,
    PreflightConfig,
    require_ready,
    run_preflight,
)
from aria.timebase import SGT, as_sgt, sgt_now

class WriterStartError(RuntimeError):
    """raised when session writers cannot be started safely"""

@dataclass(frozen=True)
class PreparedSession:
    session_id: str
    manifest_path: Path
    preflight_report: object

@dataclass(frozen=True)
class WriterContext:
    session_id: str
    manifest_path: Path
    manifest: dict
    pause_stop_controller: PauseStopController

@dataclass(frozen=True)
class StartedSession:
    context: WriterContext
    writer_handles: tuple
    lifecycle: SessionLifecycle

    def pause(self, incident_type, **kwargs):
        return self.lifecycle.pause(incident_type, **kwargs)

    def exclude_windows(self, window_ids, **kwargs):
        return self.lifecycle.exclude_windows(window_ids, **kwargs)

    def resume(self, recovery_actions, **kwargs):
        return self.lifecycle.resume(recovery_actions, **kwargs)

    def stop(self):
        return self.lifecycle.stop()

    def abort(self):
        return self.lifecycle.abort()

    def add_participant(self, **kwargs):
        return self.lifecycle.add_participant(**kwargs)


def prepare_session(
    config,
    *,
    preflight_runner=run_preflight,
    clock=sgt_now,
    session_id_factory=generate_session_id,
):

    report = preflight_runner(config)
    require_ready(report)
    now = clock()
    session_id = session_id_factory(now=now)
    manifest = build_initial_manifest(
        config,
        report,
        now=now,
        session_id=session_id,
    )
    manifest_path = (
        Path(config.output_directory)
        / "manifests"
        / f"{session_id}.json"
    )
    write_manifest_atomic(manifest, manifest_path)
    return PreparedSession(
        session_id=session_id,
        manifest_path=manifest_path,
        preflight_report=report,
    )

def _load_prepared_manifest(prepared_session):
    if not isinstance(prepared_session, PreparedSession):
        raise TypeError("prepared_session must be a PreparedSession")
    if not prepared_session.manifest_path.is_file():
        raise WriterStartError("Initial session manifest does not exist")
    try:
        with prepared_session.manifest_path.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        validate_manifest(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise WriterStartError("Initial session manifest is invalid") from error
    if manifest.get("session_id") != prepared_session.session_id:
        raise WriterStartError("Prepared session ID does not match its manifest")
    if manifest.get("status") != "planned":
        raise WriterStartError("Only a planned session may start writers")
    if manifest.get("preflight") != prepared_session.preflight_report.to_manifest():
        raise WriterStartError("Prepared manifest preflight no longer matches")
    return manifest

def _close_started_writers(handles):
    for handle in reversed(handles):
        close = getattr(handle, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass

def _validate_writer_handle(handle):
    missing = [
        method_name
        for method_name in (
            "close",
            "session_summary",
            "exclude_windows",
            "verify_excluded_windows",
        )
        if not callable(getattr(handle, method_name, None))
    ]
    if missing:
        raise TypeError("Writer handles must provide callable " + " and ".join(missing))

def _validate_pause_stop_controller(controller):
    missing = [
        method_name
        for method_name in ("pause", "resume", "stop")
        if not callable(getattr(controller, method_name, None))
    ]
    if missing:
        raise WriterStartError("Pause/stop controller must provide callable " + " and ".join(missing))

def start_prepared_session(
    prepared_session,
    writer_factories,
    *,
    clock=sgt_now,
    pause_stop_factory=PauseStopController,
    incident_id_factory=None,
):

    writer_factories = tuple(writer_factories)
    if not writer_factories:
        raise WriterStartError("At least one writer factory is required")

    manifest = _load_prepared_manifest(prepared_session)
    try:
        pause_stop_controller = pause_stop_factory()
    except Exception as error:
        raise WriterStartError("Pause/stop controller could not be initialised") from error
    if not getattr(pause_stop_controller, "ready", False):
        raise WriterStartError("Pause/stop controller is not ready")
    _validate_pause_stop_controller(pause_stop_controller)
    try:
        started_at = clock()
        if (
            not isinstance(started_at, datetime)
            or started_at.tzinfo is None
            or started_at.utcoffset() is None
        ):
            raise ValueError("clock did not return a timezone-aware datetime")
    except Exception as error:
        raise WriterStartError("Writer-start clock must be timezone-aware") from error
    started_at_sgt = as_sgt(started_at)
    running_manifest = deepcopy(manifest)
    running_manifest["status"] = "running"
    running_manifest["started_at_sgt"] = started_at_sgt
    write_manifest_atomic(running_manifest, prepared_session.manifest_path)

    context = WriterContext(
        session_id=prepared_session.session_id,
        manifest_path=prepared_session.manifest_path,
        manifest=running_manifest,
        pause_stop_controller=pause_stop_controller,
    )
    handles = []
    try:
        for factory in writer_factories:
            handle = factory(context)
            handles.append(handle)
            _validate_writer_handle(handle)
    except Exception as error:
        pause_stop_controller.stop()
        _close_started_writers(handles)
        aborted_manifest = deepcopy(running_manifest)
        aborted_manifest["status"] = "aborted"
        try:
            ended_at = clock()
        except Exception:
            ended_at = sgt_now()
        if (
            not isinstance(ended_at, datetime)
            or ended_at.tzinfo is None
            or ended_at.utcoffset() is None
        ):
            ended_at = sgt_now()
        aborted_manifest["ended_at_sgt"] = as_sgt(ended_at)
        write_manifest_atomic(aborted_manifest, prepared_session.manifest_path)
        raise WriterStartError("Writer startup failed; closing opened writers was attempted and the session was aborted") from error

    lifecycle_kwargs = {"clock": clock}
    if incident_id_factory is not None:
        lifecycle_kwargs["incident_id_factory"] = incident_id_factory
    lifecycle = SessionLifecycle(
        context,
        handles,
        pause_stop_controller,
        **lifecycle_kwargs,
    )
    return StartedSession(
        context=context,
        writer_handles=tuple(handles),
        lifecycle=lifecycle,
    )

def _config_from_args(args):
    return PreflightConfig(
        session_kind=args.session_kind,
        participant_ids=tuple(args.participant_id),
        acknowledgement_confirmed=args.acknowledgement_confirmed,
        dji_recording_disabled=args.dji_recording_disabled,
        camera_config_path=args.camera_config,
        mask_config_path=args.mask_config,
        mediamtx_config_path=args.mediamtx_config,
        output_directory=args.output_directory,
        minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
        udp_host=args.udp_host,
        udp_port=args.udp_port,
        sensor_wait_seconds=args.sensor_wait_seconds,
    )

def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Run the ARIA Zone A fail-closed preflight or validate an existing session manifest. A prepared session writes its planned manifest; application writer factories must use the programmatic start gate."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Existing local manifest JSON to validate",
    )
    parser.add_argument(
        "--validate-manifest-only",
        action="store_true",
        help="Validate the supplied manifest without starting writers",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run every live preflight check without starting writers",
    )
    parser.add_argument(
        "--prepare-session",
        action="store_true",
        help="Run preflight and write a planned initial manifest without writers",
    )
    parser.add_argument(
        "--session-kind",
        choices=["non_research_dry_run", "pilot", "participant"],
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
    parser.add_argument(
        "--dji-recording-disabled",
        action="store_true",
        help="Confirm recording is disabled on the DJI camera",
    )
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
        "--output-directory",
        type=Path,
        default=Path("data/raw"),
    )
    parser.add_argument(
        "--minimum-free-gib",
        type=float,
        default=5.0,
    )
    parser.add_argument("--udp-host", default="0.0.0.0")
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--sensor-wait-seconds", type=float, default=10.0)
    return parser

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    selected_modes = sum(
        bool(mode)
        for mode in (
            args.validate_manifest_only,
            args.preflight_only,
            args.prepare_session,
        )
    )
    if selected_modes > 1:
        parser.error("choose only one of --validate-manifest-only, --preflight-only or --prepare-session")

    if args.validate_manifest_only:
        if args.manifest is None:
            parser.error("--validate-manifest-only requires --manifest")
        with args.manifest.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        validate_manifest(manifest)
        print("Session manifest is valid; no writers were started.")
        return 0

    if args.preflight_only:
        if args.session_kind is None:
            parser.error("--preflight-only requires --session-kind")
        config = _config_from_args(args)
        report = run_preflight(config)
        for name, passed in report.checks.items():
            status = "PASS" if passed else "FAIL"
            print(f"{status} {name}: {report.details.get(name, '')}")
        print("No writers were started.")
        return 0 if report.passed else 1

    if args.prepare_session:
        if args.session_kind is None:
            parser.error("--prepare-session requires --session-kind")
        prepared = prepare_session(_config_from_args(args))
        print(f"Prepared session: {prepared.session_id}")
        print(f"Initial manifest: {prepared.manifest_path}")
        print("No writers were started.")
        return 0

    if args.manifest is not None:
        parser.error("--manifest requires --validate-manifest-only")
    else:
        parser.error("live startup is fail-closed; use --preflight-only or --prepare-session or --validate-manifest-only")

if __name__ == "__main__":
    raise SystemExit(main())
