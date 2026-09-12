"""fail-closed Phase 13 final acceptance evidence assessment"""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from aria.timebase import SGT, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "phase_13_acceptance.json"
EXPECTED_CONFIG_ID = "zone-a-phase13-final-acceptance-v2"
EXPECTED_CONFIG_SHA256 = "f4f91d78384c7cc8c5f911c1ae6c18c504f30c356aca0fe9e6ae71d9f0bdab38"
FORBIDDEN_EVIDENCE_KEYS = {
    "participant_id", "participant_name", "session_id", "raw_audio",
    "raw_video", "masked_video", "feature_vector",
}

class Phase13AcceptanceError(RuntimeError):
    """raised when Phase 13 evidence violates its privacy or shape contract"""

def _load_object(path, label):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Phase13AcceptanceError(f"cannot load {label}") from error
    if not isinstance(value, dict):
        raise Phase13AcceptanceError(f"{label} must be a JSON object")
    return value

def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)

def _timestamp(value):
    value = value or sgt_now()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise Phase13AcceptanceError("generated timestamp must be timezone-aware")
    return value.astimezone(SGT).isoformat(timespec="milliseconds")

def _artifact_hash(path):
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _load_contract(config_path):
    path = Path(config_path).resolve()
    config = _load_object(path, "Phase 13 contract")
    if path == DEFAULT_CONFIG_PATH.resolve() and _artifact_hash(path) != EXPECTED_CONFIG_SHA256:
        raise Phase13AcceptanceError("frozen Phase 13 contract hash mismatch")
    if config.get("config_id") != EXPECTED_CONFIG_ID:
        raise Phase13AcceptanceError("unsupported Phase 13 contract")
    return config

def evidence_template(config_path=DEFAULT_CONFIG_PATH):
    """return a non-participant template; blank values cannot accidentally pass"""
    config = _load_contract(config_path)
    return {
        "evidence_version": 1,
        "input_scope": "non_research",
        "participant_data_used": False,
        "external_test_accessed": False,
        "scenarios": {
            name: {"passed": False, "trace": ""}
            for name in config["acceptance"]["required_scenarios"]
        },
        "stability": {
            "duration_seconds": 0,
            "metrics": {
                name: None for name in config["stability"]["required_metrics"]
            },
            "no_sustained_degradation": False,
            "no_unexplained_gap": False,
            "no_stale_state_reuse": False,
            "accepted_degradation_limitation": {
                "accepted": False,
                "limitation_id": "",
                "operator_approved": False,
                "observed_degradation_retained": False,
                "trace": "",
            },
            "trace": "",
        },
        "release": {
            "code_revision": "",
            "artifact_sha256": {},
            "clean_environment_verified": False,
            "secret_scan_passed": False,
            "identity_and_media_scan_passed": False,
            "trace": "",
        },
    }

