import io
import json
from queue import Queue
import pytest
from aria.acceptance.aggregate_report import AggregateRunReport, COUNT_FIELDS, IPC_FIELDS
from aria.acceptance import live_runtime
from aria.acceptance.live_runtime import HardwareRun, RUNTIME_FILES, build_parser, main
from aria.acceptance.runtime import RuntimeSafetyError
from aria.acceptance.runtime_io import FrameBatchSink
from aria.acceptance.synthetic_runtime import camera_record
from aria.collection.preflight import PreflightReport, REQUIRED_CHECKS
from aria.timebase import sgt_now

FLAGS = ["--input-scope", "non_research", "--live-display-only", "--approved-staff-present", "--mask-alignment-confirmed", "--dji-recording-disabled", "--save-aggregate-report"]

def summary():
    return {
        "state": "stopped", "buffered_records": 0, "record_accounting_balanced": True,
        "counts": {"camera_records_received": 4, "sensor_records_received": 4,
                   "processed_records": 6, "discarded_records": 2, "completed_windows": 1,
                   "predictions": 2, "available_predictions": 2},
        "camera_shutdowns": [{"stopped": True, "forced": False, "failed": False,
                              "exit_code": 0, "producer_records": 7, "enqueued_records": 6,
                              "parent_dequeued_records": 4, "ipc_dropped_records": 1,
                              "staged_discarded_records": 0, "queued_discarded_records": 2,
                              "record_accounting_balanced": True}],
    }

def report(tmp_path, *, confirmed=False):
    return AggregateRunReport(root=tmp_path, preflight={name: True for name in REQUIRED_CHECKS}, clean_boot_confirmed=confirmed, source_files=RUNTIME_FILES)

def finish(value, data=None, **kwargs):
    return value.finish(summary=data or summary(), requested_clean=True, started=True, udp_closed=True, dashboard_stopped=True, **kwargs)

def test_report_is_opt_in_atomic_fixed_fields_and_operator_attestation(tmp_path):
    value = report(tmp_path, confirmed=True)
    assert json.loads(value.path.read_text())["status"] == "incomplete"
    assert finish(value)
    result = json.loads(value.path.read_text())
    assert result["status"] == "completed"
    assert result["clean_boot_operator_confirmed"] is True
    assert result["phase_13_1_complete"] is False
    assert result["shutdown"]["clean_shutdown_verified"] is True
    assert result["shutdown"]["process_exit_code"] == 0
    assert set(result["counts"]) == set(COUNT_FIELDS) | {"buffered_records", "invalid_udp_packets"}
    assert set(result["camera_ipc_counts"]) == set(IPC_FIELDS)
    assert list(value.path.parent.iterdir()) == [value.path]

def test_report_does_not_infer_clean_boot_or_copy_private_runtime_fields(tmp_path):
    data = summary()
    sentinel = "synthetic-private-sentinel-not-for-output"
    data["predictions"] = [{"local_track_id": sentinel, "predicted_activity": sentinel}]
    data["health"] = {"sensor_reading": sentinel, "source_ip": sentinel}
    data["counts"][sentinel] = 999
    data["camera_shutdowns"][0]["exception_message"] = sentinel
    value = report(tmp_path)
    assert finish(value, data)
    encoded = value.path.read_text()
    assert sentinel not in encoded and "local_track_id" not in encoded
    assert "predicted_activity" not in encoded and "source_ip" not in encoded
    assert json.loads(encoded)["clean_boot_operator_confirmed"] is False

@pytest.mark.parametrize("invalid", [-1, 1.5, True, "synthetic-secret", float("nan")])
def test_report_rejects_non_count_values_before_writing_them(tmp_path, invalid):
    value = report(tmp_path)
    data = summary()
    data["counts"]["predictions"] = invalid
    with pytest.raises(RuntimeSafetyError, match="invalid_aggregate_count"):
        finish(value, data)
    assert json.loads(value.path.read_text())["status"] == "incomplete"
    assert "synthetic-secret" not in value.path.read_text()

