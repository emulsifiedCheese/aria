from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from queue import Queue
from threading import Event, Lock
import time
import pytest
from aria.acceptance.runtime import MAX_RECORDS, RuntimeSafetyError, WindowRuntime
from aria.acceptance.runtime_io import CameraProcess, FrameBatchSink, SandboxFirebase
from aria.acceptance.synthetic_runtime import camera_record, sensor_record, run_synthetic
from aria.acceptance.live_runtime import HardwareRun, RunEvidence, main
from aria.collection.preflight import PreflightConfig, PreflightError, PreflightReport, REQUIRED_CHECKS
from aria.dashboard.app import create_dashboard_app
from aria.dashboard.integration import LocalDashboardIntegration
from aria.inference.service import LocalInferenceService
from aria.timebase import SGT

START = datetime(2026, 8, 31, 12, 0, 0, tzinfo=SGT)

@pytest.fixture(scope="module")
def service():
    return LocalInferenceService()

@pytest.fixture
def runtime(service):
    value = WindowRuntime(integration=LocalDashboardIntegration(service=service), now=START)
    value.resume(verified=True, now=START)
    return value

def populate(runtime, *, nodes=("ESP-A1", "ESP-A2"), tracks=(1, 2)):
    start = runtime.next_window
    observed = start + timedelta(seconds=1.75)
    for node in nodes:
        runtime.sensor_record(sensor_record(observed, node), now=observed)
    records = [camera_record(observed, track) for track in tracks]
    if records:
        runtime.camera_batch(records, capture_fps=30, processing_fps=7, now=observed)
    return observed, start + timedelta(seconds=3)

def test_synthetic_end_to_end_never_opens_camera_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("hardware or network access prohibited")
    monkeypatch.setattr("aria.collection.preflight.run_preflight", forbidden)
    monkeypatch.setattr("aria.cloud.firebase_sync.FirebaseRealtimeDatabaseClient._initialize", forbidden)
    report = run_synthetic(now=START)
    assert all(report["checks"].values())
    assert report["phase_13_1_complete"] is False
    assert report["runtime"]["record_accounting_balanced"]

def test_only_completed_windows_emit_and_tracks_remain_separate(runtime):
    observed, end = populate(runtime)
    assert runtime.tick(observed) == 0
    assert runtime.tick(end) == 1
    predictions = runtime.integration.snapshot(end)["predictions"]
    assert [p["local_track_id"] for p in predictions] == [1, 2]
    assert all(p["prediction_available"] for p in predictions)
    assert runtime.tick(end) == 0

def test_late_frame_cannot_reopen_completed_window(runtime):
    observed, end = populate(runtime)
    runtime.tick(end)
    runtime.camera_batch([camera_record(observed, 3)], capture_fps=30, processing_fps=7, now=end)
    assert runtime.counts["late_or_partial_records"] == 1
    assert runtime.counts["predictions"] == 2
    assert runtime.summary()["record_accounting_balanced"]

def test_partial_start_window_is_discarded(runtime):
    runtime.sensor_record(sensor_record(START, "ESP-A1"), now=START)
    assert runtime.buffered_records == 0
    assert runtime.counts["late_or_partial_records"] == 1

def test_privacy_pause_clears_inputs_display_and_blocks_inference(runtime):
    _, end = populate(runtime)
    runtime.tick(end)
    populate(runtime)
    runtime.pause()
    assert runtime.integration.snapshot(end)["predictions"] == []
    assert runtime.integration.snapshot(end)["overall_status"] == "blocked"
    assert runtime.buffered_records == 0
    count = runtime.counts["predictions"]
    assert runtime.tick(end + timedelta(seconds=10)) == 0
    assert runtime.counts["predictions"] == count
    assert runtime.summary()["record_accounting_balanced"]

def test_resume_requires_verification_and_discards_old_records(runtime):
    observed, end = populate(runtime)
    runtime.pause()
    with pytest.raises(RuntimeSafetyError):
        runtime.resume(verified=False, now=end)
    runtime.resume(verified=True, now=end)
    runtime.camera_batch([camera_record(observed)], capture_fps=30, processing_fps=7, now=end)
    assert runtime.buffered_records == 0
    assert runtime.integration.snapshot(end)["predictions"] == []

@pytest.mark.parametrize("seconds", [-1, 30])
def test_clock_jump_pauses_instead_of_replaying_stale_windows(runtime, seconds):
    with pytest.raises(RuntimeSafetyError, match="clock_or_processing_gap"):
        runtime.tick(START + timedelta(seconds=seconds))
    assert runtime.state == "paused"

def test_camera_absence_replaces_previous_activity(runtime):
    _, end = populate(runtime)
    runtime.tick(end)
    _, end = populate(runtime, tracks=())
    runtime.tick(end)
    predictions = runtime.integration.snapshot(end)["predictions"]
    assert len(predictions) == 1
    assert predictions[0]["predicted_activity"] is None
    assert predictions[0]["confidence"] is None

