from __future__ import annotations
import hashlib
import json
from pathlib import Path

INVENTORY_SCHEMA_VERSION = 1
REQUIRED_OUTPUT_KINDS = (
    "annotations",
    "camera_features",
    "telemetry_features",
)

class InventoryError(ValueError):
    """raised when source-session inven is invalid"""

def _load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise InventoryError(f"Cannot read manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise InventoryError(f"Manifest {path} must contain a JSON object")
    return value

def _safe_source_path(data_raw_dir: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise InventoryError("output relative_path must be a non-empty string")
    root = data_raw_dir.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise InventoryError(f"output path escapes data/raw: {relative_path}")
    return candidate

def _count_jsonl_records(path: Path) -> int | None:
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return sum(1 for line in stream if line.strip())

def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _output_inventory(data_raw_dir: Path, output: dict) -> dict:
    relative_path = output.get("relative_path")
    path = _safe_source_path(data_raw_dir, relative_path)
    observed = output.get("observed_record_count")
    written = output.get("written_record_count")
    excluded = output.get("excluded_record_count")
    arithmetic_matches = (
        all(isinstance(value, int) and not isinstance(value, bool)
            for value in (observed, written, excluded))
        and observed == written + excluded
    )
    physical_count = _count_jsonl_records(path)
    return {
        "kind": output.get("kind"),
        "relative_path": relative_path,
        "exists": path.exists(),
        "is_file": path.is_file(),
        "byte_size": path.stat().st_size if path.is_file() else None,
        "sha256": _sha256(path),
        "physical_record_count": physical_count,
        "declared": {
            "observed_record_count": observed,
            "written_record_count": written,
            "excluded_record_count": excluded,
            "gap_count": output.get("gap_count"),
            "longest_gap_seconds": output.get("longest_gap_seconds"),
        },
        "checks": {
            "observed_equals_written_plus_excluded": arithmetic_matches,
            "physical_count_equals_written": (
                physical_count == written
                if physical_count is not None and isinstance(written, int)
                else False
            ),
        },
        "review_status": "pending_user_validation",
    }

def _account_for_incident_log(data_raw_dir: Path, item: dict, incident_ids: list) -> None:

    if item["kind"] != "incident_log":
        return
    incident_dir = _safe_source_path(data_raw_dir, item["relative_path"])
    incident_paths = [incident_dir / f"{incident_id}.json" for incident_id in incident_ids]
    existing = [path for path in incident_paths if path.is_file()]
    item["exists"] = incident_dir.is_dir() and len(existing) == len(incident_paths)
    item["is_file"] = False
    item["byte_size"] = sum(path.stat().st_size for path in existing)
    item["physical_record_count"] = len(existing)
    combined = hashlib.sha256()
    for path in existing:
        combined.update(path.name.encode("utf-8"))
        combined.update(bytes.fromhex(_sha256(path)))
    item["sha256"] = combined.hexdigest() if existing else None
    written = item["declared"]["written_record_count"]
    item["checks"]["physical_count_equals_written"] = (isinstance(written, int) and len(existing) == written)

def _selection_reason(manifest: dict, output_by_kind: dict[str, dict]) -> str | None:
    kind = manifest.get("session_kind")
    if kind != "participant":
        return f"session_kind_{kind or 'missing'}"
    status = manifest.get("status")
    if status != "completed":
        return f"status_{status or 'missing'}"
    missing = [kind for kind in REQUIRED_OUTPUT_KINDS if kind not in output_by_kind]
    if missing:
        return "missing_required_outputs:" + ",".join(missing)
    annotations = output_by_kind["annotations"]
    if annotations["physical_record_count"] in (None, 0):
        return "no_annotations"
    empty_modalities = [
        kind
        for kind in ("camera_features", "telemetry_features")
        if output_by_kind[kind]["physical_record_count"] in (None, 0)
    ]
    if empty_modalities:
        return "empty_required_outputs:" + ",".join(empty_modalities)
    return None

def scan_source_sessions(data_raw_dir: str | Path) -> dict:

    data_raw_dir = Path(data_raw_dir)
    manifest_dir = data_raw_dir / "manifests"
    included = []
    excluded = []

    for manifest_path in sorted(manifest_dir.glob("*.json")):
        manifest = _load_json(manifest_path)
        session_id = manifest.get("session_id")
        outputs = manifest.get("outputs")
        if not isinstance(outputs, list):
            outputs = []
        output_inventory = [_output_inventory(data_raw_dir, item) for item in outputs]
        incident_ids = sorted(manifest.get("incident_ids") or [])
        for item in output_inventory:
            _account_for_incident_log(data_raw_dir, item, incident_ids)
        output_kinds = [item["kind"] for item in output_inventory]
        duplicates = sorted({kind for kind in output_kinds if output_kinds.count(kind) > 1})
        if duplicates:
            raise InventoryError(f"Manifest {manifest_path} repeats output kinds: {', '.join(duplicates)}")
        output_by_kind = {item["kind"]: item for item in output_inventory if isinstance(item["kind"], str)}
        reason = _selection_reason(manifest, output_by_kind)
        base = {
            "session_id": session_id,
            "manifest_relative_path": manifest_path.relative_to(data_raw_dir).as_posix(),
            "manifest_byte_size": manifest_path.stat().st_size,
            "manifest_sha256": _sha256(manifest_path),
            "manifest_schema_version": manifest.get("schema_version"),
            "session_kind": manifest.get("session_kind"),
            "status": manifest.get("status"),
        }
        if reason is not None:
            excluded.append({**base, "exclusion_reason": reason})
            continue

        configuration = manifest.get("configuration") or {}
        included.append({
            **base,
            "review_status": "pending_user_validation",
            "participant_count": len(manifest.get("participant_ids") or []),
            "incident_ids": incident_ids,
            "configuration": {
                "collection_profile_id": configuration.get("collection_profile_id"),
                "collection_profile_sha256": configuration.get(
                    "collection_profile_sha256"
                ),
                "mask_config_version": configuration.get("mask_config_version"),
                "mask_verified": configuration.get("mask_verified"),
                "schema_versions": configuration.get("schema_versions"),
            },
            "outputs": output_inventory,
        })

    return {
        "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
        "phase": "10.1",
        "review_status": "pending_user_validation",
        "selection_policy": {
            "session_kind": "participant",
            "status": "completed",
            "required_nonempty_outputs": list(REQUIRED_OUTPUT_KINDS),
            "excluded_kinds": ["pilot", "non_research_dry_run"],
        },
        "summary": {
            "manifest_count": len(included) + len(excluded),
            "included_session_count": len(included),
            "excluded_session_count": len(excluded),
        },
        "included_sessions": included,
        "excluded_sessions": excluded,
    }

def write_inventory(inventory: dict, output_path: str | Path) -> Path:

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    output_path.write_text(rendered, encoding="utf-8")
    return output_path

def apply_approval_decisions(inventory: dict, approval_path: str | Path) -> dict:

    approval_path = Path(approval_path)
    approvals = _load_json(approval_path)
    if approvals.get("phase") != "10.1" or approvals.get("schema_version") != 1:
        raise InventoryError("approval record must be Phase 10.1 schema version 1")
    decisions = approvals.get("decisions")
    if not isinstance(decisions, list):
        raise InventoryError("approval record decisions must be a list")
    decision_by_session = {}
    for decision in decisions:
        session_id = decision.get("session_id")
        if session_id in decision_by_session:
            raise InventoryError(f"duplicate approval decision for {session_id}")
        if decision.get("decision") != "approved":
            raise InventoryError(f"unsupported approval decision for {session_id}")
        decision_by_session[session_id] = decision

    included_ids = {item["session_id"] for item in inventory["included_sessions"]}
    if set(decision_by_session) != included_ids:
        missing = sorted(included_ids - set(decision_by_session))
        extra = sorted(set(decision_by_session) - included_ids)
        raise InventoryError(f"approval decisions do not match included sessions; missing={missing}, extra={extra}")

    for session in inventory["included_sessions"]:
        decision = decision_by_session[session["session_id"]]
        session["review_status"] = "approved"
        session["approval"] = {
            "decision": "approved",
            "decision_date_sgt": approvals.get("decision_date_sgt"),
            "decision_authority": approvals.get("decision_authority"),
            "conditions": decision.get("conditions", []),
        }
        for output in session["outputs"]:
            output["review_status"] = "approved"
    inventory["review_status"] = "approved"
    inventory["approval_record_path"] = approval_path.as_posix()
    return inventory
