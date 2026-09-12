# Original ARIA Runtime: Installation and Operation
The original ARIA source code and trained Camera-only model are included in this export.
The separate toy model and dashboard have been removed.
Invented input records are retained within the original hardware-free diagnostic for verification of the frozen model; they are not used as the live data source.

## Installation
Python 3.12 must be used, and all commands must be executed from the repository root. Any previously running demo server must first be stopped with Ctrl+C.
```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```
The full dependency set must be installed, as the previous demo-only environment is insufficient. The original `requirements.txt` has been copied without modification. The integrated deployment configuration has been prepared for macOS Apple Silicon, with FFmpeg expected at `/opt/homebrew/bin/ffmpeg`. MediaMTX and FFmpeg must be installed separately; neither is installed by pip. Other operating systems and a fresh installation of the full dependency set have not been verified as part of this export update.

## Hardware-Free Model Verification
The original diagnostic may be executed with the following command:
```sh
PYTHONPATH=src python scripts/run_phase_13.py --input-scope synthetic
```
The frozen model, missing-input handling, privacy pause, recovery and simulated cloud delivery are exercised by this diagnostic. No hardware or Firebase connection is established. Aggregate diagnostic evidence is written under `outputs/acceptance/phase_13`, which is excluded from Git. The live dashboard is not launched by this command.

## Hardware Preparation
Only ESP-A1, ESP-A2 and DJI Camera A are to be used. Wiring must be completed in accordance with `firmware/esp_a/ESP_A_README.md`. Before flashing, `WIFI_SSID`, `WIFI_PASSWORD` and `LAPTOP_IP` must be configured for the intended network in both active sketches. Credential placeholders have been retained in the export. The `A_PIR_US_MIC` configuration and local UDP port 4210 are used by ESP-A1; `A_PIR_MIC` and port 4211 are used by ESP-A2. Telemetry from both nodes is sent to laptop UDP port 5005.

MediaMTX must be started with `config/mediamtx.local.yaml`, and the DJI stream must be published to `rtmp://<laptop-ip>:1935/ingest/camera_a`. Audio is removed by the relay, and the video stream is made available locally at `rtsp://127.0.0.1:8554/live/camera_a`. A capture mode of 1920x1080 at 30 FPS must be used, and DJI recording must be disabled. Other camera previews and UDP receivers must be stopped before the integrated runner is started.

The original camera, mask, relay and tracking configurations have been preserved and are verified against their recorded hashes. The stored mask was defined for the original camera placement. Before operation at a different location or with different camera geometry, an appropriate mask must be reviewed and the configuration and associated validation checks must be explicitly updated. Physical alignment cannot be established from a matching file hash alone. These checks are retained, and automatic configuration for arbitrary hardware is not provided.

## Live Dashboard Operation
The original non-research display mode may be started from an interactive terminal only after operational approval, physical mask alignment and disabled recording have been confirmed:
```sh
PYTHONPATH=src python scripts/run_phase_13.py \
  --input-scope non_research --live-display-only \
  --approved-staff-present --mask-alignment-confirmed --dji-recording-disabled
```
All preflight checks must be passed before the dashboard is made available at http://127.0.0.1:8050/. The confirmation flags must be supplied only when the corresponding conditions have been verified by the operator. The original operating procedure and pause/recovery controls are documented in `docs/testing/phase_13_final_acceptance.md`. The `status`, `pause`, `resume-verified` and `stop` commands may be entered in the terminal. The dashboard must be closed after the runtime has been stopped.

Masked camera features and live sensor-health information are processed in memory alongside the frozen activity model and original dashboard. No staff records are saved, and no Firebase client is started. Camera-only was selected as the original activity model. Sensor availability is reflected in telemetry and health status, while activity predictions are derived from camera features. A working camera is therefore required; activity predictions cannot be produced from the sensors alone. The documented model-accuracy limitations remain applicable.

Participant collection has been closed. The collection tools have been retained solely as historical audit material. New participant sessions are not authorised by this package.

## Included Assets and Verification
The following required original assets have been included without modification:
- `models/phase_11_1/camera_only.joblib` — trained activity model
- `yolov8n.pt` — person detector
- `yolov8n-pose.pt` — pose estimator

Other research models, participant data, credentials and historical generated evaluation evidence remain excluded. The `.venv` directory, caches and runtime outputs must be excluded from uploads. Existing ZIP archives were created before this restoration; subsequent packages must be prepared from the updated folder.

Verification was completed on 12 September 2026. All 141 selected original runtime tests, 12 original hardware-free end-to-end checks and 7 runtime asset checks were passed. Every Python file under `src`, `scripts` and `tests` was verified as byte-for-byte identical to its respective original. The existing macOS Python 3.12 research environment was used for testing. Live hardware, Firebase, a fresh full installation and Windows/Linux were not tested. Excluded research records and evidence are still required by the full historical data and evaluation suite.