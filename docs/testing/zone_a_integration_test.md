# Zone A Two-Board and DJI Integration Test
## Active configuration
| Component | Identity | Interface |
|---|---|---|
| ESP8266 board 1 | `ESP-A1` | `A_PIR_US_MIC`; local UDP 4210 |
| ESP8266 board 2 | `ESP-A2` | `A_PIR_MIC`; local UDP 4211 |
| Laptop receiver | ARIA receiver | UDP 5005; accepts only ESP-A1 and ESP-A2 |
| DJI Osmo Action 5 Pro | `camera_a` | 1920x1080 at 30 FPS; RTMP to MediaMTX; local RTSP read |
Zone B, Zone T, ESP-B, ESP-T and a second camera are outside this test.

## Software mock result - 29 July 2026
The revised receiver was started on isolated test port 55005 because an older receiver process was already using the live port 5005. Sequences 0 through 10 were sent from both nodes by the two-node simulator.
| Check | Result |
|---|---|
| ESP-A1 valid packets | 11 |
| ESP-A2 valid packets | 11 |
| Separate node logs | Pass |
| Sequence gaps | 0 |
| Receiver crashes | 0 |
| Unit tests at original mock | 43 passed |

The process already listening on port 5005 had loaded the earlier three-node parser and rejected the new identities. Restart the live receiver before the physical test so it loads the revised allowlist.
The original transport mock predates the final asymmetric sensor split. The then-current 47-test unit suite separately verified that ESP-A1 requires distance fields and ESP-A2 rejects them. A new physical run was still required at that point and was subsequently completed. Attempt 3 remains historical; the 2 August Attempt 4 result also remains historical. The current Phase 2.4 endurance result is the 6 August rerun recorded later in this document and in `docs/testing/results/2026-08-06_zone_a_phase_8_3_endurance_rerun.md`.

## DJI bridge diagnostic - 29 July 2026
MediaMTX 1.19.3 loaded `config/mediamtx.local.yaml` successfully and opened RTMP port 1935 plus local RTSP port 8554. The ARIA diagnostic reached the RTSP bridge, but MediaMTX reported that no stream was available on `live/camera_a`. The physical DJI had not published to the bridge, so live resolution, FPS and dropped-frame checks were pending at the time of this 29 July diagnostic.
Those camera checks were subsequently completed. The 30 July short diagnostic confirmed 1920x1080 at approximately 30 FPS, and the 31 July Phase 3.4 endurance record reports 5,400 seconds at 29.969 measured FPS with 161,836 successful reads and no read failures. The controlled publisher interruption also recovered the local video-only path. See `docs/testing/results/2026-07-31_camera_a_phase_3_4.md` and its linked JSON evidence.

## Physical test procedure
1. The Mac's current network address must be confirmed, and the local Wi-Fi configuration and laptop IP must be entered in both sketches without credentials being saved in a shared repository copy. The site's public network must be used by the laptop, ESP-A1, ESP-A2 and DJI; a phone hotspot or private access point must not be introduced.
2. One ESP8266 must be connected at a time, `arduino-cli board list` must be run, and the matching sketch must be uploaded
3. `ESP-A1`/`aria-esp-a1`/4210 and `ESP-A2`/`aria-esp-a2`/4211 must be verified in their serial output. It must be confirmed that `A_PIR_US_MIC` is reported by ESP-A1 and `A_PIR_MIC` by ESP-A2.
4. The old receiver must be stopped, and the revised receiver must be started:
   ```bash
   PYTHONPATH=src python3 -m aria.ingestion.udp_receiver
   ```
   The expected startup line is:
   ```text
   UDP receiver started on 0.0.0.0:5005; accepting ESP-A1 and ESP-A2 only
   ```
   The two logs must be monitored separately:
   ```bash
   tail -f outputs/logs/esp_a1.log
   ```
   ```bash
   tail -f outputs/logs/esp_a2.log
   ```

5. The local camera bridge must be started:
   ```bash
   mediamtx config/mediamtx.local.yaml
   ```
6. Configure the DJI to publish to:
   ```text
   rtmp://LAPTOP_IP:1935/ingest/camera_a
   ```
7. It must be confirmed that the ingest is reported by MediaMTX with H264 and MPEG-4 Audio, followed by the ARIA-facing `live/camera_a` path with exactly one H264 track.
8. The stream must be confirmed:
   ```bash
   PYTHONPATH=src python3 scripts/test_cameras.py \
     --camera camera_a --duration 60
   ```
