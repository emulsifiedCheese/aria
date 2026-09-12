from pathlib import Path
from aria.acceptance.release import (
    build_file_records,
    collect_release_files,
    scan_release,
    source_revision,
)

def test_release_allowlist_excludes_data_outputs_retired_firmware_and_media():
    relative = {
        path.relative_to(Path(__file__).resolve().parents[2]).as_posix()
        for path in collect_release_files()
    }
    assert "firmware/esp_a/ESP_A_v1/ESP_A_v1.ino" in relative
    assert "models/phase_11_1/camera_only.joblib" in relative
    assert not any(path.startswith(("data/", "outputs/", "tmp/")) for path in relative)
    assert not any(path.startswith(("firmware/esp_b/", "firmware/esp_t/")) for path in relative)
    assert not any(path.endswith((".jpg", ".png", ".mp4", ".wav")) for path in relative)

def test_source_revision_is_deterministic_and_content_sensitive(tmp_path):
    first = tmp_path / "a.txt"
    first.write_text("one", encoding="utf-8")
    records = build_file_records([first], tmp_path)
    assert source_revision(records) == source_revision(records)
    first.write_text("two", encoding="utf-8")
    assert source_revision(build_file_records([first], tmp_path)) != source_revision(records)

def test_release_scan_rejects_private_key_email_and_media(tmp_path):
    key = tmp_path / "key.txt"
    key.write_text("-----BEGIN PRIVATE KEY-----", encoding="utf-8")
    identity = tmp_path / "identity.md"
    identity.write_text("person@example.com", encoding="utf-8")
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not real media")
    result = scan_release([key, identity, media], tmp_path)
    assert result["secret_scan_passed"] is False
    assert result["identity_and_media_scan_passed"] is False

def test_active_release_scan_passes():
    result = scan_release(collect_release_files())
    assert result["secret_scan_passed"] is True
    assert result["identity_and_media_scan_passed"] is True