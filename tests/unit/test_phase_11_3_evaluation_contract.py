import json
from hashlib import sha256
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "phase_11_3_evaluation.json"
CONFIG_SHA256 = "0c9b5e491f57a991ab071a5c6fe85b923542f7bd4b01c732137cb0d89c7d0e3a"
EXTERNAL_METRICS_PATH = PROJECT_ROOT / "outputs/evaluation/phase_11_3/external_metrics.json"
EXTERNAL_METRICS_SHA256 = "52f977c430ab540b823f3c50dc45ae279ffbd1f78f43b951f65631a35f8b355d"

def _sha256(path):
    return sha256(path.read_bytes()).hexdigest()

def _config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def test_phase_11_3_contract_is_frozen():
    config = _config()

    assert _sha256(CONFIG_PATH) == CONFIG_SHA256
    assert config["config_id"] == "zone-a-phase11.3-evaluation-v1"
    assert config["random_seed"] == 3070
    assert config["selected_model"] == {
        "name": "camera_only",
        "source_phase": "11.1",
        "artifact_path": "models/phase_11_1/camera_only.joblib",
        "artifact_sha256": "5c42e8c0d9639271f7e38c9108ba0017dd3acb1f38b3f36ef510e33c6e9fa78c",
        "feature_roots": ["camera_available", "pose_available", "camera"],
        "development_macro_f1": 0.4427914495497605,
    }
    assert config["external_evaluation"] == {
        "expected_row_count": 2068,
        "allowed_models": ["camera_only"],
        "fit_allowed": False,
        "parameter_changes_allowed": False,
        "overwrite_allowed": False,
        "verification_mode": "recompute_to_temporary_files_and_compare",
        "row_level_output_allowed": False,
    }

def test_phase_11_3_contract_pins_current_sources_and_model():
    config = _config()
    paths = {
        "participant_features_sha256": "data/processed/phase_10_2/participant_feature_windows.jsonl",
        "split_manifest_sha256": "data/processed/phase_10_3/grouped_split_manifest.jsonl",
        "split_audit_sha256": "data/processed/phase_10_3/grouped_split_audit.json",
        "phase_11_1_config_sha256": "config/phase_11_1_baselines.json",
        "phase_11_1_metrics_sha256": "outputs/evaluation/phase_11_1/baseline_metrics.json",
        "phase_11_2_config_sha256": "config/phase_11_2_multimodal.json",
        "phase_11_2_metrics_sha256": "outputs/evaluation/phase_11_2/multimodal_metrics.json",
    }
    assert {name: _sha256(PROJECT_ROOT / path) for name, path in paths.items()} == config["source_hashes"]
    assert _sha256(PROJECT_ROOT / config["selected_model"]["artifact_path"]) == (config["selected_model"]["artifact_sha256"])

def test_phase_11_3_contract_prevents_post_test_selection_and_stale_output():
    config = _config()

    assert config["external_evaluation"]["allowed_models"] == ["camera_only"]
    assert config["external_evaluation"]["fit_allowed"] is False
    assert config["external_evaluation"]["overwrite_allowed"] is False
    assert config["reliability"]["fit_calibrator"] is False
    assert config["missing_modality_policy"]["camera_unavailable"] == ("prediction_unavailable")
    assert config["missing_modality_policy"]["reuse_stale_prediction"] is False

def test_external_test_was_evaluated_once_without_changing_earlier_reports():
    for path in (
        PROJECT_ROOT / "outputs/evaluation/phase_11_1/baseline_metrics.json",
        PROJECT_ROOT / "outputs/evaluation/phase_11_2/multimodal_metrics.json",
    ):
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["external_test"]["evaluated"] is False
        assert report["external_test"]["row_count"] == 2068
    report = json.loads(EXTERNAL_METRICS_PATH.read_text(encoding="utf-8"))
    assert _sha256(EXTERNAL_METRICS_PATH) == EXTERNAL_METRICS_SHA256
    assert report["status"] == "complete_external_evaluation"
    assert report["external_test"]["evaluated"] is True
    assert report["external_test"]["row_count"] == 2068
    assert report["privacy"]["row_level_predictions_retained"] is False
