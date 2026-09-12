# Phase 9.3 frozen collection settings - three-class activation

> **Historical status:** The ACTIVE designation below applied to v5 from 4 August 2026 and was superseded by later frozen profiles. Participant collection was closed on 10 August 2026. The original acceptance decision and profile are retained as historical evidence.

Status: **ACTIVE**  
Frozen: 2026-08-04 SGT  
Profile: `zone-a-collection-v5`  
Authority: `config/collection.zone_a.v5.yaml`

## Activation decision
`zone-a-collection-v4` is superseded by Version 5 for formal sessions after the first completed Phase 9.3 run. The three-class Counter Agent
taxonomy recorded in Ethics Pack Version 4.4 is frozen:
1. `Serving/Processing`
2. `Idle/Waiting`
3. `Reaching/Handling`
The required methodology confirmation, Version 4.4 issue and participant acknowledgement were reported as recorded under approved secure controls and were confirmed by the researcher on 4 August 2026. Identifiable confirmation and signature records remain outside this repository.

## Frozen behaviour
- Schema version 3 is used for annotation and prediction records
- Schema version 8 is used for session manifests, in which consent-gated timestamped participant additions are recorded
- Historical schema-version-2 records remain unchanged. Both historical `Serving` and `Typing/Processing` labels are mapped to `Serving/Processing` in derived analysis
- Participant cards are maintained independently, and explicit local track and activity selections are required. Participant identity is never inferred by ARIA
- Camera geometry, privacy mask, ESP firmware, models, tracker settings, two-second fusion windows and 90-minute maximum remain unchanged

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
  --collection-profile config/collection.zone_a.v5.yaml \
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
`--participant-id` was required to be repeated for every participating Counter Agent. Fresh artifact verification and fail-closed live preflight were required before each session. v5 and pinned artifacts must not be edited silently; a new profile version and affected acceptance checks are required for any later methodology, schema, privacy, model, firmware, timing or procedure change.