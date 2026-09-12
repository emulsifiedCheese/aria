# Zone A Live-Site Calibration Protocol
## Purpose
The final physical positions, operating baselines and acceptance evidence for the active ARIA deployment at BatamFast, Singapore Cruise Centre (Harbourfront), are established by this protocol before participant data collection.

The following components are included in the active deployment:
| Component | Identity and configuration | Active function |
|---|---|---|
| ESP8266 board 1 | `ESP-A1`, `A_PIR_US_MIC`, local UDP `4210` | PIR motion, HC-SR04 ultrasonic distance and numerical microphone features |
| ESP8266 board 2 | `ESP-A2`, `A_PIR_MIC`, local UDP `4211` | PIR motion and numerical microphone features; no ultrasonic sensor |
| Laptop receiver | UDP `5005` | Accepts only ESP-A1 and ESP-A2 |
| Camera A | DJI Osmo Action 5 Pro, `camera_a` | One masked 1920×1080, 30 FPS view of the approved Zone A staff-side region |

Zone B, Zone T, ESP-B, ESP-T, the second camera, cross-zone inference and the Station Manager role are excluded from the active study. They must not be reintroduced by any calibration trial in this protocol.
The following conditions are verified during calibration:
- The correct identity, Zone A assignment and sensor fields are reported by each board
- Responses to intended activity are provided by ESP-A1 and ESP-A2 at their respective Zone A placements
- ESP-A1 ultrasonic readings are valid and stable across its intended working range
- Usable numerical sound-feature baselines are produced by both boards without raw audio being retained
- Laptop receive timestamps and packet continuity are suitable for later sensor-to-camera alignment
- Only the approved Zone A staff-side area can be retained from the DJI camera position
- Installation is safe, fixed and repeatable

## Scope and prerequisites
This is a technical calibration using non-research test movement and ordinary non-identifying sound. It is not a participant-recording session.
Before starting:
- Firmware version `1.1.1` must be run on both boards
- Laptop destination IP in both sketches must match deployment laptop
- Telemetry schema and UDP receiver must be current
- Only `live/camera_a` must be used by the DJI camera and MediaMTX bridge
- Ethics Pack Version 4.4, including expanded Part D, must be the current scope reference
- No customer, non-participant, payment surface, screen, sensitive document or identifying information may be visible in a retained camera region
- Final participant collection must remain disabled until site mask has been verified

## Privacy and safety controls
- Raw audio or intelligible speech must not be recorded or retained. Only numerical features transmitted by ESP-A1/A2 must be used
- Raw or masked video must not be uploaded to Firebase, cloud notebooks or other cloud services
- A camera feed must not be opened or retained while customers or non-participating staff could enter an unmasked view
- Camera setup must begin in a controlled, clear area with recording disabled
- The site-specific mask must be applied and verified before frames are used for detection, pose estimation, display beyond the calibration operator, or temporary storage
- Full-frame development mask must not be used with participant or live workplace footage
- Only non-identifying operator labels, such as `researcher`, must be used
- Participant names or real staff identifiers must not be written into calibration records or logs
- Both boards, camera mounts, USB leads and power cables must be secured so that staff and public walkways are not obstructed
- Calibration must be stopped immediately if equipment becomes hot, unstable, exposed to liquids or physically unsafe

## Required equipment and files
- ESP-A1 with PIR, HC-SR04, MAX4466 and required HC-SR04 voltage divider
- ESP-A2 with PIR and MAX4466
- Deployment laptop and site's uncontrolled public Wi-Fi network
- Suitable USB power sources and secured cables
- DJI Osmo Action 5 Pro and stable mount
- MediaMTX configured with `config/mediamtx.local.yaml`
- Measuring tape
- Removable placement markers
- Non-identifying calibration record
- Current files:
  - `firmware/esp_a/ESP_A_v1/ESP_A_v1.ino`
  - `firmware/esp_a/ESP_A2_v1/ESP_A2_v1.ino`
  - `schemas/esp_packet.schema.json`
  - `config/cameras.batamfast.yaml`
  - `config/masks.batamfast.yaml`
ESP-B, ESP-T and a second camera must not be brought to or used for this calibration.

