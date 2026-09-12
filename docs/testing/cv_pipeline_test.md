# Initial CV Pipeline Test
## Scope
The ARIA computer-vision pipeline is checked by this test using either non-research prerecorded video or the verified, masked local Camera A feed. Live testing must follow the existing consent and exclusion procedure.
```text
video input
→ privacy mask
→ one-frame latest-masked-frame buffer
→ fixed-rate processing
→ person detection and ByteTrack tracking
→ optional batched pose extraction on tracked person crops
→ JSONL feature output
```
Camera A remains configured at 1920x1080 and 30 FPS. The processing rate does not change the camera deployment mode: it controls how often the newest masked frame is selected for inference. Frames replaced before inference are counted in the final summary, and retained frame numbers preserve visible gaps for later timing and availability analysis.

## Phase 5.2 tracking-only command
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
The run can be stopped early with `q`. `--duration` must be omitted during the interactive S1-S4 scenarios.
Tracking-only mode deliberately omits pose inference. It is the required mode for Phase 5.2 S1-S4 trials because those trials assess camera-local ID continuity rather than skeletal quality.

## Full tracking and pose command
```bash
PYTHONPATH=src python3 scripts/test_cv_pipeline.py \
  --source rtsp://127.0.0.1:8554/live/camera_a \
  --camera-id camera_a \
  --mask-config config/masks.batamfast.yaml \
  --tracker-config config/bytetrack.zone_a.persistence.yaml \
  --detector-confidence 0.10 \
  --pose-confidence 0.15 \
  --keypoint-confidence 0.5 \
  --min-confident-keypoints 4 \
  --processing-fps 15 \
  --inference-size 768 \
  --pose-inference-size 384 \
  --duration 120 \
  --output data/interim/camera_a_phase_5_4_persistence_dedup_18.jsonl
```
Full mode uses the accepted person detector and ByteTrack path as the source of camera-local IDs. It then runs one batched `yolov8n-pose.pt` call over the tracked person crops. A temporary pose failure sets `pose_available: false` without deleting or renumbering the person track. Detection and pose durations are recorded separately while the version 2 Phase 6-facing record contract remains unchanged. Full mode uses a 768-pixel detector input to preserve the smaller rear subjects; the already-cropped pose inputs use 384 pixels to avoid repeating full-frame 960-pixel inference for every person.
The full-mode detector threshold matches ByteTrack's `track_low_thresh: 0.10`. Detections from 0.10 to 0.25 may recover an existing track, while `new_track_thresh: 0.25` prevents them from creating a new ID. A new detector track is also not emitted until the configured confident-keypoint gate confirms that it is a plausible person. Once confirmed, the detector ID remains available during temporary pose loss. This improves recall for small or partially occluded people without accepting weak wall detections.
The accepted Phase 5.4 profile is `config/bytetrack.zone_a.persistence.yaml`. It retains lost tracks for 90 processed frames, permits wider motion association, and disables score fusion so confidence fluctuations do not dominate geometry. Conservative same-frame duplicate suppression removes strongly matching boxes without storing a persistent identity alias.
BoT-SORT was compared once against `config/botsort.zone_a.phase_5_4.yaml`. The comparison is restricted to motion: appearance and biometric re-identification are prohibited by `with_reid: false`, and global motion compensation is disabled because Camera A is fixed. ReID must not be enabled as an informal tuning step.
The controlled comparison rejected BoT-SORT for the active deployment: it created 42 IDs versus ByteTrack's 14, increased tracking gaps from 52 to 77, and increased mean total latency from approximately 122 ms to 158 ms. ByteTrack therefore remains the selected Phase 5.4 tracker. The stricter `config/bytetrack.zone_a.phase_5_4.yaml` and rejected BoT-SORT comparison are retained as reproducible tuning evidence, not as the accepted live profile.
The BatamFast mask must be verified before the live command will process a frame. The initial YOLO detection and pose model files may require download on first use; prepare them before using the site's public network, where model downloads must not be assumed to be available or appropriate during collection.

