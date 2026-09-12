# Phase 13 Final End-to-End Acceptance
## Current disposition
**PARTIAL WITH ACCEPTED LIMITATION — Parts 13.1, 13.2 and 13.3 complete; sustained public-network degradation remains recorded.**
Participant collection closed on 10 August 2026. Phase 13 must use only a declared `non_research` or `synthetic` scope and must not start a pilot or participant session. Historical Phase 7/8/9 acceptance remains supporting evidence, but it does not replace a final-build run after Phases 12.1–12.3.
The final 1 September 2026 stability run completed 5,400.008 uninterrupted seconds with clean shutdown and all six metrics. Part 13.2 is complete only through the explicit `phase2.4-public-network-delivery` limitation; the measured sustained degradation and A1/A2 delivery values remain visible. Part 13.3 freezes a deterministic source-tree revision and archive, verifies every required artifact hash, passes secret and identity/media scans, and runs the synthetic Phase 13 demonstration from a fresh extraction. Because the accepted network limitation remains, the overall Phase 13 disposition is PARTIAL rather than an unconditional pass.

## Frozen scope
- Zone A only; ESP-A1, ESP-A2 and one wireless DJI `camera_a` stream
- 1920×1080 at 30 FPS with verified `batamfast-v2` masking before vision processing
- Frozen local Camera-only model, localhost dashboard and isolated Firebase summary uploader
- No participant/session identifiers, raw features, audio or video in Phase 13 evidence

## Diagnostic runner (31 August 2026)
The runner is maintained separately from the historical collection commands. Existing completed-window inference, the localhost dashboard and the Firebase projector/outbox are connected without collection writers being started. A new pilot or participant session is not authorised.
The synthetic checks must first be run from the repository root:
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py --input-scope synthetic
```
Synthetic numerical records are used with the frozen model in these checks. Multiple tracks, each missing ESP node, camera loss, privacy pause, fresh resume, simulated cloud failure/recovery and clean-stop accounting are exercised. No hardware or Firebase connection is opened. The absolute interpreter path is provided for the current Mac; the documented project dependencies are required for another installation.

### Equipment-only check with approved staff present
For non-research equipment commissioning, approved Counter Agents are permitted to remain in the retained staff region. Participant collection is not restarted. This separate mode must be used when no recording or staff activity evaluation is intended:
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py \
  --input-scope non_research --equipment-only \
  --approved-staff-present --mask-alignment-confirmed --dji-recording-disabled
```
The separate UDP receiver and camera preview must be stopped first; MediaMTX, the DJI stream and both ESPs must be kept running. Physical alignment of the approved mask and disabled DJI recording must be confirmed. No empty-counter confirmation is needed in this mode.
The capture mode is validated and the approved mask is applied by the camera child. Both raw and masked frames are discarded, and only health/timing metadata is sent. A detector, pose estimator, tracker or activity model is never constructed. ESP readings are parsed in memory to update packet health; numerical sensor values are not displayed or written. No cloud client, outbox, video display, activity dashboard, run manifest or event journal is started. Only terminal health summaries are printed; terminal output must not be redirected or recorded when no diagnostic files are to be retained.
Camera freshness/FPS and both ESPs' freshness/packet counts can be viewed with `status`. Camera and UDP access can be stopped with `pause`, and the mode can be closed with `stop`/Ctrl+C. Before `resume-verified`, the presence of only approved staff in the retained region, mask alignment and disabled DJI recording must be explicitly rechecked; preflight is repeated. Operation must be paused before the retained region is entered by a non-approved person or if the camera is moved. No person detector is provided in equipment-only mode; these checks must therefore be performed by the person conducting the test. The check is paused after camera/configuration failures.
Only a hardware-health check supporting 13.1 is provided. Activity inference, multi-person tracking, Firebase delivery and full Phase 13.1 acceptance are not demonstrated. No permanent acceptance record is created, and the phase cannot be marked complete by this mode.

### Live display only with approved staff present
This non-research display mode must be used only after explicit operational approval has been recorded for temporary activity labels. Participant collection is not reopened, accuracy is not scored and staff performance is not evaluated.
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py \
  --input-scope non_research --live-display-only \
  --approved-staff-present --mask-alignment-confirmed --dji-recording-disabled
