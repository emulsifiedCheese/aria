from __future__ import annotations
from dataclasses import dataclass
import math

DEFAULT_MAX_GAP_SECONDS = 1.0
DEFAULT_MIN_IOU = 0.5
DEFAULT_MAX_NORMALISED_CENTER_DISTANCE = 0.2
DEFAULT_MIN_AREA_RATIO = 0.6

@dataclass
class _CanonicalState:
    stitched_track_id: int
    last_local_track_id: int
    last_bbox: tuple[float, float, float, float]
    last_seen_at: float
    previous_center: tuple[float, float] | None = None
    previous_seen_at: float | None = None

@dataclass(frozen=True)
class _Association:
    stitched_track_id: int | None
    status: str
    reason: str

class AnonymousTrackStitcher:

    def __init__(
        self,
        *,
        max_gap_seconds=DEFAULT_MAX_GAP_SECONDS,
        min_iou=DEFAULT_MIN_IOU,
        max_normalised_center_distance=(
            DEFAULT_MAX_NORMALISED_CENTER_DISTANCE
        ),
        min_area_ratio=DEFAULT_MIN_AREA_RATIO,
    ):
        self.max_gap_seconds = self._positive_number(
            max_gap_seconds,
            "max_gap_seconds",
        )
        self.min_iou = self._unit_interval(min_iou, "min_iou")
        self.max_normalised_center_distance = self._unit_interval(
            max_normalised_center_distance,
            "max_normalised_center_distance",
        )
        self.min_area_ratio = self._unit_interval(
            min_area_ratio,
            "min_area_ratio",
        )
        self._next_stitched_track_id = 1
        self._raw_to_stitched = {}
        self._raw_last_seen_at = {}
        self._states = {}
        self._stitched_count = 0
        self._uncertain_count = 0
        self._last_observed_at = None

    def associate(self, tracks, observed_at):
        observed_at = self._nonnegative_number(observed_at, "observed_at")
        if (
            self._last_observed_at is not None
            and observed_at < self._last_observed_at
        ):
            raise ValueError("observed_at must not move backwards")
        self._last_observed_at = observed_at
        copied = [dict(track) for track in tracks]
        local_ids = [track.get("local_track_id") for track in copied]
        if any(
            not isinstance(local_id, int) or isinstance(local_id, bool)
            or local_id < 0
            for local_id in local_ids
        ):
            raise ValueError("local_track_id must be a non-negative integer")
        if len(set(local_ids)) != len(local_ids):
            raise ValueError("local_track_id values must be unique within a frame")
        for track in copied:
            self._validated_bbox(track.get("bounding_box"))

        current_ids = set(local_ids)
        associations = {}
        reserved_stitched_ids = set()
        unknown_tracks = []

        for track in copied:
            local_id = track["local_track_id"]
            stitched_id = self._raw_to_stitched.get(local_id)
            last_seen_at = self._raw_last_seen_at.get(local_id)
            if (
                stitched_id is not None
                and last_seen_at is not None
                and observed_at - last_seen_at <= self.max_gap_seconds
            ):
                associations[local_id] = _Association(
                    stitched_id,
                    "continued",
                    "existing_raw_id",
                )
                reserved_stitched_ids.add(stitched_id)
            else:
                self._raw_to_stitched.pop(local_id, None)
                unknown_tracks.append(track)

        tentative_candidates = {}
        for track in unknown_tracks:
            local_id = track["local_track_id"]
            if self._overlaps_current_track(track, copied):
                associations[local_id] = _Association(
                    None,
                    "uncertain",
                    "simultaneous_overlap",
                )
                continue

            candidates = [
                state
                for state in self._states.values()
                if state.stitched_track_id not in reserved_stitched_ids
                and state.last_local_track_id not in current_ids
                and 0 < observed_at - state.last_seen_at
                <= self.max_gap_seconds
                and self._strong_match(state, track["bounding_box"], observed_at)
            ]
            if len(candidates) == 1:
                tentative_candidates[local_id] = candidates[0]
            elif len(candidates) > 1:
                associations[local_id] = _Association(
                    None,
                    "uncertain",
                    "multiple_candidates",
                )
            else:
                stitched_id = self._allocate_stitched_id()
                associations[local_id] = _Association(
                    stitched_id,
                    "new",
                    "new_track",
                )
                reserved_stitched_ids.add(stitched_id)

        claims_by_stitched_id = {}
        for local_id, state in tentative_candidates.items():
            claims_by_stitched_id.setdefault(
                state.stitched_track_id,
                [],
            ).append(local_id)
        for stitched_id, claimants in claims_by_stitched_id.items():
            if len(claimants) > 1:
                for local_id in claimants:
                    associations[local_id] = _Association(
                        None,
                        "uncertain",
                        "multiple_candidates",
                    )
                continue
            local_id = claimants[0]
            associations[local_id] = _Association(
                stitched_id,
                "stitched",
                "unique_spatiotemporal_match",
            )
            reserved_stitched_ids.add(stitched_id)

        by_stitched_id = {}
        for local_id, association in associations.items():
            if association.stitched_track_id is not None:
                by_stitched_id.setdefault(
                    association.stitched_track_id,
                    [],
                ).append(local_id)
        for stitched_id, colliding_ids in by_stitched_id.items():
            if len(colliding_ids) <= 1:
                continue
            for local_id in colliding_ids:
                associations[local_id] = _Association(
                    None,
                    "uncertain",
                    "canonical_collision",
                )

        for track in copied:
            local_id = track["local_track_id"]
            association = associations[local_id]
            track["stitched_track_id"] = association.stitched_track_id
            track["track_association_status"] = association.status
            track["track_association_reason"] = association.reason
            if association.stitched_track_id is None:
                self._uncertain_count += 1
                continue
            if association.status == "stitched":
                self._stitched_count += 1
            self._raw_to_stitched[local_id] = association.stitched_track_id
            self._raw_last_seen_at[local_id] = observed_at
            self._update_state(
                association.stitched_track_id,
                local_id,
                track["bounding_box"],
                observed_at,
            )

        return copied

    def summary(self):
        return {
            "enabled": True,
            "stitched_record_count": self._stitched_count,
            "uncertain_record_count": self._uncertain_count,
            "canonical_track_count": self._next_stitched_track_id - 1,
            "max_gap_seconds": self.max_gap_seconds,
            "min_iou": self.min_iou,
            "max_normalised_center_distance": (
                self.max_normalised_center_distance
            ),
            "min_area_ratio": self.min_area_ratio,
        }

    def _overlaps_current_track(self, candidate, tracks):
        candidate_id = candidate["local_track_id"]
        candidate_box = candidate["bounding_box"]
        for other in tracks:
            if other["local_track_id"] == candidate_id:
                continue
            if self._box_agreement(candidate_box, other["bounding_box"]):
                return True
        return False

    def _strong_match(self, state, candidate_box, observed_at):
        predicted_box = self._predicted_box(state, observed_at)
        return self._box_agreement(predicted_box, candidate_box)

    def _box_agreement(self, first, second):
        first_area = self._area(first)
        second_area = self._area(second)
        area_ratio = min(first_area, second_area) / max(first_area, second_area)
        if area_ratio < self.min_area_ratio:
            return False
        scale = max(
            first[2] - first[0],
            first[3] - first[1],
            second[2] - second[0],
            second[3] - second[1],
            1.0,
        )
        first_center = self._center(first)
        second_center = self._center(second)
        centre_distance = math.hypot(
            first_center[0] - second_center[0],
            first_center[1] - second_center[1],
        ) / scale
        return (
            self._box_iou(first, second) >= self.min_iou
            and centre_distance <= self.max_normalised_center_distance
        )

    def _predicted_box(self, state, observed_at):
        if (
            state.previous_center is None
            or state.previous_seen_at is None
            or state.last_seen_at <= state.previous_seen_at
        ):
            return state.last_bbox
        last_center = self._center(state.last_bbox)
        elapsed = state.last_seen_at - state.previous_seen_at
        horizon = min(
            observed_at - state.last_seen_at,
            elapsed,
        )
        predicted_center = (
            last_center[0]
            + (last_center[0] - state.previous_center[0]) / elapsed * horizon,
            last_center[1]
            + (last_center[1] - state.previous_center[1]) / elapsed * horizon,
        )
        offset_x = predicted_center[0] - last_center[0]
        offset_y = predicted_center[1] - last_center[1]
        return (
            state.last_bbox[0] + offset_x,
            state.last_bbox[1] + offset_y,
            state.last_bbox[2] + offset_x,
            state.last_bbox[3] + offset_y,
        )

    def _update_state(
        self,
        stitched_id,
        local_id,
        bounding_box,
        observed_at,
    ):
        bounding_box = tuple(float(value) for value in bounding_box)
        previous = self._states.get(stitched_id)
        self._states[stitched_id] = _CanonicalState(
            stitched_track_id=stitched_id,
            last_local_track_id=local_id,
            last_bbox=bounding_box,
            last_seen_at=observed_at,
            previous_center=(
                self._center(previous.last_bbox) if previous else None
            ),
            previous_seen_at=(previous.last_seen_at if previous else None),
        )

    def _allocate_stitched_id(self):
        value = self._next_stitched_track_id
        self._next_stitched_track_id += 1
        return value

    @staticmethod
    def _center(box):
        return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)

    @staticmethod
    def _area(box):
        return (box[2] - box[0]) * (box[3] - box[1])

    @staticmethod
    def _box_iou(first, second):
        intersection_width = max(
            0.0,
            min(first[2], second[2]) - max(first[0], second[0]),
        )
        intersection_height = max(
            0.0,
            min(first[3], second[3]) - max(first[1], second[1]),
        )
        intersection = intersection_width * intersection_height
        union = (
            AnonymousTrackStitcher._area(first)
            + AnonymousTrackStitcher._area(second)
            - intersection
        )
        return intersection / union if union > 0 else 0.0

    @staticmethod
    def _validated_bbox(value):
        if (
            not isinstance(value, (list, tuple))
            or len(value) != 4
            or any(
                not isinstance(item, (int, float))
                or isinstance(item, bool)
                or not math.isfinite(item)
                for item in value
            )
            or value[2] <= value[0]
            or value[3] <= value[1]
        ):
            raise ValueError("bounding_box must contain finite x1, y1, x2, y2")

    @staticmethod
    def _positive_number(value, field_name):
        value = AnonymousTrackStitcher._nonnegative_number(value, field_name)
        if value == 0:
            raise ValueError(f"{field_name} must be greater than zero")
        return value

    @staticmethod
    def _unit_interval(value, field_name):
        value = AnonymousTrackStitcher._nonnegative_number(value, field_name)
        if value > 1:
            raise ValueError(f"{field_name} must be between zero and one")
        return value

    @staticmethod
    def _nonnegative_number(value, field_name):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{field_name} must be a finite non-negative number")
        return float(value)