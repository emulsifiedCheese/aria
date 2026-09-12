"""sesh-manifest validation and atomic local persistncce"""
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from datetime import datetime
from jsonschema import Draft202012Validator, FormatChecker
from aria.timebase import SGT, as_sgt, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "session_manifest.schema.json"
SESSION_ID_PATTERN = re.compile(
    r"^zone_a_[0-9]{8}T[0-9]{6}SGT_[a-z0-9]{4,16}$"
)
SCHEMA_VERSIONS = {
    "session_manifest": 8,
    "esp_packet": 1,
    "camera_track": 2,
    "feature_vector": 2,
    "annotation": 3,
    "prediction": 3,
    "incident": 5,
}

class ManifestValidationError(ValueError):
    """raised when session manifest fails validation"""

def _sgt_timestamp(value):
    return as_sgt(value)

def generate_session_id(now=None, suffix=None):
    now = now or sgt_now()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("session ID clock must be timezone-aware")
    timestamp = now.astimezone(SGT).strftime("%Y%m%dT%H%M%SSGT")
    suffix = suffix or secrets.token_hex(4)
    if not isinstance(suffix, str) or not re.fullmatch(r"[a-z0-9]{4,16}", suffix):
        raise ValueError("session ID suffix must contain 4-16 lowercase letters/digits")
    session_id = f"zone_a_{timestamp}_{suffix}"
    if SESSION_ID_PATTERN.fullmatch(session_id) is None:
        raise ValueError("generated session ID does not match the manifest schema")
    return session_id

def build_initial_manifest(config, preflight_report, now=None, session_id=None):
    from .preflight import (
        PreflightConfig,
        load_camera_config,
        load_session_mask,
        require_ready,
    )
    if not isinstance(config, PreflightConfig):
        raise TypeError("config must be a PreflightConfig")
    require_ready(preflight_report)
    now = now or sgt_now()
    created_at_sgt = _sgt_timestamp(now)
    session_id = session_id or generate_session_id(now=now)
    if SESSION_ID_PATTERN.fullmatch(session_id) is None:
        raise ValueError("session_id does not match the required Zone A format")

    camera = load_camera_config(config.camera_config_path)
    mask = load_session_mask(config, camera)
    if config.session_kind in {"pilot", "participant"}:
        from .collection_profile import collection_profile_metadata

        profile_metadata = collection_profile_metadata(config.collection_profile_path)
    else:
        profile_metadata = {
            "collection_profile_id": None,
            "collection_profile_sha256": None,
        }
    manifest = {
        "schema_version": 8,
        "session_id": session_id,
        "zone": "A",
        "study_scope": "consenting_counter_agents",
        "session_kind": config.session_kind,
        "status": "planned",
        "participant_ids": list(config.participant_ids),
        "participant_additions": [],
        "created_at_sgt": created_at_sgt,
        "started_at_sgt": None,
        "ended_at_sgt": None,
        "configuration": {
            "camera_id": camera["camera_id"],
            "capture_width_px": camera["width"],
            "capture_height_px": camera["height"],
            "capture_fps": int(camera["fps"]),
            "mask_config_version": mask.mask_config_version,
            "mask_verified": mask.verified,
            **profile_metadata,
            "esp_nodes": ["ESP-A1", "ESP-A2"],
            "schema_versions": dict(SCHEMA_VERSIONS),
        },
        "preflight": preflight_report.to_manifest(),
        "outputs": [],
        "incident_ids": [],
    }
    return validate_manifest(manifest)

def _load_validator(schema_path=DEFAULT_SCHEMA_PATH):
    with Path(schema_path).open(encoding="utf-8") as stream:
        schema = json.load(stream)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())

def validate_manifest(manifest, schema_path=DEFAULT_SCHEMA_PATH):
    validator = _load_validator(schema_path)
    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path)
        prefix = f" at {location}" if location else ""
        raise ManifestValidationError(f"Session manifest validation failed{prefix}: {error.message}")
    return manifest

def write_manifest_atomic(manifest, output_path, schema_path=DEFAULT_SCHEMA_PATH):
    validate_manifest(manifest, schema_path=schema_path)
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
            json.dump(manifest, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    return output_path
