import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from aria.timebase import SGT
from aria.collection.manifest import (
    ManifestValidationError,
    build_initial_manifest,
    generate_session_id,
    write_manifest_atomic,
)
from aria.collection.lifecycle import SessionLifecycle, SessionLifecycleError
from aria.collection.preflight import (
    PreflightConfig,
    PreflightError,
    PreflightReport,
    PauseStopController,
    require_ready,
)
from aria.collection.run_session import (
    PreparedSession,
    WriterStartError,
    main,
    prepare_session,
    start_prepared_session,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 7, 31, 21, 45, tzinfo=SGT)

def passing_report():
    return PreflightReport(
        checked_at_sgt="2026-07-31T21:45:00+08:00",
        checks={
            "consent_and_acknowledgement_confirmed": True,
            "camera_identity_and_mode_confirmed": True,
            "privacy_mask_verified": True,
            "audio_capture_disabled": True,
            "esp_a1_fresh": True,
            "esp_a2_fresh": True,
            "storage_ready": True,
        },
    )

def running_manifest(report):
    return {
        "schema_version": 8,
        "session_id": "zone_a_20260731T214500SGT_dryrun01",
        "zone": "A",
        "study_scope": "consenting_counter_agents",
        "session_kind": "non_research_dry_run",
        "status": "running",
        "participant_ids": [],
        "participant_additions": [],
        "created_at_sgt": "2026-07-31T21:44:00+08:00",
        "started_at_sgt": "2026-07-31T21:45:00+08:00",
        "ended_at_sgt": None,
        "configuration": {
            "camera_id": "camera_a",
            "capture_width_px": 1920,
            "capture_height_px": 1080,
            "capture_fps": 30,
            "mask_config_version": "batamfast-v1",
            "mask_verified": True,
            "collection_profile_id": None,
            "collection_profile_sha256": None,
            "esp_nodes": ["ESP-A1", "ESP-A2"],
            "schema_versions": {
                "session_manifest": 8,
                "esp_packet": 1,
                "camera_track": 2,
                "feature_vector": 2,
                "annotation": 3,
                "prediction": 3,
                "incident": 5,
            },
        },
        "preflight": report.to_manifest(),
        "outputs": [],
        "incident_ids": [],
    }

def test_lifecycle_adds_consented_participant_and_audit_entry(tmp_path):
    report = passing_report()
    manifest = running_manifest(report)
    manifest["session_kind"] = "participant"
    manifest["participant_ids"] = ["P0001"]
    manifest["configuration"]["collection_profile_id"] = "zone-a-collection-v6"
    manifest["configuration"]["collection_profile_sha256"] = "a" * 64
    manifest_path = tmp_path / "manifests" / f'{manifest["session_id"]}.json'
    write_manifest_atomic(manifest, manifest_path)
    controller = PauseStopController()
    lifecycle = SessionLifecycle(
        SimpleNamespace(
            session_id=manifest["session_id"],
            manifest_path=manifest_path,
        ),
        (),
        controller,
        clock=lambda: NOW,
    )

    addition = lifecycle.add_participant(
        participant_id="P0002",
        consent_confirmed=True,
        annotator_id="A001",
    )

    persisted = json.loads(manifest_path.read_text())
    assert persisted["participant_ids"] == ["P0001", "P0002"]
    assert persisted["participant_additions"] == [addition]
    assert addition == {
        "participant_id": "P0002",
        "added_at_sgt": "2026-07-31T21:45:00+08:00",
        "consent_confirmed": True,
        "added_by_annotator_id": "A001",
    }

    with pytest.raises(SessionLifecycleError, match="already"):
        lifecycle.add_participant(
            participant_id="P0002",
            consent_confirmed=True,
            annotator_id="A001",
        )

def preflight_config(tmp_path):
    return PreflightConfig(
        session_kind="non_research_dry_run",
        dji_recording_disabled=True,
        camera_config_path=PROJECT_ROOT / "config" / "cameras.batamfast.yaml",
        mask_config_path=PROJECT_ROOT / "config" / "masks.batamfast.yaml",
        mediamtx_config_path=PROJECT_ROOT / "config" / "mediamtx.local.yaml",
        output_directory=tmp_path,
        minimum_free_bytes=0,
        approved_output_roots=(tmp_path,),
    )

