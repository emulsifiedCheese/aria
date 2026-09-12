# Phase 9.3 frozen collection settings - polling-safe annotation controls

> **Historical status:** The ACTIVE designation below applied to v7 during the completed collection period. Participant collection was closed on 10 August 2026; no new pilot or participant sessions are authorised. The original profile and its recorded hashes are retained.

Historical metadata can be read with `load_collection_profile(verify_files=False)`;
this still validates the profile's own checksum and structure. Live-setting
validation rejects a retired profile before checking its historical artifacts
against current files. Non-retired profiles still require full artifact
verification. This preserves the recorded hashes without authorising collection.

Status: **ACTIVE**  
Frozen: 2026-08-05 SGT  
Profile: `zone-a-collection-v7`  
Authority: `config/collection.zone_a.v7.yaml`

## Activation decision
`zone-a-collection-v6` is superseded by Version 7 for later formal sessions after replacement of a participant card by the one-second browser status poll during manual track-ID entry was demonstrated in the third formal attempt.

The following behaviour is provided by the v7 interface:
- A valid manual track draft is recorded on every input event
- Participant cards are not rebuilt while a manual track field is focused
- Normal live rendering is resumed as soon as focus is moved away from that field
- The selected activity is preserved across ordinary status polls
- The prior activity is retained beside a replacement-track warning

The lifecycle safety rule is unchanged. If a selected track is absent from every processed frame in a complete two-second window, the annotation is closed before that window, and an explicit replacement track is required.

No changes are made by this revision to Ethics Pack Version 4.4, participant scope, privacy masking, consent controls, Camera A processing, ESP telemetry, two-second timing, activity labels, schemas, models or the 90-minute maximum. Original profile IDs and hashes are retained for completed v6 sessions.

## Active method
The three Counter Agent activity classes remain:
1. `Serving/Processing`
2. `Idle/Waiting`
3. `Reaching/Handling`
Annotation and prediction records remain schema version 3. Session manifests remain schema version 8.

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
`--participant-id` was required to be repeated for every participating Counter Agent. Fresh artifact verification, fail-closed live preflight and a completed manual checklist were required for every session.
