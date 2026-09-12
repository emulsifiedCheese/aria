#!/usr/bin/env python3
"""train phase 11.1 baselines on development data only"""
from pathlib import Path
from aria.modeling.baselines import build_phase_11_1_baselines

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE_10_2 = PROJECT_ROOT / "data" / "processed" / "phase_10_2"
PHASE_10_3 = PROJECT_ROOT / "data" / "processed" / "phase_10_3"
EVALUATION_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_1"

def main() -> None:
    report = build_phase_11_1_baselines(
        feature_path=PHASE_10_2 / "participant_feature_windows.jsonl",
        split_manifest_path=PHASE_10_3 / "grouped_split_manifest.jsonl",
        split_audit_path=PHASE_10_3 / "grouped_split_audit.json",
        config_path=PROJECT_ROOT / "config" / "phase_11_1_baselines.json",
        metrics_path=EVALUATION_DIR / "baseline_metrics.json",
        model_dir=PROJECT_ROOT / "models" / "phase_11_1",
        model_card_dir=EVALUATION_DIR / "model_cards",
    )
    print("Phase 11.1 baselines: COMPLETE (DEVELOPMENT ONLY)")
    print(f"Development rows: {report['development']['row_count']}")
    print(f"External rows evaluated: {int(report['external_test']['evaluated'])}")
    for name, result in report["baselines"].items():
        print(f"{name}: macro F1={result['aggregate_metrics']['macro_f1']:.6f}")

if __name__ == "__main__":
    main()