def test_sensor_loss_does_not_stop_camera_only_model(runtime):
    _, end = populate(runtime, nodes=())
    runtime.tick(end)
    state = runtime.integration.snapshot(end)
    assert state["overall_status"] == "degraded"
    assert all(p["prediction_available"] for p in state["predictions"])
    assert all(not p["availability"]["esp_a1_available"] for p in state["predictions"])

def test_buffer_is_bounded_and_accounted(runtime):
    observed = runtime.next_window + timedelta(seconds=1)
    record = sensor_record(observed, "ESP-A1")
    for _ in range(MAX_RECORDS + 1):
        runtime.sensor_record(record, now=observed)
    assert runtime.buffered_records == MAX_RECORDS
    assert runtime.counts["overflow_records"] == 1
    runtime.stop()
    assert runtime.buffered_records == 0
    assert runtime.summary()["record_accounting_balanced"]

def test_mixed_frame_batch_and_wrong_mask_are_rejected(runtime):
    observed = runtime.next_window + timedelta(seconds=1)
    records = [camera_record(observed, 1, 1), camera_record(observed, 2, 2)]
    with pytest.raises(RuntimeSafetyError, match="invalid_camera_batch"):
        runtime.camera_batch(records, capture_fps=30, processing_fps=7, now=observed)
    record = camera_record(observed)
    record["mask_config_version"] = "development"
    with pytest.raises(RuntimeSafetyError, match="invalid_camera_batch"):
        runtime.camera_batch([record], capture_fps=30, processing_fps=7, now=observed)

class CounterValue:
    value = 0
    def get_lock(self):
        return Lock()

def test_camera_sink_batches_whole_frames_and_drops_on_full_queue():
    queue = Queue(maxsize=1)
    dropped = CounterValue()
    sink = FrameBatchSink(queue, dropped)
    sink.write(camera_record(START, 1, 1))
    sink.write(camera_record(START, 2, 1))
    assert queue.empty()
    sink.write(camera_record(START + timedelta(seconds=1), 1, 2))
    sink.close()
    assert dropped.value == 1
    batch = queue.get_nowait()
    assert len(batch["records"]) == 2
    assert batch["records"][0]["frame_number"] == batch["records"][1]["frame_number"]

def test_real_outbox_offline_recovery_privacy_purge_and_cleanup(service, tmp_path):
    current = [START]
    cloud = SandboxFirebase(now=lambda: current[0], temp_parent=tmp_path)
    try:
        runtime = WindowRuntime(integration=LocalDashboardIntegration(service=service, firebase_sync=cloud), now=START)
        runtime.resume(verified=True, now=START)
        _, end = populate(runtime)
        current[0] = end
        cloud.set_offline(True)
        runtime.tick(end)
        assert cloud.flush(end)["failure"] == "unavailable"
        for file in Path(cloud.directory.name).glob("*.json"):
            payload = json.loads(file.read_text())["payload"]
            assert set(payload) <= set(cloud.sync.contract.config["payload"]["allowed_fields"])
            assert "local_track_id" not in payload and "session_id" not in payload
        current[0] += timedelta(seconds=2)
        cloud.set_offline(False)
        assert cloud.flush(current[0])["delivered"] == 2
        assert cloud.summary()["pending"] == 0
        cloud.purge()
        assert not cloud.client.digests
    finally:
        cloud.close()
    assert not Path(cloud.directory.name).exists()

def test_dashboard_route_uses_runtime_aggregator_and_clears_on_pause(runtime):
    _, end = populate(runtime)
    runtime.tick(end)
    app = create_dashboard_app(runtime.integration.aggregator)
    assert app.aria_aggregator is runtime.integration.aggregator
    assert app.server.test_client().get("/").status_code == 200
    assert app.server.test_client().get("/_dash-layout").status_code == 200
    runtime.pause()
    assert app.aria_aggregator.snapshot(end)["predictions"] == []

class FakeEvidence:
    def __init__(self):
        self.events = []
    def event(self, code, metrics=None):
        self.events.append(code)

class FakeSocket:
    def __init__(self, *args):
        self.closed = False
    def bind(self, address):
        assert address == ("0.0.0.0", 5005)
    def setblocking(self, value):
        assert value is False
    def recvfrom(self, size):
        raise BlockingIOError
    def close(self):
        self.closed = True

class FakeCamera:
    def __init__(self, mask):
        self.failed = Event()
        self.process = self
        self.alive = False
        self.messages = []
    def start(self):
        self.alive = True
    def is_alive(self):
        return self.alive
    def poll(self):
        yield from self.messages
        self.messages.clear()
    def stop(self):
        self.alive = False
        return {"stopped": True, "forced": False, "ipc_dropped_records": 0}

class FakeCloud:
    def __init__(self):
        self.purges = 0
    def purge(self):
        self.purges += 1

def test_live_person_detection_pauses_before_inference(runtime):
    cloud = FakeCloud()
    evidence = FakeEvidence()
    runner = HardwareRun(runtime, cloud, PreflightConfig("non_research_dry_run"), evidence, camera_factory=FakeCamera, socket_factory=FakeSocket, clock=lambda: START)
    runner.start(None)
    camera, sock = runner.camera, runner.udp
    camera.messages = [{"records": [camera_record(START)]}]
    runner.poll()
    assert runtime.state == "paused"
    assert not camera.alive and sock.closed
    assert runtime.counts["predictions"] == 0
    assert cloud.purges == 1
    assert "person_detected_empty_region_required" in evidence.events

