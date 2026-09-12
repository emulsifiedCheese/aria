# ARIA Zone A Live-Site Setup and Shutdown Runbook
## Status and stop condition
Participant collection was closed after the ninth retained formal session on 10 August 2026. This runbook is retained as historical acceptance and participant-session setup evidence. It must not be used to start a new pilot or participant session. Controlled non-research Phase 11-13 development may still be supported by the hardware instructions using synthetic or approved non-participant inputs.
The merged `Serving/Processing` three-class method was used for the retained participant sessions under Ethics Pack Version 4.4 and manifest-recorded frozen profiles. The same privacy boundary must be preserved in later non-research work, and participant collection is not authorised.
Only ESP-A1, ESP-A2 and `camera_a` are active. ESP-B, ESP-T, Zone B, Zone T, a second camera and role-attribution behaviour must not be powered, ingested or tested.

## Required references
- `docs/hardware/placement.md`
- `docs/data_collection/pre_session_checklist.md`
- `docs/data_collection/post_session_checklist.md`
- `docs/data_collection/session_protocol.md`
- `docs/testing/live_site_acceptance_test.md`
- `docs/testing/privacy_failure_test.md`
- `docs/testing/zone_a_integration_test.md`
- `docs/privacy/data_handling.md`
- `docs/privacy/masking_procedure.md`

## Preconditions
- Work must be performed from the repository root with `PYTHONPATH=src`
- Ethics Pack Version 4.4 has been generated, visually verified, issued and acknowledged under approved controls
- Site permission remains valid
- No customer, non-participant, real document, payment screen or other sensitive material is present during deliberate failure testing
- The laptop has sufficient local storage and a timezone-aware SGT clock
- DJI, MediaMTX and laptop recording are disabled
- The site's uncontrolled public Wi-Fi network is used by the laptop, ESP-A1, ESP-A2 and DJI
- Any required network configuration remains only in the authorised local deployment copy; never place it in logs or shared evidence
- The laptop's current network address matches the locally flashed `LAPTOP_IP` value on both boards

## 1. Place and inspect hardware
1. ESP-A1, ESP-A2 and Camera A must be positioned exactly as specified in `docs/hardware/placement.md`
2. It must be confirmed that ESP-A1 has its insulated HC-SR04 ECHO voltage divider and uses local UDP port `4210`
3. It must be confirmed that ESP-A2 has no ultrasonic sensor and uses local UDP port `4211`
4. It must be confirmed that all power and charging cables are secure and clear of staff/public routes, liquids, drawers and moving equipment
5. It must be confirmed that Camera A is clamped in its accepted final position and configured for 1920x1080 at approximately 30 FPS
6. Both boards must be powered, and 30-60 seconds must be allowed for PIR sensor stabilisation

## 2. Verify board startup state
Each board's serial output must be opened at 115200 baud, and the following must be confirmed:
| Check | ESP-A1 | ESP-A2 |
|---|---|---|
| Node ID | `ESP-A1` | `ESP-A2` |
| Sensor configuration | `A_PIR_US_MIC` | `A_PIR_MIC` |
| Local UDP port | `4210` | `4211` |
| Ultrasonic fields | required | prohibited |

Firmware versions and boot IDs must be recorded in the acceptance evidence. Wi-Fi credentials, participant details and unnecessary serial output must not be copied.

## 3. Start local camera bridge
MediaMTX must be started:
```bash
mediamtx config/mediamtx.local.yaml
```

Configure DJI to publish to the locally selected laptop address:
```text
rtmp://LAPTOP_IP:1935/ingest/camera_a
```

ARIA must read from the local relay only:
```text
rtsp://127.0.0.1:8554/live/camera_a
```

It must be confirmed that the ARIA-facing path exposes exactly one H264 video track with no audio track. Recording must remain disabled.

## 4. Run component diagnostics
The 60-second camera diagnostic must be run:
```bash
PYTHONPATH=src python3 scripts/test_cameras.py \
  --camera camera_a --duration 60
```
`camera_a`, 1920x1080 and approximately 30 FPS are required. Successful and dropped reads, measured FPS, longest gap and stream availability must be recorded.

The masked-only preview must be inspected using the accepted configuration. An unmasked preview must not be opened or retained:
```bash
PYTHONPATH=src python3 scripts/preview_privacy_mask.py \
  --source rtsp://127.0.0.1:8554/live/camera_a \
  --mask-config config/masks.batamfast.yaml
```
It must be confirmed that `camera_a` and version `batamfast-v2` are identified in the mask, that verification is complete, and that only the approved staff-side region is retained. The preview must be closed locally without frames being saved.

## 5. Run fail-closed preflight
Fresh ESP packets are awaited on UDP port `5005` during preflight. A separate receiver must not be run on the same port while this command is active.
For Phase 8 non-research work:
```bash
PYTHONPATH=src python3 -m aria.collection.run_session \
  --preflight-only \
  --session-kind non_research_dry_run \
  --dji-recording-disabled \
  --camera-config config/cameras.batamfast.yaml \
  --mask-config config/masks.batamfast.yaml \
  --mediamtx-config config/mediamtx.local.yaml \
  --output-directory data/raw
```
The preflight must fail closed if camera identity/mode, mask verification, video-only status, ESP identity/freshness, local storage, SGT clock or the pause/stop interface is invalid.
To create a validated planned manifest without starting a writer, replace `--preflight-only` with `--prepare-session`. A planned manifest must exist before any writer starts.

