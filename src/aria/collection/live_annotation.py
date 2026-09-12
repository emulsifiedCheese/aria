"""lifecycle owned, window aligned live activity annotations"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from jsonschema import Draft202012Validator, FormatChecker
from aria.collection.activity_labels import CURRENT_ACTIVITIES
from aria.timebase import SGT, as_sgt, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ANNOTATION_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "annotation.schema.json"
WINDOW_SECONDS = 2
WINDOW_MILLISECONDS = WINDOW_SECONDS * 1000
ACTIVITIES = CURRENT_ACTIVITIES
NON_USABLE_REASONS = (
    "ambiguous_activity",
    "occluded_pose",
    "missing_modality",
    "non_participant",
    "privacy_incident",
    "mask_failure",
    "stream_gap",
    "equipment_failure",
    "outside_approved_scope",
)
ANNOTATOR_ID_PATTERN = re.compile(r"^A[0-9]{3}$")
PARTICIPANT_ID_PATTERN = re.compile(r"^P[0-9]{4}$")

class LiveAnnotationError(ValueError):
    """raised when live annotation is invalid"""

@dataclass(frozen=True)
class _ActiveAnnotation:
    participant_id: str
    local_track_id: int
    label_status: str
    activity: str | None
    exclusion_reason: str | None
    started_at: datetime

def _load_validator(schema_path=ANNOTATION_SCHEMA_PATH):
    with Path(schema_path).open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _window_boundary(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LiveAnnotationError("Annotation clock must be timezone-aware")
    value = value.astimezone(SGT)
    start_ms = math.floor(value.timestamp() * 1000 / WINDOW_MILLISECONDS)
    start_ms *= WINDOW_MILLISECONDS
    return datetime.fromtimestamp(start_ms / 1000, tz=SGT)

def _window_id(value):
    start_ms = int(round(value.timestamp() * 1000))
    return f"zone_a_{start_ms}_{WINDOW_MILLISECONDS}"

def _window_ids(start, end):
    values = []
    current = start
    while current < end:
        values.append(_window_id(current))
        current += timedelta(seconds=WINDOW_SECONDS)
    return values

def _session_output(context):
    output_root = context.manifest_path.parent.parent.resolve()
    output_path = (output_root / "sessions" / context.session_id / "annotations.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_root, output_path, output_path.relative_to(output_root).as_posix()

class LiveAnnotationWriter:
    def __init__(
        self,
        context,
        *,
        annotator_id="A001",
        clock=sgt_now,
        annotation_id_factory=lambda: f"annotation_{secrets.token_hex(8)}",
        validator=None,
    ):
        if ANNOTATOR_ID_PATTERN.fullmatch(annotator_id) is None:
            raise LiveAnnotationError("annotator_id must use A000 format")
        participant_ids = tuple(context.manifest.get("participant_ids", ()))
        if not participant_ids:
            raise LiveAnnotationError("Live annotations require at least one session participant")
        self.context = context
        self.controller = context.pause_stop_controller
        self.annotator_id = annotator_id
        self.participant_ids = list(participant_ids)
        self.clock = clock
        self.annotation_id_factory = annotation_id_factory
        self.validator = validator or _load_validator()
        self.output_root, self.output_path, self.relative_path = _session_output(context)
        self.output_path.touch(exist_ok=True)
        self._active = {}
        self._replacement_required = {}
        self._observed_window_start = None
        self._observed_track_ids = set()
        self._lock = threading.RLock()
        self._paused = False
        self._closed = False
        self._observed_record_count = 0
        self._written_record_count = 0
        self._excluded_record_count = 0
        self._annotation_ids = set()
        self._participant_registrar = None
        self._last_notice = "Select a participant, visible track and activity."

    def set_participant_registrar(self, registrar):
        if not callable(registrar):
            raise TypeError("participant registrar must be callable")
        with self._lock:
            if self._participant_registrar is not None:
                raise LiveAnnotationError("Participant registrar is already configured")
            self._participant_registrar = registrar

    def add_participant(self, participant_id, *, consent_confirmed=False):

        if not isinstance(participant_id, str):
            raise LiveAnnotationError("participant_id must use P0000 format")
        participant_id = participant_id.strip().upper()
        if PARTICIPANT_ID_PATTERN.fullmatch(participant_id) is None:
            raise LiveAnnotationError("participant_id must use P0000 format")
        if consent_confirmed is not True:
            raise LiveAnnotationError("Explicit participant consent confirmation is required")
        with self._lock:
            if self._closed or self.controller.stopped:
                raise LiveAnnotationError("The annotation session has stopped")
            if self._paused or self.controller.paused:
                raise LiveAnnotationError("Participants cannot be added while paused")
            if participant_id in self.participant_ids:
                raise LiveAnnotationError("Participant already has a card")
            if self._participant_registrar is None:
                raise LiveAnnotationError("Participant registration is not ready")
            try:
                addition = self._participant_registrar(
                    participant_id=participant_id,
                    consent_confirmed=True,
                    annotator_id=self.annotator_id,
                )
            except Exception as error:
                raise LiveAnnotationError(
                    "Participant could not be added to the session manifest"
                ) from error
            self.participant_ids.append(participant_id)
            self._last_notice = f"Added consenting participant {participant_id}."
            return {"addition": addition, "status": self.status()}

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise LiveAnnotationError("Annotation clock must be timezone-aware")
        return value.astimezone(SGT)

    def _validate_state(
        self,
        participant_id,
        local_track_id,
        label_status,
        activity,
        exclusion_reason,
    ):
        if participant_id not in self.participant_ids:
            raise LiveAnnotationError("Participant is not in this session manifest")
        if (
            not isinstance(local_track_id, int)
            or isinstance(local_track_id, bool)
            or local_track_id < 0
        ):
            raise LiveAnnotationError("local_track_id must be a non-negative integer")
        if label_status not in {"labelled", "uncertain", "excluded"}:
            raise LiveAnnotationError("Unsupported label status")
        if label_status == "labelled":
            if activity not in ACTIVITIES:
                raise LiveAnnotationError("Select an approved activity")
            if exclusion_reason is not None:
                raise LiveAnnotationError("Labelled annotations cannot have an exclusion reason")
        else:
            if exclusion_reason not in NON_USABLE_REASONS:
                raise LiveAnnotationError("Uncertain and excluded annotations require a valid reason")
            if activity is not None and activity not in ACTIVITIES:
                raise LiveAnnotationError("Unsupported activity")
            if label_status == "excluded" and activity is not None:
                raise LiveAnnotationError("Excluded annotations cannot have an activity")

    def _record(self, active, ended_at, *, allow_controller_gate=False):
        window_ids = _window_ids(active.started_at, ended_at)
        if not window_ids:
            self._last_notice = ("The previous selection was shorter than one complete two-second window and was not written.")
            return None
        created_at = self._now()
        annotation_id = self.annotation_id_factory()
        if annotation_id in self._annotation_ids:
            raise LiveAnnotationError("Annotation ID factory returned a duplicate")
        record = {
            "schema_version": 3,
            "annotation_id": annotation_id,
            "session_id": self.context.session_id,
            "zone": "A",
            "participant_id": active.participant_id,
            "local_track_id": active.local_track_id,
            "window_ids": window_ids,
            "interval_start_sgt": as_sgt(active.started_at),
            "interval_end_sgt": as_sgt(ended_at),
            "label_status": active.label_status,
            "activity": active.activity,
            "exclusion_reason": active.exclusion_reason,
            "usable_for_modelling": active.label_status == "labelled",
            "annotator_id": self.annotator_id,
            "created_at_sgt": as_sgt(created_at),
        }
        errors = sorted(self.validator.iter_errors(record), key=lambda error: list(error.path))
        if errors:
            error = errors[0]
            location = ".".join(str(part) for part in error.path)
            suffix = f" at {location}" if location else ""
            raise LiveAnnotationError(f"Annotation schema validation failed{suffix}: {error.message}")
        self._observed_record_count += 1
        if not allow_controller_gate and (self.controller.paused or self.controller.stopped):
            self._excluded_record_count += 1
            return None
        with self.output_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._written_record_count += 1
        self._annotation_ids.add(annotation_id)
        self._last_notice = (
            f"Saved {active.participant_id}, track {active.local_track_id}: "
            f"{active.activity or active.label_status}."
        )
        return record

    def transition(
        self,
        *,
        participant_id,
        local_track_id,
        label_status="labelled",
        activity=None,
        exclusion_reason=None,
        now=None,
    ):
        self._validate_state(
            participant_id,
            local_track_id,
            label_status,
            activity,
            exclusion_reason,
        )
        with self._lock:
            if self._closed or self.controller.stopped:
                raise LiveAnnotationError("The annotation session has stopped")
            if self._paused or self.controller.paused:
                raise LiveAnnotationError("Annotations are disabled while paused")
            boundary = _window_boundary(now or self._now())
            new_state = _ActiveAnnotation(
                participant_id=participant_id,
                local_track_id=local_track_id,
                label_status=label_status,
                activity=activity,
                exclusion_reason=exclusion_reason,
                started_at=boundary,
            )
            current = self._active.get(participant_id)
            if current is not None and boundary < current.started_at:
                raise LiveAnnotationError("Annotation clock moved before the active interval")
            if current is not None and (
                current.participant_id,
                current.local_track_id,
                current.label_status,
                current.activity,
                current.exclusion_reason,
            ) == (
                new_state.participant_id,
                new_state.local_track_id,
                new_state.label_status,
                new_state.activity,
                new_state.exclusion_reason,
            ):
                self._last_notice = "That annotation is already active."
                return {"written": None, "status": self.status()}
            written = None
            if current is not None:
                written = self._record(current, boundary)
            self._active[participant_id] = new_state
            self._replacement_required.pop(participant_id, None)
            if written is None and current is None:
                self._last_notice = (
                    f"Started {participant_id}, track {local_track_id}: "
                    f"{activity or label_status}."
                )
            return {"written": written, "status": self.status()}

    def stop_participant(self, participant_id, *, now=None):
        with self._lock:
            if self._closed or self.controller.stopped:
                raise LiveAnnotationError("The annotation session has stopped")
            if self._paused or self.controller.paused:
                raise LiveAnnotationError("Annotations are disabled while paused")
            if participant_id not in self.participant_ids:
                raise LiveAnnotationError("Participant is not in this session manifest")
            current = self._active.pop(participant_id, None)
            replacement = self._replacement_required.pop(participant_id, None)
            if current is None:
                self._last_notice = (
                    "Cleared the replacement-track prompt."
                    if replacement is not None
                    else "No annotation was active for that participant."
                )
                return {"written": None, "status": self.status()}
            boundary = _window_boundary(now or self._now())
            if boundary < current.started_at:
                self._active[participant_id] = current
                raise LiveAnnotationError("Annotation clock moved before the active interval")
            written = self._record(current, boundary)
            return {"written": written, "status": self.status()}

    def _complete_observed_window(self, window_start, track_ids):
        for participant_id, active in list(self._active.items()):
            if active.started_at > window_start:
                continue
            if active.local_track_id in track_ids:
                continue
            self._record(active, window_start)
            self._active.pop(participant_id, None)
            self._replacement_required[participant_id] = {
                "participant_id": participant_id,
                "missing_local_track_id": active.local_track_id,
                "previous_activity": active.activity,
                "missing_window_id": _window_id(window_start),
            }
            self._last_notice = (
                f"Ended {participant_id}: track {active.local_track_id} was "
                "absent for a complete two-second window. Select the "
                "participant's current track and activity to continue."
            )

    def observe_track_snapshot(self, track_ids, frame_timestamp):
        if isinstance(frame_timestamp, str):
            try:
                frame_timestamp = datetime.fromisoformat(frame_timestamp)
            except ValueError as error:
                raise LiveAnnotationError("Frame timestamp must be valid ISO-8601") from error
        boundary = _window_boundary(frame_timestamp)
        normalised_ids = set()
        for track_id in track_ids:
            if (
                not isinstance(track_id, int)
                or isinstance(track_id, bool)
                or track_id < 0
            ):
                raise LiveAnnotationError("Visible track IDs must be non-negative integers")
            normalised_ids.add(track_id)

        with self._lock:
            if self._closed or self._paused:
                return
            if self._observed_window_start is None:
                self._observed_window_start = boundary
            elif boundary < self._observed_window_start:
                return
            elif boundary > self._observed_window_start:
                self._complete_observed_window(
                    self._observed_window_start,
                    self._observed_track_ids,
                )
                missing_start = self._observed_window_start + timedelta(seconds=WINDOW_SECONDS)
                while missing_start < boundary:
                    self._complete_observed_window(missing_start, set())
                    missing_start += timedelta(seconds=WINDOW_SECONDS)
                self._observed_window_start = boundary
                self._observed_track_ids = set()
            self._observed_track_ids.update(normalised_ids)

    def _close_all(self, now, *, allow_controller_gate=False):
        boundary = _window_boundary(now)
        for participant_id, active in list(self._active.items()):
            self._record(
                active,
                boundary,
                allow_controller_gate=allow_controller_gate,
            )
            self._active.pop(participant_id, None)

    def pause(self):
        with self._lock:
            if self._closed:
                return
            self._close_all(self._now(), allow_controller_gate=True)
            self._replacement_required = {}
            self._observed_window_start = None
            self._observed_track_ids = set()
            self._paused = True
            self._last_notice = "Collection paused; active annotations were closed."

    def resume(self):
        with self._lock:
            if self._closed:
                raise LiveAnnotationError("A stopped annotation writer cannot resume")
            self._paused = False
            self._last_notice = "Collection resumed; start new annotations."

    def _rewrite_excluding(self, window_ids):
        window_ids = set(window_ids)
        removed = 0
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.output_path.parent,
                prefix=f".{self.output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                with self.output_path.open(encoding="utf-8") as source:
                    for line_number, line in enumerate(source, start=1):
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            affected = window_ids.intersection(record["window_ids"])
                        except (KeyError, TypeError, json.JSONDecodeError) as error:
                            raise LiveAnnotationError(
                                f"Cannot verify annotation line {line_number}"
                            ) from error
                        if affected:
                            removed += 1
                        else:
                            destination.write(json.dumps(record, sort_keys=True) + "\n")
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temporary_path, self.output_path)
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
        return removed

    def exclude_windows(self, window_ids):
        with self._lock:
            removed = self._rewrite_excluding(window_ids)
            self._written_record_count -= removed
            self._excluded_record_count += removed
            return removed

    def verify_excluded_windows(self, window_ids):
        window_ids = set(window_ids)
        with self._lock, self.output_path.open(encoding="utf-8") as source:
            return not any(
                window_ids.intersection(json.loads(line)["window_ids"])
                for line in source
                if line.strip()
            )

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._close_all(self._now(), allow_controller_gate=True)
            self._closed = True
            self._paused = True
            self.output_path.touch(exist_ok=True)

    def status(self):
        with self._lock:
            return {
                "participants": list(self.participant_ids),
                "activities": list(ACTIVITIES),
                "non_usable_reasons": list(NON_USABLE_REASONS),
                "active": {
                    participant_id: {
                        "participant_id": active.participant_id,
                        "local_track_id": active.local_track_id,
                        "label_status": active.label_status,
                        "activity": active.activity,
                        "exclusion_reason": active.exclusion_reason,
                        "interval_start_sgt": as_sgt(active.started_at),
                    }
                    for participant_id, active in self._active.items()
                },
                "replacement_required": dict(self._replacement_required),
                "participant_add_enabled": self._participant_registrar is not None,
                "paused": self._paused or self.controller.paused,
                "stopped": self._closed or self.controller.stopped,
                "written_record_count": self._written_record_count,
                "last_notice": self._last_notice,
            }

    def session_summary(self):
        with self._lock:
            return {
                "kind": "annotations",
                "relative_path": self.relative_path,
                "observed_record_count": self._observed_record_count,
                "written_record_count": self._written_record_count,
                "excluded_record_count": self._excluded_record_count,
                "gap_count": 0,
                "longest_gap_seconds": 0.0,
            }
