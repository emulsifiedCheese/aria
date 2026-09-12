"""opt-in, fixed-field test outcomes and counts; never retain runtime records."""
from __future__ import annotations
import json
import os
from pathlib import Path
from uuid import uuid4
from aria.collection.preflight import REQUIRED_CHECKS
from aria.timebase import sgt_now
from .runtime import RuntimeSafetyError
from .runtime_io import ROOT, file_hash, verify_assets

COUNT_FIELDS = (
    "camera_records_received", "sensor_records_received", "processed_records",
    "discarded_records", "late_or_partial_records", "overflow_records",
    "processed_frames", "completed_windows", "predictions", "available_predictions",
    "privacy_pauses",
)
IPC_FIELDS = (
    "producer_records", "enqueued_records", "parent_dequeued_records",
    "ipc_dropped_records", "staged_discarded_records", "queued_discarded_records",
)

def _count(source, key):
    value = source.get(key, 0)
    if type(value) is not int or value < 0:
        raise RuntimeSafetyError("invalid_aggregate_count")
    return value

class AggregateRunReport:
    """1 atomic JSON report, with no arbitrary metrics/strings/event API"""

    def __init__(self, *, root, preflight, clean_boot_confirmed, source_files):
        #hashes stay in memory; output includes only the unchanged boolean
        self.hashes = {name: file_hash(ROOT / name) for name in source_files}
        self.preflight = {name: preflight.get(name) is True for name in REQUIRED_CHECKS}
        self.clean_boot_confirmed = clean_boot_confirmed is True
        self.path = Path(root) / ("aggregate_" + sgt_now().strftime("%Y%m%dT%H%M%S_") + uuid4().hex[:8])
        self.path.mkdir(parents=True, exist_ok=False)
        self.path = self.path / "summary.json"
        self.value = {
            "schema_version": 1, "kind": "phase13_aggregate_test_report", "status": "incomplete",
            "preflight": self.preflight,
            "clean_boot_operator_confirmed": self.clean_boot_confirmed,
            "test_results": {}, "counts": {}, "camera_ipc_counts": {}, "shutdown": {},
            "staff_recording_enabled": False, "cloud_enabled": False,
            "phase_13_1_complete": False,
        }
        self._save()

    def _save(self):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(self.value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)

    def finish(self, *, summary, requested_clean, started, udp_closed, dashboard_stopped):
        raw_counts = summary.get("counts", {})
        counts = {name: _count(raw_counts, name) for name in COUNT_FIELDS}
        counts["buffered_records"] = _count(summary, "buffered_records")
        counts["invalid_udp_packets"] = _count(summary, "invalid_udp_packets")
        children = summary.get("camera_shutdowns", [])
        ipc = {name: sum(_count(child, name) for child in children) for name in IPC_FIELDS}
        ipc_complete = bool(children) and all(all(name in child for name in IPC_FIELDS) for child in children)
        ipc_balanced = ipc_complete and all(
            child.get("record_accounting_balanced") is True
            and child["producer_records"] == (
                child["parent_dequeued_records"] + child["ipc_dropped_records"]
                + child["staged_discarded_records"] + child["queued_discarded_records"]
            ) for child in children
        )
        received = counts["camera_records_received"] + counts["sensor_records_received"]
        accounted = sum(counts[name] for name in (
            "processed_records", "discarded_records", "late_or_partial_records", "overflow_records", "buffered_records"
        ))
        parent_balanced = (summary.get("record_accounting_balanced") is True and received == accounted)
        #in display mode every dequeued batch must enter parent window gate
        handoff_balanced = ipc_complete and ipc["parent_dequeued_records"] == counts["camera_records_received"]
        camera_stopped = bool(children) and all(child.get("stopped") is True for child in children)
        normal_camera_exit = camera_stopped and all(
            child.get("forced") is False and child.get("failed") is False
            and type(child.get("exit_code")) is int and child["exit_code"] == 0
            for child in children
        )
        try:
            unchanged = all(file_hash(ROOT / name) == digest for name, digest in self.hashes.items())
            verify_assets()
        except Exception:
            unchanged = False
        shutdown = {
            "runtime_stopped": summary.get("state") == "stopped",
            "udp_closed": udp_closed is True,
            "dashboard_stopped": dashboard_stopped is True,
            "camera_all_stopped": camera_stopped,
            "camera_all_exited_normally": normal_camera_exit,
            "forced_camera_stops": sum(child.get("forced") is True for child in children),
            "failed_camera_workers": sum(child.get("failed") is True for child in children),
        }
        clean = (requested_clean is True and started is True and all(shutdown[name] for name in (
            "runtime_stopped", "udp_closed", "dashboard_stopped", "camera_all_stopped", "camera_all_exited_normally"
        )) and counts["buffered_records"] == 0 and parent_balanced and ipc_balanced
                 and handoff_balanced and unchanged and not summary.get("cleanup_failed", False))
        shutdown["clean_shutdown_verified"] = clean
        shutdown["process_exit_code"] = 0 if clean else 1
        self.value.update(
            status="completed" if clean else "aborted",
            counts=counts, camera_ipc_counts=ipc, shutdown=shutdown,
            test_results={
                "preflight_passed": all(self.preflight.values()),
                "runtime_started": started is True,
                "completed_windows_observed": counts["completed_windows"] > 0,
                "available_predictions_emitted": counts["available_predictions"] > 0,
                "parent_records_reconciled": parent_balanced,
                "camera_ipc_records_reconciled": ipc_balanced,
                "camera_parent_handoff_reconciled": handoff_balanced,
                "runtime_artifacts_unchanged": unchanged,
            },
        )
        self._save()
        return clean