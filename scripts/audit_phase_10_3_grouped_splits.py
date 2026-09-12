#!/usr/bin/env python3
"""check the phase 10.3 split for accounting errors and data leakage"""

from pathlib import Path

from aria.dataset.grouped_split import audit_phase_10_3_splits

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    phase_10_2 = PROCESSED_DATA / "phase_10_2"
    phase_10_3 = PROCESSED_DATA / "phase_10_3"
    report = audit_phase_10_3_splits(
        feature_path=phase_10_2 / "participant_feature_windows.jsonl",
        dataset_audit_path=phase_10_2 / "dataset_audit.json",
        policy_path=PROJECT_ROOT / "config" / "phase_10_3_split_policy.json",
        manifest_path=phase_10_3 / "grouped_split_manifest.jsonl",
        build_report_path=phase_10_3 / "grouped_split_build_report.json",
        audit_report_path=phase_10_3 / "grouped_split_audit.json",
    )
    print(f"Phase 10.3 leakage audit: {report['status'].upper()}")
    print(f"Rows: {report['reconciliation']['source_row_count']}")
    print(
        "Development / external test: "
        f"{report['reconciliation']['development_row_count']} / "
        f"{report['reconciliation']['external_test_row_count']}"
    )
    print(f"Leakage checks: {len(report['leakage_checks'])} passed")


if __name__ == "__main__":
    main()