## Output
Tracking records are written to the path supplied with `--output`, for example:
```text
data/interim/camera_a_tracks_phase_5_2.jsonl
```
Each record contains:
- Schema and mask-configuration versions
- Record type
- Camera ID
- Frame number
- SGT frame timestamp
- Explicit frame and pose availability
- Camera-local track ID
- Bounding box
- Detection confidence
- Keypoints
- Keypoint confidences
- Zone
- Capture, detection, pose and total processing latency
Every record is validated against `schemas/camera_track.schema.json` before being appended. Frame-status records use null track fields and contain no image data.
`--detector-iou` exposes YOLO's person-detection NMS IoU threshold and defaults to `0.70`. Lower thresholds remove more overlapping boxes. A candidate value must demonstrate both fewer nested duplicate tracks and retention of every genuine person during S4; hiding one overlapping person is a failure even if the remaining displayed ID is stable.
An existing local weight file must be specified by `--detector-model` so that an unplanned model download cannot be triggered after preflight during a site run. Only the detector model is changed from `yolov8n.pt` to `yolov8s.pt` in the YOLOv8s comparison; OC-SORT v3, detector IoU `0.35`, the verified mask, pose settings and 15 FPS processing target are retained. Achieved processing FPS and frame age must be recorded alongside ID continuity because a more accurate detector cannot be accepted if the preview is made materially stale.
When `--experimental-track-stitching` is enabled for a non-research trial, a track record additionally contains the raw-ID-preserving fields `stitched_track_id`, `track_association_status` and `track_association_reason`. A null stitched ID is deliberate uncertainty and must be excluded rather than manually resolved.

## Phase 5.2 controlled tracking trials
Only generic trial labels must be used; names and participant identifiers must not be entered.
The template must be copied before beginning:
```bash
cp docs/testing/phase_5_2_tracking_trials_template.csv \
  docs/testing/2026-08-01_phase_5_2_tracking_trials.csv
```
These scenarios must be run while the displayed local track IDs are observed:
1. `S1 continuous`: one consenting Counter Agent walks and works continuously; record the ID sequence and confirm it stays stable
2. `S2 short_occlusion`: the same controlled subject is briefly occluded and returns within approximately one second; the ID should remain stable
3. `S3 full_exit_reentry`: the subject fully exits, remains absent beyond the short-occlusion buffer, then re-enters; a new ID is expected
4. `S4 multiple_person`: two consenting Counter Agents move and cross within the retained region; record each generic subject label's observed ID sequence and check that no ID is shared
Pipe-separated ID sequences, such as `7|7|7` or `9|12`, must be entered before evaluation is performed:
```bash
PYTHONPATH=src python3 scripts/evaluate_tracking_trials.py \
  --input docs/testing/2026-08-01_phase_5_2_tracking_trials.csv \
  --output docs/testing/results/2026-08-01_phase_5_2_tracking_metrics.json
```
Phase 5.2 is accepted only when the evaluator reports `accepted: true` and any observed detection limitations have been documented during manual review. Adjust detector confidence or `config/bytetrack.zone_a.yaml` only from controlled masked evidence, rerunning all scenarios after each adjustment.
For the Phase 9.1 stitching candidate, `docs/testing/phase_9_1_stitching_recheck_template.csv` must be copied, the lifecycle runner must be run as `non_research_dry_run` with both `--masked-track-preview` and `--experimental-track-stitching`, and the displayed `S` ID sequences must be entered in the copied CSV. The candidate is failed by any `S?`, unexpected switch or shared S4 stitched ID. The candidate must not be enabled for a pilot or participant session.
`config/ocsort.zone_a.candidate_v2.yaml` is used in the Phase 9.1 OC-SORT duplicate-detection comparison, stitching is kept disabled, and only `--detector-iou 0.35` is changed from the normal detector settings. The value is motivated by same-frame nested boxes in the preceding non-research run and is not accepted as a participant setting. Continuous and overlapping multiple-person observations must be repeated before further consideration.
After a participant-session tracking concern, tuning from participant records or retrospectively inferred identities must not be performed. S1-S4 must first be repeated as a non-research controlled masked trial using generic `subject_1`/`subject_2` labels. For the lifecycle runner, `--masked-track-preview` must be enabled and only the printed localhost URL must be used; the same IDs written by that runner are displayed. `config/bytetrack.zone_a.persistence.yaml` must not be changed unless the controlled trial has been failed and all four scenarios have subsequently been passed by a candidate profile.
The 15 FPS processing baseline uses `track_buffer: 15`, corresponding to approximately one second of selected frames. If `--processing-fps` changes, adjust the buffer to the same starting value and rerun every controlled trial.
For Phase 5.4 pose trials, `config/bytetrack.zone_a.persistence.yaml` must be used. A lost motion track is retained for up to 90 processed frames, and pose-plausibility evidence is required before a track is emitted. Partially occluded or temporarily stationary subjects are preserved by its low recovery threshold; weak non-person tracks are rejected by the downstream confident-keypoint gate. Appearance and biometric re-identification are not used. The Phase 5.2 baseline configuration must be kept with its existing acceptance evidence.

