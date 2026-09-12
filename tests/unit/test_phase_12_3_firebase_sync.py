import json
from datetime import datetime, timedelta
import pytest
from aria.cloud.firebase_sync import (
    FirebaseContract,
    FirebaseConflictError,
    FirebasePayloadError,
    FirebasePredictionSync,
    FirebaseRealtimeDatabaseClient,
    FirebaseSyncError,
)
from aria.dashboard.integration import LocalDashboardIntegration
from aria.inference.service import LocalInferenceService
from aria.timebase import SGT
from scripts.run_local_dashboard import (
    _synthetic_camera_record,
    _synthetic_sensor_record,
)
from scripts.sync_firebase_predictions import main as sync_main
from scripts.accept_phase_12_3_firebase import main as live_acceptance_main

NOW = datetime(2026, 8, 24, 19, 0, 0, tzinfo=SGT)
SESSION_ID = "zone_a_20260824T190000SGT_synthetic1203"

class Clock:
    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value

class MemoryClient:
    def __init__(self, *, unavailable=False):
        self.records = {}
        self.unavailable = unavailable
        self.calls = 0

    def store_immutable(self, path, payload):
        self.calls += 1
        if self.unavailable:
            raise FirebaseSyncError("offline")
        current = self.records.get(path)
        if current is not None:
            left = {key: value for key, value in current.items() if key != "uploaded_at_sgt"}
            right = {key: value for key, value in payload.items() if key != "uploaded_at_sgt"}
            if left != right:
                raise FirebaseConflictError("conflict")
            return current
        self.records[path] = payload
        return payload

@pytest.fixture(scope="module")
def service():
    return LocalInferenceService()

def _prediction(service, *, start=NOW, camera=True):
    integration = LocalDashboardIntegration(service=service)
    observed = start + timedelta(milliseconds=250)
    camera_records = [_synthetic_camera_record(observed)] if camera else []
    sensors = {
        node: [_synthetic_sensor_record(node, observed)]
        for node in ("ESP-A1", "ESP-A2")
    }
    return integration.process_completed_window(
        session_id=SESSION_ID,
        window_start=start,
        camera_records=camera_records,
        sensor_records=sensors,
        emitted_at=start + timedelta(seconds=2),
    )["predictions"][0]

def _sync(tmp_path, *, client=None, clock=None):
    clock = clock or Clock()
    return FirebasePredictionSync(
        client=client or MemoryClient(),
        outbox_path=tmp_path / "outbox",
        now=clock,
    )

def test_projection_removes_every_local_identifier_and_feature(service, tmp_path):
    sync = _sync(tmp_path)
    payload = sync.contract.project(_prediction(service), uploaded_at=NOW)

    assert set(payload) == {
        "schema_version",
        "prediction_id",
        "emitted_at_sgt",
        "uploaded_at_sgt",
        "zone",
        "model_version",
        "preprocessing_version",
        "prediction_available",
        "predicted_activity",
        "confidence",
        "availability",
    }
    encoded = json.dumps(payload)
    for forbidden in (
        "session_id",
        "window_id",
        "local_track_id",
        "participant",
        "keypoints",
        "feature_vector",
        "raw_audio",
        "raw_video",
    ):
        assert forbidden not in encoded

def test_unavailable_projection_omits_null_fields(service, tmp_path):
    sync = _sync(tmp_path)
    payload = sync.contract.project(
        _prediction(service, start=NOW + timedelta(seconds=2), camera=False),
        uploaded_at=NOW + timedelta(seconds=4),
    )
    assert payload["prediction_available"] is False
    assert payload["unavailable_reason"] == "missing_camera_track"
    assert "predicted_activity" not in payload
    assert "confidence" not in payload

def test_invalid_or_extra_source_field_is_rejected_before_outbox(service, tmp_path):
    sync = _sync(tmp_path)
    unsafe = dict(_prediction(service), participant_id="forbidden")
    with pytest.raises(FirebasePayloadError, match="source prediction"):
        sync.enqueue(unsafe)
    assert sync.outbox.pending() == []

def test_enqueue_is_durable_private_and_idempotent(service, tmp_path):
    sync = _sync(tmp_path)
    prediction = _prediction(service)
    first, created = sync.enqueue(prediction, uploaded_at=NOW)
    retry, retried = sync.enqueue(
        prediction, uploaded_at=NOW + timedelta(seconds=30)
    )
    assert created is True
    assert retried is False
    assert retry == first
    files = list((tmp_path / "outbox").glob("*.json"))
    assert len(files) == 1
    encoded = files[0].read_text(encoding="utf-8")
    assert "session_id" not in encoded
    assert SESSION_ID not in encoded

def test_successful_delivery_removes_verified_outbox_record(service, tmp_path):
    client = MemoryClient()
    sync = _sync(tmp_path, client=client)
    payload, _ = sync.enqueue(_prediction(service), uploaded_at=NOW)
    result = sync.flush_due(now=NOW)
    path = f"aria/schema_version_1/predictions/{payload['prediction_id']}"
    assert result == {
        "delivered": 1,
        "conflicts": 0,
        "pending": 0,
        "failure": None,
    }
    assert client.records[path] == payload

def test_remote_identical_retry_is_success_without_mutating_original(service, tmp_path):
    client = MemoryClient()
    sync = _sync(tmp_path, client=client)
    prediction = _prediction(service)
    first, _ = sync.enqueue(prediction, uploaded_at=NOW)
    assert sync.flush_due(now=NOW)["delivered"] == 1
    second, _ = sync.enqueue(prediction, uploaded_at=NOW + timedelta(minutes=1))
    assert second["uploaded_at_sgt"] != first["uploaded_at_sgt"]
    assert sync.flush_due(now=NOW + timedelta(minutes=1))["delivered"] == 1
    assert next(iter(client.records.values()))["uploaded_at_sgt"] == first["uploaded_at_sgt"]