def test_resume_runs_fresh_preflight_before_camera_restart(runtime):
    report = PreflightReport(START.isoformat(), {key: False for key in REQUIRED_CHECKS})
    runner = HardwareRun(runtime, FakeCloud(), PreflightConfig("non_research_dry_run"), FakeEvidence(), camera_factory=FakeCamera, socket_factory=FakeSocket, preflight_runner=lambda config: report, clock=lambda: START)
    runner.start(None)
    runner.pause()
    with pytest.raises(PreflightError):
        runner.resume()
    assert runner.camera is None and runner.udp is None
    assert runtime.state == "paused"

def test_live_cli_rejects_participant_scope_and_missing_confirmations():
    with pytest.raises(SystemExit):
        main(["--input-scope", "participant"])
    with pytest.raises(SystemExit):
        main(["--input-scope", "non_research"])

def test_aggregate_manifest_never_claims_phase_completion(tmp_path):
    evidence = RunEvidence("synthetic", root=tmp_path)
    evidence.finish(clean=True, summary={"record_accounting_balanced": True})
    manifest = json.loads((evidence.path / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["phase_13_1_complete"] is False
    assert manifest["artifacts_unchanged"] is True
    assert manifest["event_count"] == 1

def test_artifact_drift_aborts_diagnostic_manifest(tmp_path, monkeypatch):
    from aria.acceptance import live_runtime
    evidence = RunEvidence("synthetic", root=tmp_path)
    monkeypatch.setattr(live_runtime, "file_hash", lambda path: "changed")
    evidence.finish(clean=True, summary={})
    assert evidence.manifest["status"] == "aborted"
    assert evidence.manifest["artifacts_unchanged"] is False

def test_synthetic_cli_failure_leaves_aborted_evidence(tmp_path, monkeypatch):
    from aria.acceptance import live_runtime, synthetic_runtime
    created = []
    def evidence_factory(scope):
        evidence = RunEvidence(scope, root=tmp_path)
        created.append(evidence)
        return evidence
    def fail():
        raise RuntimeSafetyError("synthetic_failure")
    monkeypatch.setattr(live_runtime, "RunEvidence", evidence_factory)
    monkeypatch.setattr(synthetic_runtime, "run_synthetic", fail)
    with pytest.raises(RuntimeSafetyError):
        main(["--input-scope", "synthetic"])
    assert created[0].manifest["status"] == "aborted"
    assert created[0].stream.closed

class SyntheticChildPipeline:
    """spawn-safe fake exercises real IPC and process teardown, no cam"""
    def __init__(self, **options):
        assert options["display"] is False and options["preview_callback"] is None
        assert options["output_path"] is None
        self.options = options

    def run(self):
        self.options["started_callback"]()
        frame = 1
        while not self.options["stop_requested"]():
            at = START + timedelta(milliseconds=frame * 100)
            self.options["writer"].write(camera_record(at, frame=frame))
            frame += 1
            time.sleep(.01)
        self.options["writer"].close()

def test_spawned_camera_adapter_and_clean_teardown_without_hardware():
    producer = CameraProcess(None, pipeline_factory=SyntheticChildPipeline)
    producer.start()
    try:
        assert producer.ready.wait(timeout=15)
        deadline = time.monotonic() + 5
        messages = []
        while not messages and time.monotonic() < deadline:
            messages = list(producer.poll())
            time.sleep(.02)
        assert messages and messages[0]["kind"] == "frame"
        assert not producer.failed.is_set()
    finally:
        result = producer.stop()
    assert result["stopped"] is True and result["forced"] is False
    assert result["exit_code"] == 0 and result["failed"] is False
    assert result["record_accounting_balanced"] is True
    assert result["producer_records"] == ( result["parent_dequeued_records"] + result["ipc_dropped_records"] + result["staged_discarded_records"] + result["queued_discarded_records"]
    )

def test_unstarted_camera_adapter_cleanup_is_safe():
    producer = CameraProcess(None, pipeline_factory=SyntheticChildPipeline)
    assert producer.stop()["stopped"] is True

def test_failed_initial_preflight_starts_no_outputs_or_producers(monkeypatch, tmp_path):
    from aria.acceptance import live_runtime
    report = PreflightReport(START.isoformat(), {key: False for key in REQUIRED_CHECKS})
    monkeypatch.setattr(live_runtime, "run_preflight", lambda config: report)
    def forbidden(*args, **kwargs):
        raise AssertionError("producer initialized after failed preflight")
    monkeypatch.setattr(live_runtime, "SandboxFirebase", forbidden)
    with pytest.raises(PreflightError):
        live_runtime.run_hardware(None, output_root=tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_live_cli_rejects_missing_interactive_controls(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(SystemExit):
        main(["--input-scope", "non_research", "--confirm-empty-retained-region", "--mask-alignment-confirmed", "--dji-recording-disabled"])