## Real-time performance check
Before S1-S4, run tracking-only mode for at least 60 seconds and confirm:
- The displayed view remains current rather than accumulating delay;
- H264 decoder errors do not continue under inference load;
- Track IDs respond to current movement without a growing offset;
- `read_failures` is zero or fully explained;
- `processed_frames` is sufficient for the selected processing rate;
- `effective_processing_fps` remains useful and stable;
- `frame_age_ms` p95 remains bounded rather than increasing throughout the run;
- `inference_latency_ms` is recorded for the selected model profile;
- `replaced_before_processing` is reported rather than hidden;
- Frame-number gaps correspond to deliberate replacement, not stale reuse.
Frame replacement is expected when Camera A supplies 30 FPS and CV runs at 15 FPS. It is not a stream failure. A continuously increasing visual delay, sustained decoder errors, or frozen current movement is a failure and the affected S1-S4 interval must be repeated.

## Phase 5.2 result - 1 August 2026
The 60-second low-latency tracking-only run passed with 1,820 captured frames, 858 processed frames, zero read failures and 14.283 effective processing FPS. This accepted Phase 5.2 run used the 640-pixel detector inference size shown in the command above. Phase 5.4 separately retains its accepted 768-pixel size. Mean frame age was 55.166 ms and p95 frame age was 88.058 ms. The 991.887 ms maximum occurred on frame 1 during model warm-up; the next-highest recorded latency was below 100 ms.
The final S1-S4 evaluator reported zero unexpected ID switches, zero behaviour failures, zero multiple-person ID collisions and `accepted: true`. Continuous tracking, short occlusion, full exit/re-entry and the controlled multiple-person crossing therefore passed.
One limitation remains recorded: the first behind-person crossing attempt fragmented one camera-local track. A controlled repeat using an ordinary sub-one-second crossing retained stable, distinct IDs. ByteTrack remains camera-local and may fragment under heavier or complete person-to-person occlusion; no biometric identity or re-identification is used.
Evidence:
- `data/interim/camera_a_tracks_phase_5_2_low_latency_01.jsonl`
- `docs/testing/2026-08-01_phase_5_2_tracking_trials.csv`
- `docs/testing/results/2026-08-01_phase_5_2_tracking_metrics.json`

## Phase 5.4 result - 31 July 2026
The final 120-second masked tracking-and-pose run, conducted using the persistence-first ByteTrack profile, was accepted following manual review. Camera A remained at the locked 1920x1080 and 30 FPS deployment mode while inference selected the latest masked frame at a 15 FPS target.
The run captured 3,620 frames with zero read failures and processed 837 frames at 6.969 effective FPS. Mean inference latency was 124.779 ms, p95 inference latency was 164.149 ms, mean frame age was 158.005 ms and p95 frame age was 236.314 ms. The JSONL contained 2,977 track records across 837 output frames; 96.607% of track records carried an available pose. The pipeline rejected 120 implausible-pose tracks and conservatively suppressed 367 same-frame duplicate tracks.
ID retention and overall tracking quality were considered acceptable during visual review. Known limitations remain: temporary ID swaps can occur when subjects overlap closely in the oblique camera view, occasional short-lived duplicate IDs may appear on one subject, and the effective processing rate was approximately 7 FPS rather than the 15 FPS target. These limitations are documented for Phase 6 integration and later optimisation; they do not change the Camera A deployment configuration or the version 2 Phase 6-facing record schema. CPU and RAM readings are outside the Phase 5 acceptance requirements.
Evidence:
- `data/interim/camera_a_phase_5_4_persistence_dedup_18.jsonl`
- `docs/testing/results/2026-07-31_camera_a_phase_5_4.md`

## Development mask
`config/masks.development.yaml` retains the entire configured 1920x1080 frame for `camera_a` and is for non-research test footage only. The active deployment camera is the DJI Osmo Action 5 Pro. There is no Camera B in the current deployment.
The development mask must not be used for participant collection. The final BatamFast mask must be created and verified using the mounted DJI Camera A, and only the approved Zone A staff-side region must be retained.

## Acceptance criteria
- Pipeline accepts only `camera_a`
- Privacy mask is applied before detection, tracking or pose extraction
- Only the newest waiting masked frame is retained for inference
- Phase 5.2 tracking-only mode performs no pose-model calls
- `camera_id: camera_a` and the correct frame timestamp are used in output records
- Output records pass the versioned Camera A schema
- frame/pose availability and all four latency components are explicit
- Continuous and short-occlusion trials preserve a camera-local ID
- Full exit and re-entry produces a new ID
- Multiple-person trials do not assign one ID to two controlled subjects
- No unmasked frame is written to `data/interim/` or another persistent path
- detection, tracking and pose failures are reported without bypassing masking
- Non-research test footage is kept separate from participant data