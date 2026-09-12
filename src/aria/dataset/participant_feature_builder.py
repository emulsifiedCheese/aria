"""build deterministic participant-specific 10.2 multimodal features"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from aria.fusion.window_builder import (
    ACTIVE_NODES,
    DEFAULT_WINDOW_SECONDS,
    _window_start,
    load_camera_records,
    load_sensor_records,
)
from aria.inference.preprocessing import build_track_feature_window

DATASET_SCHEMA_VERSION = 1
DATASET_VERSION = "zone-a-phase10-features-v1"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_PATH = (PROJECT_ROOT / "schemas" / "phase_10_2_participant_feature.schema.json")
DEFAULT_FEATURE_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "feature_vector.schema.json"

class ParticipantFeatureBuildError(ValueError):
    """raised when participant feature construction fails"""

def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise ParticipantFeatureBuildError(f"Cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise ParticipantFeatureBuildError(f"{path} must contain a JSON object")
    return value

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ParticipantFeatureBuildError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(value, dict):
                raise ParticipantFeatureBuildError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _participant_validator(schema_path: Path, feature_schema_path: Path):
    schema = _load_json(schema_path)
    feature_schema = _load_json(feature_schema_path)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(feature_schema)
    registry = Registry().with_resource(feature_schema["$id"], Resource.from_contents(feature_schema))
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )

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

def _window_id(record) -> str:
    start = _window_start(record["_timestamp"], DEFAULT_WINDOW_SECONDS)
    return f"zone_a_{int(start.timestamp() * 1000)}_{int(DEFAULT_WINDOW_SECONDS * 1000)}"

def _episode_id(session_id: str, participant_id: str, ordinal: int, first_window: str):
    value = f"{session_id}|{participant_id}|{ordinal}|{first_window}"
    return "episode_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

def _assign_episode_ids(rows: list[dict]) -> None:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["session_id"], row["participant_id"])].append(row)
    for (session_id, participant_id), participant_rows in sorted(grouped.items()):
        participant_rows.sort(key=lambda row: row["feature_vector"]["window_start_sgt"])
        ordinal = 0
        previous = None
        current_episode = None
        for row in participant_rows:
            start = row["feature_vector"]["window_start_sgt"]
            continues = previous is not None and (
                previous["activity"] == row["activity"]
                and previous["local_track_id"] == row["local_track_id"]
                and previous["feature_vector"]["window_end_sgt"] == start
            )
            if not continues:
                ordinal += 1
                current_episode = _episode_id(
                    session_id,
                    participant_id,
                    ordinal,
                    row["feature_vector"]["window_id"],
                )
            row["episode_id"] = current_episode
            previous = row

def build_participant_features(
    *,
    data_raw_dir: str | Path,
    inventory_path: str | Path,
    normalised_annotations_path: str | Path,
    normalisation_report_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
    feature_schema_path: str | Path = DEFAULT_FEATURE_SCHEMA_PATH,
    keypoint_confidence: float = 0.5,
) -> dict:
    """build 1 validated track-specific feature row/usable annotation window"""

    if not 0 <= keypoint_confidence <= 1:
        raise ParticipantFeatureBuildError("keypoint_confidence must be between zero and one")
    data_raw_dir = Path(data_raw_dir)
    inventory_path = Path(inventory_path)
    normalised_annotations_path = Path(normalised_annotations_path)
    normalisation_report_path = Path(normalisation_report_path)
    output_path = Path(output_path)
    report_path = Path(report_path)
    inventory = _load_json(inventory_path)
    normalisation_report = _load_json(normalisation_report_path)
    if inventory.get("review_status") != "approved":
        raise ParticipantFeatureBuildError("source inventory must be approved")
    if normalisation_report.get("status") != "complete":
        raise ParticipantFeatureBuildError("annotation normalisation must be complete")
    normalised_hash = _sha256(normalised_annotations_path)
    if normalisation_report.get("normalised_output_sha256") != normalised_hash:
        raise ParticipantFeatureBuildError("normalised annotation hash mismatch")

    annotations = _load_jsonl(normalised_annotations_path)
    usable_annotations = [record for record in annotations if record.get("usable_for_modelling") is True]
    expected_count = normalisation_report.get("usable_windows")
    if len(usable_annotations) != expected_count:
        raise ParticipantFeatureBuildError("usable annotation count does not match normalisation report")
    annotations_by_session = defaultdict(list)
    for annotation in usable_annotations:
        annotations_by_session[annotation["session_id"]].append(annotation)

    validator = _participant_validator(Path(schema_path), Path(feature_schema_path))
    rows = []
    session_reports = []
    included_ids = {session["session_id"] for session in inventory["included_sessions"]}
    unexpected = sorted(set(annotations_by_session) - included_ids)
    if unexpected:
        raise ParticipantFeatureBuildError(f"normalised annotations contain unapproved sessions: {unexpected}")

    for session in inventory["included_sessions"]:
        session_id = session["session_id"]
        session_annotations = annotations_by_session.get(session_id, [])
        session_dir = data_raw_dir / "sessions" / session_id
        camera_records = load_camera_records(session_dir / "camera_a_records.jsonl")
        sensor_records = load_sensor_records(session_dir / "esp_packets.jsonl")
        required_pairs = {
            (annotation["window_id"], annotation["local_track_id"])
            for annotation in session_annotations
        }
        camera_by_pair = defaultdict(list)
        for record in camera_records:
            if record.get("record_type") != "track":
                continue
            pair = (_window_id(record), record["local_track_id"])
            if pair in required_pairs:
                camera_by_pair[pair].append(record)
        sensors_by_window = {node_id: defaultdict(list) for node_id in ACTIVE_NODES}
        for record in sensor_records:
            window_id = _window_id(record)
            sensors_by_window[record["payload"]["node_id"]][window_id].append(record)

        configuration = session["configuration"]
        schema_versions = configuration["schema_versions"]
        session_counts = Counter()
        session_classes = Counter()
        for annotation in session_annotations:
            window_id = annotation["window_id"]
            track_records = camera_by_pair.get((window_id, annotation["local_track_id"]), [])
            if not track_records:
                raise ParticipantFeatureBuildError(
                    f"approved annotation has no selected-track records: "
                    f"{session_id}/{window_id}"
                )
            start = _window_start(track_records[0]["_timestamp"], DEFAULT_WINDOW_SECONDS)
            feature_vector = build_track_feature_window(
                start,
                track_records,
                {
                    node_id: sensors_by_window[node_id].get(window_id, [])
                    for node_id in ACTIVE_NODES
                },
                local_track_id=annotation["local_track_id"],
                keypoint_confidence=keypoint_confidence,
            )
            if feature_vector["window_id"] != window_id:
                raise ParticipantFeatureBuildError("camera and annotation windows differ")
            row = {
                "schema_version": DATASET_SCHEMA_VERSION,
                "dataset_version": DATASET_VERSION,
                "episode_id": "episode_0000000000000000",
                "session_id": session_id,
                "participant_id": annotation["participant_id"],
                "local_track_id": annotation["local_track_id"],
                "source_annotation_id": annotation["source_annotation_id"],
                "activity": annotation["derived_activity"],
                "provenance": {
                    "source_manifest_sha256": session["manifest_sha256"],
                    "source_annotation_schema_version": annotation[
                        "source_annotation_schema_version"
                    ],
                    "annotation_normalisation_sha256": normalised_hash,
                    "collection_profile_id": configuration["collection_profile_id"],
                    "collection_profile_sha256": configuration[
                        "collection_profile_sha256"
                    ],
                    "mask_config_version": configuration["mask_config_version"],
                    "camera_track_schema_version": schema_versions["camera_track"],
                    "esp_packet_schema_version": schema_versions["esp_packet"],
                    "feature_vector_schema_version": schema_versions["feature_vector"],
                },
                "feature_vector": feature_vector,
            }
            rows.append(row)
            session_counts["row_count"] += 1
            session_counts["camera_available"] += int(feature_vector["camera_available"])
            session_counts["pose_available"] += int(feature_vector["pose_available"])
            session_counts["a1_available"] += int(feature_vector["a1_available"])
            session_counts["a2_available"] += int(feature_vector["a2_available"])
            session_classes[row["activity"]] += 1
        session_reports.append({
            "session_id": session_id,
            **dict(session_counts),
            "class_counts": dict(sorted(session_classes.items())),
        })

    _assign_episode_ids(rows)
    rows.sort(key=lambda row: (
        row["session_id"],
        row["participant_id"],
        row["feature_vector"]["window_start_sgt"],
    ))
    for row in rows:
        errors = sorted(validator.iter_errors(row), key=lambda error: list(error.path))
        if errors:
            raise ParticipantFeatureBuildError(f"participant feature schema failure: {errors[0].message}")
    _write_jsonl_atomic(rows, output_path)

    totals = Counter()
    classes = Counter()
    participants = set()
    episodes = set()
    availability_patterns = Counter()
    for row in rows:
        feature = row["feature_vector"]
        totals["row_count"] += 1
        totals["camera_available"] += int(feature["camera_available"])
        totals["pose_available"] += int(feature["pose_available"])
        totals["a1_available"] += int(feature["a1_available"])
        totals["a2_available"] += int(feature["a2_available"])
        flags = (
            feature["camera_available"],
            feature["pose_available"],
            feature["a1_available"],
            feature["a2_available"],
        )
        totals["all_modalities_available"] += int(all(flags))
        pattern = "+".join(
            name if available else f"no_{name}"
            for name, available in zip(("camera", "pose", "a1", "a2"), flags)
        )
        availability_patterns[pattern] += 1
        participants.add(row["participant_id"])
        episodes.add(row["episode_id"])
        classes[row["activity"]] += 1
    report = {
        "report_schema_version": 1,
        "phase": "10.2",
        "status": "built_pending_audit",
        "dataset_version": DATASET_VERSION,
        "source_inventory_sha256": _sha256(inventory_path),
        "annotation_normalisation_sha256": normalised_hash,
        "participant_feature_output_path": output_path.as_posix(),
        "participant_feature_output_sha256": _sha256(output_path),
        **dict(totals),
        "participant_count": len(participants),
        "episode_count": len(episodes),
        "class_counts": dict(sorted(classes.items())),
        "availability_patterns": dict(sorted(availability_patterns.items())),
        "sessions": session_reports,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report