```
MediaMTX, the DJI stream and both ESPs must be kept running. Other UDP receivers and camera previews must be stopped first. Preflight is repeated in this mode, after which masked detection/pose, per-track two-second windows, the unchanged frozen model and the localhost dashboard are run together. Temporary local track labels and model estimates can be viewed at `http://127.0.0.1:8050/`; staff names and accuracy scores are not shown. Video is not displayed.
Camera/sensor records and predictions are kept in bounded process memory. No recording writer, evidence journal, manifest, Firebase client or outbox is created, including temporary projected summaries. Uploads cannot be enabled through cloud commands. `Cache-Control: no-store` is requested in HTTP responses; pages must not be saved, screenshots of staff-derived labels must not be taken, and terminal output must not be redirected. The dashboard tab must be closed after stopping, since its last rendered page may still be displayed by a disconnected browser. Protection against OS swap or independent screen-recording software cannot be guaranteed by application controls.
The terminal commands provided are `status` (aggregate health/counts only), `pause`, `privacy-failure`, `resume-verified`, `stop` and `abort`. Server-side predictions and buffers are cleared during a privacy pause, camera/UDP reception is closed, and fresh preflight is required on resume. Operation must be paused before the retained region is entered by a non-approved person or if the camera is moved; consent and identity are not recognised by the system. Approved staff only, visual mask alignment and disabled DJI recording are explicitly reconfirmed by `resume-verified`. The empty-region automatic pause is not triggered by approved staff tracks in this mode; that safeguard is retained in the old empty-region mode.
Local runtime integration can be demonstrated without staff-derived data being saved. Traceable acceptance files are not produced, cloud retention is not authorised, synthetic accuracy-independent checks are not replaced, and 13.1 is not marked complete by this mode alone. Unrelated model, firmware, mask and collection settings must be kept unchanged.

### Opt-in aggregate report for the clean-start check
Operational authorisation was subsequently recorded for the retention of test outcomes, counts and shutdown status only. Activity labels, track IDs, sensor readings, images and audio were excluded. Nothing is saved by the default live-display mode. `--save-aggregate-report` must be added only for this explicitly approved narrow report:
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py \
  --input-scope non_research --live-display-only \
  --approved-staff-present --mask-alignment-confirmed --dji-recording-disabled \
  --save-aggregate-report --clean-boot-confirmed
```
`--clean-boot-confirmed` must be used only after the agreed clean boot has been performed and the pipeline services and active devices have been restarted. Restarting the Python process after dependency installation is not accepted as clean-boot confirmation. Clean boot is recorded in the report as a manual attestation; it is not detected independently by the software. Preflight is independently rerun. The laptop's current network address must be checked after a reboot before the ESP/DJI destinations are assumed to be correct; no automatic firmware or network changes are made.
A short startup/accounting/teardown check is provided, rather than the 90-minute Phase 13.2 stability run or a repeat of every disconnect scenario. Once current cards and fresh inputs are shown in the local dashboard, `status` must be entered, followed by `stop`. The dashboard tab must be closed. The aggregate report location and whether shutdown was verified cleanly are printed by the runner. Any reported failure must be kept visible rather than marked accepted.
The only new saved artifact is `outputs/acceptance/phase_13/aggregate_*/summary.json`, created after preflight has been passed and initially marked `incomplete`. An interrupted/terminated process must not be treated as passing if finalisation is not completed. That file is atomically replaced during successful finalisation. No event log, arbitrary-metrics API or copied runtime snapshot is provided. Only the following are written by the fixed-field projection:
- Preflight booleans, the manual clean-boot attestation and fixed test outcomes
- Aggregate input, processed, discarded, completed-window and prediction counts, without IDs or activity values
- Camera-producer/IPC disposition counts and parent handoff reconciliation
- Shutdown booleans, forced/failed camera-worker counts and the resulting process exit code
- Fixed schema/status labels and false staff-recording/cloud/phase-completion flags
Code/asset hashes are checked in memory and represented only by an unchanged-result boolean. No credential, address, frame/packet timestamp, activity value, source record or arbitrary exception string is copied into the report. Camera IPC accounting is started at numerical records accepted by the in-memory sink, rather than raw camera frames. Unconsumed/staged numerical records are counted as shutdown discards without their payloads being replayed or persisted. Records received by the window runtime are covered by UDP accounting; proof of network delivery is not provided. These distinctions must be kept explicit.
Normal camera exit, closed UDP/dashboard, balanced parent/IPC counts and zero remaining buffered records can be verified through the report. Clean shutdown cannot be verified if forced stops, worker failures, source drift, missing counts, failed cleanup or report-write failures are reported. A completed diagnostic report is not accepted as automatic 13.1 sign-off: its individual checks and the prior functional evidence must still be assessed. Staff recording, cloud uploads and outboxes are kept disabled.

### Empty-region integrated diagnostic mode
For a supervised, non-research hardware check, all people, including Counter Agents, must be excluded from the retained camera region. The standalone UDP receiver and camera preview must be stopped first, while MediaMTX, the DJI stream and both ESP nodes are kept running. The approved mask's physical alignment and disabled DJI recording must be rechecked before these confirmations are entered:
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py \
  --input-scope non_research \
  --confirm-empty-retained-region \
  --mask-alignment-confirmed \
  --dji-recording-disabled
```
Fresh hardware preflight must be passed before producers are started or a run directory is created by the runner. Only the masked DJI `camera_a` relay is used as the camera source; laptop UDP port 5005 is used by ESP-A1/A2. The dashboard is provided at `http://127.0.0.1:8050/`, with no video included. The interactive terminal must be kept open.