def test_conflicting_remote_retry_stays_queued(service, tmp_path):
    client = MemoryClient()
    sync = _sync(tmp_path, client=client)
    payload, _ = sync.enqueue(_prediction(service), uploaded_at=NOW)
    path = f"aria/schema_version_1/predictions/{payload['prediction_id']}"
    client.records[path] = dict(payload, confidence=0.01)
    result = sync.flush_due(now=NOW)
    assert result["failure"] == "conflict"
    assert result["conflicts"] == 1
    assert result["pending"] == 1

def test_offline_delivery_backs_off_then_recovers(service, tmp_path):
    clock = Clock()
    client = MemoryClient(unavailable=True)
    sync = _sync(tmp_path, client=client, clock=clock)
    sync.enqueue(_prediction(service), uploaded_at=NOW)
    offline = sync.flush_due(now=NOW)
    immediate = sync.flush_due(now=NOW)
    clock.value = NOW + timedelta(seconds=1)
    client.unavailable = False
    recovered = sync.flush_due(now=clock.value)
    assert offline["failure"] == "unavailable"
    assert offline["pending"] == 1
    assert immediate["delivered"] == 0
    assert client.calls == 2
    assert recovered["delivered"] == 1
    assert recovered["pending"] == 0

def test_firebase_failure_never_blocks_inference_or_dashboard(service, tmp_path):
    client = MemoryClient(unavailable=True)
    sync = _sync(tmp_path, client=client)
    integration = LocalDashboardIntegration(service=service, firebase_sync=sync)
    observed = NOW + timedelta(milliseconds=250)
    camera = _synthetic_camera_record(observed)
    sensors = {
        node: [_synthetic_sensor_record(node, observed)]
        for node in ("ESP-A1", "ESP-A2")
    }
    integration.on_camera_record(camera, capture_fps=30.0, processing_fps=7.0)
    for records in sensors.values():
        integration.on_sensor_record(records[0])

    result = integration.process_completed_window(
        session_id=SESSION_ID,
        window_start=NOW,
        camera_records=[camera],
        sensor_records=sensors,
        emitted_at=NOW + timedelta(seconds=2),
    )
    state = integration.snapshot(NOW + timedelta(seconds=2))
    failed_upload = sync.flush_due(now=NOW)

    assert len(result["predictions"]) == 1
    assert state["overall_status"] == "ready"
    assert len(state["predictions"]) == 1
    assert sync.last_callback_status == "queued"
    assert failed_upload["failure"] == "unavailable"
    assert failed_upload["pending"] == 1

def test_nonthrowing_callback_contains_local_queue_failure(service, tmp_path):
    sync = _sync(tmp_path)
    invalid = dict(_prediction(service), participant_name="forbidden")
    assert sync.on_prediction(invalid) is False
    assert sync.last_callback_status == "queue_error"

def test_cli_queue_only_requires_safe_scope_and_never_contacts_cloud(
    service, tmp_path, capsys
):
    client = MemoryClient(unavailable=True)
    sync = _sync(tmp_path, client=client)
    source = tmp_path / "predictions.jsonl"
    source.write_text(json.dumps(_prediction(service)) + "\n", encoding="utf-8")

    result = sync_main(
        [
            "--input",
            str(source),
            "--input-scope",
            "synthetic",
            "--queue-only",
        ],
        sync_factory=lambda: sync,
    )

    assert result["queued"] == 1
    assert result["pending"] == 1
    assert client.calls == 0
    assert SESSION_ID not in capsys.readouterr().out

def test_live_acceptance_client_writes_reads_and_deletes_synthetic_marker(monkeypatch):
    class Reference:
        def __init__(self):
            self.value = None
            self.deleted = False

        def set(self, value):
            self.value = value

        def get(self):
            return self.value

        def delete(self):
            self.value = None
            self.deleted = True

    reference = Reference()
    observed = {}

    def fake_reference(path, *, app):
        observed["path"] = path
        observed["app"] = app
        return reference

    import firebase_admin.db

    monkeypatch.setattr(firebase_admin.db, "reference", fake_reference)
    contract = FirebaseContract()
    client = FirebaseRealtimeDatabaseClient(contract)
    client._app = object()

    result = client.synthetic_acceptance_round_trip("acceptance_synthetic_unit1203",created_at=NOW,)

    assert result == {
        "write_verified": True,
        "read_verified": True,
        "delete_verified": True,
    }
    assert observed["path"] == ("aria/schema_version_1/acceptance/acceptance_synthetic_unit1203")
    assert reference.deleted is True
    assert reference.value is None

def test_live_acceptance_cli_requires_exact_project_and_emits_safe_summary(capsys):
    class Client:
        def synthetic_acceptance_round_trip(self, acceptance_id, *, created_at):
            assert acceptance_id.startswith("acceptance_synthetic_")
            return {
                "write_verified": True,
                "read_verified": True,
                "delete_verified": True,
            }

    result = live_acceptance_main(
        [
            "--input-scope",
            "synthetic",
            "--confirm-live-project",
            "aria-e906f",
        ],
        client_factory=lambda contract: Client(),
        now=lambda: NOW,
    )

    assert result["passed"] is True
    assert result["participant_data_used"] is False
    assert result["external_test_accessed"] is False
    encoded = capsys.readouterr().out
    assert SESSION_ID not in encoded
    assert "participant_id" not in encoded

    with pytest.raises(SystemExit, match="does not match"):
        live_acceptance_main(
            [
                "--input-scope",
                "synthetic",
                "--confirm-live-project",
                "wrong-project",
            ],
            client_factory=lambda contract: Client(),
            now=lambda: NOW,
        )