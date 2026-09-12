# ARIA — Activity Recognition & Inference Architecture

ARIA is a privacy-preserving, multimodal human activity recognition system for shared service-counter environments.
The following components are combined in the project:
- Computer vision for person detection, tracking, pose estimation, and zone assignment
- Ambient IoT sensing from two ESP8266 nodes in Zone A
- Numerical audio features rather than recorded speech
- Feature-level multimodal fusion
- Local edge inference on a laptop
- required, non-blocking Firebase Realtime Database synchronisation for approved non-identifying prediction summaries
- A dashboard for real-time activity status and session review

Bounded in-memory windows, the frozen model and the localhost dashboard are connected by the [Phase 13 diagnostic runner](docs/testing/phase_13_final_acceptance.md#diagnostic-runner-31-august-2026), added on 31 August. Its hardware-free checks can be started with `PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py --input-scope synthetic`. An empty retained camera region and explicit privacy confirmations are required by its integrated hardware diagnostic mode; operation is paused when people are detected. Firebase transport is simulated locally and temporary summaries are purged on normal shutdown. In a separate `--equipment-only` mode, approved staff are permitted to remain during non-research camera/ESP health checks: no detection, pose, activity inference, recording, evidence files or cloud client is started. New participant collection is not authorised and Phase 13 completion is not claimed by either mode.

For the explicitly approved, non-research on-screen demonstration, `--live-display-only --approved-staff-present` is also provided in Phase 13 with the mask-alignment and recording-disabled confirmations. Local inference/dashboard operation is performed in memory without recording, evidence files, a cloud client or an outbox. The procedure is documented in the [live-display-only operating instructions](docs/testing/phase_13_final_acceptance.md#live-display-only-with-approved-staff-present). This mode is not designated as new participant collection or accuracy evaluation.

---

## Project objective

Shared service environments are often occupied by multiple staff members with different roles, with activities performed simultaneously in the same physical space. Digital activity is largely observed by existing employee-monitoring tools, while presence or movement is typically detected by occupancy systems without each person's activity being identified.

ARIA is designed to determine the activity being performed by each pseudonymised observed subject while privacy is preserved and wearable sensors are avoided. Subject links are established using session-local tracks and pseudonymised participant IDs; biometric identity recognition is not performed.

One staff role is included in the active study:
| Role | Activity classes |
|---|---|
| Counter Agent | Serving/Processing, Idle/Waiting, Reaching/Handling |

The Station Manager role and its former activity classes are retired from the active study. Role attribution is not performed by the system.
One physical zone is used in the active deployment:
| Zone | Description |
|---|---|
| Zone A | Front counter and customer-service work area |

---
## Current hardware architecture
Two independent ESP8266 sensor nodes are used by ARIA in Zone A.

### ESP-A1 and ESP-A2 — Zone A
Distinct placements within the front counter area are monitored by ESP-A1 and ESP-A2.

**ESP-A1 connected components**
- HC-SR501 PIR motion sensor
- HC-SR04 ultrasonic distance sensor
- MAX4466 analogue microphone module
- USB power

**ESP-A2 connected components**
- HC-SR501 PIR motion sensor
- MAX4466 analogue microphone module
- USB power

**Locked wiring**
| Component | ESP8266 connection |
|---|---|
| PIR OUT | D1 |
| PIR VCC | VIN |
| PIR GND | GND |
| HC-SR04 TRIG | D5 |
| HC-SR04 ECHO | D6 through voltage divider |
| HC-SR04 VCC | VIN |
| HC-SR04 GND | GND |
| MAX4466 OUT | A0 |
| MAX4466 VCC | 3V3 |
| MAX4466 GND | GND |

The HC-SR04 and its voltage divider are fitted only to ESP-A1. No ultrasonic sensor is fitted to ESP-A2, and distance fields are omitted from its packets.

### Cameras
The only deployment camera is the DJI Osmo Action 5 Pro:
- The approved masked staff-side region of Zone A is covered by Camera A
- Camera A video is streamed wirelessly through the local MediaMTX bridge
- Camera A is configured for 1920×1080 at 30 FPS

Camera A is fixed in its documented final mount, and only the approved staff-side Zone A region is retained using the verified `batamfast-v2` mask. The site-specific mask coordinates, deliberate-movement fail-closed recovery and live masked-pipeline acceptance have been completed at the approved site.

Hardware documentation and photographs are stored in [`docs/hardware/`](docs/hardware/).

---
## System architecture
An edge-first architecture is followed by ARIA.
```text
ESP-A1 ─┐
ESP-A2 ─┴── UDP JSON telemetry ──> Laptop ingestion layer
                                        │
                                     ├── DJI Camera A capture
                                     ├── ROI masking
                                     ├── Person detection and tracking
                                     ├── Pose and movement features
                                     ├── Sensor synchronisation
                                     ├── Multimodal fusion
                                     ├── Activity classification
                                     ├── Local logging
                                     └── Dashboard
                                              │
                                              └── Abstracted feature data only
                                                  to Firebase when enabled
```

### Tier 1 — Distributed sensor nodes
The following operations are performed by each ESP8266:
1. Connected sensors are read
2. Numerical features are derived locally
3. A JSON packet is constructed
4. The packet is transmitted over Wi-Fi using UDP
5. Node identity, zone, sequence number, timing, connectivity, and sensor values are included

No raw audio is transmitted.

### Tier 2 — Laptop edge host
The following operations are performed on the laptop:
- UDP packet ingestion and validation
- Camera capture
- Customer-region masking
- Person detection
- Multi-person tracking
- Pose estimation
- Temporal feature extraction
- Cross-modal synchronisation
- Feature-level fusion
- Model inference
- Local session recording
- Annotation support
- Evaluation
- Dashboard display

Raw video remains local and temporary.

### Tier 3 — Cloud layer
When enabled, only approved abstracted data is received by Firebase, such as:
- Pseudonymised identifiers
- Elapsed timestamps
- Sensor readings
- Numerical audio features
- Pose or movement features
- Fused feature vectors
- Activity predictions
- Model or session metadata

Raw video, raw audio, waveform data, intelligible speech, and participant-identifiable recordings must not be uploaded.

---
## ESP packet format
One JSON packet is transmitted by each ESP node approximately once per second.
Fields such as the following are included in a typical packet:

```json
{
  "schema_version": 1,
  "firmware_version": "1.1.1",
  "sensor_config": "A_PIR_US_MIC",
  "boot_id": 12319,
  "node_id": "ESP-A1",
  "zone": "A",
  "sequence": 222,
  "timestamp_ms": 226082,
  "wifi_connected": true,
  "wifi_rssi_dbm": -64,
  "pir_motion": false,
  "pir_recent_activity": true,
  "distance_cm": 206.16,
  "distance_valid": true,
  "audio_peak_to_peak": 52,
  "audio_activity": 7.31,
  "audio_rms": 9.21
}
```
Fields vary by node:
- ESP-A1 (`A_PIR_US_MIC`): PIR, ultrasonic distance, and numerical audio features
- ESP-A2 (`A_PIR_MIC`): PIR and numerical audio features; no ultrasonic fields

The canonical packet definition is stored in [`schemas/esp_packet.schema.json`](schemas/esp_packet.schema.json).

---
## Audio privacy
The following are neither stored nor transmitted by ARIA:
- Raw audio
- Audio waveforms
- Intelligible speech
- Speech recognition output
- Transcripts
- Voice-identification features

The MAX4466 modules are used only to compute numerical environmental audio features such as:
- Peak-to-peak amplitude
- Root mean square
- Mean absolute deviation or activity level
- Calibrated threshold states

Visually similar activities may be distinguished with the assistance of these values without conversational content being retained.

---
## Vision pipeline
The vision-pipeline foundation is implemented under [`src/aria/vision/`](src/aria/vision/) and [`src/aria/cameras/`](src/aria/cameras/). The following areas are covered by current modules:
1. Camera discovery and capture management
2. Staff-region privacy masking
3. Person-detector integration points
4. Track-management integration points
5. Pose-estimation integration points
6. Feature writing
7. Pipeline orchestration

The following components are used or are intended to be integrated in the implementation:
- OpenCV for camera capture, masking, and frame handling
- YOLO for person detection or pose estimation
- ByteTrack for persistent track continuity
- MediaPipe Pose as a lightweight pose alternative
- Random Forest or 1D-CNN models for activity classification

The privacy-mask implementation is covered by unit tests. Live validation with the physical DJI camera is complete through Phase 5.4. The final framing and verified `batamfast-v2` retained-region coordinates are recorded in the BatamFast configuration, with the accepted tracking and processing-rate limitations documented in `docs/testing/results/`.

---
## Privacy and ethics
ARIA is designed for consenting real counter staff carrying out their normal duties in a live workplace.
Real customers may be present, but they are not research participants.
The following rules are applied:
- Participation is voluntary
- No workplace consequences may be imposed for declining or withdrawing
- Only consenting staff data may be retained
- Cameras must be angled towards staff-side work area
- Customer-facing regions must be excluded by software masks
- If masking fails or customer-identifiable information enters retained region, affected footage must be excluded and deleted
- Temporarily stored video must already be masked
- Temporary video must remain local on a password-protected laptop
- Raw video must never be uploaded to Firebase or Google Colab
- No raw audio or intelligible speech may be stored
- Retained data must be pseudonymised
- Temporary masked footage is used only for annotation and quality checking
- Temporary footage must be securely deleted after verification and no later than three months after final CM3070 assessment
- Participant-code key must be retained only through withdrawal period and deleted after valid withdrawal requests are processed
- Collection must be paused, or affected intervals must be excluded and deleted, if a non-participating staff member enters a retained camera zone

Site permission was granted on 27 July 2026. The current participant-facing pack is Version 4.4, dated 4 August 2026, with an expanded Part D covering the Zone A-only, Counter Agent-only deployment and the three active activity classes. Signed consent forms, participant identities, withdrawal records, original site-permission correspondence, and identifiable research material are stored securely outside the repository.

Detailed procedures are located in [`docs/privacy/`](docs/privacy/) and participant-facing documentation is stored in [`docs/ethics/`](docs/ethics/).

---
## Repository structure
```text
.
├── AGENTS.md
├── README.md
├── config/
│   ├── cameras.batamfast.yaml
│   ├── cameras.example.yaml
│   ├── masks.batamfast.yaml
│   ├── masks.example.yaml
│   ├── masks.development.yaml
│   └── mediamtx.local.yaml
├── firmware/
│   ├── esp_a/
│   ├── esp_b/
│   ├── esp_t/
│   ├── shared/
│   └── tests/
├── src/
│   └── aria/
│       ├── cameras/
│       ├── ingestion/
│       ├── vision/
│       ├── fusion/
│       ├── collection/
│       ├── models/
│       ├── evaluation/
│       ├── cloud/
│       ├── dashboard/
│       └── logging/
├── schemas/
├── scripts/
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   ├── annotations/
│   ├── manifests/
│   └── excluded/
├── models/
├── outputs/
├── docs/
│   ├── calibration/
│   ├── data_collection/
│   ├── ethics/
│   ├── hardware/
│   ├── privacy/
│   ├── testing/
│   ├── progress/
│   └── report/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── deployment/
    └── windows/
```

### Key directories
| Directory | Purpose |
|---|---|
| `firmware/` | Active ESP-A1/ESP-A2 sketches, retired-node history and component tests |
| `src/aria/` | Implemented application modules and reserved subsystem packages |
| `schemas/` | Machine-readable telemetry schema |
| `scripts/` | Current simulator, camera diagnostic and CV test utilities |
| `data/` | Local data workspace; sensitive content is not committed |
| `models/` | Trained model files and metadata |
| `outputs/` | Evaluation results, logs, plots, and demo outputs |
| `docs/` | Ethics, hardware, privacy, calibration, testing, collection, progress and report records |
| `tests/` | Current unit suite and reserved integration/fixture areas |
| `deployment/` | Reserved for deployment support |

---
## Development setup
### Prerequisites
The following are required for laptop-side development:
- Python 3.12
- Git
- Arduino IDE
- ESP8266 board support for Arduino
- One DJI Osmo Action 5 Pro camera
- site's public Wi-Fi network shared by laptop and both active ESP nodes

CPU-based inference on a laptop is used in the target deployment. Development and unit testing are currently also being performed on macOS, with Windows deployment support retained under [`deployment/windows/`](deployment/windows/).

### Clone repository
```bash
git clone <repository-url>
cd aria
```
### Create a virtual environment
Windows PowerShell:
```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
```
Windows Command Prompt:
```bat
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
```
macOS or Linux:
```bash
python3.12 -m venv .venv
source .venv/bin/activate
```
### Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
The dependencies required by the submitted implementation are listed in requirements.txt.

### Configure application
The example environment file must be copied:
```bash
copy .env.example .env
```
On macOS or Linux:
```bash
cp .env.example .env
```
Local values must then be configured, such as:
- UDP listening address
- UDP port
- DJI Camera A RTSP source
- Output paths
- Masking coordinates
- Firebase enablement
- Logging level

`.env`, Wi-Fi credentials, private keys, or Firebase service-account credentials must never be committed.

---
## Firmware setup
Separate sketches are provided for the two active boards under `firmware/esp_a/`:
```text
firmware/esp_a/
├── ESP_A_v1/ESP_A_v1.ino      # ESP-A1
└── ESP_A2_v1/ESP_A2_v1.ino    # ESP-A2
```
For each active board:
1. Relevant `.ino` file must be opened in Arduino IDE
2. Correct ESP8266 board must be selected
3. Correct serial port must be selected
4. Local Wi-Fi configuration must be entered outside version control
5. The laptop IP and UDP port must be set
6. Sketch must be uploaded
7. Serial Monitor must be opened at configured baud rate
8. Sensor initialisation must be confirmed
9. Wi-Fi connection must be confirmed
10. Packet receipt must be confirmed on laptop

Detailed node-specific instructions are provided in:

- [`firmware/esp_a/ESP_A_README.md`](firmware/esp_a/ESP_A_README.md)

ESP-B and ESP-T documentation is retained in the repository as historical material and is not presented as the active deployment.

---
## Running current implementation
The integrated controlled-session entry point is provided at `aria.collection.live_session`, alongside the component diagnostics and test utilities below. Phase 8 acceptance and all of Phase 9 are complete. The retained formal sessions were started through the frozen-profile check, fresh preflight and pre-session gate. Participant and pilot collection is now closed; the collection command is documented only as historical implementation and audit evidence. Later system development may still be supported by non-research dry runs without participant data being collected.

### Run unit tests
```bash
PYTHONPATH=src python3 -m pytest tests/unit
```
The privacy-mask suite can be run separately:
```bash
PYTHONPATH=src python3 -m pytest tests/unit/test_privacy_mask.py
```
### Simulate two ESP-A nodes
```bash
PYTHONPATH=src python3 scripts/simulate_esp_nodes.py
```
Development telemetry for ESP-A1 and ESP-A2 is emitted by this utility so that ingestion can be exercised without the physical boards.

### Run ESP-A UDP receiver
```bash
PYTHONPATH=src python3 -m aria.ingestion.udp_receiver
```
Only ESP-A1 and ESP-A2 are accepted by the receiver on laptop UDP port `5005`. Separate readable logs are written to:
```text
outputs/logs/esp_a1.log
outputs/logs/esp_a2.log
```
Each log can be monitored in a separate Terminal pane with:
```bash
tail -f outputs/logs/esp_a1.log
```
```bash
tail -f outputs/logs/esp_a2.log
```
### Test DJI Camera A
```bash
PYTHONPATH=src python3 scripts/test_cameras.py \
  --camera camera_a \
  --duration 15 \
  --output outputs/logs/camera_a_diagnostic.json
```
Running instances of FFmpeg and MediaMTX are required. The DJI stream is published to `rtmp://<laptop-ip>:1935/ingest/camera_a`. A localhost FFmpeg relay is started automatically by MediaMTX; the H264 video is copied without re-encoding, audio is removed, and the video is republished at `rtsp://127.0.0.1:8554/live/camera_a`. Only the DJI Camera A configuration is accepted by the diagnostic, and 1920×1080 at 30 FPS is verified. The diagnostic is run headlessly, no frames are retained, and measured FPS, successful reads, read failures, estimated dropped frames, the longest inter-frame gap and local frame-read latency are reported. Frame-read latency is not presented as an end-to-end camera-to-display latency measurement.

### Test current computer-vision pipeline
For Phase 5.2 camera-local tracking, the low-latency tracking-only profile can be used:
```bash
PYTHONPATH=src python3 scripts/test_cv_pipeline.py \
  --source rtsp://127.0.0.1:8554/live/camera_a \
  --camera-id camera_a \
  --mask-config config/masks.batamfast.yaml \
  --tracker-config config/bytetrack.zone_a.yaml \
  --tracking-only \
  --processing-fps 15 \
  --inference-size 640 \
  --duration 60 \
  --output data/interim/camera_a_tracks_phase_5_2.jsonl
```
Frames are timestamped and masked immediately by the capture worker, the RTSP decoder is drained continuously, and only the newest waiting masked frame is retained. Camera A is maintained at 1920x1080 and 30 FPS; CV inference is limited by the 15 FPS value without the deployment capture mode being changed. Captured, processed, deliberately replaced and failed reads are reported in the final console summary. `--duration` must be omitted for the interactive S1-S4 trials.

For the full tracking and pose profile, `--tracking-only` must be omitted and a separate output path must be used. Camera-local IDs are supplied by the accepted person detector and ByteTrack path; keypoints are attached to those tracks through a batched pose pass. A person track is not renumbered or removed because of temporary pose failure. Bounding boxes, track IDs, skeleton lines, keypoint dots, rolling processing FPS and rolling vision-inference latency are overlaid on the masked live preview.

YOLO person-detection non-maximum suppression is controlled by the optional `--detector-iou` argument, for which Ultralytics' `0.70` is used by default. More overlapping detections are suppressed at lower values. Values below the default are designated as experimental: nested duplicate boxes may be removed, but a real person may also be suppressed when two people overlap. A fresh controlled multiple-person check is therefore required before acceptance.

An existing local detector weight is accepted by the lifecycle runner through `--detector-model`, and failure is reported before preflight if the file is missing. `yolov8n.pt` is retained as the accepted default. `yolov8s.pt` is designated as a non-research comparison candidate for testing whether present-person dropouts are reduced by the stronger detector; useful current-frame throughput must be retained and the same controlled continuity and multiple-person checks must be passed before any participant use.

An experimental non-biometric anonymous track-stitching stage is provided for controlled non-research validation only. It can be enabled with `--experimental-track-stitching`. Each box is then labelled in the preview as `R<local_track_id> / S<stitched_track_id>`; uncertainty caused by simultaneous or competing geometry is indicated by `S?`. Raw `local_track_id` records are always preserved. Only a uniquely matching recent trajectory, predicted bounding-box overlap, centre distance and size are considered by the stage; no appearance features, face recognition or biometric identity are used.

This flag is rejected by the lifecycle runner for pilot and participant sessions until a fresh S1-S4 controlled trial has been passed. Experimental stitched IDs and uncertain intervals must not be used for annotation, modelling or formal collection unless a separately versioned acceptance decision is documented.

The accepted Phase 5.4 live profile is `config/bytetrack.zone_a.persistence.yaml`, with a 768-pixel detector input, 384-pixel pose crops and conservative same-frame duplicate suppression. During the final 120-second run, 3,620 frames were captured with zero read failures, 837 frames were processed at 6.969 effective FPS, and pose data was produced for 96.607% of track records. Close-overlap ID swaps and occasional short-lived duplicate IDs are retained as documented limitations in `docs/testing/results/2026-07-31_camera_a_phase_5_4.md`.

A completed and verified `config/masks.batamfast.yaml` is required by the live command. For non-research test video only, `config/masks.development.yaml` may be supplied instead. Output is validated against `schemas/camera_track.schema.json` before each JSONL record is written. The initial model files may be downloaded by Ultralytics on first use, so they must be prepared before the site's public network is relied upon; model downloads must not be assumed to be available or appropriate during collection.

### Reproduce historical 2 August Phase 2 telemetry evidence
The historical 2 August Attempt 4 report can be reproduced from the retained mixed diagnostic stream with the following command. It is not designated as the current Phase 2 decision, and the frozen evidence file must not be overwritten. The current Phase 2.4 result from the 6 August rerun is recorded in `docs/testing/results/2026-08-06_zone_a_phase_8_3_endurance_rerun.md`: a pass was recorded for ESP-A1, while the target was missed by ESP-A2 by two packets. Phase 2 is therefore retained as complete with partial acceptance.
```bash
PYTHONPATH=src python3 scripts/generate_integration_report.py \
  --input data/raw/esp_packets.jsonl \
  --intervals docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv \
  --intervals docs/testing/2026-08-02_phase_2_4_event_intervals.csv \
  --start 2026-08-02T14:13:15+08:00 \
  --end 2026-08-02T15:43:15+08:00 \
  --output /tmp/aria_2026-08-02_phase_2_attempt_4_reproduction.md
```
The supplied templates must be copied before the run, and every timestamp must be entered from the manually recorded log:
- `docs/calibration/results/2026-07-30_phase_2_3_trial_intervals_template.csv`
- `docs/testing/phase_2_4_event_intervals_template.csv`

Only `ESP-A1` and `ESP-A2` are accepted by the analyzer. Delivery is calculated independently within each boot ID, the documented PIR and ultrasonic targets are applied, numerical audio features are summarised, and packet recovery is verified around a labelled restart or power-cycle for each board. Those recovery tests must be run one board at a time on the site's public network; the public access point must not be interrupted or replaced. A recovery is passed when a new boot ID is reported by the recovered board and packets are continuously transmitted by the other board. No raw audio or video is read or written by the analyzer.

The historical output remains **INCOMPLETE** unless the 90-minute window, all calibration trials, and one restart or power-cycle recovery trial for each active board have sufficient evidence. Participant collection is closed. Training, evaluation and ablation entry points are provided in `scripts/train_phase_11_1_baselines.py`, `scripts/train_phase_11_2_multimodal.py`, `scripts/evaluate_phase_11_3.py` and `scripts/generate_phase_11_3_ablation.py`. Local inference, dashboard and final-acceptance entry points are provided in `scripts/run_local_inference.py`, `scripts/run_local_dashboard.py`, `scripts/run_phase_13.py` and `scripts/accept_phase_13.py`.

---
## Calibration
Calibration is required before formal data collection. The final ESP-A1, ESP-A2 and DJI Camera A physical placements are documented, and Phase 2.3 site sensor calibration has been passed. The site-specific Zone A privacy mask has been established and verified at BatamFast, including deliberate-movement recovery and live-site acceptance.

The following areas are covered by the calibration procedure:
- PIR warm-up and detection range
- PIR hold time and false-trigger behaviour
- ESP-A1 ultrasonic stability and valid operating range
- Separate ESP-A1 and ESP-A2 microphone baselines
- Microphone response to normal workplace sound
- Audio threshold selection
- Per-node clock and packet timing
- Single DJI Camera A framing
- Zone A retained-region mask coverage
- Exclusion-boundary verification
- Sensor-to-camera timestamp alignment

Calibration instructions are stored in [`docs/calibration/protocol.md`](docs/calibration/protocol.md).

For Phase 4.2, the local Camera A relay must be started and the draft-safe, masked-only calibration preview can be opened with:
```bash
PYTHONPATH=src python3 scripts/preview_privacy_mask.py \
  --source rtsp://127.0.0.1:8554/live/camera_a \
  --mask-config config/masks.batamfast.yaml
```
Only the local `camera_a` path is accepted by the preview; no unmasked frames are displayed, no detection is run and no frames are written. The preview can be closed with `q`. At the operating site, it must be used under the existing consent and exclusion procedure: assistance with boundary calibration may be provided by consenting Counter Agents, while customers, non-participants and sensitive material must be kept outside the view.

For interactive polygon editing, `--interactive` can be added:
```bash
PYTHONPATH=src python3 scripts/preview_privacy_mask.py \
  --source rtsp://127.0.0.1:8554/live/camera_a \
  --mask-config config/masks.batamfast.yaml \
  --interactive
```
A polygon can be selected with `1`-`9` or `[`/`]`; a vertex can be inserted by double-clicking a boundary and moved by dragging it. A separate polygon can be started with `n`, new vertices can be added with single clicks, and the polygon can be closed with Enter after at least three points. It can be cancelled with Escape. Changes can be undone with `u` and saved with `s`. `verified: false` is always restored when changes are saved. The preview can be closed with `q`.

Calibration results are stored under `docs/calibration/results/`. The completed Phase 1 placement evidence is recorded in [`docs/calibration/results/2026-07-30_zone_a_placement_record.md`](docs/calibration/results/2026-07-30_zone_a_placement_record.md).

The following should be recorded in calibration results:
- Date and location
- ESP-A1 and ESP-A2 firmware versions, boot IDs and positions
- Board-specific sensor settings
- Sample duration
- Separate baseline statistics
- Selected thresholds
- Camera A position and verified mask coordinates
- Detected faults
- Final accepted values

For Phase 2.3, `docs/calibration/results/2026-07-30_phase_2_3_trial_intervals_template.csv` must be copied to `docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv`, and
timezone-aware Singapore timestamps must be entered for every controlled interval. `accepted=true` must be set on each audio-activity interval only after usable baseline/activity separation has been demonstrated by the numerical summary. Names, speech content and participant identifiers must not be entered in the CSV.

---
## Testing strategy
Three levels of testing are used in ARIA. Camera configuration and capture mode, the CV pipeline, telemetry parsing and schema validation, node monitoring, privacy masking and UDP node-log routing are covered by the current unit-test suite.

### Component testing
Each sensor and camera is tested independently. Examples:
- PIR trigger and decay behaviour
- Ultrasonic valid and invalid echoes
- Microphone idle and active ranges
- Public-network reassociation after an ESP restart or power-cycle
- UDP packet delivery
- Camera availability
- ROI masking correctness

### Integration testing
Interactions between subsystems are verified by integration tests. Examples:
- Simultaneous ESP-A1 and ESP-A2 packet receipt
- Node identification and schema validation
- Out-of-order packet handling
- Dropped-packet detection
- Sensor and camera synchronisation
- Fused feature construction
- Session start and stop behaviour
- Firebase upload restrictions

### End-to-end testing
The complete system is tested from physical sensing through dashboard output. The following are included in evaluation:
- Per-class precision, recall, and F1
- Macro F1
- Confusion matrices
- Leave-one-session-out cross-validation
- Modality ablation
- Tracking continuity
- End-to-end latency
- Packet loss
- Dataset class balance
- Annotation agreement where applicable
- Privacy-procedure compliance

Testing documentation is stored in [`docs/testing/`](docs/testing/).

---
## Completed data collection
Formal participant collection was closed after the ninth retained session on 10 August 2026 and will not be resumed. Ordinary workplace duties were performed by consenting Counter Agents during the retained sessions at BatamFast, Singapore Cruise Centre (Harbourfront). Site permission was granted on 27 July 2026, and the completed collection was governed by Ethics Pack Version 4.4, acknowledgement, camera-placement, masking, preflight and checklist controls.

The historical collection process was:
1. Site permission and participant consent was verified
2. A pseudonymous participant identifier was assigned
3. Pre-session checklist was completed
4. Camera positioning and masking was verified
5. ESP-A1 and ESP-A2 was verified
6. Session manifest was started
7. Sensor, camera, and system logging was started
8. Elapsed timestamps rather than unnecessary identifying information was recorded
9. Staff activities was annotated using approved activity definitions
10. Any affected segment was excluded if masking or consent requirements were breached
11. The session was stopped and validated
12. Incidents or exclusions was documented
13. Annotation and quality checks was completed
14. Temporary masked video was securely deleted within the approved retention period

Collection documentation is stored in [`docs/data_collection/`](docs/data_collection/).

### Run Phase 7.2 fail-closed preflight
The MediaMTX bridge and DJI Camera A publisher must be started, ESP-A1 and ESP-A2 must be powered, and preflight must be run before the UDP receiver or any collection writer is started:
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
During preflight, the local `camera_a` RTSP stream is opened, 1920x1080 at approximately 30 FPS and the verified BatamFast mask are validated, and the stream is inspected with `ffprobe` for exactly one H264 video track and no audio. Disabled recording is confirmed, and fresh schema-valid ESP-A1 and ESP-A2 packets are awaited on UDP port `5005`. A timezone-aware SGT clock, approved writable local storage with at least 5 GiB free by default, and the local pause/stop interface are also checked.

Under the historical pilot or participant preflight procedure, `--participant-id P0000` was repeated for each pseudonymised participant and `--acknowledgement-confirmed` was added. Every participant ID is rejected in a non-research dry run. Failure is returned by the command if any check is failed, and a writer is never started. Application writers must be supplied through the programmatic gate and integrated with the Phase 7.3 lifecycle controls.

To run the same preflight and persist a validated planned manifest with a new SGT session ID, `--preflight-only` must be replaced with `--prepare-session`. The initial manifest is written under `data/raw/manifests/`; no writer is started by this CLI mode.

The returned prepared session and writer factories must be passed by application integrations to `aria.collection.run_session.start_prepared_session`. The manifest is atomically changed to `running` by the gate before any factory is called. All writers are prevented from starting by an invalid or missing manifest. If a later factory fails, already returned writer handles are closed where possible and the manifest is atomically marked `aborted`.

### Use Phase 7.3 session lifecycle controls
A shared `pause_stop_controller` is received by every writer factory in its `WriterContext`. Records must not be accepted by writers while that controller is paused or stopped. All lifecycle changes are managed by the returned `StartedSession`:
```python
started = start_prepared_session(prepared, writer_factories)

started.pause("mask_failure")
started.exclude_windows(["zone_a_100_200"])
started.resume(["mask_reverified"], deletion_completed=True)
completed_manifest = started.stop()
```
The shared pause signal is set immediately by `pause()`, a schema-valid non-identifying incident is written, and the manifest is atomically marked `paused`. A privacy-critical incident cannot be downgraded or resumed until required deletion is recorded. Affected window IDs are linked to the incident by `exclude_windows()` so that they are retained as unusable. A verified recovery action is required by `resume()`, after which the manifest is returned to `running`.

For a clean stop, each writer must be closed successfully and `session_summary()` must be provided with its output kind, relative local file path, observed, written and excluded record counts, gap count and longest gap. The required invariant is `observed = written + excluded`. Only then is the final manifest marked `completed`. It is marked `aborted` after a close or accounting failure. This accounting contract is defined by session-manifest schema version 6. The frozen collection-profile ID and SHA-256 hash are also recorded for formal sessions; earlier manifests are rejected rather than silently reinterpreted. Incident schema version 5 is used for incident-specific recovery actions and non-downgradable privacy/deletion rules; earlier versions are rejected. Excluded-window rows are atomically deleted from persisted writer files, later writes into those windows are rejected, and absence is verified before required deletion can be completed. Final summaries are obtained only from the writer handles, output files and counts are checked, and operation is blocked when duplicate output paths or incident IDs are detected. Phase 7.3 is complete.

### Run Phase 7.4 lifecycle-owned dry run
With MediaMTX and the Camera A publisher running, DJI recording disabled, and ESP-A1/ESP-A2 powered, the integrated non-research runner can be started with:
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
The listed CV options are the accepted Phase 5.4 live profile and match the lifecycle runner defaults.

The local prompt is provided with `status`, `pause TYPE`, `resume ACTION...`, `stop` and `abort` commands. Deletion confirmation is required for privacy recovery, for example `resume mask_reverified --deletion-completed`. The session is aborted safely after end-of-input or interruption. The accepted 1 August 2026 run and exact recovery sequence are documented in [`docs/testing/phase_7_4_live_dry_run.md`](docs/testing/phase_7_4_live_dry_run.md).

Under the historical approved pilot or participant procedure, the session kind was added, one `--participant-id P0000` option was repeated for each participating Counter Agent, and `--acknowledgement-confirmed` was added. Missing or malformed pseudonyms and missing acknowledgement confirmation are rejected by the fail-closed preflight. Historical example:
```bash
PYTHONPATH=src python3 -m aria.collection.live_session \
  --session-kind participant \
  --participant-id P0000 \
  --acknowledgement-confirmed \
  --annotator-id A001 \
  --masked-track-preview \
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
  --output-directory data/raw
```
The frozen Phase 9.3 v7 command is retained above. The active collection profile and `--masked-track-preview` are required for pilot and participant sessions; operation is blocked before preflight when settings or hashed artifacts have been changed. A `http://127.0.0.1:8765/` URL is printed by the runner after the manifest-owned writers are started. That localhost URL can be opened to view only the already-masked Camera A frame, with the same camera-local track IDs written to the session JSONL. Only the latest preview frame is kept in memory, no audio or recording path is provided, binding to a non-loopback interface is prohibited, and the preview is blanked when the lifecycle is paused or stopped. The separate `preview_privacy_mask.py` utility is retained as a pre-session alignment check, and session track IDs are not exposed by it.

Under the historical pilot and participant procedure, the lifecycle-owned activity annotation controls were also provided on that same localhost page. A persistent card is provided for each pseudonymised participant, with independent track, activity, validity and end controls. A currently visible camera-local track ID must be selected in the applicable card, followed by one of the four approved activities. Annotations are opened and closed automatically by the server on two-second multimodal-window boundaries; the browser clock is not used. That participant's preceding interval is closed by a new activity or track selection; it is closed without another being started by `End annotation`. For explicit uncertain and excluded controls, one of the
schema-approved reasons must be supplied. Intervals shorter than one complete two-second window are not written.

Track presence is checked by the writer over completed two-second windows. Individual missed frames are tolerated, but if the selected track is absent throughout a complete window, the annotation is automatically closed before that missing window. A replacement-track prompt is then shown in the applicable participant card. The new visible track must be selected manually, after which the current activity must be chosen or the previous activity explicitly continued; an association between a replacement ID and the same person is not inferred by ARIA.

Validated records are appended locally to `sessions/<session_id>/annotations.jsonl`; no image, audio, name or identity mapping is added. Active annotations are closed on pause and stop, annotations are disabled while paused, incident-linked excluded windows are deleted from the annotation output, and annotation
file/count accounting is included in the completed manifest. The pseudonym `A001` is used by default for `--annotator-id`, and only `A000`-style values are accepted.

---
## Data formats
A canonical machine-readable schema is currently defined for ESP8266 telemetry in ARIA:
| Schema | Status | Purpose |
|---|---|---|
| `esp_packet.schema.json` | Implemented | ESP-A1 and ESP-A2 transmitted telemetry payloads |
| `esp_record.schema.json` | Implemented | Stored SGT receive envelope and validated ESP payload |
| `feature_vector.schema.json` | Implemented | Fused model input |
| `session_manifest.schema.json` | Implemented | Versioned Zone A session lifecycle, configuration and preflight metadata |
| `annotation.schema.json` | Implemented | Role-neutral ground-truth activity annotations with explicit uncertainty and exclusions |
| `prediction.schema.json` | Implemented | Model outputs with explicit availability and unavailable states |
| `incident.schema.json` | Implemented | Non-identifying privacy, masking and collection incidents |

All schema changes must be versioned.

---
## Logging
Logs are separated by purpose in ARIA.
| Log | Content |
|---|---|
| Sensor log | Validated telemetry from ESP-A1 and ESP-A2 |
| Camera log | Camera start, stop, frame, and health events |
| Prediction log | Activity labels and confidence values |
| Session log | Session lifecycle and configuration |
| Incident log | Masking failures, exclusions, and technical incidents |
| Audit log | Retention, deletion, upload, and administrative actions |
| Development log | Implementation progress, decisions, and unresolved issues |

Participant-identifiable content must not appear in application logs.

---
## Evaluation plan
The planned system comparison comprised:
- Vision only
- Vision and audio
- Vision and IoT
- Full multimodal fusion
- 
The primary classifier candidates are:
- Random Forest
- 1D-CNN

The primary evaluation measures are:
- Per-class F1
- Macro F1
- Confusion matrix
- Leave-one-session-out generalisation
- Tracking stability
- Latency
- Modality contribution
- Dataset quality

The target is for improved reliability over the vision-only baseline to be demonstrated through multimodal fusion while feasibility on the local edge host is retained.

---

## Security and repository hygiene
The following must not be committed:
- `.env`
- Wi-Fi credentials
- Firebase private keys
- Service-account files
- Participant names
- Consent forms
- Raw or temporary video
- Raw audio
- Excluded privacy-incident footage
- Unredacted session records
- Signed participant packs or withdrawal forms
-  participant-code key
- Original site-permission correspondence
- Completed identifiable session or exclusion logs
- Local IP configurations that expose private credentials
- Model artefacts containing sensitive data

Recommended `.gitignore` entries include:
```gitignore
.env
*.key
*.pem
firebase*.json
service-account*.json

data/raw/*
data/interim/*
data/excluded/*
outputs/logs/*
docs/privacy/incidents/private/*

!data/raw/.gitkeep
!data/interim/.gitkeep
!data/excluded/.gitkeep

models/**/*.pkl
models/**/*.joblib
models/**/*.pt
models/**/*.onnx

__pycache__/
*.py[cod]
.pytest_cache/
.venv/
```
Only anonymised, approved, and reproducible artefacts should be added to version control.

---
## Project documentation
The following documentation areas are represented or identified as planned scope in the repository:
- Participant ethics and active document version
- System architecture
- Hardware wiring
- Hardware placement
- Calibration
- Privacy and masking
- Session operation
- Activity definitions
- Annotation
- Exclusions
- Testing
- Evaluation
- Final reporting

Standalone progress and architectural-decision documents are not included in this submission. Dated implementation and acceptance records are retained under `docs/testing/results/`.

---

### Collection completion
- Phase 8 live-site acceptance and Parts 8.1-8.4 are complete; GO was recorded by the Student Researcher on 2 August 2026
- Phases 9.1-9.3 completed and formal collection closed after the revised eight-hour target was reached in the ninth retained session
- Latest ESP-A2 packet-delivery shortfall and observed network limitations accepted as explicit operational constraints; measured delivery must be retained in later reporting without the 98% target being lowered or the network being presented as a proven sole cause
- Phase 2.4 endurance execution and both supplemental per-board recovery tests completed; measured failures are included as accepted reliability risks in the Phase 8.4 GO decision

### Collection closure
- Any new pilot or participant session must not be started
- Historical preflight, session, incident, exclusion and deletion controls must be retained as audit evidence
- Only non-research or synthetic inputs must be used for later hardware, inference, dashboard and demonstration work
- Retained manifests and their recorded profile hashes must be preserved without reinterpreting later profile files as originals

### Planned after collection
- Participant-level modelling features built and audited from approved Phase 10.1 annotations — complete
- External test and grouped development validation folds frozen — complete
- Random Forest baselines — complete
- 1D-CNN comparison
- Firebase feature synchronisation
- Dashboard integration
- LOSO evaluation
- Modality ablation study
- Dataset documentation
- Final report
- Presentation video

## Author
**Ryan Aw**  
CM3070 Final Project  
University of London

---
