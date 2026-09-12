"""versioned, fail-closed collection-profile loading, drift checks"""
from __future__ import annotations
import hashlib
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CURRENT_PROFILE_ID = "zone-a-collection-v7"
CURRENT_PROFILE_VERSION = 7
DEFAULT_COLLECTION_PROFILE = PROJECT_ROOT / "config" / "collection.zone_a.v7.yaml"

class CollectionProfileError(ValueError):
    """raised when collection profile is invalid/has drifted"""

def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def load_collection_profile(path=DEFAULT_COLLECTION_PROFILE, *, verify_files=True):
    path = Path(path)
    try:
        with path.open(encoding="utf-8") as stream:
            profile = yaml.safe_load(stream)
    except OSError as error:
        raise CollectionProfileError(f"Collection profile is unavailable: {path}") from error
    if not isinstance(profile, dict):
        raise CollectionProfileError("Collection profile must be a YAML mapping")
    try:
        expected_profile_hash = path.with_suffix(".sha256").read_text(encoding="utf-8").strip()
    except OSError as error:
        raise CollectionProfileError("Frozen collection profile checksum is unavailable") from error
    if sha256_file(path) != expected_profile_hash:
        raise CollectionProfileError("Frozen collection profile file has changed; create a new profile version")

    required = {"profile_id", "profile_version", "settings", "artifacts"}
    missing = sorted(required - set(profile))
    if missing:
        raise CollectionProfileError("Collection profile is missing: " + ", ".join(missing))
    if not isinstance(profile["profile_id"], str):
        raise CollectionProfileError("Collection profile ID must be a string")
    if not isinstance(profile["profile_version"], int):
        raise CollectionProfileError("Collection profile version must be an integer")
    if not isinstance(profile["settings"], dict):
        raise CollectionProfileError("Collection profile settings must be a mapping")
    if not isinstance(profile["artifacts"], dict) or not profile["artifacts"]:
        raise CollectionProfileError("Collection profile artifacts must be a mapping")

    if verify_files:
        failures = []
        for relative_path, expected_hash in sorted(profile["artifacts"].items()):
            artifact = PROJECT_ROOT / relative_path
            if not artifact.is_file():
                failures.append(f"missing {relative_path}")
                continue
            actual_hash = sha256_file(artifact)
            if actual_hash != expected_hash:
                failures.append(f"changed {relative_path}")
        if failures:
            raise CollectionProfileError("Frozen collection artifact drift: " + "; ".join(failures))
    return profile

def collection_profile_metadata(path=DEFAULT_COLLECTION_PROFILE):
    profile = load_collection_profile(path)
    return {
        "collection_profile_id": profile["profile_id"],
        "collection_profile_sha256": sha256_file(path),
    }

def enforce_live_settings(args, path=DEFAULT_COLLECTION_PROFILE):
    """reject formal live-sesh command that differs from the freeze"""
    # Validate the profile itself before reading its retirement status. Historical
    # artifacts need not match today's files to keep collection closed.
    profile = load_collection_profile(path, verify_files=False)
    if profile.get("profile_status") == "retired_post_collection":
        raise CollectionProfileError("Participant collection is closed; the v7 profile is historical only")
    profile = load_collection_profile(path)
    if (profile["profile_id"] != CURRENT_PROFILE_ID or profile["profile_version"] != CURRENT_PROFILE_VERSION):
        raise CollectionProfileError(f"Formal collection requires {CURRENT_PROFILE_ID}")
    settings = profile["settings"]
    actual = {
        "camera_config": Path(args.camera_config).resolve(),
        "mask_config": Path(args.mask_config).resolve(),
        "mediamtx_config": Path(args.mediamtx_config).resolve(),
        "detector_model": Path(args.detector_model).resolve(),
        "pose_model": Path(args.pose_model).resolve(),
        "tracker_config": Path(args.tracker_config).resolve(),
        "detector_confidence": args.detector_confidence,
        "detector_iou": args.detector_iou,
        "pose_confidence": args.pose_confidence,
        "keypoint_confidence": args.keypoint_confidence,
        "min_confident_keypoints": args.min_confident_keypoints,
        "processing_fps": args.processing_fps,
        "inference_size": args.inference_size,
        "pose_inference_size": args.pose_inference_size,
        "udp_port": args.udp_port,
        "window_seconds": 2.0,
        "masked_track_preview": args.masked_track_preview,
        "experimental_track_stitching": args.experimental_track_stitching,
        "device": args.device,
    }
    differences = []
    for name, expected in settings.items():
        expected_value = (
            (PROJECT_ROOT / expected).resolve()
            if name.endswith("_config") or name in {"detector_model", "pose_model"}
            else expected
        )
        if actual.get(name) != expected_value:
            differences.append(f"{name}={actual.get(name)!r} (expected {expected_value!r})")
    if differences:
        raise CollectionProfileError(
            f"Formal collection settings differ from {CURRENT_PROFILE_ID}: "
            + "; ".join(differences)
        )
    return profile
