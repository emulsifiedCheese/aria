"""quality, missingness, privacy audit for 10.2 features"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median
import tempfile
from jsonschema import Draft202012Validator, FormatChecker
from aria.dataset.participant_feature_builder import _participant_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PARTICIPANT_SCHEMA = (
    PROJECT_ROOT / "schemas" / "phase_10_2_participant_feature.schema.json"
)
DEFAULT_FEATURE_SCHEMA = PROJECT_ROOT / "schemas" / "feature_vector.schema.json"
DEFAULT_EXCLUSION_SCHEMA = (
    PROJECT_ROOT / "schemas" / "phase_10_2_exclusion.schema.json"
)
FORBIDDEN_FIELD_NAMES = {
    "customer",
    "customer_details",
    "employee_name",
    "employee_number",
    "exact_shift",
    "image",
    "participant_code_key",
    "participant_name",
    "physical_description",
    "raw_audio",
    "role",
    "source_ip",
    "source_port",
    "speech",
    "station_manager",
    "transcript",
    "video",
    "audio_waveform",
}
MEDIA_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".wav", ".m4a", ".mp3", ".aac",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff",
}

class DatasetAuditError(ValueError):
    """raised when dataset fails quality/privacy audit"""

class _NumericStats:
    def __init__(self):
        self.count = 0
        self.null_count = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.minimum = None
        self.maximum = None

    def add(self, value):
        if value is None:
            self.null_count += 1
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return
        if not math.isfinite(value):
            raise DatasetAuditError("non-finite numerical feature found")
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def result(self):
        return {
            "count": self.count,
            "null_count": self.null_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": self.mean if self.count else None,
            "standard_deviation": (
                math.sqrt(self.m2 / self.count) if self.count else None
            ),
            "constant": self.count > 0 and self.minimum == self.maximum,
        }

def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise DatasetAuditError(f"{path} must contain a JSON object")
    return value

def _load_jsonl(path: Path) -> list[dict]:
    values = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                    DatasetAuditError(f"non-finite JSON value {value}")
                ))
            except json.JSONDecodeError as error:
                raise DatasetAuditError(f"{path}:{line_number}: {error}") from error
            if not isinstance(value, dict):
                raise DatasetAuditError(f"{path}:{line_number}: expected object")
            values.append(value)
    return values

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _simple_validator(path: Path):
    schema = _load_json(path)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _walk(value, path=()):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, path + (str(index),))
    else:
        yield path, value

def _field_names(value):
    if not isinstance(value, dict):
        return set()
    names = set(value)
    for child in value.values():
        if isinstance(child, dict):
            names.update(_field_names(child))
        elif isinstance(child, list):
            for item in child:
                names.update(_field_names(item))
    return names

def _feature_payload_hash(feature_vector: dict) -> str:
    payload = dict(feature_vector)
    for key in ("window_id", "window_start_sgt", "window_end_sgt"):
        payload.pop(key, None)
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()

def _write_jsonl_atomic(records, output_path: Path):
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

def audit_phase_10_2_dataset(
    *,
    feature_path: str | Path,
    build_report_path: str | Path,
    normalised_annotations_path: str | Path,
    normalisation_report_path: str | Path,
    exclusion_ledger_path: str | Path,
    audit_report_path: str | Path,
    participant_schema_path: str | Path = DEFAULT_PARTICIPANT_SCHEMA,
    feature_schema_path: str | Path = DEFAULT_FEATURE_SCHEMA,
    exclusion_schema_path: str | Path = DEFAULT_EXCLUSION_SCHEMA,
) -> dict:

    feature_path = Path(feature_path)
    build_report_path = Path(build_report_path)
    normalised_annotations_path = Path(normalised_annotations_path)
    normalisation_report_path = Path(normalisation_report_path)
    exclusion_ledger_path = Path(exclusion_ledger_path)
    audit_report_path = Path(audit_report_path)
    build_report = _load_json(build_report_path)
    normalisation_report = _load_json(normalisation_report_path)
    if build_report.get("status") != "built_pending_audit":
        raise DatasetAuditError("feature build must be pending audit")
    feature_hash = _sha256(feature_path)
    if build_report.get("participant_feature_output_sha256") != feature_hash:
        raise DatasetAuditError("participant feature hash mismatch")

    rows = _load_jsonl(feature_path)
    normalised = _load_jsonl(normalised_annotations_path)
    if len(rows) != build_report.get("row_count"):
        raise DatasetAuditError("feature row count differs from build report")
    if len(normalised) != normalisation_report.get("total_windows"):
        raise DatasetAuditError("normalised row count differs from report")

    participant_validator = _participant_validator(
        Path(participant_schema_path), Path(feature_schema_path)
    )
    exclusion_validator = _simple_validator(Path(exclusion_schema_path))
    exclusions = []
    exclusion_reasons = Counter()
    for source in normalised:
        if source.get("usable_for_modelling") is True:
            continue
        exclusion = {
            "schema_version": 1,
            "session_id": source["session_id"],
            "participant_id": source["participant_id"],
            "window_id": source["window_id"],
            "source_annotation_id": source["source_annotation_id"],
            "exclusion_reason": source["phase_10_exclusion_reason"],
        }
        errors = list(exclusion_validator.iter_errors(exclusion))
        if errors:
            raise DatasetAuditError(f"exclusion ledger schema failure: {errors[0].message}")
        exclusions.append(exclusion)
        exclusion_reasons[exclusion["exclusion_reason"]] += 1
    exclusions.sort(key=lambda row: (row["session_id"], row["participant_id"], row["window_id"]))
    _write_jsonl_atomic(exclusions, exclusion_ledger_path)

    row_keys = set()
    class_counts = Counter()
    session_counts = Counter()
    participant_counts = Counter()
    profile_counts = Counter()
    episode_rows = defaultdict(list)
    availability_patterns = Counter()
    unique_window_modalities = {}
    numeric_stats = defaultdict(_NumericStats)
    feature_payload_counts = Counter()
    prohibited_fields = Counter()
    schema_error_count = 0
    track_scope_error_count = 0
    track_assignment_owners = {}
    conflicting_track_assignment_count = 0

    for row in rows:
        errors = sorted(
            participant_validator.iter_errors(row), key=lambda error: list(error.path)
        )
        if errors:
            schema_error_count += 1
            raise DatasetAuditError(f"participant feature schema failure: {errors[0].message}")
        forbidden = _field_names(row).intersection(FORBIDDEN_FIELD_NAMES)
        prohibited_fields.update(forbidden)
        feature = row["feature_vector"]
        key = (row["session_id"], row["participant_id"], feature["window_id"])
        if key in row_keys:
            raise DatasetAuditError(f"duplicate participant/window row: {key}")
        row_keys.add(key)
        if (
            feature["camera"]["unique_track_count"] != 1
            or feature["camera"]["track_record_count"] < 1
        ):
            track_scope_error_count += 1
        assignment_key = (row["session_id"], feature["window_id"], row["local_track_id"])
        existing_owner = track_assignment_owners.setdefault(assignment_key, row["participant_id"])
        if existing_owner != row["participant_id"]:
            conflicting_track_assignment_count += 1
        class_counts[row["activity"]] += 1
        session_counts[row["session_id"]] += 1
        participant_counts[row["participant_id"]] += 1
        profile_counts[
            row["provenance"]["collection_profile_id"]
            + ":"
            + row["provenance"]["collection_profile_sha256"][:8]
        ] += 1
        episode_rows[row["episode_id"]].append(row)
        flags = (
            feature["camera_available"],
            feature["pose_available"],
            feature["a1_available"],
            feature["a2_available"],
        )
        pattern = "+".join(
            name if available else f"no_{name}"
            for name, available in zip(("camera", "pose", "a1", "a2"), flags)
        )
        availability_patterns[pattern] += 1
        temporal_key = (row["session_id"], feature["window_id"])
        sensor_flags = (feature["a1_available"], feature["a2_available"])
        previous_flags = unique_window_modalities.setdefault(temporal_key, sensor_flags)
        if previous_flags != sensor_flags:
            raise DatasetAuditError("shared sensor availability differs within a window")
        for path, value in _walk(feature):
            numeric_stats[".".join(path)].add(value)
        feature_payload_counts[_feature_payload_hash(feature)] += 1

    if prohibited_fields:
        raise DatasetAuditError(f"prohibited fields found: {dict(sorted(prohibited_fields.items()))}")
    if track_scope_error_count:
        raise DatasetAuditError(f"{track_scope_error_count} rows contain invalid participant-track scope")
    if conflicting_track_assignment_count:
        raise DatasetAuditError(f"{conflicting_track_assignment_count} conflicting participant/track assignments")

    episode_classes = Counter()
    episode_lengths_by_class = defaultdict(list)
    episode_integrity_errors = 0
    for episode_id, episode in episode_rows.items():
        identities = {
            (row["session_id"], row["participant_id"], row["local_track_id"], row["activity"])
            for row in episode
        }
        if len(identities) != 1:
            episode_integrity_errors += 1
            continue
        activity = next(iter(identities))[3]
        episode_classes[activity] += 1
        episode_lengths_by_class[activity].append(len(episode))
    if episode_integrity_errors:
        raise DatasetAuditError("episode contains mixed participant, track or activity")

    media_files = sorted(
        str(path)
        for root in {feature_path.parent, exclusion_ledger_path.parent}
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
    )
    if media_files:
        raise DatasetAuditError("media file found in processed dataset directory")

    numeric_result = {path: stats.result() for path, stats in sorted(numeric_stats.items())}
    constant_features = sorted(path for path, stats in numeric_result.items() if stats["constant"])
    episode_summary = {}
    for activity, lengths in sorted(episode_lengths_by_class.items()):
        episode_summary[activity] = {
            "episode_count": len(lengths),
            "minimum_windows": min(lengths),
            "median_windows": median(lengths),
            "maximum_windows": max(lengths),
        }
    duplicate_payload_rows = sum(
        count - 1 for count in feature_payload_counts.values() if count > 1
    )
    reconciliation = {
        "normalised_windows": len(normalised),
        "included_feature_rows": len(rows),
        "excluded_windows": len(exclusions),
        "balances": len(normalised) == len(rows) + len(exclusions),
    }
    if not reconciliation["balances"]:
        raise DatasetAuditError("included and excluded counts do not reconcile")

    report = {
        "report_schema_version": 1,
        "phase": "10.2",
        "status": "pass",
        "participant_feature_sha256": feature_hash,
        "exclusion_ledger_sha256": _sha256(exclusion_ledger_path),
        "reconciliation": reconciliation,
        "quality_audit": {
            "schema_error_count": schema_error_count,
            "duplicate_participant_window_count": 0,
            "track_scope_error_count": track_scope_error_count,
            "conflicting_track_assignment_count": 0,
            "non_finite_numeric_count": 0,
            "row_count": len(rows),
            "unique_temporal_window_count": len(unique_window_modalities),
            "participant_count": len(participant_counts),
            "episode_count": len(episode_rows),
            "class_counts": dict(sorted(class_counts.items())),
            "session_counts": dict(sorted(session_counts.items())),
            "participant_counts": dict(sorted(participant_counts.items())),
            "profile_counts": dict(sorted(profile_counts.items())),
            "availability_patterns": dict(sorted(availability_patterns.items())),
            "episode_summary": episode_summary,
            "duplicate_numerical_payload_rows": duplicate_payload_rows,
            "constant_numerical_fields": constant_features,
            "numerical_fields": numeric_result,
        },
        "privacy_audit": {
            "passed": True,
            "schema_allowlist_enforced": True,
            "prohibited_field_count": 0,
            "processed_media_file_count": 0,
            "raw_audio_or_speech_field_count": 0,
            "identity_or_role_field_count": 0,
            "retired_component_field_count": 0,
        },
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
    }
    audit_report_path.parent.mkdir(parents=True, exist_ok=True)
    audit_report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