| Terminal command | Effect |
| --- | --- |
| `status` | print and journal aggregate runtime, camera and node health |
| `pause` or `privacy-failure` | block inference, clear displayed predictions and buffered records, stop camera/UDP producers and purge the temporary outbox |
| `resume-verified` | explicitly reconfirm an empty retained region, visual mask alignment and disabled DJI recording; rerun preflight and start fresh producers/windows |
| `cloud-offline` / `cloud-online` | fail/restore the local simulated transport; never contact Firebase |
| `stop` or Ctrl+C | close producers and dashboard, purge temporary summaries and write final aggregate evidence |
| `abort` | perform cleanup and mark the run aborted |

The runner is paused if a person is reported in its camera metadata. This is provided as a secondary safeguard, not reliable person exclusion: the scene must be supervised, and operation must be paused before anyone enters. Staff must not be deliberately introduced to demonstrate activities. Live multi-person activity recognition is therefore not demonstrated in hardware mode; the synthetic checks must be used for that integration boundary.
The runner is also paused after camera configuration changes or camera-process failure/timeouts. Recovery is not performed automatically. After physical camera movement, operation must be paused immediately and must not be resumed until alignment has been visually reverified; physical movement cannot be detected by file-hash checks. A stuck camera child is terminated after bounded shutdown waits; forced termination is reported and a clean-run disposition is prevented.

### Retention and limits
Raw sensor/camera records and local predictions are kept in memory. The real Firebase projector, outbox and retry implementation are used, but their remote client is replaced by a local-only substitute with no network implementation or credentials. Up to 512 projected summaries may be stored temporarily on disk; they are deleted during privacy pause and normal shutdown. Live Firebase delivery and restart durability are not tested. Temporary files may be left after abrupt OS/process termination; cleanup after a crash is not guaranteed by normal cleanup.
Two-second windows are used with one second of late-arrival grace. A partial window is discarded at startup/resume. Inputs are bounded to 1,024 buffered records, eight queued camera batches and 128 records per frame. Late, partial and overflow drops are counted. Inference is paused after a backward clock or processing backlog exceeding eight seconds; camera startup/no-message timeouts are set to 45/five seconds. Runs are stopped after at most 5,400 seconds, including time spent paused.
Only `manifest.json` and fixed-code `events.jsonl` are written beneath `outputs/acceptance/phase_13/run_*` during each run. Aggregate counts, health, source/asset hashes, an event-file checksum and the final disposition are included; raw inputs, identities and activities are excluded. Inputs received by the parent window runtime are covered by record accounting; IPC overflow is reported separately, and queued records discarded on camera shutdown are not presented as an end-to-end capture reconciliation. Capture FPS is calculated as frame-attempt index change over capture timestamps; processing FPS is calculated as the reciprocal processed-frame timestamp interval. Local completed-window processing over the last 4,096 samples is measured by prediction p95; capture-to-display latency is not measured.
A completed diagnostic manifest is not accepted as a completed Phase 13 assessment. `phase_13_1_complete: false` is always recorded by the runner. Sustained 90-minute healthy operation, storage growth, live Firebase acceptance, a clean installation and a release revision are not proven by its diagnostics. Manual evidence review is still required; synthetic results must never be copied into live-evidence claims.

