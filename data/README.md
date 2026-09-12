# ARIA Data Directory Contract
## Purpose and authority
Retained local numerical telemetry, privacy-masked camera features, multimodal windows and session-control records from the completed Zone A participant-collection period are stored in this directory, together with rebuildable Phase 10 outputs. 
Participant identities, raw audio, intelligible speech, raw/unmasked video and cloud copies of local media must not be stored here.
Only the following devices are used in the active system:
- ESP-A1 with `A_PIR_US_MIC`
- ESP-A2 with `A_PIR_MIC`
- DJI Camera A identified as `camera_a`

ESP-B, ESP-T, Zone B, Zone T and a second camera are historical and must not be included in retained participant data or current modelling inputs. All retained participants were consenting Counter Agents covered by Ethics Pack Version 4.4 and amended Part D. Employment roles are neither recorded nor inferred by ARIA.

Participant collection was closed after the ninth retained formal session on 10 August 2026. Only storage, modelling and retention rules are defined in this README; no new pilot or participant collection is authorised.

## Core privacy rules
- Only pseudonymised participant IDs must be used; the participant-code key must be kept outside this project and dataset
- Names, employee numbers, exact shifts, customer details or physical descriptions must never be used in filenames or records
- Only numerical features are provided by microphones. Audio waveforms, recordings, speech, transcripts and voice identifiers must never be retained
- The approved Camera A privacy mask must be applied and validated before detection, tracking, pose extraction, display or feature output
- Only numerical Camera A records, such as timestamps, camera-local track IDs, bounding boxes, confidences, skeletal keypoints and availability fields, must be stored
- Raw/unmasked frames must never be stored in `data/`. Any explicitly permitted temporary masked video must be kept in approved restricted local storage outside the repository and handled under the retention schedule
- Raw or masked video, raw audio or excluded data must never be uploaded to Firebase, cloud notebooks or messaging services
- An incident/exclusion decision must be treated as authoritative over annotation or apparent record quality

In this project, the earliest retained machine-readable numerical records are designated as `raw`. Raw audio and raw video are not permitted by this designation.

## Directory map
| Path | Current purpose | Permitted contents |
|---|---|---|
| `data/raw/` | local first-stage runtime output | schema-valid ESP telemetry, invalid-packet diagnostics, lifecycle-owned session directories |
| `data/raw/sessions/` | session-scoped writer output | numerical ESP packets and numerical privacy-masked Camera A records only |
| `data/raw/manifests/` | canonical retained manifest location | completed, aborted and historical lifecycle-state session manifests |
| `data/raw/incidents/` | canonical retained incident location | schema-version-5 non-identifying incident JSON |
| `data/interim/` | rebuildable intermediate output | camera track/pose JSONL, multimodal feature windows and other numerical derived records |
| `data/processed/` | audited local model datasets | model-ready numerical tables and split assignments created only after exclusion, privacy and leakage audits |
| `data/annotations/` | retained annotation location | schema-version-3 role-neutral annotation records; historical v2 records remain unchanged |
| `data/excluded/` | temporary local quarantine | privacy-invalid or operationally invalid material pending prompt deletion; never modelling input |
| `data/quarantine/` | isolated rejected-session evidence | local numerical records from failed controls; never modelling input and ignored by version control |
| `data/historical/` | historical diagnostic evidence | retired-node or mixed-progression telemetry retained only for traceability; never current modelling input |
| `data/manifests/` | unused legacy/reserved directory | do not write current manifests here; use `data/raw/manifests/` |
Additional data locations must not be created without documenting their purpose, privacy controls, retention rule and relationship to the session manifest.

## Record and schema mapping
| Record | Schema or contract |
|---|---|
| stored ESP receive envelope | `schemas/esp_record.schema.json` |
| nested ESP-A1/A2 telemetry payload | `schemas/esp_packet.schema.json` |
| camera A numerical track/pose records | `schemas/camera_track.schema.json` |
| multimodal feature windows | `schemas/feature_vector.schema.json` |
| session lifecycle and output accounting | `schemas/session_manifest.schema.json` |
| activity annotations | `schemas/annotation.schema.json` |
| phase 10.3 split assignments | `schemas/phase_10_3_split_assignment.schema.json` |
| model predictions | `schemas/prediction.schema.json` |
| privacy/operational incidents | `schemas/incident.schema.json` |

Every stored envelope and nested payload must validate against its current supported schema version before it is treated as usable. A structurally valid record remains unusable when its window is excluded, its session is aborted, its incident is unresolved or its privacy provenance is incomplete.

## Identifiers and time
- The SGT form is used for session IDs: `zone_a_YYYYMMDDTHHMMSSSGT_<non-identifying-token>`
- The pseudonymised `P0000` form is used for participant IDs. The mapping to a person must never be stored in this directory
- Camera track IDs are camera-local technical identifiers, not identities and not persistent biometric links
- Only bounded numerical time windows are identified by multimodal window IDs
- Incident and annotation IDs must be defined in accordance with their schemas, with no identity information included
- Timezone-aware SGT timestamps must be used for camera/sensor alignment and session lifecycle records. ESP `timestamp_ms` is retained as device-uptime evidence only

