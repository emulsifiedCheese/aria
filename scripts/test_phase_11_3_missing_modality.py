#!/usr/bin/env python3
"""generate phase 11.3 missing-modality evidence"""
from __future__ import annotations
import json
from pathlib import Path
from aria.modeling.missing_modality import build_missing_modality_evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "phase_11_3_evaluation.json"
OUTPUT_PATH = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_3" / "missing_modality_evidence.json"
TABLE_PATH = PROJECT_ROOT / "outputs" / "evaluation" / "phase_11_3" / "missing_modality_table.md"

def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    report = build_missing_modality_evidence(config["missing_modality_policy"])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        "# Phase 11.3 missing-modality behaviour",
        "",
        "Synthetic control-flow test only. No participant data or external-test rows were used.",
        "",
        "| Scenario | Camera A | ESP-A1 | ESP-A2 | Expected | Actual | Model invoked | Stale output reused | Status |",
        "|---|---:|---:|---:|---|---|---:|---:|---:|",
    ]
    for result in report["scenarios"]:
        available = result["availability"]
        rows.append(
            f"| {result['scenario']} | {available['camera_a']} | {available['esp_a1']} | "
            f"{available['esp_a2']} | {result['expected_action']} | {result['actual_action']} | "
            f"{result['model_invoked']} | {result['stale_prediction_reused']} | {result['status']} |"
        )
    rows.extend((
        "",
        "Camera A loss returns an unavailable result with cleared activity and confidence. Sensor loss does not block the frozen Camera-only model.",
        "",
    ))
    TABLE_PATH.write_text("\n".join(rows), encoding="utf-8")
    print(f"Status: {report['status']}")
    print(f"Scenarios: {report['scenario_count']}")
    print(f"JSON: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Table: {TABLE_PATH.relative_to(PROJECT_ROOT)}")

if __name__ == "__main__":
    main()