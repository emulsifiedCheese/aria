# Phase 9.3 frozen collection settings - split annotation layout

> **Historical status:** The ACTIVE designation below applied to v6 from 5 August 2026 and was superseded by v7. Participant collection was closed on 10 August 2026. The original acceptance decision and frozen profile are retained as historical evidence.

Status: **ACTIVE**  
Frozen: 2026-08-05 SGT  
Profile: `zone-a-collection-v6`  
Authority: `config/collection.zone_a.v6.yaml`

## Activation decision
`zone-a-collection-v5` is superseded by Version 6 for formal sessions following acceptance of the desktop split annotation layout during manual review on 5 August 2026. Only the arrangement of the annotation interface is changed in this revision:
- The complete masked Camera A display is retained on the left
- The annotation heading, instructions, add-participant control and notice are displayed below the display
- The participant-card grid is positioned at the top right and can be scrolled independently
- The two-by-two rule is retained for four cards, and the three-plus-two desktop rule is retained for five cards
- A stacked layout is used on narrow screens
No changes are made by this revision to Ethics Pack Version 4.4, participant scope, privacy masking, consent controls, Camera A processing, ESP telemetry,
two-second timing, activity labels, schemas, models or 90-minute maximum.

## Active method
The three Counter Agent activity classes remain:
1. `Serving/Processing`
2. `Idle/Waiting`
3. `Reaching/Handling`

Annotation and prediction records remain schema version 3. Session manifests remain schema version 8. Historical v5 and earlier sessions remain unchanged.

## Formal command
Under the historical procedure, the following command was permitted only after the manual checklist was completed and Camera A, MediaMTX, ESP-A1 and ESP-A2 were live:
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
  --collection-profile config/collection.zone_a.v6.yaml \
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
`--participant-id` was required to be repeated for every participating Counter Agent. Fresh artifact verification, fail-closed live preflight and a completed manual checklist were required for every session.