## Evidence workflow
```bash
PYTHONPATH=src python3 scripts/accept_phase_13.py \
  --write-template outputs/acceptance/phase_13/evidence.json
```
The synthetic and permitted non-research diagnostic scopes above must be used. No saved traces are produced in equipment-only mode with approved staff present, and the integrated recognition scenarios are not satisfied. Every acceptance trace must be completed with a local log or dated report path, and its source scope must be identified. Credentials, identities, audio and video must not be included in the evidence. Missing final-scenario requirements must be retained as incomplete; new participant data must not be collected to satisfy them. Assessment can then be performed with:
```bash
PYTHONPATH=src python3 scripts/accept_phase_13.py \
  --evidence outputs/acceptance/phase_13/evidence.json \
  --output outputs/acceptance/phase_13/assessment.json
```
A part is kept incomplete by the assessor for any failed check, missing trace, duration below 5,400 seconds, missing stability metric, changed required-artifact hash, absent code revision or unverified clean environment.

## 13.1 Final scenario
1. Services, the Camera A bridge and both active ESP nodes must be started from a clean boot, and preflight must be passed in `non_research` mode
2. Camera A metadata, ESP-A1/A2 records, two-second windows, the frozen model, dashboard and Firebase boundary must be run together
3. Multiple local tracks and ordinary activity labels must be demonstrated without role attribution using synthetic records; no new staff/participant session is permitted
4. ESP-A1 must be disconnected and restored, followed by ESP-A2. Explicit degraded operation must be shown while Camera-only prediction and operation of the other node are continued
5. The approved mask must be made unavailable. Dashboard status must be set to blocked, and integrated completed-window inference must be paused until explicit re-verification
6. Firebase must be made unavailable. Local inference/dashboard operation must be continued; only non-identifying summaries may be placed in the outbox
7. Operation must be stopped cleanly, and counts and retained-data rules must be reconciled

## 13.2 Session-length stability
The final build must be run for at least 5,400 seconds. Capture/processing FPS, ESP-A1/A2 delivery, prediction p95 latency and storage growth must be recorded. Below-target results must be retained as limitations. The absence of sustained degradation, unexplained gaps and stale-state reuse must be confirmed.

