from pathlib import Path
import yaml
from scripts.test_cameras import validate_deployment_cameras

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CAMERA_CONFIG_PATH = PROJECT_ROOT / "config" / "cameras.batamfast.yaml"
MEDIAMTX_CONFIG_PATH = PROJECT_ROOT / "config" / "mediamtx.local.yaml"

def test_deployment_uses_only_dji_camera_in_zone_a():
    with CAMERA_CONFIG_PATH.open(encoding="utf-8") as file:
        cameras = {
            camera["camera_id"]: camera
            for camera in yaml.safe_load(file)["cameras"]
        }

    assert set(cameras) == {"camera_a"}
    assert cameras["camera_a"]["camera_model"] == "DJI Osmo Action 5 Pro"
    assert cameras["camera_a"]["transport"] == "wireless_rtsp"
    assert cameras["camera_a"]["zone"] == "A"
    assert cameras["camera_a"]["source"] == ("rtsp://127.0.0.1:8554/live/camera_a")
    assert cameras["camera_a"]["width"] == 1920
    assert cameras["camera_a"]["height"] == 1080
    assert cameras["camera_a"]["fps"] == 30

def test_builtin_camera_is_rejected_for_camera_a():
    cameras = [
        {
            "camera_id": "camera_a",
            "camera_model": "MacBook Camera",
            "transport": "usb",
            "zone": "A",
            "source": 0,
        },
    ]

    try:
        validate_deployment_cameras(cameras)
    except ValueError as error:
        assert "built-in and Continuity cameras are not allowed" in str(error)
    else:
        raise AssertionError("Built-in Camera A source was accepted")

def test_mediamtx_relay_exposes_video_only_to_aria():
    with MEDIAMTX_CONFIG_PATH.open(encoding="utf-8") as file:
        config = yaml.safe_load(file)

    ingest = config["paths"]["ingest/camera_a"]
    live = config["paths"]["live/camera_a"]
    relay_command = ingest["runOnAvailable"]

    assert ingest["record"] is False
    assert live["record"] is False
    assert ingest["runOnAvailableRestart"] is True
    assert "/opt/homebrew/bin/ffmpeg" in relay_command
    assert "rtsp://127.0.0.1:8554/ingest/camera_a" in relay_command
    assert "rtsp://127.0.0.1:8554/live/camera_a" in relay_command
    assert "-map 0:v:0" in relay_command
    assert "-c:v copy" in relay_command
    assert "-an" in relay_command

    remote_permissions = config["authInternalUsers"][0]["permissions"]
    local_permissions = config["authInternalUsers"][1]["permissions"]

    assert remote_permissions == [
        {"action": "publish", "path": "ingest/camera_a"}
    ]
    assert {
        "action": "publish",
        "path": "live/camera_a",
    } in local_permissions