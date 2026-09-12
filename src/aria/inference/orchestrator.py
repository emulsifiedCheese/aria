"""completed-window orchestration and idempotent local prediction delivery"""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from threading import Lock
from jsonschema import ValidationError
from aria.fusion.window_builder import ACTIVE_NODES, DEFAULT_WINDOW_SECONDS, _window_start
from aria.inference.preprocessing import build_track_feature_window
from aria.inference.service import InferenceInputError, LocalInferenceService
from aria.timebase import SGT

class PredictionDeliveryError(RuntimeError):
    """raised when local prediction log cannot preserve its schema or idempotency"""

class LocalPredictionWriter:
    """append schema-valid predictions once per deterministic prediction id"""

    def __init__(self, output_path, *, validator):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.validator = validator
        self._records = {}
        self._lock = Lock()
        self._load_existing()

    def _load_existing(self):
        if not self.output_path.exists():
            return
        try:
            with self.output_path.open(encoding="utf-8") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        self.validator.validate(record)
                    except (json.JSONDecodeError, ValidationError) as error:
                        raise PredictionDeliveryError(
                            f"invalid existing prediction at line {line_number}: {error}"
                        ) from error
                    prediction_id = record["prediction_id"]
                    previous = self._records.get(prediction_id)
                    if previous is not None and previous != record:
                        raise PredictionDeliveryError(f"conflicting existing prediction ID: {prediction_id}")
                    self._records[prediction_id] = record
        except OSError as error:
            raise PredictionDeliveryError(f"cannot read prediction log: {error}") from error

    def append(self, record):
        """append new record, returning false for an identical retry"""
        try:
            self.validator.validate(record)
        except ValidationError as error:
            raise PredictionDeliveryError(f"prediction schema failure: {error.message}") from error
        prediction_id = record["prediction_id"]
        with self._lock:
            previous = self._records.get(prediction_id)
            if previous is not None:
                if previous == record:
                    return False
                raise PredictionDeliveryError(f"conflicting prediction retry: {prediction_id}")
            encoded = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            try:
                with self.output_path.open("a", encoding="utf-8") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as error:
                raise PredictionDeliveryError(f"cannot append prediction: {error}") from error
            self._records[prediction_id] = record
            return True

class LocalInferenceOrchestrator:
    """build and deliver predictions for 1 explicitly completed 2s window"""

    def __init__(self, service=None, *, writer=None, on_prediction=None):
        self.service = service or LocalInferenceService()
        self.writer = writer
        self.on_prediction = on_prediction
        if writer is not None and writer.validator is not self.service.prediction_validator:
            if writer.validator.schema != self.service.prediction_validator.schema:
                raise PredictionDeliveryError("writer and service prediction schemas differ")

    def process_completed_window(
        self,
        *,
        session_id,
        window_start,
        camera_records,
        sensor_records,
        emitted_at=None,
    ):
        if not isinstance(window_start, datetime) or window_start.tzinfo is None:
            raise InferenceInputError("window_start must be a timezone-aware datetime")
        window_start = window_start.astimezone(SGT)
        if window_start != _window_start(window_start, DEFAULT_WINDOW_SECONDS):
            raise InferenceInputError("window_start must align to a two-second boundary")
        if not isinstance(sensor_records, dict) or set(sensor_records) != set(ACTIVE_NODES):
            raise InferenceInputError("sensor_records must contain exactly ESP-A1 and ESP-A2")

        tracks = defaultdict(list)
        for record in camera_records:
            if record.get("record_type") != "track":
                continue
            track_id = record.get("local_track_id")
            if not isinstance(track_id, int) or isinstance(track_id, bool) or track_id < 0:
                raise InferenceInputError("camera track record has an invalid local_track_id")
            tracks[track_id].append(record)
        track_ids = sorted(tracks) if tracks else [None]
        if emitted_at is None:
            emitted_at = window_start + timedelta(seconds=DEFAULT_WINDOW_SECONDS)

        records = []
        written = 0
        for track_id in track_ids:
            feature_vector = build_track_feature_window(
                window_start,
                tracks.get(track_id, []),
                sensor_records,
                local_track_id=track_id,
                keypoint_confidence=self.service.config["preprocessing"][
                    "keypoint_confidence_threshold"
                ],
            )
            prediction = self.service.predict(
                session_id=session_id,
                local_track_id=track_id,
                feature_vector=feature_vector,
                emitted_at=emitted_at,
            )
            if self.writer is None or self.writer.append(prediction):
                written += int(self.writer is not None)
                if self.on_prediction is not None:
                    self.on_prediction(prediction)
            records.append(prediction)
        return {"predictions": records, "written_count": written}