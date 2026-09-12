import pytest
from scripts.evaluate_tracking_trials import evaluate_rows, parse_track_ids

def row(scenario_id, scenario_type, subject_label, track_ids):
    return {
        "scenario_id": scenario_id,
        "scenario_type": scenario_type,
        "subject_label": subject_label,
        "observed_track_ids": track_ids,
        "notes": "",
    }

def test_expected_tracking_behaviour_is_accepted():
    result = evaluate_rows(
        [
            row("S1", "continuous", "subject_1", "7|7|7"),
            row("S2", "short_occlusion", "subject_1", "8|8"),
            row("S3", "full_exit_reentry", "subject_1", "9|12"),
            row("S4", "multiple_person", "subject_1", "13|13"),
            row("S4", "multiple_person", "subject_2", "14|14"),
        ]
    )

    assert result["accepted"] is True
    assert result["unexpected_id_switches"] == 0
    assert result["multiple_person_id_collisions"] == 0

def test_fragmentation_and_multiple_person_collision_are_rejected():
    result = evaluate_rows(
        [
            row("S1", "continuous", "subject_1", "7|8"),
            row("S4", "multiple_person", "subject_1", "10"),
            row("S4", "multiple_person", "subject_2", "10"),
        ]
    )

    assert result["accepted"] is False
    assert result["unexpected_id_switches"] == 1
    assert result["multiple_person_id_collisions"] == 1

def test_track_ids_must_be_non_negative_integers():
    with pytest.raises(ValueError, match="non-negative integers"):
        parse_track_ids("7|not-an-id")