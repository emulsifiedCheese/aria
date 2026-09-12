"""fail-closed pause, exclusion, recovery, clean-stop controls"""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from jsonschema import Draft202012Validator, FormatChecker
from .manifest import validate_manifest, write_manifest_atomic
from aria.timebase import as_sgt, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INCIDENT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "incident.schema.json"
INCIDENT_TYPES = {
    "non_participant_entry",
    "privacy_boundary_breach",
    "camera_movement",
    "mask_failure",
    "camera_stream_loss",
    "esp_a1_loss",
    "esp_a2_loss",
    "storage_failure",
    "equipment_failure",
}
PRIVACY_CRITICAL_TYPES = {
    "non_participant_entry",
    "privacy_boundary_breach",
    "camera_movement",
    "mask_failure",
}
OUTPUT_KINDS = {
    "telemetry_features",
    "camera_features",
    "multimodal_windows",
    "annotations",
    "predictions",
    "incident_log",
}
REQUIRED_RECOVERY_ACTIONS = {
    "non_participant_entry": {"retained_region_cleared"},
    "privacy_boundary_breach": {"privacy_boundary_restored"},
    "camera_movement": {"camera_reverified", "mask_reverified"},
    "mask_failure": {"mask_reverified"},
    "camera_stream_loss": {"stream_recovered"},
    "esp_a1_loss": {"node_recovered"},
    "esp_a2_loss": {"node_recovered"},
    "storage_failure": {"storage_recovered"},
    "equipment_failure": {"equipment_recovered"},
}
PARTICIPANT_ID_PATTERN = re.compile(r"^P[0-9]{4}$")
ANNOTATOR_ID_PATTERN = re.compile(r"^A[0-9]{3}$")

class SessionLifecycleError(RuntimeError):
    """raised when session lifecycle ops cannot complete safely"""

def _sgt_timestamp(value):
    return as_sgt(value)

def _load_incident_validator(schema_path=DEFAULT_INCIDENT_SCHEMA_PATH):
    with Path(schema_path).open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def validate_incident(incident, schema_path=DEFAULT_INCIDENT_SCHEMA_PATH):
    errors = sorted(
        _load_incident_validator(schema_path).iter_errors(incident),
        key=lambda error: list(error.path),
    )
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path)
        prefix = f" at {location}" if location else ""
        raise SessionLifecycleError(f"Incident validation failed{prefix}: {error.message}")
    return incident


