# Wireless DJI Camera A Test
## Scope
The DJI Osmo Action 5 Pro is validated as the only active camera, Camera A, over the site's uncontrolled public Wi-Fi network. The stream is kept local and MediaMTX recording is disabled. Because a microphone disable control is not exposed by DJI Mimo for this camera, audio is removed by a localhost FFmpeg relay before the stream is exposed to ARIA.

## Network arrangement
- The site's uncontrolled public Wi-Fi network is used by the MacBook, ESP-A1, ESP-A2 and DJI camera
- DJI Mimo is run on a second phone or tablet to configure the Action 5 Pro livestream
- No cloud livestream destination is permitted
Access-point load, channel conditions, roaming and client management on this network cannot be controlled during the study. Resulting delivery limitations must be recorded without the acceptance thresholds being lowered or Wi-Fi being claimed as the proven cause.

## Start the local bridge
From the repository root:
```bash
brew install ffmpeg
mediamtx config/mediamtx.local.yaml
```
FFmpeg is required as a one-time prerequisite. The relay is started and stopped automatically by MediaMTX with the DJI publisher.

The MacBook's current public-network IPv4 address must be obtained from macOS network settings or with this command in Terminal:
```bash
ipconfig getifaddr en0
```
In DJI Mimo, RTMP with 1080p at 30 FPS must be selected, and the 2 Mbps bitrate must be used initially. The publish destination must be set to:
```text
rtmp://MACBOOK_IP:1935/ingest/camera_a
```
This public-network ingest is accepted by MediaMTX, FFmpeg is launched with video stream copying and audio disabled, and the video-only local stream is exposed to ARIA at:
```text
rtsp://127.0.0.1:8554/live/camera_a
```
## Acceptance criteria
- Incoming video is exactly 1920x1080 at approximately 30 FPS
- Measured frame rate is approximately 30 FPS
- Only the intended Zone A staff-side retained area is shown by Camera A
- Exactly one H264 track and no audio track are advertised by the ARIA-facing `live/camera_a` path
- Neither the incoming audio nor video is recorded by MediaMTX or FFmpeg
- ESP-A1 and ESP-A2 remain live while the single DJI Camera A operates
- `A_PIR_US_MIC` packets are continuously sent by ESP-A1, and `A_PIR_MIC` packets without distance fields are continuously sent by ESP-A2
- The RTMP publisher and ARIA reader are recovered cleanly after a brief disconnect
- The 90-minute stability run has no unexplained stream loss
- Observed latency, jitter and excluded intervals are recorded
If the test is passed at 2 Mbps, it must be repeated at 4 Mbps, and the highest bitrate at which the stability test is completed without ESP telemetry or Camera A being affected must be retained.