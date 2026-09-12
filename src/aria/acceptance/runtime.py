"""bounded, memory-only completed-window runtime for non-research acceptance. no cam, sensor or local prediction records are written by this module. only the schema-restricted Firebase projector may receive predictions"""
from __future__ import annotations
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timedelta
import math
from threading import RLock
import time
from uuid import uuid4
from aria.dashboard.integration import LocalDashboardIntegration
from aria.fusion.window_builder import _window_start
from aria.timebase import SGT, sgt_now

NODES = ("ESP-A1", "ESP-A2")
WINDOW = timedelta(seconds=2)
LATENESS = timedelta(seconds=1)
MAX_RECORDS = 1024

class RuntimeSafetyError(RuntimeError):
    """fixed-code runtime failure; never include raw inputs in this error"""

def timestamp(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeSafetyError("invalid_clock")
    return value.astimezone(SGT)

class WindowRuntime:
    """serialise producers, inference and privacy transitions behind one gate"""

    def __init__(self, *, integration=None, now=None):
        self.integration = integration or LocalDashboardIntegration()
        if self.integration.orchestrator.writer is not None:
            raise RuntimeSafetyError("persistent_prediction_writer_prohibited")
        self.lock = RLock()
        self.counts = Counter()
        self.latencies = deque(maxlen=4096)
        self.latency_observer = None
        self.buffers = {}
        self.buffered_records = 0
        self.state = "paused"
        self.last_now = timestamp(now or sgt_now())
        self.started = self.last_now
        self.next_window = _window_start(self.last_now, 2) + WINDOW
        #required by unchanged local prediction schema; never persisted
        self._ephemeral_id = ("zone_a_" + self.started.strftime("%Y%m%dT%H%M%SSGT_") + uuid4().hex[:12])
        self.last_camera_at = None
        self.integration.set_mask_verified(False)

    def resume(self, *, verified, now):
        with self.lock:
            if verified is not True or self.state == "stopped":
                raise RuntimeSafetyError("verified_resume_required")
            current = timestamp(now)
            self._discard_buffers()
            #nvr replay a partial window or a pre-pause track
            self.next_window = _window_start(current, 2) + WINDOW
            self.last_now = current
            self.last_camera_at = None
            self.integration.set_mask_verified(True)
            self.state = "running"

    def _discard_buffers(self):
        self.counts["discarded_records"] += self.buffered_records
        self.buffers.clear()
        self.buffered_records = 0

    def pause(self):
        with self.lock:
            self.state = "paused"
            self._discard_buffers()
            self.last_camera_at = None
            self.integration.set_mask_verified(False)
            self.counts["privacy_pauses"] += 1

    def stop(self):
        with self.lock:
            self._discard_buffers()
            self.state = "stopped"
            self.integration.set_mask_verified(False)

    def _bucket(self, observed, now, size):
        start = _window_start(observed, 2)
        if observed > now or start < self.next_window:
            self.counts["late_or_partial_records"] += size
            return None
        if (now - observed).total_seconds() > 4:
            self.counts["late_or_partial_records"] += size
            return None
        if self.buffered_records + size > MAX_RECORDS:
            self.counts["overflow_records"] += size
            return None
        self.buffered_records += size
        return self.buffers.setdefault(start, {"camera": [], "sensors": {node: [] for node in NODES}})

    def camera_batch(self, records, *, capture_fps, processing_fps, now):
        """1 atomic processed frame: never split its tracks across windows"""
        with self.lock:
            self.counts["camera_records_received"] += len(records)
            if self.state != "running":
                self.counts["discarded_records"] += len(records)
                return
            if not records or len(records) > 128:
                raise RuntimeSafetyError("invalid_camera_batch")
            current = timestamp(now)
            first = records[0]
            observed = timestamp(first["frame_timestamp_sgt"])
            for record in records:
                self.integration._validate_camera_record(record)
                if (
                    record["frame_number"] != first["frame_number"]
                    or record["frame_timestamp_sgt"] != first["frame_timestamp_sgt"]
                    or record["mask_config_version"] != "batamfast-v2"
                ):
                    raise RuntimeSafetyError("invalid_camera_batch")
            bucket = self._bucket(observed, current, len(records))
            if bucket is None:
                return
            self.integration.on_camera_record(first, capture_fps=capture_fps, processing_fps=processing_fps)
            self.last_camera_at = observed if first["frame_available"] else None
            bucket["camera"].extend(dict(deepcopy(record), _timestamp=observed) for record in records)
            self.counts["processed_frames"] += 1
            self.counts["maximum_simultaneous_tracks"] = max(self.counts["maximum_simultaneous_tracks"],sum(record["record_type"] == "track" for record in records),)

    def sensor_record(self, record, *, now):
        with self.lock:
            self.counts["sensor_records_received"] += 1
            self.integration._validate_sensor_record(record)
            if record["payload"]["firmware_version"] != "1.1.1":
                raise RuntimeSafetyError("unexpected_esp_firmware")
            if self.state != "running":
                self.counts["discarded_records"] += 1
                return
            current = timestamp(now)
            observed = timestamp(record["received_at_sgt"])
            bucket = self._bucket(observed, current, 1)
            if bucket is None:
                return
            self.integration.on_sensor_record(record)
            node = record["payload"]["node_id"]
            bucket["sensors"][node].append(dict(deepcopy(record), _timestamp=observed))

    def tick(self, now):
        with self.lock:
            current = timestamp(now)
            if self.state != "running":
                return 0
            if current < self.last_now or current - self.next_window > timedelta(seconds=8):
                self.pause()
                raise RuntimeSafetyError("clock_or_processing_gap")
            self.last_now = current
            completed = 0
            while self.next_window + WINDOW + LATENESS <= current:
                start = self.next_window
                bucket = self.buffers.pop(start, {"camera": [], "sensors": {n: [] for n in NODES}})
                size = len(bucket["camera"]) + sum(map(len, bucket["sensors"].values()))
                self.buffered_records -= size
                camera_records = bucket["camera"]
                if self.last_camera_at is None or (current - self.last_camera_at).total_seconds() > 2:
                    camera_records = []
                    self.integration.on_camera_unavailable()
                began = time.perf_counter()
                result = self.integration.process_completed_window(
                    session_id=self._ephemeral_id, window_start=start,
                    camera_records=camera_records, sensor_records=bucket["sensors"],
                    emitted_at=current,
                )
                latency = (time.perf_counter() - began) * 1000
                self.latencies.append(latency)
                self.counts["processed_records"] += size
                self.counts["completed_windows"] += 1
                for prediction in result["predictions"]:
                    self.counts["predictions"] += 1
                    self.counts["available_predictions"] += int(prediction["prediction_available"])
                self.next_window += WINDOW
                completed += 1
                if self.latency_observer is not None:
                    self.latency_observer(latency)
            return completed

    def summary(self):
        """aggregate accounting only: never include tracks, windows or activities"""
        with self.lock:
            received = self.counts["camera_records_received"] + self.counts["sensor_records_received"]
            accounted = sum(self.counts[name] for name in (
                "processed_records", "discarded_records", "late_or_partial_records", "overflow_records"
            )) + self.buffered_records
            ordered = sorted(self.latencies)
            return {
                "state": self.state,
                "counts": dict(self.counts),
                "buffered_records": self.buffered_records,
                "record_accounting_balanced": received == accounted,
                "prediction_latency_p95_ms": (
                    round(ordered[min(len(ordered) - 1, math.ceil(.95 * len(ordered)) - 1)], 3)
                    if ordered else None
                ),
                "latency_sample_count": len(ordered),
                "latency_definition": "local_completed_window_processing_last_4096_samples",
                "raw_record_files_created": 0,
                "local_prediction_files_created": 0,
            }