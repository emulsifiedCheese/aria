#!/usr/bin/env python3
"""preflight or run the frozen phase 11.3 external evaluation"""
from argparse import ArgumentParser
from pathlib import Path
from aria.modeling.evaluation import evaluate_phase_11_3, preflight_phase_11_3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE_10_2 = PROJECT_ROOT / "data" / "processed" / "phase_10_2"
PHASE_10_3 = PROJECT_ROOT / "data" / "processed" / "phase_10_3"
PHASE_11_1 = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_1"
PHASE_11_2 = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_2"
METRICS_PATH = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_3" / "external_metrics.json"

def _paths():
    return {
        "feature_path": PHASE_10_2 / "participant_feature_windows.jsonl",
        "split_manifest_path": PHASE_10_3 / "grouped_split_manifest.jsonl",
        "split_audit_path": PHASE_10_3 / "grouped_split_audit.json",
        "phase_11_1_config_path": PROJECT_ROOT / "config" / "phase_11_1_baselines.json",
        "phase_11_1_metrics_path": PHASE_11_1 / "baseline_metrics.json",
        "phase_11_2_config_path": PROJECT_ROOT / "config" / "phase_11_2_multimodal.json",
        "phase_11_2_metrics_path": PHASE_11_2 / "multimodal_metrics.json",
        "model_path": PROJECT_ROOT / "models" / "phase_11_1" / "camera_only.joblib",
        "config_path": PROJECT_ROOT / "config" / "phase_11_3_evaluation.json",
        "metrics_path": METRICS_PATH,
    }

def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-external",
        action="store_true",
        help="open the locked external partition and write the one-time result",
    )
    args = parser.parse_args()
    if not args.execute_external:
        report = preflight_phase_11_3(**_paths())
        print("Phase 11.3 external evaluation preflight: READY")
        print(f"Selected model: {report['selected_model']}")
        print(f"Locked external rows: {report['external_row_count']}")
        print("External rows loaded for prediction: 0")
        print("No evaluation output was written")
        return
    report = evaluate_phase_11_3(**_paths())
    print("Phase 11.3 external evaluation: COMPLETE")
    print(f"External rows: {report['external_test']['row_count']}")
    print(f"Macro F1: {report['classification']['macro_f1']:.6f}")

if __name__ == "__main__":
    main()