def test_preflight_report_requires_every_known_check():
    checks = dict(passing_report().checks)
    del checks["storage_ready"]
    with pytest.raises(ValueError, match="missing checks: storage_ready"):
        PreflightReport("2026-07-31T21:45:00+08:00", checks)

def test_preflight_failure_is_fail_closed():
    checks = dict(passing_report().checks)
    checks["privacy_mask_verified"] = False
    report = PreflightReport("2026-07-31T21:45:00+08:00", checks)
    with pytest.raises(PreflightError, match="privacy_mask_verified"):
        require_ready(report)

def test_invalid_manifest_is_not_written(tmp_path):
    report = passing_report()
    manifest = deepcopy(running_manifest(report))
    manifest["configuration"]["camera_id"] = "camera_b"
    output_path = tmp_path / "session_manifest.json"

    with pytest.raises(ManifestValidationError):
        write_manifest_atomic(manifest, output_path)

    assert not output_path.exists()

def test_cli_supports_validation_only_without_starting_writers(tmp_path, capsys):
    report = passing_report()
    manifest_path = tmp_path / "session_manifest.json"
    write_manifest_atomic(running_manifest(report), manifest_path)

    assert main(
        ["--manifest", str(manifest_path), "--validate-manifest-only"]
    ) == 0
    assert "no writers were started" in capsys.readouterr().out

def test_cli_runs_preflight_only_and_remains_fail_closed(monkeypatch, capsys):
    monkeypatch.setattr("aria.collection.run_session.run_preflight",lambda config: passing_report(),)
    result = main(
        [
            "--preflight-only",
            "--session-kind",
            "non_research_dry_run",
            "--dji-recording-disabled",
        ]
    )
    assert result == 0
    output = capsys.readouterr().out
    assert "PASS privacy_mask_verified" in output
    assert "No writers were started" in output

def test_cli_returns_failure_when_preflight_does_not_pass(monkeypatch, capsys):
    report = passing_report()
    checks = dict(report.checks)
    checks["audio_capture_disabled"] = False
    failing = PreflightReport(report.checked_at_sgt, checks)
    monkeypatch.setattr("aria.collection.run_session.run_preflight",lambda config: failing,)
    result = main(
        [
            "--preflight-only",
            "--session-kind",
            "non_research_dry_run",
        ]
    )
    assert result == 1
    assert "FAIL audio_capture_disabled" in capsys.readouterr().out

def test_session_id_is_sgt_based_and_non_identifying():
    assert generate_session_id(NOW, suffix="abcd1234") == ("zone_a_20260731T214500SGT_abcd1234")
    with pytest.raises(ValueError, match="timezone-aware"):
        generate_session_id(datetime(2026, 7, 31, 13, 45), suffix="abcd1234")
    with pytest.raises(ValueError, match="lowercase"):
        generate_session_id(NOW, suffix="ParticipantName")

def test_initial_manifest_is_planned_and_locks_configuration(tmp_path):
    manifest = build_initial_manifest(
        preflight_config(tmp_path),
        passing_report(),
        now=NOW,
        session_id="zone_a_20260731T214500SGT_dryrun01",
    )
    assert manifest["status"] == "planned"
    assert manifest["started_at_sgt"] is None
    assert manifest["participant_ids"] == []
    assert manifest["configuration"] == {
        "camera_id": "camera_a",
        "capture_width_px": 1920,
        "capture_height_px": 1080,
        "capture_fps": 30,
        "mask_config_version": "batamfast-v2",
        "mask_verified": True,
        "collection_profile_id": None,
        "collection_profile_sha256": None,
        "esp_nodes": ["ESP-A1", "ESP-A2"],
        "schema_versions": {
            "session_manifest": 8,
            "esp_packet": 1,
            "camera_track": 2,
            "feature_vector": 2,
            "annotation": 3,
            "prediction": 3,
            "incident": 5,
        },
    }

def prepare_with_fakes(tmp_path, report=None):
    report = report or passing_report()
    return prepare_session(
        preflight_config(tmp_path),
        preflight_runner=lambda config: report,
        clock=lambda: NOW,
        session_id_factory=lambda now: "zone_a_20260731T214500SGT_dryrun01",
    )

