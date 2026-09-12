#!/usr/bin/env python3
"""run the phase 10.2 data-quality and privacy audit"""

from pathlib import Path

from aria.dataset.dataset_audit import audit_phase_10_2_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    phase_10_1 = PROCESSED_DATA / "phase_10_1"
    phase_10_2 = PROCESSED_DATA / "phase_10_2"
    report = audit_phase_10_2_dataset(
        feature_path=phase_10_2 / "participant_feature_windows.jsonl",
        build_report_path=phase_10_2 / "participant_feature_build_report.json",
        normalised_annotations_path=phase_10_1 / "normalised_annotation_windows.jsonl",
        normalisation_report_path=phase_10_1 / "annotation_normalisation_report.json",
        exclusion_ledger_path=phase_10_2 / "exclusion_ledger.jsonl",
        audit_report_path=phase_10_2 / "dataset_audit.json",
    )
    quality = report["quality_audit"]
    print(f"Phase 10.2 audit: {report['status'].upper()}")
    print(f"Rows: {quality['row_count']}")
    print(f"Episodes: {quality['episode_count']}")
    print(f"Exclusions: {report['reconciliation']['excluded_windows']}")
    print(f"Privacy audit: {'PASS' if report['privacy_audit']['passed'] else 'FAIL'}")
    print(f"Availability patterns: {quality['availability_patterns']}")


if __name__ == "__main__":
    main()