## Information to record
### Session details
The following must be recorded:
- Calibration date and location
- Start and end times (SGT)
- Operator role identifier
- Laptop IP and current source revision, if available
- Firmware version and boot ID for each board
- Camera model and stream identity
- Relevant site conditions, including unusual noise, obstructions, moving air,
  open doors or lighting changes
- Every interruption, deviation or repeated trial

### Placement details
The following must be recorded separately for ESP-A1 and ESP-A2:
- Exact position and height
- PIR direction
- Microphone position and orientation
- Power and cable route
- Initial and final Wi-Fi RSSI
- Intended coverage within Zone A
- Every physical adjustment and its reason
The following must also be recorded for ESP-A1:
- Ultrasonic direction and height
- Voltage-divider confirmation
- Fixed reflective surfaces in its field
- Tape-measured reference distances
The following must be recorded for Camera A:
- Mount position, height and direction
- 1920×1080 at 30 FPS capture confirmation
- RTMP publication and local RTSP read paths
- Mask coordinates and verification status
- Retained staff-side boundary
- Excluded customer-facing and sensitive areas
- Any movement of camera after mask verification

### Evidence files
Only approved, non-identifying evidence must be retained:
- UDP receiver diagnostic log
- Separate ESP-A1 and ESP-A2 logs
- Calibration result table
- Aggregate packet statistics
- Numerical sensor summaries
- Final equipment measurements
- Final mask coordinates
- A pass/fail decision with corrective actions
Unmasked screenshots or raw audio must not be retained.

## Suggested 60-minute plan
| Time | Activity |
|---|---|
| 0–5 minutes | safety check, open record and mark proposed positions |
| 5–10 minutes | power ESP-A1 and ESP-A2 and allow PIR stabilisation |
| 10–15 minutes | verify identities, schema, receiver logs and clear-site baseline |
| 15–28 minutes | calibrate ESP-A1 PIR, ultrasonic and numerical audio features |
| 28–38 minutes | calibrate ESP-A2 PIR and numerical audio features |
| 38–50 minutes | verify DJI stream, framing and site-specific mask |
| 50–57 minutes | run combined two-board and one-camera validation |
| 57–60 minutes | review evidence and record calibration decision |

The session must be extended if a trial must be repeated. The number of required trials must not be reduced merely to fit the suggested schedule.

## Acceptance targets
| Area | Acceptance target |
|---|---|
| Active scope | only ESP-A1, ESP-A2 and DJI Camera A are present and enabled |
| Identity and schema | every valid packet has expected node ID, Zone A identity and sensor configuration |
| ESP-A1 payload | distance and audio fields are present |
| ESP-A2 payload | audio fields are present and distance fields are absent |
| Delivery | Measure against unchanged 98% target overall and per board; retain any accepted public-network shortfall as an explicit operational limitation |
| Packet order | no unexplained boot-ID change; gaps, duplicates, restarts and out-of-order packets are recorded |
| PIR intended movement | at least 4 of 5 intended movements are detected at each board placement |
| PIR placement separation | no more than 1 of 5 movements local to other board's placement causes an unintended trigger |
| PIR hold | approximately 10 seconds, allowing for the one-second packet interval |
| ESP-A1 ultrasonic validity | at least 95% valid readings at every intended operating point |
| ESP-A1 ultrasonic accuracy | median reading within the greater of 10 cm or 10% of the tape-measured reference |
| ESP-A1 ultrasonic stability | interquartile range no greater than 10 cm at each stationary point |
| Numerical audio baseline | separate distributions recorded for ESP-A1 and ESP-A2 without raw audio |
| Numerical audio separation | at least one numerical feature shows a usable separation between baseline and controlled ordinary activity |
| Camera identity | only `camera_a` is configured and the source is the local DJI RTSP bridge |
| Camera mode | 1920×1080 at 30 FPS |
| Privacy mask | verified, non-empty, resolution-matched and limited to the approved Zone A staff-side area |
| Exclusions | customer-facing areas, screens, payment surfaces, sensitive documents and non-participants are excluded |
| Timing readiness | laptop timestamps, boot IDs and controlled-trial markers are available for later alignment |

## Procedure
### 1. Open calibration record
1. Session details must be recorded, and site clearance for technical calibration must be confirmed
2. `docs/calibration/results/2026-07-30_phase_2_3_trial_intervals_template.csv` must be copied to `docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv`. Timezone-aware Singapore start/end timestamps must be recorded for every baseline, PIR, ultrasonic and numerical-audio interval
3. It must be confirmed that active scope is ESP-A1, ESP-A2, Zone A and Camera A only
4. It must be confirmed that no participant collection is running
5. Sufficient local storage must be confirmed, and all cloud video uploads must be disabled
6. Any deviation must be noted before continuing

