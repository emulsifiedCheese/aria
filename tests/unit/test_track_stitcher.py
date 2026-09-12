import pytest
from aria.vision.track_stitcher import AnonymousTrackStitcher

def track(local_track_id, box=(10, 10, 110, 210)):
    return {
        "local_track_id": local_track_id,
        "bounding_box": list(box),
        "detection_confidence": 0.8,
    }

def test_new_raw_id_continues_with_one_anonymous_id():
    stitcher = AnonymousTrackStitcher()
    first = stitcher.associate([track(2)], 10.0)[0]
    second = stitcher.associate([track(2, (12, 10, 112, 210))], 10.1)[0]
    assert first["stitched_track_id"] == 1
    assert first["track_association_status"] == "new"
    assert second["stitched_track_id"] == 1
    assert second["track_association_status"] == "continued"
    assert first["local_track_id"] == second["local_track_id"] == 2

def test_unique_nearby_replacement_is_stitched_without_changing_raw_id():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)
    replacement = stitcher.associate(
        [track(6, (12, 10, 112, 210))],
        10.2,
    )[0]

    assert replacement["local_track_id"] == 6
    assert replacement["stitched_track_id"] == 1
    assert replacement["track_association_status"] == "stitched"
    assert replacement["track_association_reason"] == ("unique_spatiotemporal_match")

def test_simultaneous_overlapping_raw_ids_are_uncertain_not_merged():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)

    result = stitcher.associate(
        [track(2), track(6, (12, 10, 112, 210))],
        10.1,
    )

    by_raw_id = {item["local_track_id"]: item for item in result}
    assert by_raw_id[2]["stitched_track_id"] == 1
    assert by_raw_id[6]["stitched_track_id"] is None
    assert by_raw_id[6]["track_association_reason"] == ("simultaneous_overlap")

def test_flash_is_uncertain_then_takeover_can_be_uniquely_stitched():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)
    flashed = stitcher.associate([track(2), track(6, (12, 10, 112, 210))],10.1)

    takeover = stitcher.associate([track(6, (13, 10, 113, 210))],10.2,)[0]

    flashed_by_raw_id = {item["local_track_id"]: item for item in flashed}
    assert flashed_by_raw_id[6]["stitched_track_id"] is None
    assert takeover["local_track_id"] == 6
    assert takeover["stitched_track_id"] == 1
    assert takeover["track_association_status"] == "stitched"

def test_multiple_recent_candidates_are_left_uncertain():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate(
        [
            track(2, (10, 10, 110, 210)),
            track(3, (300, 10, 400, 210)),
        ],
        10.0,
    )
    stitcher.associate(
        [
            track(2, (10, 10, 110, 210)),
            track(3, (14, 10, 114, 210)),
        ],
        10.1,
    )
    stitcher.associate(
        [
            track(2, (10, 10, 110, 210)),
            track(3, (14, 10, 114, 210)),
        ],
        10.2,
    )

    result = stitcher.associate(
        [track(6, (12, 10, 112, 210))],
        10.3,
    )[0]

    assert result["stitched_track_id"] is None
    assert result["track_association_status"] == "uncertain"
    assert result["track_association_reason"] == "multiple_candidates"

def test_replacement_after_gap_is_a_new_anonymous_track():
    stitcher = AnonymousTrackStitcher(max_gap_seconds=1.0)
    stitcher.associate([track(2)], 10.0)
    result = stitcher.associate([track(6)], 11.1)[0]
    assert result["stitched_track_id"] == 2
    assert result["track_association_status"] == "new"

def test_geometrically_distant_raw_id_is_a_new_anonymous_track():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)
    result = stitcher.associate(
        [track(6, (500, 10, 600, 210))],
        10.2,
    )[0]
    assert result["stitched_track_id"] == 2
    assert result["track_association_status"] == "new"

def test_reappearing_old_raw_id_creates_canonical_collision_uncertainty():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)
    stitcher.associate([track(6)], 10.1)
    result = stitcher.associate([track(2), track(6)], 10.2)
    assert {item["stitched_track_id"] for item in result} == {None}
    assert {item["track_association_reason"] for item in result} == {"canonical_collision"}

def test_summary_counts_stitches_and_uncertain_records():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)
    stitcher.associate([track(6)], 10.1)
    stitcher.associate([track(2), track(6)], 10.2)
    summary = stitcher.summary()
    assert summary["stitched_record_count"] == 1
    assert summary["uncertain_record_count"] == 2
    assert summary["canonical_track_count"] == 1

@pytest.mark.parametrize(
    "tracks",
    [
        [track(2), track(2)],
        [track(-1)],
        [track(2, (10, 10, 10, 20))],
    ],
)
def test_rejects_invalid_frame_tracks(tracks):
    stitcher = AnonymousTrackStitcher()

    with pytest.raises(ValueError):
        stitcher.associate(tracks, 10.0)

def test_rejects_observation_time_moving_backwards():
    stitcher = AnonymousTrackStitcher()
    stitcher.associate([track(2)], 10.0)

    with pytest.raises(ValueError, match="must not move backwards"):
        stitcher.associate([track(2)], 9.9)