"""fail-closed Phase 12.1 local activity inference service"""
from __future__ import annotations
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import joblib
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import numpy as np
from aria.inference.preprocessing import (
    camera_feature_matrix,
)
from aria.modeling.missing_modality import EXPECTED_POLICY, apply_missing_modality_policy
from aria.timebase import SGT

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_1_inference.json"
EXPECTED_CONFIG_ID = "zone-a-phase12.1-local-inference-v1"
EXPECTED_CONFIG_SHA256 = ("68fa975e859a386c32d991557a88303b1f403f23b5886ff4dbf5093c49befba8")

class InferenceStartupError(RuntimeError):
    """raised before inference when a frozen artifact or contract check fails"""

class InferenceInputError(ValueError):
    """raised when an input cannot produce a schema-valid prediction record"""

def _sha256(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path, *, purpose):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise InferenceStartupError(f"Cannot load {purpose}: {error}") from error
    if not isinstance(value, dict):
        raise InferenceStartupError(f"{purpose} must contain a JSON object")
    return value

def _validator(path, *, purpose):
    schema = _load_json(path, purpose=purpose)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:
        raise InferenceStartupError(f"Invalid {purpose}: {error}") from error
    return Draft202012Validator(schema, format_checker=FormatChecker())

def _sgt_text(value):
    if value is None:
        value = datetime.now(tz=SGT)
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InferenceInputError("emitted_at must be a timezone-aware datetime")
    return value.astimezone(SGT).isoformat(timespec="milliseconds")