### 2. Install ESP-A1
1. ESP-A1 must be positioned to observe its defined portion of the Zone A staff-side counter workspace
2. The PIR must be aimed at intended staff movement and away from public walkways, sunlight, heat sources and moving air where practical
3. The HC-SR04 must be aimed across the intended working distance, with customers and unstable moving surfaces excluded from its direction
4. It must be confirmed that HC-SR04 echo line uses the required voltage divider
5. Microphone away must be positioned from direct airflow and vibration
6. Board, power lead and sensor wiring must be secured
7. All placement details must be measured and recorded

### 3. Install ESP-A2
1. ESP-A2 must be positioned at the second defined Zone A placement
2. The PIR must be aimed at the activity area intended to be supplemented by ESP-A2
3. Unnecessary overlap must be avoided with ESP-A1 while retaining the required Zone A coverage
4. Microphone away must be positioned from direct airflow and vibration
5. It must be confirmed that no ultrasonic sensor is attached
6. Board, power lead and sensor wiring must be secured
7. All placement details must be measured and recorded

### 4. Start and verify telemetry
1. Receiver must be started:
   ```bash
   PYTHONPATH=src python3 -m aria.ingestion.udp_receiver
   ```
2. The startup message must be confirmed:
   ```text
   UDP receiver started on 0.0.0.0:5005; accepting ESP-A1 and ESP-A2 only
   ```
3. Both boards must be powered, and 30–60 seconds must be allowed for PIR stabilisation
4. Each Serial Monitor must be checked at 115200 baud
5. The following settings must be confirmed:

   | Node | Zone | Firmware | Sensor configuration | Local UDP |
   |---|---|---|---|---:|
   | ESP-A1 | A | `1.1.1` | `A_PIR_US_MIC` | 4210 |
   | ESP-A2 | A | `1.1.1` | `A_PIR_MIC` | 4211 |

6. It must be confirmed that ESP-A1 packets include `distance_cm` and `distance_valid`
7. It must be confirmed that ESP-A2 packets omit both distance fields
8. It must be confirmed that both boards include all required PIR, audio, Wi-Fi, boot, sequence and timestamp fields
9. The separate logs must be followed:
   ```bash
   tail -f outputs/logs/esp_a1.log
   ```
   ```bash
   tail -f outputs/logs/esp_a2.log
   ```
10. Firmware versions, boot IDs, initial RSSI and any invalid packets must be recorded.

### 5. Record clear-site baseline
1. Baseline start time must be marked
2. Intended sensing areas must be kept clear for five minutes
3. Deliberate movement or sound near either board must be avoided
4. Baseline end time must be marked
5. The following must be calculated for each board and each numerical audio feature:
   - Sample count
   - Minimum and maximum
   - Median
   - 25th and 75th percentiles
   - 95th percentile
6. For ESP-A1, the valid ultrasonic-reading percentage must be calculated and fixed surfaces represented by the readings must be noted
7. Unexplained PIR triggers must be counted, and likely environmental causes must be investigated
Real undisturbed site conditions should be represented by the baseline. Artificial silence must not be manufactured.

### 6. Calibrate ESP-A1
#### PIR trials
1. Five ordinary test movements inside ESP-A1's intended coverage must be performed
2. A stationary position must be resumed, and sufficient time must be allowed for the PIR output to clear between repetitions
3. Current motion, recent-activity state and missed detections must be recorded
4. Five movements must be performed within ESP-A2's intended placement
5. Any unintended ESP-A1 triggers must be recorded
6. It must be confirmed that the observed recent-activity hold is approximately 10 seconds

#### Ultrasonic trials
1. At least three representative operating points across the intended working range must be marked
2. Actual sensor-to-target distance must be measured with a tape
3. A stable, non-identifying target must be held at each point
4. At least 30 ESP-A1 readings per point must be collected
5. Valid-reading percentage, median, interquartile range and error must be calculated
6. Any failed point must be repeated after checking alignment, obstruction, voltage divider and reflective surfaces

