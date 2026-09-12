import json
from datetime import datetime
from types import SimpleNamespace
import pytest
from aria.collection.live_annotation import (
    ACTIVITIES,
    LiveAnnotationError,
    LiveAnnotationWriter,
)
from aria.collection.preflight import PauseStopController
from aria.timebase import SGT

SESSION_ID = "zone_a_20260804T150000SGT_test0001"

def test_live_interface_exposes_exactly_the_three_merged_classes():
    assert ACTIVITIES == ("Serving/Processing","Idle/Waiting","Reaching/Handling",)

def test_add_participant_requires_consent_and_creates_one_new_card(tmp_path):
    additions = []
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(0))
    writer.set_participant_registrar(lambda **payload: additions.append(payload) or payload)

    result = writer.add_participant("p0003", consent_confirmed=True)

    assert result["status"]["participants"] == ["P0001", "P0002", "P0003"]
    assert additions == [{
        "participant_id": "P0003",
        "consent_confirmed": True,
        "annotator_id": "A001",
    }]

    with pytest.raises(LiveAnnotationError, match="already has a card"):
        writer.add_participant("P0003", consent_confirmed=True)
    with pytest.raises(LiveAnnotationError, match="consent"):
        writer.add_participant("P0004")
    with pytest.raises(LiveAnnotationError, match="P0000"):
        writer.add_participant("participant four", consent_confirmed=True)

class Clock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

def context(tmp_path, participant_ids=("P0001", "P0002")):
    return SimpleNamespace(
        session_id=SESSION_ID,
        manifest_path=tmp_path / "manifests" / f"{SESSION_ID}.json",
        manifest={"participant_ids": list(participant_ids)},
        pause_stop_controller=PauseStopController(),
    )

def value(second):
    return datetime(2026, 8, 4, 15, 0, second, tzinfo=SGT)

def test_transition_writes_schema_valid_window_aligned_annotation(tmp_path):
    clock = Clock(value(1))
    writer = LiveAnnotationWriter(
        context(tmp_path),
        clock=clock,
        annotation_id_factory=lambda: "annotation_test_0001",
    )

    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Idle/Waiting",
        now=value(1),
    )
    result = writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Serving/Processing",
        now=value(5),
    )

    record = result["written"]
    assert record["interval_start_sgt"] == "2026-08-04T15:00:00+08:00"
    assert record["interval_end_sgt"] == "2026-08-04T15:00:04+08:00"
    assert record["window_ids"] == ["zone_a_1785826800000_2000","zone_a_1785826802000_2000",]
    assert record["activity"] == "Idle/Waiting"
    assert record["usable_for_modelling"] is True
    persisted = json.loads(writer.output_path.read_text().strip())
    assert persisted == record

def test_track_change_closes_prior_segment_without_identity_inference(tmp_path):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(8))
    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Serving/Processing",
        now=value(0),
    )
    result = writer.transition(
        participant_id="P0001",
        local_track_id=4,
        activity="Serving/Processing",
        now=value(4),
    )

    assert result["written"]["local_track_id"] == 1
    assert result["status"]["active"]["P0001"]["local_track_id"] == 4

def test_pause_closes_active_annotations_after_shared_gate_pauses(tmp_path):
    writer_context = context(tmp_path)
    clock = Clock(value(0))
    writer = LiveAnnotationWriter(writer_context, clock=clock)
    writer.transition(
        participant_id="P0001",
        local_track_id=2,
        activity="Reaching/Handling",
        now=value(0),
    )
    clock.value = value(4)
    writer_context.pause_stop_controller.pause()
    writer.pause()

    assert writer.session_summary()["written_record_count"] == 1
    assert writer.status()["active"] == {}
    with pytest.raises(LiveAnnotationError, match="paused"):
        writer.transition(
            participant_id="P0001",
            local_track_id=2,
            activity="Idle/Waiting",
        )

