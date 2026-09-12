"""isolate cam A producer and local-only Firebase acceptance transport"""
from __future__ import annotations
from collections import OrderedDict
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
from queue import Empty, Full
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
from aria.cloud.firebase_sync import (
    FirebaseConflictError, FirebasePredictionSync, FirebaseUnavailableError,
)
from aria.timebase import sgt_now
from .runtime import RuntimeSafetyError

ROOT = Path(__file__).resolve().parents[3]
ASSETS = {
    "config/cameras.batamfast.yaml": "1b057b512b571bb3f65d0c1f470c653a453b9615b70bc154f93b4adebea7d8bf",
    "config/masks.batamfast.yaml": "afb994e95f892fe0115093fedda7132d1c8261209cfbde072c4b69a205ca39d5",
    "config/mediamtx.local.yaml": "8a3a135a819e00ab93cedc8b299f4838836840670e621e5d931d5c0859e9ce73",
    "config/bytetrack.zone_a.persistence.yaml": "993ee4e4e1330d50b94dfe77a84e4b28a18a78b19b96ea77fdab51ee506722c9",
    "yolov8n.pt": "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
    "yolov8n-pose.pt": "c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212",
    "src/aria/vision/pipeline.py": "75c63b79f74bfb4f8ec79a2ab1cc880e8ff19ea8bf7ace19a52bd95f33e96f7b",
}
CV_OPTIONS = {
    "detector_model": str(ROOT / "yolov8n.pt"),
    "pose_model": str(ROOT / "yolov8n-pose.pt"),
    "tracker_config": str(ROOT / "config/bytetrack.zone_a.persistence.yaml"),
    "detector_confidence": .10, "detector_iou": .70,
    "pose_confidence": .15, "keypoint_confidence": .5,
    "min_confident_keypoints": 4, "processing_fps": 15,
    "inference_size": 768, "pose_inference_size": 384,
    "experimental_track_stitching": False,
}

def file_hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def verify_assets():
    for name, expected in ASSETS.items():
        path = ROOT / name
        if not path.is_file() or file_hash(path) != expected:
            raise RuntimeSafetyError("runtime_asset_changed: " + name)
    return dict(ASSETS)

class FrameBatchSink:
    """replace a disk FeatureWriter; IPC carries numerical records, never frames"""

    def __init__(self, queue, dropped, *, produced=None, enqueued=None):
        self.queue = queue
        self.dropped = dropped
        self.produced = produced
        self.enqueued = enqueued
        self.records = []
        self.previous = None

    def write(self, record):
        if self.records and record["frame_number"] != self.records[0]["frame_number"]:
            self.flush()
        if len(self.records) >= 128:
            raise RuntimeSafetyError("too_many_tracks_in_frame")
        self.records.append(record)
        if self.produced is not None:
            self.produced.value += 1

    def flush(self):
        if not self.records:
            return
        first = self.records[0]
        current = (first["frame_number"], datetime.fromisoformat(first["frame_timestamp_sgt"]))
        capture_fps = processing_fps = None
        if self.previous:
            elapsed = (current[1] - self.previous[1]).total_seconds()
            if elapsed > 0:
                capture_fps = (current[0] - self.previous[0]) / elapsed
                processing_fps = 1 / elapsed
        self.previous = current
        try:
            self.queue.put_nowait({
                "kind": "frame", "records": self.records,
                "capture_fps": capture_fps, "processing_fps": processing_fps,
            })
            if self.enqueued is not None:
                self.enqueued.value += len(self.records)
        except Full:
            with self.dropped.get_lock():
                self.dropped.value += len(self.records)
        self.records = []

    def close(self):
        self.flush()

def _camera_main(queue, dropped, stop, ready, failed, mask, pipeline_factory=None,
                 equipment_only=False, produced=None, enqueued=None):
    # no OpenCV/YOLO initialization on import or --help. only spawned hardware child constructs the real pipeline, after parent preflight
    with open(os.devnull, "w") as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            if equipment_only:
                from .equipment_runtime import camera_health_loop
                verify_assets()
                camera_health_loop(queue, stop, ready, mask)
                return
            from collections import deque
            if pipeline_factory is None:
                from aria.vision.pipeline import CVPipeline
                pipeline_factory = CVPipeline
            verify_assets()
            sink = FrameBatchSink(queue, dropped, produced=produced, enqueued=enqueued)
            pipeline = pipeline_factory(
                camera_id="camera_a", source="rtsp://127.0.0.1:8554/live/camera_a",
                mask_config=mask, output_path=None, writer=sink,
                display=False, preview_callback=None,
                stop_requested=stop.is_set, started_callback=ready.set,
                **CV_OPTIONS,
            )
            pipeline.inference_latencies_ms = deque(maxlen=4096)
            pipeline.frame_ages_ms = deque(maxlen=4096)
            pipeline.run()
        except Exception:
            failed.set()
        finally:
            # never leave a child waiting for parent to drain a feeder
            queue.cancel_join_thread()