#### Numerical audio-feature trials
1. At least one minute of controlled ordinary counter activity must be recorded without recording raw audio
2. Non-sensitive sounds, such as normal movement or keyboard activity, must be used
3. Real customer interactions or intelligible conversation must not be used as a calibration stimulus
4. Feature distributions must be compared with the ESP-A1 baseline
5. A proposed downstream feature or threshold must be recorded only if the acceptance target is met
6. `accepted=true` must be set for the ESP-A1 audio-activity interval only after evidence of usable separation from the ESP-A1 baseline has been provided by the generated numerical summary

### 7. Calibrate ESP-A2
#### PIR trials
1. Five ordinary test movements inside ESP-A2's intended coverage must be performed
2. A stationary position must be resumed, and sufficient time must be allowed for the PIR output to clear between repetitions
3. Current motion, recent-activity state and missed detections must be recorded
4. Five movements must be performed within ESP-A1's intended placement
5. Any unintended ESP-A2 triggers must be recorded
6. It must be confirmed that the observed recent-activity hold is approximately 10 seconds

#### Numerical audio-feature trials
1. At least one minute of controlled ordinary counter activity must be recorded without recording raw audio
2. The same non-sensitive stimulus type used for ESP-A1 must be used where practical
3. Real customer interactions or intelligible conversation must not be used
4. Feature distributions must be compared with the ESP-A2 baseline
5. A proposed downstream feature or threshold must be recorded only if the acceptance target is met
6. `accepted=true` must be set for the ESP-A2 audio-activity interval only after evidence of usable separation from the ESP-A2 baseline has been provided by the generated numerical summary
Ultrasonic trials must not be performed for ESP-A2.

### 8. Verify DJI Camera A and privacy mask
1. It must be confirmed that the area is controlled and clear of customers, non-participants, screens, payment surfaces and sensitive documents. Consenting Counter Agents may assist with live boundary calibration
2. MediaMTX must be started:
   ```bash
   /opt/homebrew/bin/mediamtx config/mediamtx.local.yaml
   ```
3. The DJI stream must be published to:
   ```text
   rtmp://<laptop-ip>:1935/ingest/camera_a
   ```
4. It must be confirmed that MediaMTX starts the FFmpeg hook and republishes exactly one H264 video track with no audio
5. It must be confirmed that ARIA reads only:
   ```text
   rtsp://127.0.0.1:8554/live/camera_a
   ```
6. Camera diagnostic must be run:
   ```bash
   PYTHONPATH=src python3 scripts/test_cameras.py --camera camera_a --duration 15
   ```
7. The camera identity and the 1920×1080 at 30 FPS capture mode must be confirmed
8. Masked-only draft calibration preview must be run:
   ```bash
   PYTHONPATH=src python3 scripts/preview_privacy_mask.py \
     --source rtsp://127.0.0.1:8554/live/camera_a \
     --mask-config config/masks.batamfast.yaml
   ```
   `verified: false` is permitted by the utility only for calibration; no unmasked frame is displayed, no detection is run and no frames are written
   `--interactive` can be added so that the polygons can be edited safely in the masked preview
   A polygon can be selected with `1`-`9` or `[`/`]`. A point can be inserted by double-clicking its boundary and moved by dragging it.
   A separate polygon can be started with `n`; its points can be added with single clicks, and it can be completed with Enter after at least three points. It can be cancelled with Escape. Changes can be undone with `u` and saved with `s`. `verified: false` is enforced when changes are saved.
10. With recording disabled, the retained rectangle must be set in `config/masks.batamfast.yaml`
11. The preview must be closed with `q`, polygon vertices must be adjusted as needed, and the preview must then be restarted
12. It must be ensured that only the approved Zone A staff-side region is retained by the mask
13. All exclusion boundaries and normal Counter Agent movement must be verified at edges of retained region
14. The preview must be closed with `q`
15. `verified: true` must be set only after the final position and coordinates have been accepted
16. The privacy-failure procedure must be run, and rejection of the following by the participant-mode pipeline must be confirmed:
    - A missing or unverified mask;
    - A wrong camera identity;
    - A resolution mismatch;
    - An empty mask; and
    - Out-of-bounds coordinates
17. Final mount measurements and mask coordinates must be recorded

Following any camera movement after verification, the mask verification is invalidated and the procedure in this section must be repeated.