def test_exclusion_removes_any_annotation_containing_affected_window(tmp_path):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(8))
    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Idle/Waiting",
        now=value(0),
    )
    writer.stop_participant("P0001", now=value(6))
    affected = "zone_a_1785826802000_2000"

    assert writer.exclude_windows([affected]) == 1
    assert writer.verify_excluded_windows([affected]) is True
    assert writer.output_path.read_text() == ""
    assert writer.session_summary()["excluded_record_count"] == 1

@pytest.mark.parametrize(
    "changes, message",
    [
        ({"participant_id": "P9999"}, "manifest"),
        ({"local_track_id": -1}, "non-negative"),
        ({"activity": "Ad hoc work"}, "approved activity"),
    ],
)
def test_transition_rejects_out_of_scope_input(tmp_path, changes, message):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(0))
    payload = {
        "participant_id": "P0001",
        "local_track_id": 1,
        "activity": "Idle/Waiting",
    }
    payload.update(changes)
    with pytest.raises(LiveAnnotationError, match=message):
        writer.transition(**payload)

def test_close_finalises_active_interval_after_lifecycle_stop_gate(tmp_path):
    writer_context = context(tmp_path)
    clock = Clock(value(0))
    writer = LiveAnnotationWriter(writer_context, clock=clock)
    writer.transition(
        participant_id="P0001",
        local_track_id=3,
        activity="Serving/Processing",
    )
    clock.value = value(4)
    writer_context.pause_stop_controller.stop()
    writer.close()

    assert writer.session_summary()["written_record_count"] == 1
    assert writer.status()["stopped"] is True

def test_missing_track_for_complete_window_closes_before_missing_window(tmp_path):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(8))
    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Idle/Waiting",
        now=value(0),
    )

    writer.observe_track_snapshot({1}, value(0))
    writer.observe_track_snapshot(set(), value(2))
    writer.observe_track_snapshot({4}, value(4))

    records = [
        json.loads(line) for line in writer.output_path.read_text().splitlines()
    ]
    assert len(records) == 1
    assert records[0]["interval_start_sgt"] == "2026-08-04T15:00:00+08:00"
    assert records[0]["interval_end_sgt"] == "2026-08-04T15:00:02+08:00"
    assert records[0]["window_ids"] == ["zone_a_1785826800000_2000"]
    status = writer.status()
    assert status["active"] == {}
    assert status["replacement_required"]["P0001"] == {
        "participant_id": "P0001",
        "missing_local_track_id": 1,
        "previous_activity": "Idle/Waiting",
        "missing_window_id": "zone_a_1785826802000_2000",
    }

def test_one_visible_frame_keeps_track_active_for_complete_window(tmp_path):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(8))
    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Serving/Processing",
        now=value(0),
    )

    writer.observe_track_snapshot(set(), value(0))
    writer.observe_track_snapshot({1}, value(1))
    writer.observe_track_snapshot({1}, value(2))
    writer.observe_track_snapshot(set(), value(4))

    assert writer.status()["active"]["P0001"]["local_track_id"] == 1
    assert writer.status()["replacement_required"] == {}

def test_replacement_selection_starts_new_segment_without_guessing_identity(tmp_path):
    writer = LiveAnnotationWriter(context(tmp_path), clock=lambda: value(8))
    writer.transition(
        participant_id="P0001",
        local_track_id=1,
        activity="Serving/Processing",
        now=value(0),
    )
    writer.observe_track_snapshot({1}, value(0))
    writer.observe_track_snapshot({4}, value(2))
    writer.observe_track_snapshot({4}, value(4))

    assert writer.status()["replacement_required"]["P0001"]["missing_local_track_id"] == 1
    writer.transition(
        participant_id="P0001",
        local_track_id=4,
        activity="Serving/Processing",
        now=value(4),
    )

    assert writer.status()["replacement_required"] == {}
    assert writer.status()["active"]["P0001"]["local_track_id"] == 4