def test_prepare_session_writes_initial_manifest_atomically(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    assert prepared.manifest_path == (
        tmp_path
        / "manifests"
        / "zone_a_20260731T214500SGT_dryrun01.json"
    )
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "planned"
    assert list(prepared.manifest_path.parent.glob("*.tmp")) == []

def test_failed_preflight_creates_no_manifest(tmp_path):
    passing = passing_report()
    checks = dict(passing.checks)
    checks["storage_ready"] = False
    failing = PreflightReport(passing.checked_at_sgt, checks)
    with pytest.raises(PreflightError, match="storage_ready"):
        prepare_with_fakes(tmp_path, report=failing)
    assert not (tmp_path / "manifests").exists()

class FakeWriter:
    def __init__(self, kind="telemetry_features", relative_path="telemetry.jsonl"):
        self.closed = False
        self.paused = False
        self.kind = kind
        self.relative_path = relative_path

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def close(self):
        self.closed = True

    def exclude_windows(self, window_ids):
        self.excluded_window_ids = set(window_ids)

    def verify_excluded_windows(self, window_ids):
        return set(window_ids).issubset(getattr(self, "excluded_window_ids", set()))

    def session_summary(self):
        return {
            "kind": self.kind,
            "relative_path": self.relative_path,
            "observed_record_count": 120,
            "written_record_count": 118,
            "excluded_record_count": 2,
            "gap_count": 1,
            "longest_gap_seconds": 0.4,
        }

def test_writer_factory_runs_only_after_running_manifest_exists(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    observed = []
    writer = FakeWriter()

    def factory(context):
        stored = json.loads(context.manifest_path.read_text())
        observed.append((context.manifest_path.exists(), stored["status"]))
        return writer

    started = start_prepared_session(
        prepared,
        [factory],
        clock=lambda: NOW,
    )
    assert observed == [(True, "running")]
    assert started.writer_handles == (writer,)
    assert json.loads(prepared.manifest_path.read_text())["status"] == "running"

def test_writer_gate_requires_factory_and_keeps_manifest_planned(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    with pytest.raises(WriterStartError, match="At least one"):
        start_prepared_session(prepared, [], clock=lambda: NOW)
    assert json.loads(prepared.manifest_path.read_text())["status"] == "planned"

def test_unready_pause_controller_keeps_manifest_planned(tmp_path):
    prepared = prepare_with_fakes(tmp_path)

    class UnreadyController:
        ready = False

    with pytest.raises(WriterStartError, match="not ready"):
        start_prepared_session(
            prepared,
            [lambda context: FakeWriter()],
            clock=lambda: NOW,
            pause_stop_factory=UnreadyController,
        )
    assert json.loads(prepared.manifest_path.read_text())["status"] == "planned"

def test_incomplete_pause_controller_keeps_manifest_planned(tmp_path):
    prepared = prepare_with_fakes(tmp_path)

    class IncompleteController:
        ready = True

        def stop(self):
            pass

    with pytest.raises(WriterStartError, match="must provide callable pause and resume"):
        start_prepared_session(
            prepared,
            [lambda context: FakeWriter()],
            clock=lambda: NOW,
            pause_stop_factory=IncompleteController,
        )
    assert json.loads(prepared.manifest_path.read_text())["status"] == "planned"

def test_tampered_manifest_blocks_every_writer(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    manifest = json.loads(prepared.manifest_path.read_text())
    manifest["configuration"]["camera_id"] = "camera_b"
    prepared.manifest_path.write_text(json.dumps(manifest))
    called = False

    def factory(context):
        nonlocal called
        called = True

    with pytest.raises(WriterStartError, match="invalid"):
        start_prepared_session(prepared, [factory], clock=lambda: NOW)
    assert called is False

def test_partial_writer_start_is_closed_and_manifest_aborted(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    first_writer = FakeWriter()
    contexts = []

    def fail(context):
        contexts.append(context)
        raise RuntimeError("writer unavailable")

    with pytest.raises(WriterStartError, match="session was aborted"):
        start_prepared_session(
            prepared,
            [lambda context: first_writer, fail],
            clock=lambda: NOW,
        )
    assert first_writer.closed is True
    assert contexts[0].pause_stop_controller.stopped is True
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "aborted"
    assert stored["ended_at_sgt"] == "2026-07-31T21:45:00+08:00"

def test_null_writer_handle_aborts_startup(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    contexts = []

    def return_none(context):
        contexts.append(context)
        return None

    with pytest.raises(WriterStartError, match="session was aborted"):
        start_prepared_session(
            prepared,
            [return_none],
            clock=lambda: NOW,
        )

    assert contexts[0].pause_stop_controller.stopped is True
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "aborted"
    assert stored["ended_at_sgt"] == "2026-07-31T21:45:00+08:00"

def test_incomplete_writer_handle_is_closed_and_aborts_startup(tmp_path):
    class WriterWithoutSummary:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    prepared = prepare_with_fakes(tmp_path)
    writer = WriterWithoutSummary()
    contexts = []

    def return_incomplete(context):
        contexts.append(context)
        return writer

    with pytest.raises(WriterStartError, match="session was aborted"):
        start_prepared_session(
            prepared,
            [return_incomplete],
            clock=lambda: NOW,
        )

    assert writer.closed is True
    assert contexts[0].pause_stop_controller.stopped is True
    assert json.loads(prepared.manifest_path.read_text())["status"] == "aborted"

def test_writer_start_failure_uses_sgt_fallback_when_abort_clock_fails(tmp_path):
    class FailingAbortClock:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            if self.calls == 1:
                return NOW
            raise RuntimeError("clock unavailable during abort")

    prepared = prepare_with_fakes(tmp_path)
    contexts = []

    def fail(context):
        contexts.append(context)
        raise RuntimeError("writer unavailable")

    with pytest.raises(WriterStartError, match="session was aborted"):
        start_prepared_session(
            prepared,
            [fail],
            clock=FailingAbortClock(),
        )
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "aborted"
    assert stored["ended_at_sgt"].endswith("+08:00")
    assert contexts[0].pause_stop_controller.stopped is True

def test_privacy_pause_exclusion_and_verified_resume_are_persisted(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_mask_test",
    )

    incident = started.pause("mask_failure")
    assert incident["deletion_required"] is True
    assert writer.paused is True
    assert started.context.pause_stop_controller.paused is True
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "paused"
    assert stored["incident_ids"] == ["incident_mask_test"]

    updated = started.exclude_windows(["zone_a_100_200"])
    assert updated["affected_window_ids"] == ["zone_a_100_200"]
    assert "interval_excluded" in updated["actions"]
    with pytest.raises(SessionLifecycleError, match="deletion must be completed"):
        started.resume(["mask_reverified"])

    resolved = started.resume(["mask_reverified"],deletion_completed=True,)
    assert resolved["status"] == "resolved"
    assert resolved["deletion_completed"] is True
    assert writer.paused is False
    assert started.context.pause_stop_controller.paused is False
    assert json.loads(prepared.manifest_path.read_text())["status"] == "running"
    incident_path = tmp_path / "incidents" / "incident_mask_test.json"
    assert json.loads(incident_path.read_text()) == resolved

def test_operational_pause_can_resume_without_deletion(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: FakeWriter()],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_stream_test",
    )
    incident = started.pause("camera_stream_loss")
    assert incident["severity"] == "operational"
    assert incident["deletion_required"] is False
    resolved = started.resume(["stream_recovered"])
    assert resolved["recovery_verified"] is True

def test_duplicate_incident_id_cannot_overwrite_prior_evidence(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_duplicate",
    )
    started.pause("camera_stream_loss")
    first = started.resume(["stream_recovered"])
    incident_path = tmp_path / "incidents" / "incident_duplicate.json"

    with pytest.raises(SessionLifecycleError, match="already exists"):
        started.pause("esp_a1_loss")

    assert json.loads(incident_path.read_text()) == first
    assert json.loads(prepared.manifest_path.read_text())["status"] == "running"
    assert writer.paused is False
    assert started.context.pause_stop_controller.paused is False

def test_tampered_manifest_cannot_resolve_incident_evidence(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: FakeWriter()],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_tampered_resume",
    )
    opened = started.pause("camera_stream_loss")
    manifest = json.loads(prepared.manifest_path.read_text())
    manifest["status"] = "running"
    prepared.manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(SessionLifecycleError, match="Only a paused session"):
        started.resume(["stream_recovered"])

    incident_path = tmp_path / "incidents" / "incident_tampered_resume.json"
    assert json.loads(incident_path.read_text()) == opened
    assert started.lifecycle.open_incident == opened
    assert started.context.pause_stop_controller.paused is True

def test_writer_recovery_failure_keeps_incident_and_manifest_paused(tmp_path):
    class RecoveryFailureWriter(FakeWriter):
        def resume(self):
            raise RuntimeError("camera has not recovered")

    prepared = prepare_with_fakes(tmp_path)
    writer = RecoveryFailureWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_failed_recovery",
    )
    opened = started.pause("camera_stream_loss")

    with pytest.raises(SessionLifecycleError, match="remains paused"):
        started.resume(["stream_recovered"])

    assert started.lifecycle.open_incident == opened
    assert json.loads(prepared.manifest_path.read_text())["status"] == "paused"
    incident_path = tmp_path / "incidents" / "incident_failed_recovery.json"
    assert json.loads(incident_path.read_text())["status"] == "open"
    assert started.context.pause_stop_controller.paused is True

def test_abort_closes_writers_and_records_terminal_manifest(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
    )

    aborted = started.abort()

    assert aborted["status"] == "aborted"
    assert aborted["ended_at_sgt"] == "2026-07-31T21:45:00+08:00"
    assert writer.closed is True
    assert started.context.pause_stop_controller.stopped is True

def test_abort_from_pause_preserves_open_incident_evidence(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: FakeWriter()],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_abort_test",
    )
    started.pause("camera_stream_loss")

    aborted = started.abort()

    assert aborted["status"] == "aborted"
    incident_path = tmp_path / "incidents" / "incident_abort_test.json"
    incident = json.loads(incident_path.read_text())
    assert incident["status"] == "open"
    assert "session_aborted" in incident["actions"]

def test_resume_requires_recovery_action_for_the_incident_type(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: FakeWriter()],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_recovery_test",
    )
    started.pause("camera_stream_loss")

    with pytest.raises(SessionLifecycleError, match="stream_recovered"):
        started.resume(["collection_paused"])
    assert json.loads(prepared.manifest_path.read_text())["status"] == "paused"

def test_exclusion_failure_keeps_canonical_deletion_requirement(tmp_path):
    class RejectingExclusionWriter(FakeWriter):
        def exclude_windows(self, window_ids):
            raise RuntimeError("cannot apply exclusion")

    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: RejectingExclusionWriter()],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_exclusion_test",
    )
    started.pause("equipment_failure")
    with pytest.raises(SessionLifecycleError, match="remains paused"):
        started.exclude_windows(["zone_a_100_200"])

    assert started.lifecycle.open_incident["deletion_required"] is True
    with pytest.raises(SessionLifecycleError, match="deletion must be completed"):
        started.resume(["equipment_recovered"])
    assert json.loads(prepared.manifest_path.read_text())["status"] == "paused"