class CameraProcess:
    def __init__(self, mask, *, context=None, pipeline_factory=None, equipment_only=False):
        ctx = context or multiprocessing.get_context("spawn")
        self.queue = ctx.Queue(maxsize=8)
        self.dropped = ctx.Value("i", 0)
        # child-only writers; parent reads after join, without draining frame IPC
        self.produced = ctx.Value("q", 0, lock=False)
        self.enqueued = ctx.Value("q", 0, lock=False)
        self.dequeued = 0
        self.stop_requested = ctx.Event()
        self.ready = ctx.Event()
        self.failed = ctx.Event()
        self.process = ctx.Process(
            target=_camera_main,
            args=(self.queue, self.dropped, self.stop_requested, self.ready, self.failed,
                  mask, pipeline_factory, equipment_only, self.produced, self.enqueued),
            name="aria-phase13-camera", daemon=True,
        )

    def start(self):
        self.process.start()

    def poll(self):
        for _ in range(8):
            try:
                message = self.queue.get_nowait()
                if message.get("kind") == "frame":
                    self.dequeued += len(message["records"])
                yield message
            except Empty:
                break

    def stop(self):
        self.stop_requested.set()
        if self.process.pid is None:
            self.queue.close()
            self.queue.cancel_join_thread()
            return self._shutdown_summary(stopped=True, forced=False)
        self.process.join(timeout=3)
        forced = self.process.is_alive()
        if forced:
            self.process.terminate()
            self.process.join(timeout=2)
        if self.process.is_alive():
            self.process.kill()
            self.process.join(timeout=2)
        stopped = not self.process.is_alive()
        #channel is never reused on resume, even after forced shutdown
        self.queue.close()
        self.queue.cancel_join_thread()
        return self._shutdown_summary(stopped=stopped, forced=forced)

    def _shutdown_summary(self, *, stopped, forced):
        produced, enqueued, dropped = self.produced.value, self.enqueued.value, self.dropped.value
        staged = produced - enqueued - dropped
        queued = enqueued - self.dequeued
        balanced = (min(produced, enqueued, dropped, staged, queued, self.dequeued) >= 0
                    and produced == self.dequeued + dropped + staged + queued)
        return {
            "stopped": stopped, "forced": forced,
            "failed": self.failed.is_set(), "exit_code": self.process.exitcode,
            "producer_records": produced, "enqueued_records": enqueued,
            "parent_dequeued_records": self.dequeued, "ipc_dropped_records": dropped,
            "staged_discarded_records": staged, "queued_discarded_records": queued,
            "record_accounting_balanced": balanced,
        }

class LocalOnlyFirebaseClient:
    """no network implementation exists here; retain bounded retry digests only"""

    def __init__(self):
        self.offline = False
        self.digests = OrderedDict()
        self.delivered = 0

    def store_immutable(self, path, payload):
        if self.offline:
            raise FirebaseUnavailableError("simulated_offline")
        digest = sha256(json.dumps(
            {k: v for k, v in payload.items() if k != "uploaded_at_sgt"},
            sort_keys=True,
        ).encode()).hexdigest()
        if path in self.digests and self.digests[path] != digest:
            raise FirebaseConflictError("simulated_conflict")
        self.digests[path] = digest
        if len(self.digests) > 4096:
            self.digests.popitem(last=False)
        self.delivered += 1

class SandboxFirebase:
    """real projector/outbox/retry; local fake remote and owned temporary files."""

    def __init__(self, *, now=sgt_now, temp_parent=None):
        self.directory = TemporaryDirectory(prefix="aria-phase13-outbox-", dir=temp_parent)
        self.client = LocalOnlyFirebaseClient()
        try:
            self.sync = FirebasePredictionSync(
                client=self.client, outbox_path=self.directory.name, now=now
            )
        except BaseException:
            self.directory.cleanup()
            raise
        self.lock = Lock()
        self.stop_requested = Event()
        self.worker = None
        self.errors = 0
        self.discarded = 0

    def on_prediction(self, record):
        with self.lock:
            try:
                if len(self.sync.outbox.pending()) >= 512:
                    self.errors += 1
                    return False
                accepted = self.sync.on_prediction(record)
                if self.sync.last_callback_status == "queue_error":
                    self.errors += 1
                return accepted
            except Exception:
                self.errors += 1
                return False

    def flush(self, now=None):
        with self.lock:
            try:
                return self.sync.flush_due(now=now, limit=8)
            except Exception:
                self.errors += 1
                return {"failure": "queue_error"}

    def start(self):
        def work():
            while not self.stop_requested.wait(.25):
                self.flush()
        self.worker = Thread(target=work, name="aria-phase13-local-cloud", daemon=True)
        self.worker.start()

    def set_offline(self, value):
        with self.lock:
            self.client.offline = value

    def purge(self):
        with self.lock:
            pending = self.sync.outbox.pending()
            for item in pending:
                self.sync.outbox.remove(item["payload"])
            self.discarded += len(pending)
            self.client.digests.clear()

    def summary(self):
        with self.lock:
            return {
                "mode": "local_simulation_no_network",
                "offline": self.client.offline,
                "pending": len(self.sync.outbox.pending()),
                "simulated_deliveries": self.client.delivered,
                "queue_errors": self.errors,
                "discarded_at_privacy_or_shutdown": self.discarded,
            }

    def close(self):
        self.stop_requested.set()
        if self.worker is not None:
            self.worker.join(timeout=3)
            if self.worker.is_alive():
                raise RuntimeSafetyError("cloud_worker_did_not_stop")
        self.purge()
        self.directory.cleanup()