### Opt-in aggregate stability diagnostics
For an explicitly approved non-research, transient local display check only, with approved staff only in the retained region, the current mask rechecked and DJI recording disabled:
```bash
PYTHONPATH=src /opt/homebrew/bin/python3.12 scripts/run_phase_13.py \
  --input-scope non_research --live-display-only \
  --approved-staff-present --mask-alignment-confirmed \
  --dji-recording-disabled --save-aggregate-report --stability-check
```
This mode is not designated as a participant session or accuracy evaluation. Historical collection commands must not be reused. No cloud client, outbox or staff-record writer is constructed. Only the fixed aggregate report is saved under the printed `outputs/acceptance/phase_13/aggregate_*/summary.json` path. No activity labels, track IDs, sensor readings, images, audio, addresses or arbitrary exception text are copied to that report. The default display mode is unchanged. `--clean-boot-confirmed` is optional and must only be added after an actual clean boot; a clean boot is not silently asserted during stability assessment.
Measurement is started after the first fresh masked camera and both fresh ESP inputs are received, rather than at command launch. A maximum of 60 seconds is allowed for this starting condition. Once started, measurement is stopped automatically after 5,400 elapsed monotonic seconds; an early stop, startup timeout, pause or runtime interruption is not accepted as a full uninterrupted run. `pause` must still be used BEFORE the retained region is entered by non-approved people or the camera is moved. Privacy must be prioritised over completion of the duration. The existing explicit re-verification is required for resume; a pause is not erased and an accepted 90-minute interval is not restarted by resumption. Nodes must not be deliberately disconnected during this stability check.
Aggregate progress is included in `status`. The single report is checkpointed about every 60 seconds while polling and marked incomplete until verified shutdown. The last incomplete checkpoint is retained after abrupt termination. Measurement is frozen before teardown during normal shutdown; an otherwise short run cannot be completed using teardown time. The browser tab must be closed afterwards. Part 13.2 is never marked complete automatically by the report. The report and trace must be reviewed before the unchanged acceptance evidence is populated; stability is not established by clean shutdown alone.
Metric definitions and limits:
- Capture/processing FPS are interval-weighted producer rates over frame intervals delivered to the parent: summed capture-index steps or processed intervals divided by summed source-timestamp intervals. They are not dashboard refresh rate or a guarantee that every frame reached the parent. Missing/invalid intervals are counted; camera freshness and IPC-drop diagnostics must also be reviewed.
- Each ESP delivery estimate is forward unique packet count divided by that count plus observed sequence gaps. Only protocol sequence/boot metadata is held transiently; it is not saved. Duplicates and older arrivals cannot inflate the numerator. Restart and non-increasing arrival counts remain visible. No gap is inferred across a boot or deliberate pause. Missing packets before the first or after the last received packet are not estimated; trailing outages remain visible in health observations. Reordering can overestimate loss, so this is not a complete transport audit.
- Prediction p95 is nearest-rank local completed-window processing latency, not camera-to-display latency. Only numerical durations are held in memory, at most 4,096 samples. Overflow or invalid samples make p95 unavailable, not a silently truncated full-run statistic. Normal 90-minute two-second-window run fits within this bound.
- Storage growth is net regular-file bytes under project `outputs`, from measurement start to before teardown, excluding this report directory. File contents and names are not saved. Negative growth is possible; unrelated concurrent output changes can affect it. It is not disk-free-space growth or an independent privacy audit. Missing storage measurements remain null, not zero.
- Health sample counts, longest observed degraded interval, maximum observation gap, stale-prediction observations and pause count support review. These are polling observations, not continuous proof. No additional sustained-degradation duration threshold is introduced; the three acceptance judgments remain unset pending review. Packet-loss results and existing warning thresholds are not relaxed.
A hardware run is not started merely by the addition of this reporting support. Phase 13.2 is kept unassessed until the actual final-build run has been completed and reviewed.

## 13.3 Release freeze
The exact code revision and SHA-256 values must be recorded for every artifact named by `config/phase_13_acceptance.json`. Secret and identity/media scans must be run, and the frozen build must then be installed and demonstrated in a clean environment. A source folder without a resolvable revision cannot be passed.
No Git metadata is included in the repository copy, so a deterministic `source-tree-sha256` revision is used in Part 13.3, calculated from a sorted manifest of included file paths, sizes and hashes. That manifest is embedded in the release archive. During verification, the archive is extracted into a fresh temporary directory, every manifest entry is rechecked, and the hardware-free synthetic Phase 13 demonstration is rerun from the extracted source. `data/`, prior `outputs/`, temporary files, caches, retired ESP firmware, alternative model artifacts and image/audio/video files are excluded by the allowlist. Generated release evidence is retained under `outputs/acceptance/phase_13/release_*`.
The individual generated checks are passed by all three parts. The overall disposition is retained as `partial_accepted_limitation`, matching the Phase 2 treatment, because the accepted network-degradation limitation is applied in Part 13.2.

### Accepted public-network degradation amendment
One exception is added in Contract v2 with explicit operational approval matching the established Phase 2.4 treatment: only the degradation requirement may be satisfied by sustained degradation attributable to the documented public-network delivery limitation. The measured degradation must be kept false/recorded, the exact limitation ID and decision trace are required, and full duration, all six metrics, no unexplained gap and no stale-state reuse must still be passed. This is not designated as a general waiver and must not be used for privacy, camera, inference, retention, duration or unexplained-gap failures. Operational completion with an accepted limitation is recorded; public Wi-Fi is not asserted as the proven sole cause, and attainment of the packet-delivery target is not asserted.