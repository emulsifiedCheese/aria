from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml
from aria.collection.collection_profile import (
    CollectionProfileError,
    enforce_live_settings,
    load_collection_profile,
    sha256_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

def frozen_args(**overrides):
    values = {
        "camera_config": PROJECT_ROOT / "config/cameras.batamfast.yaml",
        "mask_config": PROJECT_ROOT / "config/masks.batamfast.yaml",
        "mediamtx_config": PROJECT_ROOT / "config/mediamtx.local.yaml",
        "detector_model": PROJECT_ROOT / "yolov8n.pt",
        "pose_model": PROJECT_ROOT / "yolov8n-pose.pt",
        "tracker_config": PROJECT_ROOT / "config/bytetrack.zone_a.persistence.yaml",
        "detector_confidence": 0.10,
        "detector_iou": 0.70,
        "pose_confidence": 0.15,
        "keypoint_confidence": 0.5,
        "min_confident_keypoints": 4,
        "processing_fps": 15.0,
        "inference_size": 768,
        "pose_inference_size": 384,
        "udp_port": 5005,
        "masked_track_preview": True,
        "experimental_track_stitching": False,
        "device": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)

def test_v7_post_collection_profile_metadata_remains_readable_as_history():
    profile = load_collection_profile(verify_files=False)
    assert profile["profile_id"] == "zone-a-collection-v7"
    assert profile["profile_version"] == 7
    assert profile["profile_status"] == "retired_post_collection"

def test_v4_profile_metadata_remains_readable_as_history():
    profile = load_collection_profile(PROJECT_ROOT / "config/collection.zone_a.v4.yaml",verify_files=False,)
    assert profile["profile_id"] == "zone-a-collection-v4"
    assert profile["deployment"]["mask_config_version"] == "batamfast-v2"

def test_formal_live_settings_reject_retired_v7():
    with pytest.raises(CollectionProfileError, match="collection is closed"):
        enforce_live_settings(frozen_args())

def test_formal_setting_drift_is_still_rejected_when_artifacts_are_verified(monkeypatch,):
    current_profile = load_collection_profile(verify_files=False)
    current_profile.pop("profile_status", None)
    monkeypatch.setattr("aria.collection.collection_profile.load_collection_profile",lambda _path, **kwargs: current_profile,)
    with pytest.raises(CollectionProfileError, match="processing_fps"):
        enforce_live_settings(frozen_args(processing_fps=30.0))

    with pytest.raises(CollectionProfileError, match="device"):
        enforce_live_settings(frozen_args(device="mps"))

def test_artifact_drift_is_rejected(tmp_path):
    profile_path = tmp_path / "profile.yaml"
    source = PROJECT_ROOT / "config/collection.zone_a.v7.yaml"
    checksum_path = profile_path.with_suffix(".sha256")
    profile_path.write_text(source.read_text().replace(
        "1b057b512b571bb3f65d0c1f470c653a453b9615b70bc154f93b4adebea7d8bf",
        "0" * 64,
    ))
    checksum_path.write_text(sha256_file(source) + "\n")
    with pytest.raises(CollectionProfileError, match="profile file has changed"):
        load_collection_profile(profile_path)

@pytest.mark.parametrize("retired", [True, False])
@pytest.mark.parametrize("artifact_state", ["changed", "missing"])
def test_retirement_precedes_artifact_checks_but_other_profiles_reject_drift(
    tmp_path, retired, artifact_state,
):
    profile = load_collection_profile(verify_files=False)
    artifact = tmp_path / "synthetic_artifact.txt"
    artifact.write_text("original synthetic content")
    profile["artifacts"] = {str(artifact): sha256_file(artifact)}
    if not retired:
        profile.pop("profile_status")
    profile_path = tmp_path / "synthetic_profile.yaml"
    profile_path.write_text(yaml.safe_dump(profile))
    profile_path.with_suffix(".sha256").write_text(sha256_file(profile_path) + "\n")
    if artifact_state == "changed":
        artifact.write_text("changed synthetic content")
    else:
        artifact.unlink()

    expected = "collection is closed" if retired else f"artifact drift: {artifact_state}"
    with pytest.raises(CollectionProfileError, match=expected):
        enforce_live_settings(frozen_args(), profile_path)