## Raw runtime records
The following records may be stored in `data/raw/`:
- ESP-A1/A2 JSONL receive envelopes accepted by `esp_record.schema.json`, each containing a payload accepted by `esp_packet.schema.json`
- Locally rejected-packet diagnostics in which only the receive endpoint, validation error, packet byte count and SHA-256 digest are stored, never packet content
- planned/running/paused/completed/aborted manifests
- Incident records
- Session-scoped numerical Camera A and ESP outputs

The following material must not be stored:
- Audio or video files
- Unmasked or masked frame images
- Participant names, consent records or participant-code key
- Wi-Fi credentials, private keys or service-account credentials
- Telemetry from retired nodes in a retained participant session
- Files from a session that bypassed preflight or the manifest-backed writer gate

Every lifecycle-owned output must be accounted for in a completed schema-version-8 manifest using its relative local path, observed, written and excluded record counts, gap count and longest gap. For every output, observed must equal written plus excluded. An `aborted` session remains unusable until reviewed under the approved data-handling procedure.

The existing generic `data/raw/esp_packets.jsonl` and `data/raw/esp_packets_pretest.jsonl` files are retained as mixed historical diagnostic evidence containing retired-node records. Their timestamp fields were migrated to the SGT-only contract, but their historical record content is otherwise retained for traceability. Data must not be appended to these files, and the files must not be used directly for modelling. The completed pilot and participant sessions are retained under the lifecycle-owned `data/raw/sessions/<session_id>/` structure, where retained sessions are separated and the exact files in scope are identified by their manifests.

## Interim and processed records
Reproducibly derived numerical records are stored in `data/interim/`. The following must be preserved:
- source/session/config/schema versions
- Timezone-aware timestamps and window boundaries
- Per-modality record and missing counts
- `camera_available`, `pose_available`, `a1_available` and `a2_available`
- Camera-local track semantics
- Explicit quality and timing fields

Missing observations must be represented using availability flags and `null` where the schema permits it. A missing modality must not be represented as a zero value that could be interpreted as an observed measurement.

Rebuildable, local-only Phase 10 model-ready numerical datasets are stored in `data/processed/` after data-quality, privacy, exclusion and grouped-split controls have been passed. Phase 10.3 assignments are governed by `config/phase_10_3_split_policy.json`; generated assignments must not be edited manually, and external-test rows must not be used during development. Participant-derived processed contents are ignored by version control and remain subject to the privacy and sharing controls below.

## Annotations
Annotation records must be stored in `data/annotations/` and governed by:
- `schemas/annotation.schema.json`
- `docs/data_collection/annotation_protocol.md`

Only the approved role-neutral activity labels are permitted in current derived records: `Serving/Processing`, `Idle/Waiting` and `Reaching/Handling`. `Serving` or `Typing/Processing` may be retained in historical schema-v2 source records; those labels must be mapped to `Serving/Processing` only in derived data and must not be rewritten in the source. Uncertain or excluded intervals remain unusable for modelling. Identity, employment role, customer attributes, conversation content and private screen content must not be inferred.

## Excluded and incident-affected data
`data/excluded/` is designated as a temporary local quarantine, not an archive or evidence repository. The following procedures must be followed:
- `docs/privacy/customer_exclusion.md`
- `docs/privacy/privacy_incident_procedure.md`
- `docs/privacy/retention_schedule.md`

When an incident affects retained data:
1. Collection must be paused or refused
2. All affected window IDs must be linked to schema-valid incident
3. Affected material must be isolated locally
4. Its inclusion in annotation, training, evaluation or demonstration must be prevented
5. Required deletion must be completed promptly
6. Deletion must be recorded using IDs, SGT time, data category and operator role only
Prohibited content must never be retained merely to prove that deletion occurred.

## Version-control and ignore boundaries
Generated contents under the following locations are excluded by the current `.gitignore`:
- `data/raw/`
- `data/interim/`
- `data/excluded/`
- `data/annotations/`
- `data/processed/`
- Generated contents under `data/quarantine/`
- Generated contents under `data/historical/`
A version-control safeguard is provided by ignore rules; permission to share a file is not established by those rules. Filenames and contents must be reviewed before sharing or submission.

Safe README files are retained as visible files through explicit exceptions. Generated annotation, processed, quarantined and historical records are kept local and ignored, but session, incident, exclusion, retention and sharing controls are not replaced by ignore rules. `data/manifests/` is not the canonical retained manifest location and must remain unused; retained manifests are stored under `data/raw/manifests/`.

Only documentation is included in README and placeholder files. Real participant examples must never be included.

## Retention and deletion
`docs/privacy/retention_schedule.md` and `docs/privacy/data_handling.md` must be applied. In particular:
- Customer-affected and mask-failure material must be deleted as soon as identified
- Permitted temporary masked video must be deleted after annotation/quality checking
  and within approved maximum period
- Consent and acknowledgement records must be kept securely outside this project
- Participant-code key must be deleted after the approved withdrawal deadline
- Pseudonymised data must not be publicly released or reused without the applicable participant permission

## Before sharing, submission or model use
- It must be confirmed that every included record has valid schema/config provenance
- It must be confirmed that no included window is linked to an exclusion or unresolved incident
- It must be confirmed that source session manifest is valid and not aborted
- Filenames and contents must be scanned for identities, credentials and private keys
- It must be confirmed that no raw audio, intelligible speech, raw/unmasked video or prohibited masked video is present
- Caches, runtime logs, temporary files and unneeded large model/data artefacts must be removed
- Only anonymised, approved and reproducible evidence extracts must be included
- The audit must be recorded without copying prohibited content into the report