@pytest.mark.parametrize("failure", ["forced", "failed", "exit", "counts", "handoff", "missing_ipc", "cleanup"])
def test_report_cannot_pass_unknown_or_failed_shutdown(tmp_path, failure):
    data = summary()
    child = data["camera_shutdowns"][0]
    if failure in ("forced", "failed"):
        child[failure] = True
    elif failure == "exit":
        child["exit_code"] = 1
    elif failure == "counts":
        data["counts"]["processed_records"] += 1
    elif failure == "handoff":
        child["parent_dequeued_records"] += 1
        child["queued_discarded_records"] -= 1
    elif failure == "missing_ipc":
        child.pop("producer_records")
    else:
        data["cleanup_failed"] = True
    value = report(tmp_path)
    assert not finish(value, data)
    result = json.loads(value.path.read_text())
    assert result["status"] == "aborted"
    assert result["shutdown"]["process_exit_code"] == 1

def test_report_rejects_source_drift(tmp_path, monkeypatch):
    value = report(tmp_path)
    monkeypatch.setattr("aria.acceptance.aggregate_report.file_hash", lambda path: "changed")
    assert not finish(value)
    assert value.value["test_results"]["runtime_artifacts_unchanged"] is False

@pytest.mark.parametrize("flags", [
    ["--input-scope", "synthetic", "--save-aggregate-report"],
    ["--input-scope", "non_research", "--equipment-only", "--save-aggregate-report"],
    ["--input-scope", "non_research", "--clean-boot-confirmed"],
])
def test_report_flags_require_explicit_display_mode(flags):
    with pytest.raises(SystemExit):
        main(flags)

def test_sink_counts_staged_enqueued_and_full_queue_discard():
    class Counter:
        value = 0
        def get_lock(self):
            from contextlib import nullcontext
            return nullcontext()
    produced, enqueued, dropped = Counter(), Counter(), Counter()
    queue = Queue(maxsize=1)
    sink = FrameBatchSink(queue, dropped, produced=produced, enqueued=enqueued)
    sink.write(camera_record(sgt_now(), frame=1))
    assert (produced.value, enqueued.value, dropped.value) == (1, 0, 0)
    sink.write(camera_record(sgt_now(), frame=2))
    assert (produced.value, enqueued.value, dropped.value) == (2, 1, 0)
    sink.close()
    assert (produced.value, enqueued.value, dropped.value) == (2, 1, 1)

def test_opted_in_display_report_does_not_enable_cloud_or_recording(monkeypatch, tmp_path):
    #reuse existing display test's numerical-only substitutes
    from test_phase_13_live_display import Camera, Socket
    def forbidden(*args, **kwargs):
        raise AssertionError("raw evidence/cloud boundary constructed")
    monkeypatch.setattr(live_runtime, "SandboxFirebase", forbidden)
    monkeypatch.setattr(live_runtime, "RunEvidence", forbidden)
    monkeypatch.setattr(live_runtime, "run_preflight", lambda config: PreflightReport(
        sgt_now().isoformat(), {name: True for name in REQUIRED_CHECKS}))
    class CountedCamera(Camera):
        def stop(self):
            result = super().stop()
            result.update({key: 0 for key in IPC_FIELDS})
            result.update(failed=False, exit_code=0, record_accounting_balanced=True)
            return result
    def hardware_factory(*args, **kwargs):
        return HardwareRun(*args, **kwargs, camera_factory=CountedCamera, socket_factory=Socket)
    monkeypatch.setattr(live_runtime, "HardwareRun", hardware_factory)
    class Server:
        def serve_forever(self):
            pass
        def shutdown(self):
            pass
        def server_close(self):
            pass
    monkeypatch.setattr("werkzeug.serving.make_server", lambda *args, **kwargs: Server())
    monkeypatch.setattr("sys.stdin", io.StringIO("stop\n"))
    monkeypatch.setattr(live_runtime.select, "select", lambda readers, *args: (readers, [], []))
    assert live_runtime.run_hardware(build_parser().parse_args(FLAGS), output_root=tmp_path) == 0
    files = list(tmp_path.rglob("*.*"))
    assert len(files) == 1 and files[0].name == "summary.json"
    value = json.loads(files[0].read_text())
    assert value["staff_recording_enabled"] is False and value["cloud_enabled"] is False
    assert value["shutdown"]["clean_shutdown_verified"] is True
    assert value["test_results"]["available_predictions_emitted"] is False
    assert value["phase_13_1_complete"] is False