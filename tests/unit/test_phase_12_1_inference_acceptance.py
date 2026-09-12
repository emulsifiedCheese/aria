import json
import pytest
from aria.inference.acceptance import (
    InferenceAcceptanceError,
    build_phase_12_1_acceptance,
    write_phase_12_1_acceptance,
)

@pytest.fixture(scope="module")
def report():
    return build_phase_12_1_acceptance(warmup_iterations=1,measured_iterations=3,)

def test_synthetic_acceptance_passes_without_participant_or_external_data(report):
    assert report["status"] == "pass"
    assert report["scope"] == "synthetic local inference integration"
    assert report["privacy_and_behaviour"]["participant_data_used"] is False
    assert report["privacy_and_behaviour"]["external_test_used"] is False
    assert report["privacy_and_behaviour"]["firebase_used"] is False

def test_acceptance_proves_offline_live_matrix_parity(report):
    assert report["offline_live_parity"] == {
        "feature_names_match": True,
        "matrix_shape": [1, 23],
        "matrix_equal_with_nan": True,
    }
    assert report["checks"]["offline_live_preprocessing_parity"] is True

def test_acceptance_persists_only_schema_valid_abstract_predictions(report):
    privacy = report["privacy_and_behaviour"]
    assert privacy["status"] == "pass"
    assert privacy["prediction_schema_valid"] is True
    assert privacy["forbidden_output_keys_found"] == []
    assert privacy["raw_or_masked_video_persisted"] is False
    assert privacy["raw_audio_persisted"] is False
    assert privacy["raw_features_persisted"] is False
    assert privacy["persisted_prediction_count"] == 4

def test_acceptance_records_finite_integration_latency(report):
    latency = report["latency"]
    assert latency["clock"] == "perf_counter_ns"
    assert latency["measured_iterations_per_path"] == 3
    for path in (
        "feature_build_validation_model_and_serialisation",
        "end_to_end_with_durable_local_jsonl_delivery",
    ):
        assert 0 <= latency[path]["minimum_ms"] <= latency[path]["maximum_ms"]
        assert latency[path]["p50_ms"] <= latency[path]["p95_ms"] <= latency[path]["p99_ms"]
    assert report["checks"]["local_delivery_within_window_p95"] is True

def test_acceptance_writer_is_atomic_and_refuses_failed_report(tmp_path, report):
    output = tmp_path / "acceptance.json"
    digest = write_phase_12_1_acceptance(report, output)

    written = json.loads(output.read_text(encoding="utf-8"))
    assert written == report
    assert len(digest) == 64

    failed = dict(report, status="fail")
    with pytest.raises(InferenceAcceptanceError, match="did not pass"):
        write_phase_12_1_acceptance(failed, tmp_path / "failed.json")