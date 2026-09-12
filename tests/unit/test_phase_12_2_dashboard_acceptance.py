from pathlib import Path
import pytest
from aria.dashboard.acceptance import DashboardAcceptanceError, run_acceptance
from scripts.accept_phase_12_2 import main

PNG = b"\x89PNG\r\n\x1a\n" + (b"synthetic-dashboard-evidence" * 500)

def _screenshots(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    for name in ("ready.png", "degraded.png", "blocked.png"):
        (tmp_path / name).write_bytes(PNG)
    return tmp_path

def test_acceptance_covers_frozen_scenarios_privacy_and_screenshots(tmp_path):
    report = run_acceptance(_screenshots(tmp_path))

    assert report["passed"] is True
    assert report["scenario_names_match_contract"] is True
    assert len(report["scenarios"]) == 14
    assert all(item["passed"] for item in report["scenarios"].values())
    assert all(item["passed"] for item in report["privacy"].values())
    assert all(item["passed"] for item in report["screenshots"].values())
    assert report["participant_data_used"] is False
    assert report["external_test_accessed"] is False
    assert report["firebase_used"] is False

def test_acceptance_fails_when_screenshot_evidence_is_missing(tmp_path):
    with pytest.raises(DashboardAcceptanceError, match="acceptance failed"):
        run_acceptance(tmp_path)

def test_cli_writes_deterministic_local_json_evidence(tmp_path):
    screenshots = _screenshots(tmp_path / "screens")
    output = tmp_path / "acceptance.json"

    report = main(["--screenshot-dir", str(screenshots), "--output", str(output)])

    assert report["passed"] is True
    assert output.is_file()
    assert '"participant_data_used": false' in output.read_text(encoding="utf-8")
    assert not list(Path(tmp_path).rglob("*.tmp"))