def test_clean_stop_closes_writers_and_records_accounting(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    first = FakeWriter()
    second = FakeWriter("predictions", "predictions.jsonl")
    started = start_prepared_session(
        prepared,
        [lambda context: first, lambda context: second],
        clock=lambda: NOW,
    )
    (tmp_path / "telemetry.jsonl").touch()
    (tmp_path / "predictions.jsonl").touch()

    completed = started.stop()
    assert first.closed is True
    assert second.closed is True
    assert started.context.pause_stop_controller.stopped is True
    assert completed["status"] == "completed"
    assert completed["ended_at_sgt"] == "2026-07-31T21:45:00+08:00"
    assert completed["outputs"] == [first.session_summary(),second.session_summary(),]
    assert json.loads(prepared.manifest_path.read_text()) == completed

def test_clean_stop_is_blocked_while_an_incident_is_open(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
        incident_id_factory=lambda: "incident_open_test",
    )
    started.pause("equipment_failure")

    with pytest.raises(SessionLifecycleError, match="Resolve the open incident"):
        started.stop()
    assert writer.closed is False
    assert json.loads(prepared.manifest_path.read_text())["status"] == "paused"

def test_writer_close_failure_aborts_instead_of_completing(tmp_path):
    class BrokenWriter(FakeWriter):
        def close(self):
            raise OSError("disk flush failed")

    prepared = prepare_with_fakes(tmp_path)
    started = start_prepared_session(
        prepared,
        [lambda context: BrokenWriter()],
        clock=lambda: NOW,
    )
    with pytest.raises(SessionLifecycleError, match="marked aborted"):
        started.stop()
    stored = json.loads(prepared.manifest_path.read_text())
    assert stored["status"] == "aborted"
    assert stored["ended_at_sgt"] == "2026-07-31T21:45:00+08:00"

def test_invalid_final_accounting_aborts_instead_of_completing(tmp_path):
    class InvalidSummaryWriter(FakeWriter):
        def session_summary(self):
            summary = super().session_summary()
            summary["relative_path"] = "../outside.jsonl"
            return summary

    prepared = prepare_with_fakes(tmp_path)
    writer = InvalidSummaryWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
    )

    with pytest.raises(SessionLifecycleError, match="accounting was invalid"):
        started.stop()
    assert writer.closed is True
    assert json.loads(prepared.manifest_path.read_text())["status"] == "aborted"

