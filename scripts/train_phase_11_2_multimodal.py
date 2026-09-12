#!/usr/bin/env python3
"""train phase 11.2 early-fusion candidates on development data only"""
from pathlib import Path

from aria.modeling.multimodal import build_phase_11_2_multimodal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PHASE_10_2 = PROJECT_ROOT / "data" / "processed" / "phase_10_2"
PHASE_10_3 = PROJECT_ROOT / "data" / "processed" / "phase_10_3"
PHASE_11_1 = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_1"
EVALUATION_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_2"


def main() -> None:
    report = build_phase_11_2_multimodal(
        feature_path=PHASE_10_2 / "participant_feature_windows.jsonl",
        split_manifest_path=PHASE_10_3 / "grouped_split_manifest.jsonl",
        split_audit_path=PHASE_10_3 / "grouped_split_audit.json",
        baseline_metrics_path=PHASE_11_1 / "baseline_metrics.json",
        config_path=PROJECT_ROOT / "config" / "phase_11_2_multimodal.json",
        metrics_path=EVALUATION_DIR / "multimodal_metrics.json",
        model_dir=PROJECT_ROOT / "models" / "phase_11_2",
        model_card_dir=EVALUATION_DIR / "model_cards",
    )
    print("Phase 11.2 multimodal candidates: COMPLETE (DEVELOPMENT ONLY)")
    print(f"Development rows: {report['development']['row_count']}")
    print(f"External rows evaluated: {int(report['external_test']['evaluated'])}")
    for name, result in report["multimodal_candidates"].items():
        print(f"{name}: macro F1={result['aggregate_metrics']['macro_f1']:.6f}")
    print(f"Selected multimodal candidate: {report['selected_multimodal_candidate']}")


if __name__ == "__main__":
    main()
