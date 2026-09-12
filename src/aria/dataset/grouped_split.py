"""deterministic external test and dev-cv splits for 10.3"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import tempfile
from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "phase_10_3_split_assignment.schema.json"
POLICY_ID = "zone-a-phase10.3-external-test-loso-v1"

class GroupedSplitError(ValueError):
    """raised when grouped split construction/validation fails"""

def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise GroupedSplitError(f"Cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise GroupedSplitError(f"{path} must contain a JSON object")
    return value

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise GroupedSplitError(f"{path}:{line_number}: expected a JSON object")
                records.append(value)
    except json.JSONDecodeError as error:
        raise GroupedSplitError(f"{path}: invalid JSONL: {error}") from error
    except OSError as error:
        raise GroupedSplitError(f"Cannot read {path}: {error}") from error
    return records

def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

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

def _write_json_atomic(value: dict, output_path: Path) -> None:
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
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise

def _row_key(row: dict) -> tuple[str, str, str]:
    return (
        row["session_id"],
        row["participant_id"],
        row["feature_vector"]["window_id"],
    )

def _assignment_key(assignment: dict) -> tuple[str, str, str]:
    return (
        assignment["session_id"],
        assignment["participant_id"],
        assignment["window_id"],
    )

def _assignment_id(dataset_hash: str, key: tuple[str, str, str]) -> str:
    value = "|".join((dataset_hash, *key))
    return "split_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

def _validate_policy(policy: dict) -> None:
    required = {
        "schema_version",
        "policy_id",
        "dataset_version",
        "expected_source_dataset_sha256",
        "expected_source_audit_sha256",
        "external_test",
        "development_validation",
        "grouping_rules",
    }
    if set(policy) != required:
        raise GroupedSplitError("split policy fields differ from the frozen contract")
    if policy["schema_version"] != 1 or policy["policy_id"] != POLICY_ID:
        raise GroupedSplitError("unsupported split policy")
    if policy["development_validation"].get("method") != "leave_one_session_out":
        raise GroupedSplitError("development validation must be leave-one-session-out")
    fold_sessions = policy["development_validation"].get("fold_sessions")
    if not isinstance(fold_sessions, dict) or not fold_sessions:
        raise GroupedSplitError("split policy must freeze development fold sessions")
    if len(set(fold_sessions.values())) != len(fold_sessions):
        raise GroupedSplitError("one development session is assigned to multiple folds")
    expected_folds = [f"fold_{index:02d}" for index in range(1, len(fold_sessions) + 1)]
    if sorted(fold_sessions) != expected_folds:
        raise GroupedSplitError("development fold IDs must be contiguous and stable")
    rules = policy["grouping_rules"]
    for rule in (
        "external_participant_isolation",
        "external_session_isolation",
        "episode_integrity",
        "temporal_window_integrity",
        "development_validation_session_isolation",
    ):
        if rules.get(rule) is not True:
            raise GroupedSplitError(f"required grouping rule is not enabled: {rule}")
    if rules.get("development_validation_participant_isolation") is not False:
        raise GroupedSplitError("the approved policy must disclose recurring development participants")

def _summary(rows: list[dict]) -> dict:
    classes = Counter()
    availability = Counter()
    participants = set()
    sessions = set()
    episodes = set()
    windows = set()
    for row in rows:
        feature = row["feature_vector"]
        classes[row["activity"]] += 1
        participants.add(row["participant_id"])
        sessions.add(row["session_id"])
        episodes.add(row["episode_id"])
        windows.add((row["session_id"], feature["window_id"]))
        availability["camera_available"] += int(feature["camera_available"])
        availability["pose_available"] += int(feature["pose_available"])
        availability["a1_available"] += int(feature["a1_available"])
        availability["a2_available"] += int(feature["a2_available"])
        availability["all_modalities_available"] += int(all((
            feature["camera_available"],
            feature["pose_available"],
            feature["a1_available"],
            feature["a2_available"],
        )))
    return {
        "row_count": len(rows),
        "participant_count": len(participants),
        "participants": sorted(participants),
        "session_count": len(sessions),
        "sessions": sorted(sessions),
        "episode_count": len(episodes),
        "unique_temporal_window_count": len(windows),
        "class_counts": dict(sorted(classes.items())),
        "modality_available_counts": dict(sorted(availability.items())),
    }

def _connected_components(rows: list[dict]) -> list[dict]:
    adjacency = defaultdict(set)
    for row in rows:
        session = f"session:{row['session_id']}"
        participant = f"participant:{row['participant_id']}"
        adjacency[session].add(participant)
        adjacency[participant].add(session)
    remaining = set(adjacency)
    components = []
    while remaining:
        pending = [min(remaining)]
        nodes = set()
        while pending:
            node = pending.pop()
            if node in nodes:
                continue
            nodes.add(node)
            remaining.discard(node)
            pending.extend(sorted(adjacency[node] - nodes, reverse=True))
        components.append({
            "participants": sorted(
                node.removeprefix("participant:")
                for node in nodes if node.startswith("participant:")
            ),
            "sessions": sorted(
                node.removeprefix("session:")
                for node in nodes if node.startswith("session:")
            ),
        })
    return sorted(components, key=lambda item: item["sessions"])

def _prepare_inputs(feature_path: Path, audit_path: Path, policy_path: Path):
    policy = _load_json(policy_path)
    _validate_policy(policy)
    audit = _load_json(audit_path)
    if audit.get("status") != "pass":
        raise GroupedSplitError("Phase 10.2 dataset audit must pass before splitting")
    dataset_hash = _sha256(feature_path)
    audit_hash = _sha256(audit_path)
    if dataset_hash != policy["expected_source_dataset_sha256"]:
        raise GroupedSplitError("Phase 10.2 feature hash differs from frozen policy")
    if audit_hash != policy["expected_source_audit_sha256"]:
        raise GroupedSplitError("Phase 10.2 audit hash differs from frozen policy")
    if audit.get("participant_feature_sha256") != dataset_hash:
        raise GroupedSplitError("Phase 10.2 audit does not describe the source features")
    rows = _load_jsonl(feature_path)
    if len(rows) != audit.get("quality_audit", {}).get("row_count"):
        raise GroupedSplitError("source feature count differs from the passed audit")
    if any(row.get("dataset_version") != policy["dataset_version"] for row in rows):
        raise GroupedSplitError("source feature dataset version differs from policy")
    keys = [_row_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise GroupedSplitError("source contains duplicate participant/window rows")
    return policy, rows, dataset_hash, audit_hash

def build_phase_10_3_splits(
    *,
    feature_path: str | Path,
    dataset_audit_path: str | Path,
    policy_path: str | Path,
    manifest_path: str | Path,
    build_report_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict:

    feature_path = Path(feature_path)
    dataset_audit_path = Path(dataset_audit_path)
    policy_path = Path(policy_path)
    manifest_path = Path(manifest_path)
    build_report_path = Path(build_report_path)
    policy, rows, dataset_hash, audit_hash = _prepare_inputs(feature_path, dataset_audit_path, policy_path)
    schema = _load_json(Path(schema_path))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    external_sessions = set(policy["external_test"]["session_ids"])
    external_participants = set(policy["external_test"]["participant_ids"])
    fold_sessions = policy["development_validation"]["fold_sessions"]
    session_to_fold = {session: fold for fold, session in fold_sessions.items()}
    source_sessions = {row["session_id"] for row in rows}
    if source_sessions != external_sessions | set(session_to_fold):
        raise GroupedSplitError("frozen policy does not account for every source session")

    actual_external_participants = {row["participant_id"] for row in rows if row["session_id"] in external_sessions}
    development_participants = {row["participant_id"] for row in rows if row["session_id"] not in external_sessions}
    if actual_external_participants != external_participants:
        raise GroupedSplitError("external-test participants differ from frozen policy")
    if external_participants & development_participants:
        raise GroupedSplitError("external-test participant appears in development")

    assignments = []
    for row in rows:
        key = _row_key(row)
        external = row["session_id"] in external_sessions
        assignment = {
            "schema_version": 1,
            "split_policy_id": policy["policy_id"],
            "dataset_version": policy["dataset_version"],
            "assignment_id": _assignment_id(dataset_hash, key),
            "partition": "external_test" if external else "development",
            "validation_fold_id": None if external else session_to_fold[row["session_id"]],
            "session_id": row["session_id"],
            "participant_id": row["participant_id"],
            "episode_id": row["episode_id"],
            "window_id": row["feature_vector"]["window_id"],
            "source_annotation_id": row["source_annotation_id"],
        }
        errors = sorted(validator.iter_errors(assignment), key=lambda error: list(error.path))
        if errors:
            raise GroupedSplitError(f"split assignment schema failure: {errors[0].message}")
        assignments.append(assignment)
    assignments.sort(key=_assignment_key)
    _write_jsonl_atomic(assignments, manifest_path)

    development = [row for row in rows if row["session_id"] not in external_sessions]
    external = [row for row in rows if row["session_id"] in external_sessions]
    folds = []
    for fold_id, validation_session in sorted(fold_sessions.items()):
        validation = [row for row in development if row["session_id"] == validation_session]
        training = [row for row in development if row["session_id"] != validation_session]
        folds.append({
            "fold_id": fold_id,
            "validation_session_id": validation_session,
            "validation": _summary(validation),
            "training": _summary(training),
            "participant_overlap_count": len(
                {row["participant_id"] for row in validation}
                & {row["participant_id"] for row in training}
            ),
        })
    report = {
        "report_schema_version": 1,
        "phase": "10.3",
        "status": "built_pending_audit",
        "split_policy_id": policy["policy_id"],
        "split_policy_sha256": _sha256(policy_path),
        "source_dataset_sha256": dataset_hash,
        "source_audit_sha256": audit_hash,
        "manifest_sha256": _sha256(manifest_path),
        "row_count": len(assignments),
        "partition_summary": {
            "development": _summary(development),
            "external_test": _summary(external),
        },
        "development_cross_validation": {
            "method": "leave_one_session_out",
            "fold_count": len(folds),
            "folds": folds,
        },
        "participant_session_connectivity": {
            "component_count": len(_connected_components(rows)),
            "components": _connected_components(rows),
        },
        "external_test_access_rule": policy["external_test"]["access_rule"],
        "known_limitation": (
            "Development validation isolates sessions and episodes but recurring development participants may occur in training and validation."
        ),
    }
    _write_json_atomic(report, build_report_path)
    return report

def audit_phase_10_3_splits(
    *,
    feature_path: str | Path,
    dataset_audit_path: str | Path,
    policy_path: str | Path,
    manifest_path: str | Path,
    build_report_path: str | Path,
    audit_report_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> dict:

    feature_path = Path(feature_path)
    dataset_audit_path = Path(dataset_audit_path)
    policy_path = Path(policy_path)
    manifest_path = Path(manifest_path)
    build_report_path = Path(build_report_path)
    audit_report_path = Path(audit_report_path)
    policy, rows, dataset_hash, audit_hash = _prepare_inputs(
        feature_path, dataset_audit_path, policy_path
    )
    build_report = _load_json(build_report_path)
    if build_report.get("status") != "built_pending_audit":
        raise GroupedSplitError("Phase 10.3 build must be pending audit")
    if build_report.get("source_dataset_sha256") != dataset_hash:
        raise GroupedSplitError("split build report source hash mismatch")
    if build_report.get("source_audit_sha256") != audit_hash:
        raise GroupedSplitError("split build report audit hash mismatch")
    manifest_hash = _sha256(manifest_path)
    if build_report.get("manifest_sha256") != manifest_hash:
        raise GroupedSplitError("split manifest hash differs from build report")

    assignments = _load_jsonl(manifest_path)
    schema = _load_json(Path(schema_path))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    schema_errors = sum(
        1 for assignment in assignments for _ in validator.iter_errors(assignment)
    )
    if schema_errors:
        raise GroupedSplitError(f"split manifest has {schema_errors} schema failures")

    source_keys = {_row_key(row) for row in rows}
    assignment_keys = [_assignment_key(assignment) for assignment in assignments]
    duplicate_assignment_count = len(assignment_keys) - len(set(assignment_keys))
    missing_assignment_count = len(source_keys - set(assignment_keys))
    unexpected_assignment_count = len(set(assignment_keys) - source_keys)
    if duplicate_assignment_count or missing_assignment_count or unexpected_assignment_count:
        raise GroupedSplitError("split manifest does not account for source rows exactly once")

    by_key = {_row_key(row): row for row in rows}
    external_assignments = [
        assignment for assignment in assignments
        if assignment["partition"] == "external_test"
    ]
    development_assignments = [
        assignment for assignment in assignments
        if assignment["partition"] == "development"
    ]
    external_sessions = {item["session_id"] for item in external_assignments}
    development_sessions = {item["session_id"] for item in development_assignments}
    external_participants = {item["participant_id"] for item in external_assignments}
    development_participants = {item["participant_id"] for item in development_assignments}
    external_episodes = {item["episode_id"] for item in external_assignments}
    development_episodes = {item["episode_id"] for item in development_assignments}
    external_windows = {
        (item["session_id"], item["window_id"]) for item in external_assignments
    }
    development_windows = {
        (item["session_id"], item["window_id"]) for item in development_assignments
    }

    episode_folds = defaultdict(set)
    window_folds = defaultdict(set)
    session_folds = defaultdict(set)
    assignment_id_count = Counter()
    for assignment in assignments:
        assignment_id_count[assignment["assignment_id"]] += 1
        group = assignment["validation_fold_id"] or "external_test"
        episode_folds[assignment["episode_id"]].add(group)
        window_folds[(assignment["session_id"], assignment["window_id"])].add(group)
        session_folds[assignment["session_id"]].add(group)
        source = by_key[_assignment_key(assignment)]
        if assignment["episode_id"] != source["episode_id"]:
            raise GroupedSplitError("manifest episode differs from source feature row")
        if assignment["source_annotation_id"] != source["source_annotation_id"]:
            raise GroupedSplitError("manifest annotation differs from source feature row")

    fold_sessions = policy["development_validation"]["fold_sessions"]
    actual_fold_sessions = {
        fold_id: sorted({
            item["session_id"] for item in development_assignments
            if item["validation_fold_id"] == fold_id
        })
        for fold_id in sorted(fold_sessions)
    }
    expected_fold_sessions = {
        fold_id: [session_id] for fold_id, session_id in sorted(fold_sessions.items())
    }
    checks = {
        "source_rows_assigned_exactly_once": (
            duplicate_assignment_count == 0
            and missing_assignment_count == 0
            and unexpected_assignment_count == 0
        ),
        "assignment_ids_unique": all(count == 1 for count in assignment_id_count.values()),
        "schema_valid": schema_errors == 0,
        "external_sessions_match_policy": (
            external_sessions == set(policy["external_test"]["session_ids"])
        ),
        "external_participants_match_policy": (
            external_participants == set(policy["external_test"]["participant_ids"])
        ),
        "external_session_isolation": not (external_sessions & development_sessions),
        "external_participant_isolation": not (
            external_participants & development_participants
        ),
        "external_episode_isolation": not (external_episodes & development_episodes),
        "external_temporal_window_isolation": not (
            external_windows & development_windows
        ),
        "episodes_wholly_assigned": all(len(groups) == 1 for groups in episode_folds.values()),
        "temporal_windows_wholly_assigned": all(
            len(groups) == 1 for groups in window_folds.values()
        ),
        "sessions_wholly_assigned": all(len(groups) == 1 for groups in session_folds.values()),
        "development_fold_sessions_match_policy": (
            actual_fold_sessions == expected_fold_sessions
        ),
        "external_test_access_frozen": (
            policy["external_test"]["access_rule"] == "final_evaluation_only"
        ),
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise GroupedSplitError(f"Phase 10.3 leakage audit failed: {failed}")

    external_rows = [by_key[_assignment_key(item)] for item in external_assignments]
    development_rows = [by_key[_assignment_key(item)] for item in development_assignments]
    report = {
        "report_schema_version": 1,
        "phase": "10.3",
        "status": "pass",
        "split_policy_id": policy["policy_id"],
        "split_policy_sha256": _sha256(policy_path),
        "source_dataset_sha256": dataset_hash,
        "source_audit_sha256": audit_hash,
        "split_manifest_sha256": manifest_hash,
        "split_build_report_sha256": _sha256(build_report_path),
        "reconciliation": {
            "source_row_count": len(rows),
            "manifest_assignment_count": len(assignments),
            "development_row_count": len(development_assignments),
            "external_test_row_count": len(external_assignments),
            "duplicate_assignment_count": duplicate_assignment_count,
            "missing_assignment_count": missing_assignment_count,
            "unexpected_assignment_count": unexpected_assignment_count,
            "balances": len(rows) == len(assignments),
        },
        "leakage_checks": checks,
        "partition_summary": {
            "development": _summary(development_rows),
            "external_test": _summary(external_rows),
        },
        "development_fold_sessions": actual_fold_sessions,
        "disclosed_limitation": (
            "Leave-one-session-out development folds are session-independent but not participant-independent because participants recur across sessions."
        ),
    }
    _write_json_atomic(report, audit_report_path)
    return report
