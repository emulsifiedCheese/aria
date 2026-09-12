#!/usr/bin/env python3
"""validate approved annotations and turn them into two-second windows"""

from pathlib import Path

from aria.dataset.annotation_normalizer import normalise_approved_annotations

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "phase_10_1"


def main() -> None:
    report = normalise_approved_annotations(
        data_raw_dir=PROJECT_ROOT / "data" / "raw",
        inventory_path=OUTPUT_DIR / "source_session_inventory.json",
        output_path=OUTPUT_DIR / "normalised_annotation_windows.jsonl",
        report_path=OUTPUT_DIR / "annotation_normalisation_report.json",
    )
    print(f"Validated {report['source_annotation_count']} source annotations")
    print(f"Wrote {report['total_windows']} derived two-second annotation windows")
    print(f"Usable for modelling: {report['usable_windows']}")
    print(f"Selected-track-absent exclusions: {report['track_absent_windows']}")
    print(
        "New exclusions from selected-track absence: "
        f"{report['newly_excluded_track_absent_windows']}"
    )
    print(f"Incident-affected references: {report['incident_affected_windows']}")
    print(
        "Conflicting track-assignment groups: "
        f"{report['conflicting_track_assignment_group_count']}"
    )
    print(
        "New exclusions from conflicting track assignments: "
        f"{report['newly_excluded_conflicting_track_assignment_windows']}"
    )
    print(f"Class counts: {report['usable_class_counts']}")


if __name__ == "__main__":
    main()
