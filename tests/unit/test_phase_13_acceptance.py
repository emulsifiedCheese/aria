from hashlib import sha256
import json
import pytest
from aria.acceptance.phase13 import (
    PROJECT_ROOT,
    Phase13AcceptanceError,
    assess_phase_13,
    evidence_template,
)

def _complete_evidence():
    evidence = evidence_template()
    for scenario in evidence["scenarios"].values():
        scenario.update(passed=True, trace="outputs/acceptance/phase_13/run.log")
    evidence["stability"].update(
        duration_seconds=5400,
        no_sustained_degradation=True,
        no_unexplained_gap=True,
        no_stale_state_reuse=True,
        trace="outputs/acceptance/phase_13/stability.json",
    )
    evidence["stability"]["metrics"] = {key: 1.0 for key in evidence["stability"]["metrics"]}
    config = json.loads((PROJECT_ROOT / "config/phase_13_acceptance.json").read_text())
    evidence["release"].update(
        code_revision="0123456789abcdef",
        clean_environment_verified=True,
        secret_scan_passed=True,
        identity_and_media_scan_passed=True,
        trace="outputs/acceptance/phase_13/release.md",
    )
    evidence["release"]["artifact_sha256"] = {
        relative: sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in config["release"]["required_artifacts"]
    }
    return evidence

def test_blank_template_is_fail_closed():
    result = assess_phase_13(evidence_template())
    assert result["complete"] is False
    assert all(part["complete"] is False for part in result["parts"].values())

def test_complete_traceable_evidence_passes():
    assert assess_phase_13(_complete_evidence())["complete"] is True

def _accepted_network_limitation(evidence):
    evidence["stability"]["no_sustained_degradation"] = False
    evidence["stability"]["accepted_degradation_limitation"] = {
        "accepted": True,
        "limitation_id": "phase2.4-public-network-delivery",
        "operator_approved": True,
        "observed_degradation_retained": True,
        "trace": "docs/testing/results/network-limitation.md",
    }
    return evidence

def test_explicit_network_limitation_can_satisfy_only_degradation_requirement():
    result = assess_phase_13(_accepted_network_limitation(_complete_evidence()))
    checks = result["parts"]["13.2"]["checks"]
    assert checks["no_sustained_degradation"] is False
    assert checks["accepted_network_limitation"] is True
    assert checks["degradation_requirement_satisfied"] is True
    assert result["parts"]["13.2"]["complete"] is True
    assert result["complete"] is False
    assert result["operationally_complete_with_accepted_limitation"] is True
    assert result["disposition"] == "partial_accepted_limitation"

@pytest.mark.parametrize("change", [
    ("accepted", False),
    ("limitation_id", "unapproved-limitation"),
    ("operator_approved", False),
    ("observed_degradation_retained", False),
    ("trace", ""),
])
def test_network_limitation_fails_closed_without_each_required_attestation(change):
    evidence = _accepted_network_limitation(_complete_evidence())
    evidence["stability"]["accepted_degradation_limitation"][change[0]] = change[1]
    result = assess_phase_13(evidence)
    assert result["parts"]["13.2"]["checks"]["accepted_network_limitation"] is False
    assert result["parts"]["13.2"]["complete"] is False

@pytest.mark.parametrize("failed", ["duration", "gap", "stale", "metrics", "main_trace"])
def test_network_limitation_does_not_waive_other_stability_requirements(failed):
    evidence = _accepted_network_limitation(_complete_evidence())
    if failed == "duration":
        evidence["stability"]["duration_seconds"] = 5399
    elif failed == "gap":
        evidence["stability"]["no_unexplained_gap"] = False
    elif failed == "stale":
        evidence["stability"]["no_stale_state_reuse"] = False
    elif failed == "metrics":
        evidence["stability"]["metrics"]["camera_capture_fps"] = None
    else:
        evidence["stability"]["trace"] = ""
    assert assess_phase_13(evidence)["parts"]["13.2"]["complete"] is False

def test_missing_trace_short_run_and_changed_hash_cannot_pass():
    evidence = _complete_evidence()
    evidence["scenarios"]["privacy_failure_safe_pause"]["trace"] = ""
    evidence["stability"]["duration_seconds"] = 5399
    evidence["release"]["artifact_sha256"]["schemas/prediction.schema.json"] = "0" * 64
    result = assess_phase_13(evidence)
    assert all(part["complete"] is False for part in result["parts"].values())

@pytest.mark.parametrize("key", ["participant_id", "raw_video", "feature_vector"])
def test_forbidden_evidence_keys_are_rejected(key):
    evidence = _complete_evidence()
    evidence[key] = "prohibited"
    with pytest.raises(Phase13AcceptanceError, match="forbidden evidence keys"):
        assess_phase_13(evidence)
