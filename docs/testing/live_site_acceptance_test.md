# Zone A Live-Site Acceptance Test

> **Historical collection-readiness procedure:** Participant collection closed on 10 August 2026. The dated GO decision and the conditions applied to the retained sessions are documented here; no new pilot or participant collection is authorised.

## Status
Current result: **COMPLETE — Phase 8.4 GO recorded on 2 August 2026**
This is the final acceptance procedure for the active ARIA deployment. The earlier three-zone, three-node and two-camera acceptance scope is superseded by this procedure.

## Active configuration
| Component | Required identity and configuration |
|---|---|
| Monitored area | Zone A only: approved front-counter staff-side region |
| ESP-A1 | `ESP-A1`, `A_PIR_US_MIC`, local UDP 4210 |
| ESP-A2 | `ESP-A2`, `A_PIR_MIC`, local UDP 4211 |
| Laptop receiver | UDP 5005; accepts ESP-A1 and ESP-A2 only |
| Camera A | DJI Osmo Action 5 Pro, `camera_a`, 1920x1080 at approximately 30 FPS |
| Camera bridge | DJI RTMP publish to MediaMTX; ARIA reads local RTSP |
Zone B, Zone T, ESP-B, ESP-T and a second camera are outside the active deployment and must not contribute research data.

## Preconditions
- The participant-facing Ethics Pack Version 4.3 PDF has been generated and visually verified
- Every participating Counter Agent has received Version 4.3 and acknowledged the amended Part D
- Site permission remains valid
- Only consenting Counter Agents are included in the active study
- Station Managers and all other non-participants remain outside the retained Zone A region; collection pauses or affected intervals are excluded and deleted if they enter it
- The DJI is fixed in its final position
- The BatamFast Zone A mask has been populated and marked verified
- Customer-facing areas, screens, payment areas and sensitive documents are outside the retained region
- The laptop microphone and all DJI/MediaMTX recording are disabled
- The MediaMTX/FFmpeg relay exposes one H264 track with no audio to ARIA
- The laptop, ESP-A1, ESP-A2 and DJI use the site's public Wi-Fi network; no phone hotspot or private access point is introduced
- Any required network configuration remains only in the local flash copy and is not included in shared logs or documentation
- The Mac's current network address matches `LAPTOP_IP` in both sketches

## Procedure
1. Photograph or diagram final equipment positions without including participants or customer-identifiable information
2. ESP-A1 and ESP-A2 must be powered, and their serial startup output must be inspected at 115200 baud
3. It must be confirmed that `A_PIR_US_MIC`, local UDP 4210 and the expected laptop destination are reported by ESP-A1
4. It must be confirmed that `A_PIR_MIC` and local UDP 4211 are reported by ESP-A2 and that no ultrasonic sensor or distance fields are included
5. The receiver must be started:
   ```bash
   PYTHONPATH=src python3 -m aria.ingestion.udp_receiver
   ```
6. It must be confirmed that packets appear in both node logs:
   ```bash
   tail -f outputs/logs/esp_a1.log
   ```
   ```bash
   tail -f outputs/logs/esp_a2.log
   ```
7. MediaMTX must be started:
   ```bash
   mediamtx config/mediamtx.local.yaml
   ```
8. DJI stream must be published to `rtmp://LAPTOP_IP:1935/ingest/camera_a`
9. It must be confirmed that `live/camera_a` is exposed by MediaMTX with exactly one H264 track and no audio track
10. Camera diagnostic must be run:
   ```bash
   PYTHONPATH=src python3 scripts/test_cameras.py \
     --camera camera_a --duration 60
   ```
11. It must be demonstrated that only the approved masked Zone A staff-side region is included in the retained view
12. Every scenario must be completed in  `docs/testing/privacy_failure_test.md` using non-research test conditions
13. ESP-A1, ESP-A2 and Camera A must be run together for at least 90 minutes in accordance with `docs/testing/zone_a_integration_test.md`
14. ESP-A1 must be restarted or power-cycled while ESP-A2 is kept active, followed by ESP-A2 while ESP-A1 is kept active. Reassociation of each board with the public
    network, a new boot ID and resumed telemetry must be confirmed. The public access point must not be interrupted.
15. Each process must be stopped normally, and the diagnostic logs and completed result tables must be preserved.

## Acceptance criteria
| Check | Pass condition |
|---|---|
| Deployment scope | Only Zone A, ESP-A1, ESP-A2 and DJI Camera A are active |
| Participant scope | Only consenting Counter Agents are included; no Station Manager classification or role attribution |
| Ethics documentation | Verified Version 4.3 PDF issued and amended Part D acknowledged |
| ESP identity | Correct node IDs, sensor configurations and local ports |
| UDP delivery | Measure each board against the unchanged 98% target; ESP-A2's accepted public-network shortfall must remain explicit in the final decision |
| ESP-A1 payload | Distance and audio fields present |
| ESP-A2 payload | Audio fields present; distance fields absent |
| Receiver | No crash, malformed normal packets or cross-node interference |
| ESP recovery | Each board recovers after its own restart or power-cycle while the other board continues |
| Camera mode | 1920x1080 at approximately 30 FPS |
| Camera stability | Drops, longest gap, latency and disconnects recorded |
| Privacy mask | Only approved Zone A staff-side pixels retained |
| Audio privacy | No raw or intelligible audio retained |
| Cloud restriction | No raw or masked video uploaded |
| Failure handling | Collection pauses or affected intervals are excluded |

## Evidence and result
The following must be recorded:
- Test date, start/end time and duration in SGT;
- Firmware versions, boot IDs and board network addresses;
- Packet counts, gaps, restarts and RSSI for both boards;
- Camera successful/dropped frames, FPS, latency and longest gap;
- Mask verification result and verifier;
- Each privacy-failure scenario and recovery result; and
- Final pass/fail decision with unresolved limitations.
Current consolidated result: **COMPLETE — GO**. The dated Phase 8.1 calibration record, Phase 8.2 privacy-failure and recovery record, Phase 8.3 combined-run evidence and Phase 8.4 decision are complete. GO was recorded by the Student Researcher at `2026-08-02T16:44:13+08:00`. The documented public-network, camera and tracking limitations were accepted without lowering the targets or reclassifying failed measurements. During the completed collection period, a fresh fail-closed preflight and pre-session checklist were required to be passed before the intended participant session could be authorised.

Decision record:
`docs/testing/results/2026-08-02_phase_8_4_go_decision.md`.