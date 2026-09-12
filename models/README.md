# Model artefacts
This directory is reserved for trained ARIA model artefacts and their non-identifying provenance metadata. Raw participant data, annotation exports, video, audio, names and participant-code keys must not be stored here.

## Current computer-vision dependencies
The standard Ultralytics model weights listed below are used by the current detector and pose pipeline. They are local runtime dependencies rather than ARIA-trained research outputs:
| Local file | Purpose | SHA-256 |
|---|---|---|
| `../yolov8n.pt` | person detection | `f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36` |
| `../yolov8n-pose.pt` | skeletal-keypoint estimation | `c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212` |
They are used with the pinned `ultralytics==8.3.70` dependency. A missing standard weight can be downloaded by Ultralytics on first use, so both files must be prepared and verified before site work rather than models being downloaded during collection.
Root-level `.pt` files and generated artefacts under this directory are ignored by `.gitignore`. The source model, software version, training-data scope, feature/schema versions, evaluation result and cryptographic hash must be recorded for any future ARIA-trained model before it is accepted.

## Privacy boundary
A model must not be trained or retained until its source windows have been accepted through the session, incident, exclusion and leakage checks. A model produced from participant data is retained as a controlled research artefact even when no direct media is included. Publication or upload is prohibited without the applicable approval.