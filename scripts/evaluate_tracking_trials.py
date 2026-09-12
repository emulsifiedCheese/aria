#!/usr/bin/env python3
"""check whether controlled tracking trials meet the expected id behaviour"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

SCENARIO_TYPES = {
    "continuous",
    "short_occlusion",
    "full_exit_reentry",
    "multiple_person",
}
REQUIRED_COLUMNS = {
    "scenario_id",
    "scenario_type",
    "subject_label",
    "observed_track_ids",
    "notes",
}

def parse_track_ids(value: str) -> list[int]:
    values = [part.strip() for part in value.split("|") if part.strip()]
    if not values:
        raise ValueError("observed_track_ids must contain at least one ID")
    try:
        track_ids = [int(value) for value in values]
    except ValueError as error:
        raise ValueError(
            "observed_track_ids must be pipe-separated non-negative integers"
        ) from error
    if any(track_id < 0 for track_id in track_ids):
        raise ValueError("observed track IDs must be non-negative")
    return track_ids

def evaluate_rows(rows: list[dict[str, str]]) -> dict:
    results = []
    multiple_person_ids = defaultdict(dict)
    for row_number, row in enumerate(rows, start=2):
        scenario_type = row["scenario_type"].strip()
        if scenario_type not in SCENARIO_TYPES:
            raise ValueError(
                f"Row {row_number} has unsupported scenario_type "
                f"{scenario_type!r}"
            )

        scenario_id = row["scenario_id"].strip()
        subject_label = row["subject_label"].strip()
        if not scenario_id or not subject_label:
            raise ValueError(
                f"Row {row_number} requires scenario_id and subject_label"
            )

        track_ids = parse_track_ids(row["observed_track_ids"])
        transitions = sum(
            current != previous
            for previous, current in zip(track_ids, track_ids[1:])
        )
        expected_transitions = 1 if scenario_type == "full_exit_reentry" else 0
        unexpected_fragmentation = max(0, transitions - expected_transitions)
        behavior_pass = transitions == expected_transitions

        if scenario_type == "multiple_person":
            multiple_person_ids[scenario_id][subject_label] = set(track_ids)

        results.append(
            {
                "scenario_id": scenario_id,
                "scenario_type": scenario_type,
                "subject_label": subject_label,
                "observed_track_ids": track_ids,
                "id_transitions": transitions,
                "expected_id_transitions": expected_transitions,
                "unexpected_fragmentation": unexpected_fragmentation,
                "behavior_pass": behavior_pass,
                "notes": row["notes"].strip(),
            }
        )

    collisions = []
    for scenario_id, subjects in multiple_person_ids.items():
        labels = sorted(subjects)
        for index, first_label in enumerate(labels):
            for second_label in labels[index + 1 :]:
                shared = sorted(
                    subjects[first_label] & subjects[second_label]
                )
                if shared:
                    collisions.append({
                        "scenario_id": scenario_id,
                        "subject_labels": [first_label, second_label],
                        "shared_track_ids": shared,
                    })

    return {
        "schema_version": 1,
        "trial_rows": len(results),
        "unexpected_id_switches": sum(
            result["unexpected_fragmentation"]
            for result in results
        ),
        "behavior_failures": sum(
            not result["behavior_pass"] for result in results
        ),
        "multiple_person_id_collisions": len(collisions),
        "accepted": all(result["behavior_pass"] for result in results) and not collisions,
        "results": results,
        "collisions": collisions,
    }

def load_and_evaluate(path: str | Path) -> dict:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                f"Tracking trial CSV is missing columns: {sorted(missing)}"
            )
        return evaluate_rows(list(reader))

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate pseudonymous controlled Camera A tracking trials."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = load_and_evaluate(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
