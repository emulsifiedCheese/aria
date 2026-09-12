"""thread-safe, schema-valid Phase 12.2 dashboard snapshots"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import yaml
from aria.ingestion.node_monitor import NodeMonitor
from aria.timebase import SGT, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_2_dashboard.json"
FROZEN_CONFIG_SHA256 = "1fcd1343f854691e2bce3fabb22b4f9b6f2b048a6d94e9406a7d31be1dcaca76"

class DashboardStateError(RuntimeError):
    """raised when dashboard input or state violates the frozen contract"""

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _load_json(path, *, purpose):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DashboardStateError(f"cannot load {purpose}: {path}") from error
    if not isinstance(value, dict):
        raise DashboardStateError(f"{purpose} must be a JSON object")
    return value

def _as_sgt(value, *, field):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise DashboardStateError(f"{field} must be an ISO timestamp") from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DashboardStateError(f"{field} must be timezone-aware")
    value = value.astimezone(SGT)
    return value

def _timestamp(value):
    return value.isoformat(timespec="milliseconds")

class DashboardStateAggregator:
    """combine local prediction, camera and ESP health into 1 safe snapshot"""

    def __init__(self, config_path=DEFAULT_CONFIG_PATH, *, node_monitor=None):
        self.config_path = Path(config_path).resolve()
        if self.config_path == DEFAULT_CONFIG_PATH.resolve():
            if _sha256(self.config_path) != FROZEN_CONFIG_SHA256:
                raise DashboardStateError("frozen dashboard contract hash mismatch")
        self.config = _load_json(self.config_path, purpose="dashboard contract")
        self._lock = Lock()
        self.node_monitor = node_monitor or NodeMonitor()

        inputs = self.config["inputs"]
        for path_key, hash_key, purpose in (
            ("dashboard_state_schema_path", "dashboard_state_schema_sha256", "dashboard state schema"),
            ("prediction_schema_path", "prediction_schema_sha256", "prediction schema"),
            ("inference_contract_path", "inference_contract_sha256", "inference contract"),
            ("camera_config_path", "camera_config_sha256", "camera config"),
            ("mask_config_path", "mask_config_sha256", "mask config"),
        ):
            path = PROJECT_ROOT / inputs[path_key]
            if not path.is_file() or _sha256(path) != inputs[hash_key]:
                raise DashboardStateError(f"{purpose} hash mismatch")

        state_schema = _load_json(
            PROJECT_ROOT / inputs["dashboard_state_schema_path"],
            purpose="dashboard state schema",
        )
        prediction_schema = _load_json(
            PROJECT_ROOT / inputs["prediction_schema_path"],
            purpose="prediction schema",
        )
        try:
            Draft202012Validator.check_schema(state_schema)
            Draft202012Validator.check_schema(prediction_schema)
        except Exception as error:
            raise DashboardStateError("dashboard contract contains an invalid schema") from error
        self.state_validator = Draft202012Validator(state_schema, format_checker=FormatChecker())
        self.prediction_validator = Draft202012Validator(prediction_schema, format_checker=FormatChecker())

        try:
            mask_config = yaml.safe_load((PROJECT_ROOT / inputs["mask_config_path"]).read_text(encoding="utf-8"))
            camera_mask = mask_config["masks"][self.config["scope"]["camera_id"]]
        except (OSError, KeyError, TypeError, yaml.YAMLError) as error:
            raise DashboardStateError("cannot load frozen Camera A mask state") from error
        if camera_mask.get("mask_config_version") != inputs["mask_config_version"]:
            raise DashboardStateError("Camera A mask version does not match dashboard contract")

        self._mask_verified = camera_mask.get("verified") is True
        self._camera = {
            "available": False,
            "last_frame_at": None,
            "capture_fps": None,
            "processing_fps": None,
        }
        self._predictions = {}
        self._predictions_by_id = {}
        self._current_window_id = None
        self._current_window_emitted_at = None
        self._sensor_counters = {}

    def set_mask_verified(self, verified):
        """update runtime verification state; only explicit bool is accepted"""
        if not isinstance(verified, bool):
            raise DashboardStateError("mask_verified must be boolean")
        with self._lock:
            self._mask_verified = verified
            if not verified:
                # A privacy pause must remove activity immediately, not merely
                # put a warning above the previous person's prediction.
                self._predictions.clear()
                self._predictions_by_id.clear()
                self._current_window_id = None
                self._current_window_emitted_at = None
                self._camera = {
                    "available": False, "last_frame_at": None,
                    "capture_fps": None, "processing_fps": None,
                }

    @property
    def mask_verified(self):
        """return the current fail-closed privacy-gate state"""
        with self._lock:
            return self._mask_verified

    def update_camera(
        self,
        *,
        available,
        last_frame_at=None,
        capture_fps=None,
        processing_fps=None,
    ):
        if not isinstance(available, bool):
            raise DashboardStateError("camera available must be boolean")
        if available and last_frame_at is None:
            raise DashboardStateError("available camera requires last_frame_at")
        parsed_time = (
            _as_sgt(last_frame_at, field="last_frame_at")
            if last_frame_at is not None
            else None
        )
        for value, field in (
            (capture_fps, "capture_fps"),
            (processing_fps, "processing_fps"),
        ):
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or value < 0
            ):
                raise DashboardStateError(f"{field} must be non-negative or null")
        with self._lock:
            self._camera = {
                "available": available,
                "last_frame_at": parsed_time,
                "capture_fps": float(capture_fps) if capture_fps is not None else None,
                "processing_fps": (
                    float(processing_fps) if processing_fps is not None else None
                ),
            }

    def update_sensor(self, payload, received_at):
        """update active-node health and return existing diagnostic messages"""
        node_id = payload.get("node_id") if isinstance(payload, dict) else None
        if node_id not in self.config["scope"]["active_sensor_nodes"]:
            raise DashboardStateError("dashboard accepts only ESP-A1 and ESP-A2")
        with self._lock:
            try:
                messages = self.node_monitor.update(payload, received_at)
            except (KeyError, TypeError, ValueError) as error:
                raise DashboardStateError("invalid sensor health update") from error
            self._update_sensor_counters(payload)
            return messages

    def _update_sensor_counters(self, payload):
        node_id = payload["node_id"]
        sequence = payload["sequence"]
        boot_id = payload["boot_id"]
        counters = self._sensor_counters.get(node_id)
        if counters is None:
            self._sensor_counters[node_id] = {
                "sequence": sequence,
                "boot_id": boot_id,
                "packets_received": 1,
                "packet_gap_events": 0,
                "estimated_packets_lost": 0,
            }
            return

        counters["packets_received"] += 1
        if boot_id != counters["boot_id"]:
            counters["sequence"] = sequence
            counters["boot_id"] = boot_id
        elif sequence > counters["sequence"]:
            if sequence > counters["sequence"] + 1:
                counters["packet_gap_events"] += 1
                counters["estimated_packets_lost"] += sequence - counters["sequence"] - 1
            counters["sequence"] = sequence

    def on_prediction(self, record):
        """accept a schema-valid prediction callback without retaining its session id"""
        try:
            self.prediction_validator.validate(record)
        except ValidationError as error:
            raise DashboardStateError(
                f"prediction schema failure: {error.message}"
            ) from error

        safe_record = {
            key: deepcopy(record[key])
            for key in (
                "prediction_id",
                "window_id",
                "local_track_id",
                "emitted_at_sgt",
                "prediction_available",
                "predicted_activity",
                "confidence",
                "unavailable_reason",
                "availability",
            )
        }
        emitted_at = _as_sgt(record["emitted_at_sgt"], field="emitted_at_sgt")
        prediction_id = safe_record["prediction_id"]

        with self._lock:
            previous = self._predictions_by_id.get(prediction_id)
            if previous is not None:
                if previous != safe_record:
                    raise DashboardStateError(
                        f"conflicting prediction retry: {prediction_id}"
                    )
                return False

            if (
                self._current_window_emitted_at is not None
                and emitted_at < self._current_window_emitted_at
            ):
                return False
            if record["window_id"] != self._current_window_id:
                self._predictions.clear()
                self._predictions_by_id.clear()
                self._current_window_id = record["window_id"]
                self._current_window_emitted_at = emitted_at

            self._predictions[safe_record["local_track_id"]] = safe_record
            self._predictions_by_id[prediction_id] = safe_record
            return True

    def snapshot(self, now=None):
        now = _as_sgt(now or sgt_now(), field="now")
        with self._lock:
            state = self._build_state(now)
        try:
            self.state_validator.validate(state)
        except ValidationError as error:
            raise DashboardStateError(
                f"dashboard state schema failure: {error.message}"
            ) from error
        return deepcopy(state)

    def _build_state(self, now):
        policy = self.config["state_policy"]
        camera = self._camera_state(now, policy)
        sensors = {
            node_id: self._sensor_state(node_id, now, policy)
            for node_id in self.config["scope"]["active_sensor_nodes"]
        }
        predictions = [
            self._prediction_state(record, now, policy)
            for _, record in sorted(
                self._predictions.items(),
                key=lambda item: (-1 if item[0] is None else item[0]),
            )
        ]
        warnings = self._warning_state(camera, sensors, predictions, policy)
        if not self._mask_verified:
            overall_status = "blocked"
        elif warnings:
            overall_status = "degraded"
        else:
            overall_status = "ready"

        state = {
            "schema_version": self.config["inputs"]["dashboard_state_schema_version"],
            "dashboard_version": policy["dashboard_version"],
            "generated_at_sgt": _timestamp(now),
            "zone": self.config["scope"]["zone"],
            "overall_status": overall_status,
            "privacy": {
                "local_only": True,
                "mask_verified": self._mask_verified,
                "privacy_ready": self._mask_verified,
                "video_enabled": False,
            },
            "camera": camera,
            "sensors": sensors,
            "predictions": predictions,
            "warnings": warnings,
        }
        digest = sha256(
            json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        state["snapshot_id"] = f"dashboard_{digest}"
        return state

    def _camera_state(self, now, policy):
        last_frame_at = self._camera["last_frame_at"]
        age = (
            max(0.0, (now - last_frame_at).total_seconds())
            if last_frame_at is not None
            else None
        )
        fresh = (
            self._camera["available"]
            and age is not None
            and age <= policy["camera_stale_after_seconds"]
        )
        return {
            "camera_id": self.config["scope"]["camera_id"],
            "available": self._camera["available"],
            "fresh": fresh,
            "last_frame_at_sgt": _timestamp(last_frame_at) if last_frame_at else None,
            "age_seconds": round(age, 3) if age is not None else None,
            "capture_fps": self._camera["capture_fps"],
            "processing_fps": self._camera["processing_fps"],
            "mask_verified": self._mask_verified,
        }

    def _sensor_state(self, node_id, now, policy):
        node = self.node_monitor.nodes.get(node_id)
        if node is None:
            return {
                "available": False,
                "fresh": False,
                "stale": False,
                "last_received_at_sgt": None,
                "age_seconds": None,
                "packets_received": 0,
                "packet_gap_events": 0,
                "estimated_packets_lost": 0,
                "packet_loss_percent": None,
            }
        last_received = _as_sgt(node["received_at"], field="received_at")
        age = max(0.0, (now - last_received).total_seconds())
        stale = age > policy["sensor_stale_after_seconds"]
        counters = self._sensor_counters.get(node_id, {})
        received = counters.get("packets_received", 0)
        lost = counters.get("estimated_packets_lost", 0)
        denominator = received + lost
        loss_percent = (100.0 * lost / denominator) if denominator else None
        return {
            "available": True,
            "fresh": not stale,
            "stale": stale,
            "last_received_at_sgt": _timestamp(last_received),
            "age_seconds": round(age, 3),
            "packets_received": received,
            "packet_gap_events": counters.get("packet_gap_events", 0),
            "estimated_packets_lost": lost,
            "packet_loss_percent": (
                round(loss_percent, 6) if loss_percent is not None else None
            ),
        }

    @staticmethod
    def _prediction_state(record, now, policy):
        emitted_at = _as_sgt(record["emitted_at_sgt"], field="emitted_at_sgt")
        age = max(0.0, (now - emitted_at).total_seconds())
        return {
            **deepcopy(record),
            "age_seconds": round(age, 3),
            "stale": age > policy["prediction_stale_after_seconds"],
        }

    def _warning_state(self, camera, sensors, predictions, policy):
        warnings = []

        def add(code, severity, source):
            value = {"code": code, "severity": severity, "source": source}
            if value not in warnings:
                warnings.append(value)

        if not self._mask_verified:
            add("mask_unverified", "critical", "privacy")
        if not camera["available"]:
            add("camera_unavailable", "warning", "camera_a")
        elif not camera["fresh"]:
            add("camera_stale", "warning", "camera_a")

        for node_id, sensor in sensors.items():
            prefix = node_id.lower().replace("-", "_")
            if not sensor["available"]:
                add(f"{prefix}_unavailable", "warning", node_id)
            elif sensor["stale"]:
                add(f"{prefix}_stale", "warning", node_id)
            if (
                sensor["packets_received"] >= policy["packet_loss_warning_min_packets"]
                and sensor["packet_loss_percent"] is not None
                and sensor["packet_loss_percent"] > policy["packet_loss_warning_percent"]
            ):
                add(f"{prefix}_packet_loss", "warning", node_id)

        if not predictions:
            add("prediction_unavailable", "warning", "inference")
        for prediction in predictions:
            if prediction["stale"]:
                add("prediction_stale", "warning", "inference")
            if not prediction["prediction_available"]:
                if prediction["unavailable_reason"] == "model_error":
                    add("model_error", "critical", "inference")
                else:
                    add("prediction_unavailable", "warning", "inference")
            if not prediction["availability"]["pose_available"]:
                add("pose_unavailable", "info", "inference")
        return sorted(warnings, key=lambda item: (item["severity"], item["source"], item["code"]))