class LocalInferenceService:
    """load frozen model once and produce stateless local predictions"""

    def __init__(self, config_path=DEFAULT_CONFIG_PATH, *, project_root=PROJECT_ROOT):
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path)
        if _sha256(self.config_path) != EXPECTED_CONFIG_SHA256:
            raise InferenceStartupError("Phase 12.1 inference contract hash mismatch")
        self.config = _load_json(self.config_path, purpose="inference contract")
        self._validate_contract()

        preprocessing = self.config["preprocessing"]
        self.feature_schema_path = self._verified_path(
            preprocessing["feature_schema_path"],
            preprocessing["feature_schema_sha256"],
            "feature schema",
        )
        self.prediction_schema_path = self._verified_path(
            preprocessing["prediction_schema_path"],
            preprocessing["prediction_schema_sha256"],
            "prediction schema",
        )
        model_config = self.config["model"]
        self.model_path = self._verified_path(
            model_config["artifact_path"],
            model_config["artifact_sha256"],
            "model artifact",
        )
        self.feature_validator = _validator(
            self.feature_schema_path,
            purpose="feature schema",
        )
        self.prediction_validator = _validator(
            self.prediction_schema_path,
            purpose="prediction schema",
        )
        try:
            self.model = joblib.load(self.model_path)
        except Exception as error:
            raise InferenceStartupError(f"Cannot load frozen model: {error}") from error
        self._validate_model()

    def _verified_path(self, relative_path, expected_hash, purpose):
        path = (self.project_root / relative_path).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError as error:
            raise InferenceStartupError(f"{purpose} escapes the project root") from error
        if not path.is_file():
            raise InferenceStartupError(f"{purpose} is unavailable: {relative_path}")
        if _sha256(path) != expected_hash:
            raise InferenceStartupError(f"{purpose} hash mismatch")
        return path

    def _validate_contract(self):
        if self.config.get("config_id") != EXPECTED_CONFIG_ID:
            raise InferenceStartupError("unsupported Phase 12.1 inference contract")
        scope = self.config.get("scope", {})
        if (
            scope.get("zone") != "A"
            or scope.get("camera_id") != "camera_a"
            or scope.get("active_sensor_nodes") != ["ESP-A1", "ESP-A2"]
            or scope.get("participant_collection_allowed") is not False
        ):
            raise InferenceStartupError("inference scope differs from the frozen contract")
        model = self.config.get("model", {})
        if any(
            model.get(field) is not False
            for field in (
                "fit_allowed",
                "calibration_allowed",
                "parameter_changes_allowed",
                "fallback_model_allowed",
            )
        ):
            raise InferenceStartupError("model mutation is prohibited")
        if model.get("confidence_threshold") is not None:
            raise InferenceStartupError("confidence threshold differs from the frozen contract")
        preprocessing = self.config.get("preprocessing", {})
        if (
            preprocessing.get("window_duration_ms") != 2000
            or preprocessing.get("track_scope") != "one_local_track_id"
            or preprocessing.get("cross_track_aggregation_allowed") is not False
            or len(preprocessing.get("feature_names", [])) != 23
        ):
            raise InferenceStartupError("preprocessing differs from the frozen contract")
        frozen_policy = self.config.get("missing_modality_policy", {})
        if {key: frozen_policy.get(key) for key in EXPECTED_POLICY} != EXPECTED_POLICY:
            raise InferenceStartupError("missing-modality policy differs from Phase 11.3")

    def _validate_model(self):
        classes = getattr(self.model, "classes_", None)
        feature_count = getattr(self.model, "n_features_in_", None)
        if classes is None or set(classes) != set(self.config["model"]["class_labels"]):
            raise InferenceStartupError("model classes differ from the frozen contract")
        if feature_count != len(self.config["preprocessing"]["feature_names"]):
            raise InferenceStartupError("model feature count differs from the frozen contract")
        if not callable(getattr(self.model, "predict", None)) or not callable(
            getattr(self.model, "predict_proba", None)
        ):
            raise InferenceStartupError("model does not expose frozen prediction methods")

    def _predict_camera(self, feature_vector):
        preprocessing = self.config["preprocessing"]
        matrix = camera_feature_matrix(
            feature_vector,
            feature_roots=preprocessing["feature_roots"],
            feature_names=preprocessing["feature_names"],
        )
        predicted_activity = self.model.predict(matrix)[0]
        probabilities = np.asarray(self.model.predict_proba(matrix), dtype=float)
        if probabilities.shape != (1, len(self.model.classes_)):
            raise RuntimeError("model probability shape differs from its classes")
        if not np.isfinite(probabilities).all():
            raise RuntimeError("model returned non-finite probabilities")
        classes = list(self.model.classes_)
        if predicted_activity not in classes:
            raise RuntimeError("model predicted an unknown activity")
        confidence = float(probabilities[0, classes.index(predicted_activity)])
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise RuntimeError("model returned an invalid confidence")
        if confidence != float(np.max(probabilities[0])):
            raise RuntimeError("predicted class is not the maximum-probability class")
        return str(predicted_activity), confidence

    def predict(self, *, session_id, local_track_id, feature_vector, emitted_at=None):
        """return 1 current prediction without retaining an earlier result"""
        try:
            self.feature_validator.validate(feature_vector)
        except ValidationError as error:
            raise InferenceInputError(f"feature vector schema failure: {error.message}") from error
        if local_track_id is None:
            if feature_vector["camera_available"]:
                raise InferenceInputError(
                    "local_track_id may be null only when the camera track is unavailable"
                )
        elif (
            not isinstance(local_track_id, int)
            or isinstance(local_track_id, bool)
            or local_track_id < 0
        ):
            raise InferenceInputError("local_track_id must be a non-negative integer or null")

        policy = self.config["missing_modality_policy"]
        phase_11_policy = {key: policy[key] for key in EXPECTED_POLICY}
        try:
            result = apply_missing_modality_policy(
                phase_11_policy,
                camera_available=feature_vector["camera_available"],
                a1_available=feature_vector["a1_available"],
                a2_available=feature_vector["a2_available"],
                predict_camera=lambda: self._predict_camera(feature_vector),
            )
        except Exception:
            result = {
                "prediction_available": False,
                "predicted_activity": None,
                "confidence": None,
                "unavailable_reason": "model_error",
            }

        window_id = feature_vector["window_id"]
        identity = (
            f"{session_id}|{window_id}|{local_track_id}|"
            f"{self.config['model']['version']}|"
            f"{self.config['preprocessing']['version']}"
        )
        record = {
            "schema_version": self.config["preprocessing"]["prediction_schema_version"],
            "prediction_id": "prediction_" + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "session_id": session_id,
            "window_id": window_id,
            "zone": "A",
            "local_track_id": local_track_id,
            "emitted_at_sgt": _sgt_text(emitted_at),
            "model_version": self.config["model"]["version"],
            "preprocessing_version": self.config["preprocessing"]["version"],
            "feature_schema_version": self.config["preprocessing"]["feature_schema_version"],
            "prediction_available": result["prediction_available"],
            "predicted_activity": result["predicted_activity"],
            "confidence": result["confidence"],
            "unavailable_reason": result["unavailable_reason"],
            "availability": {
                "camera_available": feature_vector["camera_available"],
                "pose_available": feature_vector["pose_available"],
                "esp_a1_available": feature_vector["a1_available"],
                "esp_a2_available": feature_vector["a2_available"],
            },
        }
        try:
            self.prediction_validator.validate(record)
        except ValidationError as error:
            raise InferenceInputError(f"prediction schema failure: {error.message}") from error
        return record