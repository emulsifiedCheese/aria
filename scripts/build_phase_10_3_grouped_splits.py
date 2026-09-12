#!/usr/bin/env python3
"""build the frozen phase 10.3 development and external-test split"""

from pathlib import Path

from aria.dataset.grouped_split import build_phase_10_3_splits

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    phase_10_2 = PROCESSED_DATA / "phase_10_2"
    phase_10_3 = PROCESSED_DATA / "phase_10_3"
    report = build_phase_10_3_splits(
        feature_path=phase_10_2 / "participant_feature_windows.jsonl",
        dataset_audit_path=phase_10_2 / "dataset_audit.json",
        policy_path=PROJECT_ROOT / "config" / "phase_10_3_split_policy.json",
        manifest_path=phase_10_3 / "grouped_split_manifest.jsonl",
        build_report_path=phase_10_3 / "grouped_split_build_report.json",
    )
    print("Phase 10.3 split build: BUILT PENDING AUDIT")
    print(f"Rows: {report['row_count']}")
    print(
        "Development / external test: "
        f"{report['partition_summary']['development']['row_count']} / "
        f"{report['partition_summary']['external_test']['row_count']}"
    )
    folds = report["development_cross_validation"]["fold_count"]
    print(f"Development folds: {folds}")


if __name__ == "__main__":
    main()