def write_incident_atomic(
    incident,
    output_path,
    schema_path=DEFAULT_INCIDENT_SCHEMA_PATH,
):
    validate_incident(incident, schema_path=schema_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            json.dump(incident, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return output_path

def _normalise_summary(summary, output_root):
    if not isinstance(summary, dict):
        raise SessionLifecycleError("Each writer summary must be a dictionary")
    required = {
        "kind",
        "relative_path",
        "observed_record_count",
        "written_record_count",
        "excluded_record_count",
        "gap_count",
        "longest_gap_seconds",
    }
    missing = sorted(required.difference(summary))
    if missing:
        raise SessionLifecycleError("Writer summary is missing: " + ", ".join(missing))
    normalised = {key: summary[key] for key in required}
    if normalised["kind"] not in OUTPUT_KINDS - {"incident_log"}:
        raise SessionLifecycleError("Writer summary has an unsupported output kind")
    output_root = Path(output_root).resolve()
    output_path = (output_root / normalised["relative_path"]).resolve()
    try:
        output_path.relative_to(output_root)
    except ValueError as error:
        raise SessionLifecycleError("Writer output path is outside the session output root") from error
    if not output_path.is_file():
        raise SessionLifecycleError("Writer output file does not exist")
    observed_record_count = normalised["observed_record_count"]
    written_record_count = normalised["written_record_count"]
    excluded_record_count = normalised["excluded_record_count"]
    if (
        isinstance(observed_record_count, int)
        and not isinstance(observed_record_count, bool)
        and isinstance(written_record_count, int)
        and not isinstance(written_record_count, bool)
        and isinstance(excluded_record_count, int)
        and not isinstance(excluded_record_count, bool)
        and observed_record_count
        != written_record_count + excluded_record_count
    ):
        raise SessionLifecycleError("Observed writer records must equal written plus excluded records")
    return normalised

class SessionLifecycle:
    def __init__(
        self,
        context,
        writer_handles,
        pause_stop_controller,
        *,
        clock=sgt_now,
        incident_id_factory=lambda: f"incident_{secrets.token_hex(6)}",
    ):
        self.context = context
        self.writer_handles = tuple(writer_handles)
        self.pause_stop_controller = pause_stop_controller
        self.clock = clock
        self.incident_id_factory = incident_id_factory
        self._lock = threading.RLock()
        self._open_incident = None
        self._closed = False

    @property
    def manifest_path(self):
        return self.context.manifest_path

    @property
    def output_root(self):
        return self.manifest_path.parent.parent

    @property
    def open_incident(self):
        return deepcopy(self._open_incident)

    def _now(self):
        try:
            return _sgt_timestamp(self.clock())
        except Exception as error:
            raise SessionLifecycleError("Session lifecycle clock must be timezone-aware") from error

    def _load_manifest(self):
        try:
            with self.manifest_path.open(encoding="utf-8") as stream:
                manifest = json.load(stream)
            return validate_manifest(manifest)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise SessionLifecycleError("Session manifest is missing or invalid") from error

    def _incident_path(self, incident_id):
        return self.output_root / "incidents" / f"{incident_id}.json"

    def add_participant(
        self,
        *,
        participant_id,
        consent_confirmed=False,
        annotator_id,
    ):
        if (
            not isinstance(participant_id, str)
            or PARTICIPANT_ID_PATTERN.fullmatch(participant_id) is None
        ):
            raise SessionLifecycleError("Participant ID must use P0000 format")
        if consent_confirmed is not True:
            raise SessionLifecycleError("Explicit participant consent is required")
        if (
            not isinstance(annotator_id, str)
            or ANNOTATOR_ID_PATTERN.fullmatch(annotator_id) is None
        ):
            raise SessionLifecycleError("Annotator ID must use A000 format")

        with self._lock:
            if self._closed:
                raise SessionLifecycleError("A closed session cannot add participants")
            manifest = self._load_manifest()
            if manifest["session_kind"] not in {"pilot", "participant"}:
                raise SessionLifecycleError("Participants can be added only to pilot or participant sessions")
            if manifest["status"] != "running":
                raise SessionLifecycleError("Participants can be added only while the session is running")
            if participant_id in manifest["participant_ids"]:
                raise SessionLifecycleError("Participant is already in this session")
            addition = {
                "participant_id": participant_id,
                "added_at_sgt": self._now(),
                "consent_confirmed": True,
                "added_by_annotator_id": annotator_id,
            }
            updated = deepcopy(manifest)
            updated["participant_ids"].append(participant_id)
            updated["participant_additions"].append(addition)
            write_manifest_atomic(updated, self.manifest_path)
            return deepcopy(addition)

    def _apply_exclusions(self, window_ids):
        for handle in self.writer_handles:
            exclude = getattr(handle, "exclude_windows", None)
            verify = getattr(handle, "verify_excluded_windows", None)
            if not callable(exclude) or not callable(verify):
                raise SessionLifecycleError("Every writer must enforce and verify persisted exclusions")
            try:
                exclude(tuple(window_ids))
                verified = verify(tuple(window_ids))
            except Exception as error:
                raise SessionLifecycleError("A writer could not apply the exclusion; session remains paused") from error
            if verified is not True:
                raise SessionLifecycleError("A writer still contains excluded records; session remains paused")
                
    def _verify_exclusions(self, window_ids):
        for handle in self.writer_handles:
            verify = getattr(handle, "verify_excluded_windows", None)
            if not callable(verify) or verify(tuple(window_ids)) is not True:
                raise SessionLifecycleError("Required deletion could not be verified; session remains paused")

    def pause(
        self,
        incident_type,
        *,
        affected_window_ids=(),
        deletion_required=None,
        severity=None,
    ):

        with self._lock:
            if self._closed:
                raise SessionLifecycleError("A closed session cannot be paused")
            if self._open_incident is not None:
                raise SessionLifecycleError("Resolve the open incident before pausing again")
            if incident_type not in INCIDENT_TYPES:
                raise SessionLifecycleError("Unsupported incident type")

            manifest = self._load_manifest()
            if manifest["status"] != "running":
                raise SessionLifecycleError("Only a running session can be paused")

            incident_id = self.incident_id_factory()
            incident_path = self._incident_path(incident_id)
            if incident_id in manifest["incident_ids"] or incident_path.exists():
                raise SessionLifecycleError("Incident ID already exists")
            affected_window_ids = list(dict.fromkeys(affected_window_ids))
            privacy_critical = incident_type in PRIVACY_CRITICAL_TYPES
            if privacy_critical and deletion_required is False:
                raise SessionLifecycleError("Privacy-critical incidents cannot disable required deletion")
            deletion_required = privacy_critical or bool(deletion_required)
            severity = severity or ("privacy_critical" if privacy_critical else "operational")
            if privacy_critical and severity != "privacy_critical":
                raise SessionLifecycleError("Privacy-critical incidents cannot be downgraded")
            actions = ["collection_paused", "affected_data_isolated"]
            if affected_window_ids:
                actions.append("interval_excluded")
            incident = {
                "schema_version": 5,
                "incident_id": incident_id,
                "session_id": self.context.session_id,
                "zone": "A",
                "incident_type": incident_type,
                "severity": severity,
                "status": "open",
                "started_at_sgt": self._now(),
                "ended_at_sgt": None,
                "affected_window_ids": affected_window_ids,
                "actions": actions,
                "deletion_required": bool(deletion_required),
                "deletion_completed": False,
                "deletion_completed_at_sgt": None,
                "recovery_verified": False,
                "resumed_at_sgt": None,
                "operator_role": "student_researcher",
            }
            validate_incident(incident)

            self.pause_stop_controller.pause()
            for handle in self.writer_handles:
                pause = getattr(handle, "pause", None)
                if callable(pause):
                    try:
                        pause()
                    except Exception:
                        pass

            paused_manifest = deepcopy(manifest)
            paused_manifest["status"] = "paused"
            paused_manifest["incident_ids"].append(incident_id)
            try:
                write_incident_atomic(incident, incident_path)
                write_manifest_atomic(paused_manifest, self.manifest_path)
            except Exception as error:
                self.pause_stop_controller.stop()
                for handle in reversed(self.writer_handles):
                    close = getattr(handle, "close", None)
                    if callable(close):
                        try:
                            close()
                        except Exception:
                            pass
                aborted_manifest = deepcopy(manifest)
                aborted_manifest["status"] = "aborted"
                aborted_manifest["ended_at_sgt"] = self._now()
                write_manifest_atomic(aborted_manifest, self.manifest_path)
                self._closed = True
                raise SessionLifecycleError("Pause evidence could not be persisted; session was aborted") from error
            self._open_incident = incident
            if affected_window_ids:
                self._apply_exclusions(affected_window_ids)
            return deepcopy(incident)

    def exclude_windows(self, window_ids, *, deletion_required=True):
        with self._lock:
            if self._open_incident is None:
                raise SessionLifecycleError("An open paused incident is required")
            window_ids = list(dict.fromkeys(window_ids))
            if not window_ids:
                raise SessionLifecycleError("At least one affected window ID is required")
            incident = deepcopy(self._open_incident)
            incident["affected_window_ids"] = list(dict.fromkeys(incident["affected_window_ids"] + window_ids))
            if "interval_excluded" not in incident["actions"]:
                incident["actions"].append("interval_excluded")
            if deletion_required:
                incident["deletion_required"] = True
            write_incident_atomic(incident,self._incident_path(incident["incident_id"]),)
            self._open_incident = incident
            self._apply_exclusions(window_ids)
            return deepcopy(incident)

    def resume(self, recovery_actions, *, deletion_completed=False):

        with self._lock:
            if self._closed:
                raise SessionLifecycleError("A closed session cannot resume")
            if self._open_incident is None:
                raise SessionLifecycleError("There is no paused incident to resolve")
            incident = deepcopy(self._open_incident)
            recovery_actions = list(dict.fromkeys(recovery_actions))
            if not recovery_actions:
                raise SessionLifecycleError("Verified recovery actions are required")
            required_actions = REQUIRED_RECOVERY_ACTIONS[incident["incident_type"]]
            missing_actions = sorted(required_actions.difference(recovery_actions))
            if missing_actions:
                raise SessionLifecycleError(
                    "Recovery is missing required actions: "
                    + ", ".join(missing_actions)
                )
            if incident["deletion_required"] and not deletion_completed:
                raise SessionLifecycleError("Required deletion must be completed before collection resumes")
            if incident["deletion_required"]:
                self._verify_exclusions(incident["affected_window_ids"])

            manifest = self._load_manifest()
            if manifest["status"] != "paused":
                raise SessionLifecycleError("Only a paused session can resume")

            for handle in self.writer_handles:
                resume = getattr(handle, "resume", None)
                if callable(resume):
                    try:
                        resume()
                    except Exception as error:
                        raise SessionLifecycleError(
                            "A writer could not recover; session remains paused"
                        ) from error

            resolved_at = self._now()
            incident["actions"] = list(dict.fromkeys(incident["actions"] + recovery_actions))
            if deletion_completed:
                incident["deletion_completed"] = True
                incident["deletion_completed_at_sgt"] = resolved_at
                if "affected_data_deleted" not in incident["actions"]:
                    incident["actions"].append("affected_data_deleted")
            incident["status"] = "resolved"
            incident["ended_at_sgt"] = resolved_at
            incident["recovery_verified"] = True
            incident["resumed_at_sgt"] = resolved_at
            write_incident_atomic(incident,self._incident_path(incident["incident_id"]),)

            running_manifest = deepcopy(manifest)
            running_manifest["status"] = "running"
            write_manifest_atomic(running_manifest, self.manifest_path)

            self.pause_stop_controller.resume()
            self._open_incident = None
            return deepcopy(incident)

    def abort(self):
        with self._lock:
            if self._closed:
                raise SessionLifecycleError("Session has already stopped")
            manifest = self._load_manifest()
            if manifest["status"] not in {"running", "paused"}:
                raise SessionLifecycleError( "Only a running or paused session can be aborted")

            ended_at_sgt = self._now()
            self.pause_stop_controller.stop()
            close_errors = []
            for handle in reversed(self.writer_handles):
                close = getattr(handle, "close", None)
                if not callable(close):
                    close_errors.append("writer has no close method")
                    continue
                try:
                    close()
                except Exception as error:
                    close_errors.append(str(error) or type(error).__name__)

            if self._open_incident is not None:
                incident = deepcopy(self._open_incident)
                if "session_aborted" not in incident["actions"]:
                    incident["actions"].append("session_aborted")
                write_incident_atomic(incident,self._incident_path(incident["incident_id"]),)
                self._open_incident = incident

            aborted = deepcopy(manifest)
            aborted["status"] = "aborted"
            aborted["ended_at_sgt"] = ended_at_sgt
            write_manifest_atomic(aborted, self.manifest_path)
            self._closed = True
            if close_errors:
                raise SessionLifecycleError(
                    "Session was aborted but writer close failed: "
                    + "; ".join(close_errors)
                )
            return deepcopy(aborted)

    def stop(self):

        with self._lock:
            if self._closed:
                raise SessionLifecycleError("Session has already stopped")
            if self._open_incident is not None:
                raise SessionLifecycleError("Resolve the open incident before completing the session")
            manifest = self._load_manifest()
            if manifest["status"] != "running":
                raise SessionLifecycleError("Only a running session can stop cleanly")

            ended_at_sgt = self._now()
            self.pause_stop_controller.stop()
            close_errors = []
            for handle in reversed(self.writer_handles):
                close = getattr(handle, "close", None)
                if not callable(close):
                    close_errors.append("writer has no close method")
                    continue
                try:
                    close()
                except Exception as error:
                    close_errors.append(str(error) or type(error).__name__)

            if close_errors:
                aborted = deepcopy(manifest)
                aborted["status"] = "aborted"
                aborted["ended_at_sgt"] = ended_at_sgt
                write_manifest_atomic(aborted, self.manifest_path)
                self._closed = True
                raise SessionLifecycleError(
                    "Writer close failed; session was marked aborted: "
                    + "; ".join(close_errors)
                )

            try:
                writer_summaries = [handle.session_summary() for handle in self.writer_handles]

                completed = deepcopy(manifest)
                completed["status"] = "completed"
                completed["ended_at_sgt"] = ended_at_sgt
                completed["outputs"] = [
                    _normalise_summary(summary, self.output_root)
                    for summary in writer_summaries
                ]
                relative_paths = [output["relative_path"] for output in completed["outputs"]]
                if len(relative_paths) != len(set(relative_paths)):
                    raise SessionLifecycleError("Writer output paths must be unique within a session")
                if completed["incident_ids"]:
                    completed["outputs"].append(
                        {
                            "kind": "incident_log",
                            "relative_path": "incidents",
                            "observed_record_count": len(completed["incident_ids"]),
                            "written_record_count": len(completed["incident_ids"]),
                            "excluded_record_count": 0,
                            "gap_count": 0,
                            "longest_gap_seconds": 0.0,
                        }
                    )
                write_manifest_atomic(completed, self.manifest_path)
            except Exception as error:
                aborted = deepcopy(manifest)
                aborted["status"] = "aborted"
                aborted["ended_at_sgt"] = ended_at_sgt
                write_manifest_atomic(aborted, self.manifest_path)
                self._closed = True
                raise SessionLifecycleError("Final accounting was invalid; session was marked aborted") from error
            self._closed = True
            return deepcopy(completed)
