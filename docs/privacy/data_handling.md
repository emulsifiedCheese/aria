# ARIA Zone A Data-Handling Procedure
> **Review status:** Approved by the project owner on 30 July 2026.  
> **Active scope:** ESP-A1, ESP-A2 and `camera_a` in Zone A only.

## Purpose
The creation, storage, access, exclusion, transfer and deletion of ARIA data are governed by this procedure. Technical calibration, approved participant sessions, annotation, modelling, evaluation and demonstration are covered.
Participant collection is not authorised by this procedure. Under the historical collection rules, the current ethics, consent, site, privacy-mask and acceptance gates had to be passed before collection could be started.

## Core rules
- Only the minimum data required for the approved Zone A study must be collected
- Pseudonymised participant IDs must be used in research data and application output
- Participant-code key must be stored separately from research dataset
- Raw audio, intelligible speech, transcripts or voice identifiers must never be stored
- Verified privacy mask must be applied before detection, tracking, pose estimation, display, feature output or permitted temporary masked storage
- Raw and masked video must be kept local. Neither may ever be uploaded to Firebase, cloud notebooks or other cloud services
- Footage containing customers, non-participants, mask failures, payment areas, private screens or sensitive documents must not be retained
- Zone B, Zone T, ESP-B, ESP-T and a second camera must be treated as historical only

## Data categories and approved locations
| Data category | Approved location | Repository/submission rule |
|---|---|---|
| ESP-A1/A2 numerical telemetry | Local `data/raw/` during authorised work | Generated content is ignored and excluded from the submission archive |
| Invalid-packet diagnostics | Local `data/raw/` | Payloads containing identifiers or secrets must not be included |
| Runtime health and node logs | Local `outputs/logs/` | Generated logs are ignored and reviewed before any evidence extract |
| Pseudonymised camera/pose features | Local `data/interim/` or approved derived-data location | Schema-valid numerical records only |
| Temporary masked staff-zone video | Approved local encrypted/restricted storage only | Never versioned or uploaded; deleted under the retention schedule |
| Excluded or privacy-invalid intervals | Isolated local exclusion area pending prompt deletion | Never used for training, evaluation or demonstration |
| Participant-code key | Approved secure location separate from the dataset | Never stored in this repository |
| Consent, withdrawal and acknowledgement records | Approved secure external storage | Never stored in this repository |
| Models and evaluation summaries | Local project outputs | Included only after privacy and prohibited-data audit |
| Optional Firebase records | Approved abstracted features or predictions only | No raw/masked video, raw audio, names or participant-code keys |

## Access and separation
- Access to identifiable research records must be limited to the student researcher and authorised supervisor/advisor as required by the approved study
- Consent and acknowledgement records must be kept separate from pseudonymised sensor, feature, annotation and model data
- Participant names, employee numbers, exact shift details, customer details and the participant-code key must not be placed in filenames, logs or fixtures
- Participant data must not be copied into cloud notebooks, public repositories, messaging systems or unapproved removable storage
- The laptop must be locked when unattended, and the operating system's encrypted storage and account access controls must be used

## Camera and audio handling
1. `camera_a`, the fixed final mount, 1920x1080 at 30 FPS and the versioned verified mask must be confirmed before participant processing
2. Local MediaMTX/FFmpeg relay must be used to expose one H264 video track with no audio to ARIA
3. Only the masked staff-side frame must be processed
4. Unmasked screenshots or raw camera streams must not be saved
5. Temporary masked video must be retained only when permitted for annotation or quality checking and only for documented retention period
6. ESP microphone modules must be used only for short-window numerical features. Waveforms must never be retained, and speech must never be reconstructed

## Session lifecycle
### Before a session
- Current participant-facing pack and acknowledgements must be confirmed
- Pre-session checklist must be completed
- Camera identity, mask, audio removal, ESP identities and storage must be verified
- A pseudonymised session ID must be created, and the session record must be opened
- It must be confirmed that only consenting Counter Agents can enter retained region

### During a session
- Mask status, camera availability, packet health and storage must be monitored
- Collection must be paused immediately if the retained area is entered by a customer or non-participant
- Collection must be paused after camera movement, mask failure, stream failure or any privacy incident
- Only non-identifying technical and exclusion information must be recorded

### After a session
- Writers must be stopped cleanly, and the post-session checklist must be completed
- Expected and actual packet/frame/feature counts must be reconciled
- Invalid or customer-affected intervals must be isolated and deleted as required
- Annotation and quality checks must be completed using pseudonymised identifiers
- Retention and deletion actions must be recorded

## Privacy incidents and exclusions
If a mask failure, non-participant entry, customer exposure, sensitive surface exposure or incorrect camera configuration occurs:
1. Collection must be paused or stopped immediately
2. The affected interval must be marked invalid
3. The interval must be prevented from being included in detection output, training or evaluation
4. Affected footage must be isolated and deleted as soon as identified
5. Incident and corrective action must be recorded without participant identities
6. Camera position and mask must be re-verified before collection is resumed
`docs/privacy/privacy_incident_procedure.md`, `docs/privacy/customer_exclusion.md` and session exclusion procedure must be followed.

## Retention and disposal
`docs/privacy/retention_schedule.md` must be applied. In particular:
- Customer-affected and mask-failure footage must be deleted as soon as identified
- Temporary masked staff-zone video must be deleted after annotation and quality checking, and no later than documented maximum
- Signed consent records must be kept securely and separately from the dataset
- Participant-code key must be deleted after withdrawal deadline
- Pseudonymised data must not be publicly released or reused without the participant's applicable optional permission
The data category, affected session or interval, date, reason and operator role must be identified in deletion records without identifiable content being copied into the repository.

## Repository and submission controls
- `.gitignore` must be used to exclude generated raw/interim/excluded data, runtime logs, consent records, credentials, media, caches and generated model binaries
- Ignore rules must be treated as a safeguard; file safety is not established by those rules
- Before sharing or submission, filenames and contents must be audited for credentials, participant identities, raw audio, prohibited video and private keys
- Deployment Wi-Fi credentials must be replaced with placeholders before final submission or sharing
- Only anonymised, approved and reproducible evidence extracts must be included

## Verification checklist
- [x] This procedure has been reviewed and approved by the project owner
- [x] `.gitignore` has been reviewed and approved
- [x] Consented participant PDFs have been moved to secure storage outside repository
- [x] No participant-code key or identifiable consent record is present
- [x] No raw audio or prohibited raw/unmasked video is present
- [ ] Generated data and logs are excluded from submission archive
- [x] Firebase/cloud boundary has been checked
- [x] Retention and deletion records are ready before collection
- [ ] Final credential and prohibited-data audit is complete before submission