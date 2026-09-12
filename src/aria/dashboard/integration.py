"""in-mem integration between Phase 12.1 inference and local dashboard"""
from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from aria.dashboard.state import DashboardStateAggregator, DashboardStateError
from aria.inference.orchestrator import LocalInferenceOrchestrator
from aria.inference.service import LocalInferenceService
from aria.ingestion.record_schema import validate_esp_record

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CAMERA_SCHEMA_PATH = PROJECT_ROOT / "schemas" / "camera_track.schema.json"

class DashboardIntegrationError(RuntimeError):
    """raised when producer cannot cross dashboard integration boundary"""

class PrivacyGateError(DashboardIntegrationError):
    """raised when inference is attempted while the verified mask is unavailable"""

def _camera_validator():
    try:
        schema = json.loads(CAMERA_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DashboardIntegrationError("cannot load Camera A record schema") from error
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:
        raise DashboardIntegrationError("invalid Camera A record schema") from error
    return Draft202012Validator(schema, format_checker=FormatChecker())

class LocalDashboardIntegration:
    """connect validated local producer summaries without retaining raw inputs"""

    def __init__(
        self, *, aggregator=None, service=None, writer=None, firebase_sync=None
    ):
        self.aggregator = aggregator or DashboardStateAggregator()
        self.service = service or LocalInferenceService()
        self.firebase_sync = firebase_sync
        self.camera_validator = _camera_validator()
        self.orchestrator = LocalInferenceOrchestrator(
            self.service,
            writer=writer,
            on_prediction=self._on_prediction,
        )

    def _on_prediction(self, prediction):
        """update local state first, then enqueue an isolated optional cloud copy."""
        accepted = self.aggregator.on_prediction(prediction)
        if self.firebase_sync is not None:
            self.firebase_sync.on_prediction(prediction)
        return accepted

    def _validate_camera_record(self, record):
        if not isinstance(record, dict):
            raise DashboardIntegrationError("camera record must be an object")
        schema_record = {key: value for key, value in record.items() if key != "_timestamp"}
        try:
            self.camera_validator.validate(schema_record)
        except ValidationError as error:
            raise DashboardIntegrationError("invalid Camera A record") from error
        if record.get("camera_id") != "camera_a" or record.get("zone") != "A":
            raise DashboardIntegrationError("only Camera A in Zone A is accepted")
        return record

    @staticmethod
    def _validate_sensor_record(record):
        if not isinstance(record, dict):
            raise DashboardIntegrationError("ESP record must be an object")
        try:
            schema_record = {key: value for key, value in record.items() if key != "_timestamp"}
            validate_esp_record(schema_record)
        except (ValueError, KeyError) as error:
            raise DashboardIntegrationError("invalid active ESP record") from error
        return record

    def on_camera_record(self, record, *, capture_fps, processing_fps):
        """validate 1 metadata-only Camera A record and update camera health"""
        self._validate_camera_record(record)

        available = record.get("frame_available") is True
        try:
            self.aggregator.update_camera(
                available=available,
                last_frame_at=record.get("frame_timestamp_sgt") if available else None,
                capture_fps=capture_fps if available else None,
                processing_fps=processing_fps if available else None,
            )
        except DashboardStateError as error:
            raise DashboardIntegrationError("invalid Camera A health update") from error

    def on_camera_unavailable(self):
        """clear cam A availability without reusing an earlier frame timestamp"""
        self.aggregator.update_camera(available=False)

    def on_sensor_record(self, record):
        """validate 1 ESP receive envelope and update only dashboard health state"""
        self._validate_sensor_record(record)
        try:
            return self.aggregator.update_sensor(record["payload"], record["received_at_sgt"])
        except (KeyError, DashboardStateError) as error:
            raise DashboardIntegrationError("invalid active ESP record") from error

    def set_mask_verified(self, verified):
        """forward explicit runtime mask-verification transition"""
        try:
            self.aggregator.set_mask_verified(verified)
        except DashboardStateError as error:
            raise DashboardIntegrationError("invalid privacy-mask state") from error

    def process_completed_window(
        self,
        *,
        session_id,
        window_start,
        camera_records,
        sensor_records,
        emitted_at=None,
    ):
        """run frozen model and deliver its safe callback to the dashboard"""
        if not self.aggregator.mask_verified:
            raise PrivacyGateError("privacy mask is not verified; completed-window inference is paused")
        for record in camera_records:
            self._validate_camera_record(record)
        if not isinstance(sensor_records, dict):
            raise DashboardIntegrationError("sensor records must be grouped by active node")
        for node_id, records in sensor_records.items():
            for record in records:
                self._validate_sensor_record(record)
                if record["payload"]["node_id"] != node_id:
                    raise DashboardIntegrationError("ESP record is grouped under the wrong active node")
        return self.orchestrator.process_completed_window(
            session_id=session_id,
            window_start=window_start,
            camera_records=camera_records,
            sensor_records=sensor_records,
            emitted_at=emitted_at,
        )

    def snapshot(self, now=None):
        """return integration's schema-valid dashboard snapshot"""
        return self.aggregator.snapshot(now)