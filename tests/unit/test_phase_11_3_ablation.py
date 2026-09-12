import json
import pytest
from aria.modeling.ablation import AblationError, MODEL_ORDER, build_ablation_artifacts

LABELS = ("Serving/Processing", "Idle/Waiting", "Reaching/Handling")

def _report():
    results = {}
    for index, name in enumerate(MODEL_ORDER):
        value = 0.45 - index * 0.03
        results[name] = {
            "macro_f1": value,
            "balanced_accuracy": value - 0.01,
            "accuracy": value + 0.1,
            "per_class": {
                label: {"f1": value - class_index * 0.05}
                for class_index, label in enumerate(LABELS)
            },
            "macro_f1_difference_from_camera_only": value - 0.45,
        }
    return {
        "phase": "11.3",
        "status": "complete_external_evaluation",
        "config_id": "zone-a-phase11.3-evaluation-v1",
        "development_ablation": results,
    }

def test_builds_development_ablation_table_and_figure(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    table_path = tmp_path / "table.md"
    figure_path = tmp_path / "figure.png"
    metrics_path.write_text(json.dumps(_report()), encoding="utf-8")

    result = build_ablation_artifacts(metrics_path=metrics_path,table_path=table_path,figure_path=figure_path,)
    table = table_path.read_text(encoding="utf-8")
    assert result["model_count"] == 7
    assert result["selected_model"] == "camera_only"
    assert "Alternative models were not scored on the external test" in table
    assert "Camera A + ESP-A1 + ESP-A2" in table
    assert "Reaching/Handling F1" in table
    assert figure_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert figure_path.stat().st_size > 10_000

def test_rejects_incomplete_ablation_evidence(tmp_path):
    report = _report()
    report["development_ablation"].pop("camera_a2")
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(AblationError, match="model set is incomplete"):
        build_ablation_artifacts(
            metrics_path=metrics_path,
            table_path=tmp_path / "table.md",
            figure_path=tmp_path / "figure.png",
        )