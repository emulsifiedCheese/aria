#!/usr/bin/env python3
"""generate the phase 11.3 development ablation table and figure"""
from pathlib import Path
from aria.modeling.ablation import build_ablation_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_DIR = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_3"

def main() -> None:
    result = build_ablation_artifacts(
        metrics_path=EVALUATION_DIR / "external_metrics.json",
        table_path=EVALUATION_DIR / "development_ablation_table.md",
        figure_path=EVALUATION_DIR / "figures" / "development_modality_ablation.png",
    )
    print(f"Generated ablation table for {result['model_count']} frozen models")
    print(f"Selected development model: {result['selected_model']}")
    print(result["table_path"])
    print(result["figure_path"])

if __name__ == "__main__":
    main()