#!/usr/bin/env python3
"""build the participant-level feature dataset used for modelling"""

from pathlib import Path

from aria.dataset.participant_feature_builder import build_participant_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DATA = PROJECT_ROOT / "data" / "processed"


def main() -> None:
    phase_10_1 = PROCESSED_DATA / "phase_10_1"
    phase_10_2 = PROCESSED_DATA / "phase_10_2"
    report = build_participant_features(
        data_raw_dir=PROJECT_ROOT / "data" / "raw",
        inventory_path=phase_10_1 / "source_session_inventory.json",
        normalised_annotations_path=phase_10_1 / "normalised_annotation_windows.jsonl",
        normalisation_report_path=phase_10_1 / "annotation_normalisation_report.json",
        output_path=phase_10_2 / "participant_feature_windows.jsonl",
        report_path=phase_10_2 / "participant_feature_build_report.json",
    )
    print(f"Built {report['row_count']} participant feature windows")
    print(f"Participants: {report['participant_count']}")
    print(f"Episodes: {report['episode_count']}")
    print(f"Classes: {report['class_counts']}")
    print(
        "Availability: "
        f"camera={report['camera_available']}, pose={report['pose_available']}, "
        f"A1={report['a1_available']}, A2={report['a2_available']}"
    )
    print(f"All modalities available: {report['all_modalities_available']}")


if __name__ == "__main__":
    main()