def assess_phase_13(evidence, config_path=DEFAULT_CONFIG_PATH, *, now=None):
    """assess evidence without converting missing or failed checks into a pass"""
    if not isinstance(evidence, dict):
        raise Phase13AcceptanceError("Phase 13 evidence must be a JSON object")
    forbidden = set(_walk_keys(evidence)) & FORBIDDEN_EVIDENCE_KEYS
    if forbidden:
        raise Phase13AcceptanceError("forbidden evidence keys: " + ", ".join(sorted(forbidden)))
    config = _load_contract(config_path)
    if evidence.get("input_scope") not in config["scope"]["accepted_input_scopes"]:
        raise Phase13AcceptanceError("input scope must be synthetic or non_research")
    if evidence.get("participant_data_used") is not False:
        raise Phase13AcceptanceError("participant evidence is prohibited after collection closure")
    if evidence.get("external_test_accessed") is not False:
        raise Phase13AcceptanceError("Phase 13 must not access the frozen external test")
    required = config["acceptance"]["required_scenarios"]
    scenarios = evidence.get("scenarios")
    if not isinstance(scenarios, dict) or set(scenarios) != set(required):
        raise Phase13AcceptanceError("scenario evidence must contain exactly the required scenarios")
    scenario_checks = {}
    for name in required:
        item = scenarios[name]
        if not isinstance(item, dict):
            raise Phase13AcceptanceError(f"scenario {name} must be an object")
        scenario_checks[name] = item.get("passed") is True and bool(str(item.get("trace", "")).strip())
    stability = evidence.get("stability", {})
    metrics = stability.get("metrics", {}) if isinstance(stability, dict) else {}
    metric_names = config["stability"]["required_metrics"]
    duration = stability.get("duration_seconds") if isinstance(stability, dict) else None
    stability_checks = {
        "approved_duration": isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and duration >= config["stability"]["minimum_duration_seconds"],
        "all_metrics_recorded": isinstance(metrics, dict)
        and set(metrics) == set(metric_names)
        and all(isinstance(metrics[name], (int, float)) and not isinstance(metrics[name], bool) for name in metric_names),
        "no_sustained_degradation": stability.get("no_sustained_degradation") is True,
        "no_unexplained_gap": stability.get("no_unexplained_gap") is True,
        "no_stale_state_reuse": stability.get("no_stale_state_reuse") is True,
        "trace_recorded": bool(str(stability.get("trace", "")).strip()),
    }
    limitation = stability.get("accepted_degradation_limitation", {})
    limitation_contract = config["stability"].get("accepted_degradation_limitation", {})
    accepted_limitation = (
        isinstance(limitation, dict)
        and limitation_contract.get("allowed") is True
        and limitation.get("accepted") is True
        and limitation.get("limitation_id") == limitation_contract.get("limitation_id")
        and limitation.get("operator_approved") is True
        and limitation.get("observed_degradation_retained") is True
        and bool(str(limitation.get("trace", "")).strip())
        and stability.get("no_sustained_degradation") is False
    )
    stability_checks["accepted_network_limitation"] = accepted_limitation
    stability_checks["degradation_requirement_satisfied"] = (stability_checks["no_sustained_degradation"] or accepted_limitation)
    release = evidence.get("release", {})
    hashes = release.get("artifact_sha256", {}) if isinstance(release, dict) else {}
    artifact_checks = {}
    for relative in config["release"]["required_artifacts"]:
        path = PROJECT_ROOT / relative
        artifact_checks[relative] = (path.is_file() and isinstance(hashes, dict)and hashes.get(relative) == _artifact_hash(path))
    release_checks = {
        "code_revision_recorded": bool(str(release.get("code_revision", "")).strip()),
        "required_artifacts_frozen": all(artifact_checks.values()),
        "clean_environment_verified": release.get("clean_environment_verified") is True,
        "secret_scan_passed": release.get("secret_scan_passed") is True,
        "identity_and_media_scan_passed": release.get("identity_and_media_scan_passed") is True,
        "trace_recorded": bool(str(release.get("trace", "")).strip()),
    }
    parts = {
        "13.1": {"complete": all(scenario_checks.values()), "checks": scenario_checks},
        "13.2": {"complete": all(stability_checks[name] for name in (
            "approved_duration", "all_metrics_recorded",
            "degradation_requirement_satisfied", "no_unexplained_gap",
            "no_stale_state_reuse", "trace_recorded",
        )), "checks": stability_checks},
        "13.3": {"complete": all(release_checks.values()), "checks": release_checks,
                 "artifact_checks": artifact_checks},
    }
    all_parts_complete = all(part["complete"] for part in parts.values())
    operationally_complete_with_limitation = all_parts_complete and accepted_limitation
    return {
        "acceptance_id": config["config_id"],
        "generated_at_sgt": _timestamp(now),
        "input_scope": evidence["input_scope"],
        "participant_data_used": False,
        "external_test_accessed": False,
        "complete": all_parts_complete and not accepted_limitation,
        "operationally_complete_with_accepted_limitation": operationally_complete_with_limitation,
        "disposition": (
            "partial_accepted_limitation"
            if operationally_complete_with_limitation
            else "complete" if all_parts_complete else "incomplete"
        ),
        "parts": parts,
    }