### 9. Run combined validation
Without moving accepted equipment:
1. It must be confirmed that both boards remain present in receiver
2. It must be confirmed that Camera A remains connected with its verified mask
3. One intended movement must be performed at ESP-A1 placement
4. One intended movement must be performed at ESP-A2 placement
5. A stable target must be presented at one accepted ESP-A1 ultrasonic point
6. It must be confirmed that expected packets, camera health and timestamps are recorded
7. Interval must be inspected for malformed packets, gaps, restarts, unexpected triggers, invalid distance readings or camera drops
8. It must be confirmed that no retired node, zone, camera or role is included in active output

Identity must not be inferred from PIR, distance or sound features. Cross-zone movement inference must not be attempted.

### 10. Record decision
One outcome must be marked:
- **Pass** — all mandatory targets are met;
- **Complete with accepted operational limitations** — execution, safety, privacy and recovery requirements are complete, but a measured non-privacy operational target remains below threshold and is carried unchanged into the Phase 8.4 decision;
- **Conditional pass** — only documented non-privacy corrective work remains;
  or
- **Fail** — a mandatory, safety, privacy or scope requirement is unmet

A target must not be lowered or its failed measurement converted into a pass through acceptance of an operational limitation. The measured result, deployment constraint and residual risk must be stated so that an explicit GO/NO-GO decision can be made in Phase 8.4.

For a conditional pass or failure, the following must be recorded:
- Failed target
- Evidence
- Corrective action
- Owner
- Retest date
- Final disposition
Participant collection must not be started after a conditional pass or failure. Collection is not authorised solely by completion with an accepted operational limitation; it remains blocked until GO is explicitly recorded in Phase 8.4 and the limitation is included in that decision.

## Result record
The completed current record is `docs/calibration/results/2026-08-02_phase_8_1_live_site_calibration.md`. The blank table below is retained only as a reusable template for a later recalibration after equipment movement, configuration change or replacement; it is not an outstanding Phase 8.1 record.

| Item | Result or evidence |
|---|---|
| Date, location and Singapore time | |
| Operator role identifier | |
| ESP-A1 firmware version and boot ID | |
| ESP-A2 firmware version and boot ID | |
| Final ESP-A1 position and measurements | |
| Final ESP-A2 position and measurements | |
| ESP-A1 PIR result | |
| ESP-A2 PIR result | |
| ESP-A1 ultrasonic result | |
| ESP-A1 numerical audio baseline/result | |
| ESP-A2 numerical audio baseline/result | |
| Packet delivery and fault summary | |
| DJI Camera A position and stream result | |
| Site-mask coordinates and verification | |
| Exclusion-boundary result | |
| Timing evidence retained | |
| Deviations and corrective actions | |
| Final decision | |
| Operator initials and date | |

## Stop and invalidate conditions
Calibration must be stopped and the affected interval must be marked invalid if:
- Node identity, sensor configuration or zone is wrong
- The wrong firmware or local UDP port is used by ESP-A1 or ESP-A2
- Ultrasonic fields are emitted by ESP-A2
- Packets are malformed or cannot be separated by node
- Equipment or cabling is unsafe
- Raw audio is recorded
- An unmasked or incorrectly masked camera frame is retained or processed
- A customer, non-participant or sensitive surface enters retained region
- The camera is moved after mask verification
- Any raw or masked video is uploaded to a cloud service
- Participant-identifying information is entered into calibration records
- Retired zones, nodes, cameras or roles are introduced into procedure
The issue must be corrected and documented, and the affected section must be repeated before calibration is accepted.

## Generate Phase 2 evidence report
After controlled calibration and the formal endurance run, the completed calibration interval file must be used together with the Phase 2.4 event interval file:
```bash
PYTHONPATH=src python3 scripts/generate_integration_report.py \
  --input data/raw/esp_packets.jsonl \
  --intervals docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv \
  --intervals docs/testing/2026-08-02_phase_2_4_event_intervals.csv \
  --start 2026-08-02T14:13:15+08:00 \
  --end 2026-08-02T15:43:15+08:00 \
  --output docs/testing/results/2026-08-02_zone_a_phase_2_4_run_4_evidence.md
```
Phase 2.3 must not be marked complete unless **PASS** is reported in the generated report and the source interval timestamps and all corrective actions have been manually reviewed.