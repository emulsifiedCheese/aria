"""validate, normalise approved 10.1 annotations/2s window"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from jsonschema import Draft202012Validator, FormatChecker
from aria.collection.activity_labels import map_activity_label
from aria.timebase import SGT

WINDOW_MS = 2000
WINDOW_PATTERN = re.compile(r"^zone_a_([0-9]+)_2000$")
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DERIVED_SCHEMA = (
    PROJECT_ROOT / "schemas" / "phase_10_1_annotation_window.schema.json"
)

class AnnotationNormalisationError(ValueError):
    """raised when annotation validation/normalisation fails"""

def _validator(path: Path) -> Draft202012Validator:
    with path.open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise AnnotationNormalisationError(f"{path}:{line_number}: invalid JSON: {error}") from error
    return records

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _window_times(window_id: str) -> tuple[datetime, datetime]:
    match = WINDOW_PATTERN.fullmatch(window_id)
    if match is None:
        raise AnnotationNormalisationError(f"invalid two-second window ID: {window_id}")
    start = datetime.fromtimestamp(int(match.group(1)) / 1000, tz=SGT)
    return start, start + timedelta(milliseconds=WINDOW_MS)

def _expected_window_ids(start_text: str, end_text: str) -> list[str]:
    start = datetime.fromisoformat(start_text).astimezone(SGT)
    end = datetime.fromisoformat(end_text).astimezone(SGT)
    if start >= end:
        raise AnnotationNormalisationError("annotation interval must have positive length")
    values = []
    current = start
    while current < end:
        values.append(f"zone_a_{int(round(current.timestamp() * 1000))}_{WINDOW_MS}")
        current += timedelta(milliseconds=WINDOW_MS)
    return values

def _camera_track_windows(camera_path: Path, required_windows: set[str]) -> dict:
    tracks = defaultdict(set)
    with camera_path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise AnnotationNormalisationError(
                    f"{camera_path}:{line_number}: invalid JSON: {error}"
                ) from error
            if record.get("record_type") != "track":
                continue
            timestamp = datetime.fromisoformat(record["frame_timestamp_sgt"])
            start_ms = math.floor(timestamp.timestamp() * 1000 / WINDOW_MS) * WINDOW_MS
            window_id = f"zone_a_{start_ms}_{WINDOW_MS}"
            if window_id in required_windows:
                tracks[window_id].add(record["local_track_id"])
    return tracks

def _annotation_schema_path(schema_dir: Path, version: int) -> Path:
    if version == 2:
        return schema_dir / "annotation.v2.schema.json"
    if version == 3:
        return schema_dir / "annotation.schema.json"
    raise AnnotationNormalisationError(f"unsupported source annotation schema version: {version}")

def _phase_10_reason(annotation: dict, track_present: bool, incident_affected: bool):
    if incident_affected:
        return "incident_affected"
    if not track_present:
        return "selected_track_absent"
    if annotation["label_status"] == "uncertain":
        return "source_uncertain"
    if annotation["label_status"] == "excluded":
        return "source_excluded"
    return None

def _write_jsonl_atomic(records: list[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            for record in records:
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
                stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise

def normalise_approved_annotations(
    *,
    data_raw_dir: str | Path,
    inventory_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
    schema_dir: str | Path | None = None,
    derived_schema_path: str | Path = DEFAULT_DERIVED_SCHEMA,
) -> dict:

    data_raw_dir = Path(data_raw_dir)
    inventory_path = Path(inventory_path)
    output_path = Path(output_path)
    report_path = Path(report_path)
    schema_dir = Path(schema_dir or PROJECT_ROOT / "schemas")
    inventory = _load_json(inventory_path)
    if inventory.get("review_status") != "approved":
        raise AnnotationNormalisationError("source inventory must be approved")

    source_validators = {
        version: _validator(_annotation_schema_path(schema_dir, version))
        for version in (2, 3)
    }
    derived_validator = _validator(Path(derived_schema_path))
    derived_records = []
    annotation_ids = set()
    participant_windows = {}
    session_reports = []
    track_absent_references = []
    source_schema_counts = Counter()
    source_status_counts = Counter()

    for session in inventory["included_sessions"]:
        if session.get("review_status") != "approved":
            raise AnnotationNormalisationError(f"session is not approved: {session.get('session_id')}")
        session_id = session["session_id"]
        manifest = _load_json(data_raw_dir / session["manifest_relative_path"])
        session_dir = data_raw_dir / "sessions" / session_id
        annotation_path = session_dir / "annotations.jsonl"
        camera_path = session_dir / "camera_a_records.jsonl"
        annotations = _load_jsonl(annotation_path)
        required_windows = {
            window_id for record in annotations for window_id in record.get("window_ids", [])
        }
        tracks_by_window = _camera_track_windows(camera_path, required_windows)
        incident_windows = set()
        for incident_id in session.get("incident_ids", []):
            incident = _load_json(data_raw_dir / "incidents" / f"{incident_id}.json")
            if incident.get("session_id") != session_id:
                raise AnnotationNormalisationError(f"incident {incident_id} belongs to another session")
            incident_windows.update(incident.get("affected_window_ids", []))

        participants = set(manifest.get("participant_ids", []))
        session_started = datetime.fromisoformat(manifest["started_at_sgt"])
        session_ended = datetime.fromisoformat(manifest["ended_at_sgt"])
        session_counts = Counter()
        session_classes = Counter()
        for annotation in annotations:
            version = annotation.get("schema_version")
            if version not in source_validators:
                raise AnnotationNormalisationError(f"unsupported annotation schema version: {version}")
            errors = sorted(
                source_validators[version].iter_errors(annotation),
                key=lambda error: list(error.path),
            )
            if errors:
                raise AnnotationNormalisationError(
                    f"{session_id}/{annotation.get('annotation_id')}: schema failure: "
                    f"{errors[0].message}"
                )
            if annotation["annotation_id"] in annotation_ids:
                raise AnnotationNormalisationError(f"duplicate annotation ID: {annotation['annotation_id']}")
            annotation_ids.add(annotation["annotation_id"])
            if annotation["session_id"] != session_id:
                raise AnnotationNormalisationError("annotation session ID mismatch")
            if annotation["participant_id"] not in participants:
                raise AnnotationNormalisationError(f"annotation participant is absent from manifest: {session_id}")
            expected = _expected_window_ids(annotation["interval_start_sgt"], annotation["interval_end_sgt"])
            annotation_start = datetime.fromisoformat(annotation["interval_start_sgt"])
            annotation_end = datetime.fromisoformat(annotation["interval_end_sgt"])
            if annotation_start < session_started or annotation_end > session_ended:
                raise AnnotationNormalisationError(f"annotation interval falls outside session: {annotation['annotation_id']}")
            if annotation["window_ids"] != expected:
                raise AnnotationNormalisationError(f"annotation window sequence mismatch: {annotation['annotation_id']}")
            derived_activity = map_activity_label(annotation["activity"], source_schema_version=version)
            source_schema_counts[str(version)] += 1
            source_status_counts[annotation["label_status"]] += 1
            for window_id in annotation["window_ids"]:
                key = (session_id, annotation["participant_id"], window_id)
                if key in participant_windows:
                    raise AnnotationNormalisationError(f"overlapping participant annotation window: {key}")
                participant_windows[key] = annotation["annotation_id"]
                track_present = annotation["local_track_id"] in tracks_by_window.get(window_id, set())
                incident_affected = window_id in incident_windows
                reason = _phase_10_reason(annotation, track_present, incident_affected)
                usable = annotation["usable_for_modelling"] and reason is None
                if not track_present:
                    track_absent_references.append({
                        "session_id": session_id,
                        "source_annotation_id": annotation["annotation_id"],
                        "window_id": window_id,
                        "source_usable_for_modelling": annotation[
                            "usable_for_modelling"
                        ],
                    })
                start, end = _window_times(window_id)
                derived = {
                    "schema_version": 1,
                    "session_id": session_id,
                    "participant_id": annotation["participant_id"],
                    "local_track_id": annotation["local_track_id"],
                    "window_id": window_id,
                    "window_start_sgt": start.isoformat(timespec="milliseconds"),
                    "window_end_sgt": end.isoformat(timespec="milliseconds"),
                    "source_annotation_id": annotation["annotation_id"],
                    "source_annotation_schema_version": version,
                    "source_activity": annotation["activity"],
                    "derived_activity": derived_activity,
                    "source_label_status": annotation["label_status"],
                    "source_exclusion_reason": annotation["exclusion_reason"],
                    "track_present": track_present,
                    "incident_affected": incident_affected,
                    "usable_for_modelling": usable,
                    "phase_10_exclusion_reason": reason,
                }
                validation_errors = list(derived_validator.iter_errors(derived))
                if validation_errors:
                    raise AnnotationNormalisationError(f"derived annotation schema failure: {validation_errors[0].message}")
                derived_records.append(derived)
                session_counts["total_windows"] += 1
                session_counts["usable_windows"] += int(usable)
                session_counts["track_absent_windows"] += int(not track_present)
                session_counts["newly_excluded_track_absent_windows"] += int(not track_present and annotation["usable_for_modelling"])
                session_counts["incident_affected_windows"] += int(incident_affected)
                session_counts["source_nonusable_windows"] += int(not annotation["usable_for_modelling"])
                if usable:
                    session_classes[derived_activity] += 1
        session_reports.append({
            "session_id": session_id,
            "source_annotation_count": len(annotations),
            **dict(session_counts),
            "usable_class_counts": dict(sorted(session_classes.items())),
        })

    track_participants = defaultdict(set)
    for record in derived_records:
        if record["track_present"]:
            track_participants[
                (record["session_id"], record["window_id"], record["local_track_id"])
            ].add(record["participant_id"])
    conflicting_track_keys = {
        key for key, participants in track_participants.items() if len(participants) > 1
    }
    conflict_references = []
    newly_excluded_conflicts = 0
    for record in derived_records:
        key = (record["session_id"], record["window_id"], record["local_track_id"])
        if key not in conflicting_track_keys:
            continue
        conflict_references.append({
            "session_id": record["session_id"],
            "source_annotation_id": record["source_annotation_id"],
            "window_id": record["window_id"],
            "local_track_id": record["local_track_id"],
            "source_usable_for_modelling": (
                record["source_label_status"] == "labelled"
            ),
        })
        if record["usable_for_modelling"]:
            record["usable_for_modelling"] = False
            record["phase_10_exclusion_reason"] = "conflicting_track_assignment"
            newly_excluded_conflicts += 1

    session_reports = []
    records_by_session = defaultdict(list)
    for record in derived_records:
        records_by_session[record["session_id"]].append(record)
    for session in inventory["included_sessions"]:
        session_records = records_by_session[session["session_id"]]
        counts = Counter()
        classes = Counter()
        annotation_count = len({
            record["source_annotation_id"] for record in session_records
        })
        for record in session_records:
            counts["total_windows"] += 1
            counts["usable_windows"] += int(record["usable_for_modelling"])
            counts["track_absent_windows"] += int(not record["track_present"])
            counts["newly_excluded_track_absent_windows"] += int(
                not record["track_present"]
                and record["source_label_status"] == "labelled"
            )
            counts["conflicting_track_assignment_windows"] += int(
                (
                    record["session_id"],
                    record["window_id"],
                    record["local_track_id"],
                ) in conflicting_track_keys
            )
            counts["newly_excluded_conflicting_track_assignment_windows"] += int(
                record["phase_10_exclusion_reason"]
                == "conflicting_track_assignment"
            )
            counts["incident_affected_windows"] += int(record["incident_affected"])
            counts["source_nonusable_windows"] += int(
                record["source_label_status"] != "labelled"
            )
            if record["usable_for_modelling"]:
                classes[record["derived_activity"]] += 1
        session_reports.append({
            "session_id": session["session_id"],
            "source_annotation_count": annotation_count,
            **dict(counts),
            "usable_class_counts": dict(sorted(classes.items())),
        })

    _write_jsonl_atomic(derived_records, output_path)
    totals = Counter()
    classes = Counter()
    for record in derived_records:
        totals["total_windows"] += 1
        totals["usable_windows"] += int(record["usable_for_modelling"])
        totals["track_absent_windows"] += int(not record["track_present"])
        totals["newly_excluded_track_absent_windows"] += int(
            not record["track_present"]
            and record["source_label_status"] == "labelled"
        )
        totals["conflicting_track_assignment_windows"] += int(
            (
                record["session_id"],
                record["window_id"],
                record["local_track_id"],
            ) in conflicting_track_keys
        )
        totals["newly_excluded_conflicting_track_assignment_windows"] += int(
            record["phase_10_exclusion_reason"]
            == "conflicting_track_assignment"
        )
        totals["incident_affected_windows"] += int(record["incident_affected"])
        totals["source_nonusable_windows"] += int(record["source_label_status"] != "labelled")
        if record["usable_for_modelling"]:
            classes[record["derived_activity"]] += 1
    report = {
        "report_schema_version": 1,
        "phase": "10.1",
        "status": "complete",
        "source_inventory_sha256": _sha256(inventory_path),
        "normalised_output_path": output_path.as_posix(),
        "normalised_output_sha256": _sha256(output_path),
        "source_annotation_count": len(annotation_ids),
        "source_annotation_schema_counts": dict(sorted(source_schema_counts.items())),
        "source_annotation_status_counts": dict(sorted(source_status_counts.items())),
        **dict(totals),
        "usable_class_counts": dict(sorted(classes.items())),
        "track_absent_references": track_absent_references,
        "conflicting_track_assignment_group_count": len(conflicting_track_keys),
        "conflicting_track_assignment_references": conflict_references,
        "sessions": session_reports,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