## 6. Run Phase 8 acceptance scenario
`docs/testing/live_site_acceptance_test.md` and `docs/testing/zone_a_integration_test.md` must be followed for the formal interval.
- Both boards, Camera A, the verified mask and health monitoring must be run together
- Packet delivery, gaps, restarts and RSSI must be recorded separately for each board
- Camera FPS, successful/dropped reads, latency, longest gap and disconnects must be recorded
- ESP-A1 and ESP-A2 recovery must be tested separately by restarting or power-cycling only one board at a time. A new boot ID, public-network reassociation, resumed telemetry and uninterrupted packets from the other board must be confirmed. The public access point must not be interrupted or reconfigured.
- Non-research privacy-failure scenarios must be completed in `docs/testing/privacy_failure_test.md`
- Each board must be measured against the unchanged 98% delivery target. ESP-A2's accepted public-network shortfall must be retained as a known operational limitation without the target being lowered or the network being claimed as a proven cause.
- Every pause, exclusion, deletion and recovery action must be recorded

For a lifecycle-owned non-research run:
```bash
PYTHONPATH=src python3 -m aria.collection.live_session \
  --dji-recording-disabled \
  --camera-config config/cameras.batamfast.yaml \
  --mask-config config/masks.batamfast.yaml \
  --mediamtx-config config/mediamtx.local.yaml \
  --tracker-config config/bytetrack.zone_a.persistence.yaml \
  --detector-confidence 0.10 \
  --pose-confidence 0.15 \
  --keypoint-confidence 0.5 \
  --min-confident-keypoints 4 \
  --processing-fps 15 \
  --inference-size 768 \
  --pose-inference-size 384 \
  --output-directory data/raw
```
These are the accepted Phase 5.4 live CV settings and are also used as the lifecycle runner defaults. The options must be kept explicit in the acceptance command so that the tested configuration is visible in the manual test record.

The local `status`, `pause TYPE`, `resume ACTION...`, `stop` and `abort` commands must be used. Individual application writers must not be closed independently.

### Phase 9.3 formal participant session
The active v7 template is provided below. A historical profile must not be substituted.

The manifest-owned masked browser preview must be kept open for the full retained session. Each pseudonymised participant's persistent card must be used to select the current visible local track and dominant approved activity. Two-second SGT boundaries are recorded automatically by the server. A card must be changed only when that participant's track, activity or validity changes; local track IDs are not designated as participant IDs.
```bash
PYTHONPATH=src python3 -m aria.collection.live_session \
  --session-kind participant \
  --participant-id P0000 \
  --acknowledgement-confirmed \
  --annotator-id A001 \
  --dji-recording-disabled \
  --camera-config config/cameras.batamfast.yaml \
  --mask-config config/masks.batamfast.yaml \
  --mediamtx-config config/mediamtx.local.yaml \
  --collection-profile config/collection.zone_a.v7.yaml \
  --detector-model yolov8n.pt \
  --pose-model yolov8n-pose.pt \
  --tracker-config config/bytetrack.zone_a.persistence.yaml \
  --detector-confidence 0.10 \
  --detector-iou 0.70 \
  --pose-confidence 0.15 \
  --keypoint-confidence 0.5 \
  --min-confident-keypoints 4 \
  --processing-fps 15 \
  --inference-size 768 \
  --pose-inference-size 384 \
  --masked-track-preview \
  --output-directory data/raw
```
Replace `P0000` with each applicable pseudonym and repeat the option for multiple consenting participants. Sessions may finish below the approved
90-minute maximum. End normally with `stop`, verify the completed manifest and output accounting, complete the post-session checklist, and resolve every incident, exclusion and deletion action before retaining the session.

## 7. Pause and recovery rules
Collection must be paused immediately for:
- Customer or non-participant entry
- Camera movement or privacy-boundary change
- missing, unverified or failed mask
- Camera stream loss
- ESP-A1 or ESP-A2 loss
- Storage failure
- Unsafe equipment or cable movement
Only schema-approved, non-identifying incident information must be recorded. All affected window IDs must be excluded. Resumption from privacy-critical incidents is prohibited until required isolation/deletion is complete and the incident-specific recovery action has been verified. Both camera and mask reverification are required after camera movement.
If safe recovery cannot be demonstrated, abort the session and quarantine its outputs for review; do not mark the manifest completed.

## 8. Clean shutdown
1. The session must be stopped through the lifecycle controller so that every writer is closed and file, record, exclusion and gap accounting is reported
2. It must be confirmed that the final manifest is schema-valid and that `completed` is recorded. An `aborted` manifest must be treated as unusable until reviewed.
3. The post-session checklist, incident records and required deletions must be completed
4. DJI publishing must be stopped
5. MediaMTX must be stopped
6. ESP-A1 and ESP-A2 must be powered down
7. Only approved numerical evidence and non-identifying summaries must be preserved
8. Raw/masked video and raw audio must be excluded from the repository and cloud services

## Evidence to retain
- Dated Phase 8 acceptance record and explicit GO/NO-GO decision
- firmware/config/mask versions and non-identifying placement confirmation
- Per-board packet counts, delivery, gaps, restarts and RSSI
- Camera health and video-only verification
- Preflight report and planned/final manifests
- Schema-valid incident and exclusion records
- Completed pre/post-session checklists and deletion evidence
Phase 8.4 GO does not override a failed live check. If any mandatory admin, privacy, equipment or preflight condition fails, that session
is a NO-GO and no writer may start until the condition is corrected and reverified.