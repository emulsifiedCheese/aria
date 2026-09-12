"""durable, privacy-bounded Phase 12.3 Firebase prediction delivery"""
from __future__ import annotations
from datetime import datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Callable
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from aria.timebase import SGT, sgt_now

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "phase_12_3_firebase.json"
EXPECTED_CONFIG_ID = "zone-a-phase12.3-firebase-v1"
EXPECTED_CONFIG_SHA256 = (
    "48e3cb907c7586e43dcf9bc956331408df557c739c2e1f581b55e30b2bbb2afb"
)

class FirebaseSyncError(RuntimeError):
    """safe base error for the Phase 12.3 cloud boundary"""

class FirebasePayloadError(FirebaseSyncError):
    """raised when a prediction cannot cross the frozen cloud schema"""

class FirebaseOutboxError(FirebaseSyncError):
    """raised when durable local queue state cannot be preserved"""

class FirebaseUnavailableError(FirebaseSyncError):
    """raised for an unavailable or unauthenticated Firebase connection"""

class FirebaseConflictError(FirebaseSyncError):
    """raised when an immutable remote ID already has different content"""

def _sha256(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _load_object(path, *, label, error_type=FirebaseSyncError):
    try:
        with Path(path).open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise error_type(f"cannot load {label}") from error
    if not isinstance(value, dict):
        raise error_type(f"{label} must contain a JSON object")
    return value

def _timestamp(value=None):
    value = value or sgt_now()
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise FirebasePayloadError("timestamp must be timezone-aware")
    return value.astimezone(SGT).isoformat(timespec="milliseconds")


def _parse_timestamp(value, *, error_type=FirebaseOutboxError):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise error_type("invalid outbox timestamp") from error
    if parsed.tzinfo is None:
        raise error_type("outbox timestamp must be timezone-aware")
    return parsed.astimezone(SGT)

def _same_immutable_prediction(left, right):
    """compare retry content while allowing the original upload time to remain"""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    return {key: value for key, value in left.items() if key != "uploaded_at_sgt"} == {key: value for key, value in right.items() if key != "uploaded_at_sgt"}

class FirebaseContract:
    """load and verify every artifact pinned by the frozen Phase 12.3 contract"""

    def __init__(self, config_path=DEFAULT_CONFIG_PATH, *, project_root=PROJECT_ROOT):
        self.project_root = Path(project_root).resolve()
        self.config_path = Path(config_path).resolve()
        if _sha256(self.config_path) != EXPECTED_CONFIG_SHA256:
            raise FirebaseSyncError("Phase 12.3 Firebase contract hash mismatch")
        self.config = _load_object(self.config_path, label="Firebase contract")
        if self.config.get("config_id") != EXPECTED_CONFIG_ID:
            raise FirebaseSyncError("unsupported Phase 12.3 Firebase contract")
        if self.config.get("scope", {}).get("participant_upload_authorized") is not False:
            raise FirebaseSyncError("participant upload boundary differs from frozen contract")
        if self.config.get("firebase", {}).get("product") != "realtime_database":
            raise FirebaseSyncError("Firebase product differs from frozen contract")

        inputs = self.config["inputs"]
        self.source_schema_path = self._verified_path(
            inputs["prediction_schema_path"],
            inputs["prediction_schema_sha256"],
            "source prediction schema",
        )
        self.cloud_schema_path = self._verified_path(
            inputs["firebase_prediction_schema_path"],
            inputs["firebase_prediction_schema_sha256"],
            "Firebase prediction schema",
        )
        self._verified_path(
            inputs["inference_contract_path"],
            inputs["inference_contract_sha256"],
            "inference contract",
        )
        self._verified_path(
            inputs["database_rules_path"],
            inputs["database_rules_sha256"],
            "database rules",
        )
        self.source_validator = self._validator(self.source_schema_path)
        self.cloud_validator = self._validator(self.cloud_schema_path)

    def _verified_path(self, relative_path, expected_hash, label):
        path = (self.project_root / relative_path).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError as error:
            raise FirebaseSyncError(f"{label} escapes the project root") from error
        if not path.is_file() or _sha256(path) != expected_hash:
            raise FirebaseSyncError(f"{label} is unavailable or changed")
        return path

    @staticmethod
    def _validator(path):
        schema = _load_object(path, label="JSON schema")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:
            raise FirebaseSyncError("invalid frozen JSON schema") from error
        return Draft202012Validator(schema, format_checker=FormatChecker())

    def project(self, prediction, *, uploaded_at=None):
        """reduce one local prediction to the exact non-identifying cloud shape"""
        try:
            self.source_validator.validate(prediction)
        except ValidationError as error:
            raise FirebasePayloadError("source prediction does not satisfy the frozen schema") from error

        payload = {
            "schema_version": self.config["inputs"]["firebase_prediction_schema_version"],
            "prediction_id": prediction["prediction_id"],
            "emitted_at_sgt": prediction["emitted_at_sgt"],
            "uploaded_at_sgt": _timestamp(uploaded_at),
            "zone": prediction["zone"],
            "model_version": prediction["model_version"],
            "preprocessing_version": prediction["preprocessing_version"],
            "prediction_available": prediction["prediction_available"],
            "availability": dict(prediction["availability"]),
        }
        if prediction["prediction_available"]:
            payload["predicted_activity"] = prediction["predicted_activity"]
            payload["confidence"] = prediction["confidence"]
        else:
            payload["unavailable_reason"] = prediction["unavailable_reason"]
        try:
            self.cloud_validator.validate(payload)
        except ValidationError as error:
            raise FirebasePayloadError("projected prediction does not satisfy the Firebase schema") from error
        if set(payload) - set(self.config["payload"]["allowed_fields"]):
            raise FirebasePayloadError("projected prediction contains a forbidden field")
        return payload

class DurableFirebaseOutbox:
    """atomic, restart-safe queue containing only schema-valid cloud payloads"""

    def __init__(self, path, *, validator, backoff_seconds, now: Callable = sgt_now):
        self.path = Path(path)
        self.validator = validator
        self.backoff_seconds = tuple(backoff_seconds)
        if not self.backoff_seconds or any(value <= 0 for value in self.backoff_seconds):
            raise FirebaseOutboxError("retry backoff must contain positive values")
        self.now = now
        self._lock = Lock()
        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise FirebaseOutboxError("cannot create Firebase outbox") from error

    def _path_for(self, prediction_id):
        if not isinstance(prediction_id, str) or not prediction_id.startswith("prediction_"):
            raise FirebaseOutboxError("invalid prediction ID for outbox")
        return self.path / f"{prediction_id}.json"

    def _atomic_write(self, destination, value):
        temporary = destination.with_suffix(f".tmp-{os.getpid()}")
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
            directory_fd = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise FirebaseOutboxError("cannot persist Firebase outbox record") from error

    def _read(self, path):
        envelope = _load_object(path, label="Firebase outbox record", error_type=FirebaseOutboxError)
        if set(envelope) != {
            "outbox_schema_version",
            "queued_at_sgt",
            "attempt_count",
            "next_attempt_at_sgt",
            "payload",
        }:
            raise FirebaseOutboxError("invalid Firebase outbox envelope")
        if envelope["outbox_schema_version"] != 1:
            raise FirebaseOutboxError("unsupported Firebase outbox schema")
        if not isinstance(envelope["attempt_count"], int) or envelope["attempt_count"] < 0:
            raise FirebaseOutboxError("invalid Firebase outbox attempt count")
        _parse_timestamp(envelope["queued_at_sgt"])
        _parse_timestamp(envelope["next_attempt_at_sgt"])
        try:
            self.validator.validate(envelope["payload"])
        except ValidationError as error:
            raise FirebaseOutboxError("invalid payload in Firebase outbox") from error
        if path != self._path_for(envelope["payload"]["prediction_id"]):
            raise FirebaseOutboxError("Firebase outbox filename does not match payload")
        return envelope

    def enqueue(self, payload):
        try:
            self.validator.validate(payload)
        except ValidationError as error:
            raise FirebasePayloadError("invalid Firebase payload") from error
        destination = self._path_for(payload["prediction_id"])
        with self._lock:
            if destination.exists():
                existing = self._read(destination)
                if _same_immutable_prediction(existing["payload"], payload):
                    return existing["payload"], False
                raise FirebaseConflictError("conflicting prediction already queued")
            queued_at = _timestamp(self.now())
            envelope = {
                "outbox_schema_version": 1,
                "queued_at_sgt": queued_at,
                "attempt_count": 0,
                "next_attempt_at_sgt": queued_at,
                "payload": payload,
            }
            self._atomic_write(destination, envelope)
            return payload, True

    def pending(self):
        records = [self._read(path) for path in self.path.glob("prediction_*.json")]
        return sorted(records, key=lambda item: item["queued_at_sgt"])

    def due(self, now=None):
        now = (now or self.now()).astimezone(SGT)
        return [
            item
            for item in self.pending()
            if _parse_timestamp(item["next_attempt_at_sgt"]) <= now
        ]

    def mark_failed(self, payload, *, now=None):
        destination = self._path_for(payload["prediction_id"])
        with self._lock:
            envelope = self._read(destination)
            attempt = envelope["attempt_count"] + 1
            delay = self.backoff_seconds[min(attempt - 1, len(self.backoff_seconds) - 1)]
            current = (now or self.now()).astimezone(SGT)
            envelope["attempt_count"] = attempt
            envelope["next_attempt_at_sgt"] = _timestamp(current + timedelta(seconds=delay))
            self._atomic_write(destination, envelope)

    def remove(self, payload):
        destination = self._path_for(payload["prediction_id"])
        with self._lock:
            envelope = self._read(destination)
            if not _same_immutable_prediction(envelope["payload"], payload):
                raise FirebaseConflictError("delivered payload differs from queued record")
            try:
                destination.unlink()
            except OSError as error:
                raise FirebaseOutboxError("cannot remove delivered outbox record") from error

class FirebaseRealtimeDatabaseClient:
    """lazy Firebase Admin client restricted by the configured auth override"""

    def __init__(self, contract):
        self.contract = contract
        self._app = None

    def _initialize(self):
        if self._app is not None:
            return
        variable = self.contract.config["authentication"]["credential_environment_variable"]
        credential_value = os.environ.get(variable)
        if not credential_value:
            raise FirebaseUnavailableError(f"{variable} is not configured")
        credential_path = Path(credential_value).expanduser().resolve()
        try:
            credential_path.relative_to(self.contract.project_root)
        except ValueError:
            pass
        else:
            raise FirebaseUnavailableError("Firebase credential must remain outside repository")
        if not credential_path.is_file():
            raise FirebaseUnavailableError("Firebase credential file is unavailable")
        try:
            import firebase_admin
            from firebase_admin import credentials

            options = {
                "databaseURL": self.contract.config["firebase"]["database_url"],
                "databaseAuthVariableOverride": self.contract.config["authentication"][
                    "database_auth_variable_override"
                ],
            }
            self._app = firebase_admin.initialize_app(
                credentials.Certificate(str(credential_path)),
                options,
                name=f"aria-phase12-3-{id(self)}",
            )
        except Exception as error:
            raise FirebaseUnavailableError("cannot initialize Firebase client") from error

    def store_immutable(self, path, payload):
        self._initialize()
        conflict = False

        def preserve_or_create(current):
            nonlocal conflict
            if current is None:
                return payload
            if _same_immutable_prediction(current, payload):
                return current
            conflict = True
            return current

        try:
            from firebase_admin import db

            result = db.reference(path, app=self._app).transaction(preserve_or_create)
        except Exception as error:
            raise FirebaseUnavailableError("Firebase transaction failed") from error
        if conflict or not _same_immutable_prediction(result, payload):
            raise FirebaseConflictError("immutable Firebase prediction conflicts")
        return result

    def synthetic_acceptance_round_trip(self, acceptance_id, *, created_at=None):
        """write, verify and immediately delete 1 bounded synthetic marker"""
        if (
            not isinstance(acceptance_id, str)
            or not acceptance_id.startswith("acceptance_synthetic_")
            or not acceptance_id.replace("_", "").isalnum()
            or len(acceptance_id) > 80
        ):
            raise FirebasePayloadError("invalid synthetic acceptance ID")
        evidence = {
            "schema_version": 1,
            "input_scope": "synthetic",
            "participant_data_used": False,
            "created_at_sgt": _timestamp(created_at),
        }
        path = self.contract.config["firebase"]["acceptance_path_template"].format(
            acceptance_id=acceptance_id
        )
        self._initialize()
        try:
            from firebase_admin import db

            reference = db.reference(path, app=self._app)
            reference.set(evidence)
            if reference.get() != evidence:
                raise FirebaseSyncError("live acceptance read-back mismatch")
        except FirebaseSyncError:
            raise
        except Exception as error:
            raise FirebaseUnavailableError("live acceptance write/read failed") from error
        finally:
            if "reference" in locals():
                try:
                    reference.delete()
                except Exception as error:
                    raise FirebaseUnavailableError(
                        "live acceptance cleanup failed"
                    ) from error
        try:
            if reference.get() is not None:
                raise FirebaseSyncError("live acceptance record still exists")
        except FirebaseSyncError:
            raise
        except Exception as error:
            raise FirebaseUnavailableError(
                "live acceptance deletion verification failed"
            ) from error
        return {
            "write_verified": True,
            "read_verified": True,
            "delete_verified": True,
        }

class FirebasePredictionSync:
    """queue callbacks immediately and retry Firebase outside inference execution"""

    def __init__(
        self,
        *,
        contract=None,
        client=None,
        outbox_path=None,
        now: Callable = sgt_now,
    ):
        self.contract = contract or FirebaseContract()
        delivery = self.contract.config["delivery"]
        configured_path = outbox_path or (self.contract.project_root / delivery["outbox_path"])
        self.outbox = DurableFirebaseOutbox(
            configured_path,
            validator=self.contract.cloud_validator,
            backoff_seconds=delivery["retry_backoff_seconds"],
            now=now,
        )
        self.client = client or FirebaseRealtimeDatabaseClient(self.contract)
        self.now = now
        self.last_callback_status = "not_called"
        self._stop = Event()
        self._worker = None

    def enqueue(self, prediction, *, uploaded_at=None):
        payload = self.contract.project(
            prediction, uploaded_at=uploaded_at or self.now()
        )
        return self.outbox.enqueue(payload)

    def on_prediction(self, prediction):
        """non-throwing inference callback; network access never occurs here(!)"""
        try:
            _, created = self.enqueue(prediction)
        except FirebaseSyncError:
            self.last_callback_status = "queue_error"
            return False
        self.last_callback_status = "queued" if created else "already_queued"
        return created

    def _remote_path(self, payload):
        return self.contract.config["firebase"]["prediction_path_template"].format(prediction_id=payload["prediction_id"])

    def flush_due(self, *, now=None, limit=None):
        """deliver oldest due records, stopping after the first remote failure"""
        delivered = 0
        conflict = 0
        failure = None
        for envelope in self.outbox.due(now):
            if limit is not None and delivered >= limit:
                break
            payload = envelope["payload"]
            try:
                self.client.store_immutable(self._remote_path(payload), payload)
                self.outbox.remove(payload)
                delivered += 1
            except FirebaseConflictError:
                conflict += 1
                failure = "conflict"
                break
            except FirebaseSyncError:
                self.outbox.mark_failed(payload, now=now)
                failure = "unavailable"
                break
            except Exception:
                self.outbox.mark_failed(payload, now=now)
                failure = "unavailable"
                break
        return {
            "delivered": delivered,
            "conflicts": conflict,
            "pending": len(self.outbox.pending()),
            "failure": failure,
        }

    def start_worker(self, *, poll_seconds=0.5):
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self._worker is not None and self._worker.is_alive():
            return self._worker
        self._stop.clear()

        def run():
            while not self._stop.wait(poll_seconds):
                self.flush_due()

        self._worker = Thread(target=run, name="aria-firebase-sync", daemon=True)
        self._worker.start()
        return self._worker

    def stop_worker(self, *, timeout=2.0):
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=timeout)
        return self._worker is None or not self._worker.is_alive()