def test_excluded_count_cannot_exceed_total_count(tmp_path):
    class ContradictorySummaryWriter(FakeWriter):
        def session_summary(self):
            summary = super().session_summary()
            summary["excluded_record_count"] = summary["observed_record_count"] + 1
            return summary

    prepared = prepare_with_fakes(tmp_path)
    writer = ContradictorySummaryWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
    )
    (tmp_path / writer.relative_path).touch()

    with pytest.raises(SessionLifecycleError, match="accounting was invalid"):
        started.stop()
    assert json.loads(prepared.manifest_path.read_text())["status"] == "aborted"

def test_duplicate_writer_output_paths_abort_final_accounting(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    first = FakeWriter("telemetry_features", "shared.jsonl")
    second = FakeWriter("predictions", "shared.jsonl")
    started = start_prepared_session(
        prepared,
        [lambda context: first, lambda context: second],
        clock=lambda: NOW,
    )
    (tmp_path / "shared.jsonl").touch()

    with pytest.raises(SessionLifecycleError, match="accounting was invalid"):
        started.stop()
    assert json.loads(prepared.manifest_path.read_text())["status"] == "aborted"

def test_clean_stop_rejects_external_summary_override(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
    )

    with pytest.raises(TypeError):
        started.stop([writer.session_summary()])

    assert writer.closed is False
    assert json.loads(prepared.manifest_path.read_text())["status"] == "running"

def test_missing_output_file_aborts_instead_of_completing(tmp_path):
    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter(relative_path="missing-output.jsonl")
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=lambda: NOW,
    )

    with pytest.raises(SessionLifecycleError, match="accounting was invalid"):
        started.stop()
    assert json.loads(prepared.manifest_path.read_text())["status"] == "aborted"

def test_stop_clock_failure_does_not_close_or_stop_a_running_session(tmp_path):
    class FailingStopClock:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            if self.calls == 1:
                return NOW
            raise RuntimeError("clock unavailable")

    prepared = prepare_with_fakes(tmp_path)
    writer = FakeWriter()
    clock = FailingStopClock()
    started = start_prepared_session(
        prepared,
        [lambda context: writer],
        clock=clock,
    )

    with pytest.raises(SessionLifecycleError, match="clock must be timezone-aware"):
        started.stop()
    assert writer.closed is False
    assert started.context.pause_stop_controller.stopped is False
    assert json.loads(prepared.manifest_path.read_text())["status"] == "running"

def test_cli_can_prepare_manifest_without_starting_writers(monkeypatch, tmp_path, capsys):
    prepared = PreparedSession(
        session_id="zone_a_20260731T214500SGT_dryrun01",
        manifest_path=tmp_path / "manifest.json",
        preflight_report=passing_report(),
    )
    monkeypatch.setattr("aria.collection.run_session.prepare_session",lambda config: prepared,)
    assert main(
        [
            "--prepare-session",
            "--session-kind",
            "non_research_dry_run",
            "--dji-recording-disabled",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert prepared.session_id in output
    assert "No writers were started" in output