9. All three components must be run together for at least 90 minutes. The boards must be kept in their planned Zone A positions, and the verified Zone A privacy mask must be applied
   before any participant data is present.
10. Before the formal window, `docs/testing/phase_2_4_event_intervals_template.csv` must be copied to a dated result file. Exact SGT start/end timestamps must be recorded for one controlled recovery test per board.
11. ESP-A2 and Camera A must be kept running, and ESP-A1 must then be restarted or powered off and back on. Reassociation with the public network, a changed `boot_id`, resumed telemetry and continued delivery by ESP-A2 must be confirmed.
12. ESP-A1 and Camera A must be kept running, and the same restart or power-cycle test must be repeated for ESP-A2. The site's public access point must not be interrupted, replaced or reconfigured during either trial.
13. The evidence report must be generated:
    ```bash
    PYTHONPATH=src python3 scripts/generate_integration_report.py \
      --input data/raw/esp_packets.jsonl \
      --intervals docs/calibration/results/2026-07-30_phase_2_3_trial_intervals.csv \
      --intervals docs/testing/2026-08-02_phase_2_4_event_intervals.csv \
      --start 2026-08-02T14:13:15+08:00 \
      --end 2026-08-02T15:43:15+08:00 \
      --output docs/testing/results/2026-08-02_zone_a_phase_2_4_run_4_evidence.md
    ```
14. The report must be reviewed against the receiver and serial logs. Every **INCOMPLETE** or failed target must be retained as evidence, and its measured result must be included in the final disposition; it must not be rewritten as a pass.

## Acceptance criteria
- Both boards remain present for the full interval
- ESP-A1 supplies `distance_cm` and `distance_valid`
- ESP-A2 sends no `distance_cm` or `distance_valid` fields
- Each board is measured against the unchanged 98% target. ESP-A2's accepted public-network shortfall remains an explicit limitation and is not rewritten as a passing measurement
- No malformed packets or receiver crashes occur
- A restart is recognised by a changed `boot_id`
- One controlled restart or power-cycle recovery passes for each active board, with the other board continuing to send packets.
- Failure or restart of one board does not stop the other board or camera
- DJI capture remains at 1920x1080 and approximately 30 FPS
- Dropped DJI frames and the longest frame gap are recorded
- No sustained stream-performance degradation is observed
- Only the approved masked Zone A staff-side region is included in the retained camera view
- No raw audio, raw video or masked video is uploaded to cloud services

## Evidence paths
- `data/raw/esp_packets.jsonl`
- `outputs/logs/udp_receiver.log`
- `outputs/logs/esp_a1.log`
- `outputs/logs/esp_a2.log`
- Completed camera diagnostic output
- Completed privacy-failure and live-site acceptance records
- Completed calibration and recovery interval CSV files
- Generated Zone A Phase 2 telemetry evidence report

## Results to record after the physical run
| Metric | ESP-A1 | ESP-A2 | DJI Camera A |
|---|---:|---:|---:|
| Duration | 90 minutes | 90 minutes | Separate Phase 3.4 evidence |
| Expected packets/frames | 5,400 | 5,400 | 161,838 nominal at 29.97 FPS |
| Received packets/successful frames | 5,302 | 5,290 | 161,684 successful reads |
| Delivery/drop percentage | 98.185% delivery | 97.963% delivery | 29.941 measured FPS; diagnostic drop estimate recorded |
| Longest gap | 3.098 s | 4.011 s | 6.650 s |
| Restarts/disconnections | None during endurance; 2 August recovery passed | None during endurance; 2 August recovery passed before the microcontroller replacement | No read failure or disconnect |
| Mean RSSI or FPS | -60.963 dBm | -59.603 dBm | 29.941 FPS |

Current Phase 2.4 result: **COMPLETE WITH PARTIAL ACCEPTANCE**. Only the ESP microcontroller node on the ESP-A2 sensor board was replaced on 5 August 2026 after consistently poor performance in the earlier formal runs. Both boards then remained active for the full 6 August 90-minute rerun. ESP-A1 passed at 98.185%; ESP-A2 improved from 91.056% in Attempt 4 to 97.963%, but remained two packets short of the unchanged 98% target. The 2 August Attempt 4 result is retained as historical comparison evidence. Its ESP-A2 recovery trial predates the replacement and remains supplemental evidence with that limitation. See `docs/testing/results/2026-08-06_zone_a_phase_8_3_endurance_rerun.md` and `docs/testing/results/2026-08-02_zone_a_phase_2_4_run_4.md`.