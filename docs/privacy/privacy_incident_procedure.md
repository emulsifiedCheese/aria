# Privacy and Operational Incident Procedure
## Purpose and scope
The refusal, pause, exclusion, recovery and recording procedures for privacy or operational failures in the active Zone A deployment are defined here. It applies to ESP-A1, ESP-A2 and `camera_a` only.
Customers remain outside the behind-counter retained region. Ordinary customer presence outside the verified mask is not an incident. Ordinary entry by an eligible consenting Counter Agent is also not an incident. The procedure is triggered only when the retained participant-only boundary, required equipment state or safe session lifecycle is no longer valid.
Only technical state and pseudonymous identifiers are included in incident records. Names, employee numbers, appearance descriptions, customer details, conversation content, exact shifts and participant-code keys must never be recorded.

## Governing controls
- `schemas/incident.schema.json`, schema version 5, is used for incident records
- The current `schemas/session_manifest.schema.json` contract is used for session state and writer accounting
- `src/aria/collection/lifecycle.py` owns pause, exclusion, recovery, abort and clean-stop transitions
- Data handling and deletion follow `docs/privacy/data_handling.md` and `docs/privacy/retention_schedule.md`
- customer/non-participant contingencies follow `docs/privacy/customer_exclusion.md`

## Incident classification and recovery
| Incident type | Default severity | Deletion rule | Required recovery action |
|---|---|---|---|
| `non_participant_entry` | `privacy_critical` | Required | `retained_region_cleared` |
| `privacy_boundary_breach` | `privacy_critical` | Required | `privacy_boundary_restored` |
| `camera_movement` | `privacy_critical` | Required | `camera_reverified` and `mask_reverified` |
| `mask_failure` | `privacy_critical` | Required | `mask_reverified` |
| `camera_stream_loss` | `operational` | Required when affected records are invalid or stale | `stream_recovered` |
| `esp_a1_loss` | `operational` | Required when affected fused windows are excluded | `node_recovered` |
| `esp_a2_loss` | `operational` | Required when affected fused windows are excluded | `node_recovered` |
| `storage_failure` | `operational` | Required when output integrity is uncertain | `storage_recovered` |
| `equipment_failure` | `operational` | Required when affected records are invalid | `equipment_recovered` |

The four privacy-critical types cannot be downgraded and cannot disable their deletion requirement. An operational incident may be escalated or marked for deletion when its affected interval cannot be considered valid.

## Fail-closed sequence
```text
Detect invalid state
-> refuse startup or pause the running session
-> create a schema-valid incident
-> isolate and exclude affected windows
-> complete required deletion
-> correct the cause
-> verify incident-specific recovery
-> resolve and resume, or abort
```

If an invalid state is detected before writers are started, preflight must be failed and `collection_refused` and `no_data_written` must be used where an incident record is required. A running manifest and ordinary collection output must not be created.

## Immediate response during a running session
1. Call lifecycle `pause()` with applicable incident type immediately
2. Shared pause/stop controller must stop every writer from accepting new records
3. Persist schema-v5 incident and atomically mark manifest `paused`
4. The timezone-aware SGT start time and available affected window IDs must be recorded; the pause must not be delayed while the final interval is calculated
5. `exclude_windows()` must be used to add every later-identified affected window
6. All affected windows must be kept unusable for modelling, evaluation and demonstration
7. Affected data must be isolated locally, and upload or external transfer must be prevented
The lifecycle records `collection_paused` and `affected_data_isolated`. `interval_excluded` is added when affected window IDs are present. If pause evidence cannot be persisted safely, the lifecycle stops writers and marks the session `aborted`.

## Required incident record
Every incident must record only the schema-approved fields:
- `schema_version` set to `5`
- Unique incident and session IDs
- Zone A and one supported incident type
- Severity and open/resolved status
- SGT start/end and resumed timestamps
- Unique affected window IDs
- Approved action values
- Deletion required/completed state and deletion completion time
- Recovery verification state
- Operator role `student_researcher`
Free-text identity fields and additional properties must not be added. Incident JSON must be stored under the lifecycle-owned local incident directory and validated before it is used as acceptance evidence.

## Exclusion and deletion
- Complete interval must be excluded from earliest plausible invalid state until verified recovery
- When timing is uncertain, use wider interval
- Excluded windows must be treated as unusable even when some modalities remained available
- Atomically delete any already-written numerical rows belonging to an excluded window and reject later writes into that window
- It must be verified that affected window IDs are absent from every lifecycle-owned writer before recording required deletion as complete
- Customer-affected, mask-failure and other privacy-invalid material must be isolated and deleted as soon as identified
- Operationally invalid records must be deleted when incident is marked as requiring deletion
- Deletion must be recorded using IDs, SGT time, data category and operator role only
- Prohibited content must never be retained merely to prove that deletion occurred
- Raw/masked video, raw audio or excluded material must never be uploaded to Firebase, cloud notebooks or messaging services

## Incident-specific recovery checks
### Non-participant entry
- It must be confirmed that retained region contains only eligible consenting Counter Agents
- Affected-data deletion must be completed
- `retained_region_cleared` must be recorded

### Privacy-boundary breach
- Approved physical and masked boundary must be restored
- Affected-data deletion must be completed
- Masked-only view must be inspected
- `privacy_boundary_restored` must be recorded

### Camera movement
- Collection must be kept paused, and the existing mask must be treated as unverified
- The fixed camera position must be restored or formally accepted
- Reopen masked-only preview and recheck every retained boundary
- Save/confirm appropriate verified mask version
- Affected-data deletion must be completed
- Both `camera_reverified` and `mask_reverified` must be recorded

### Mask failure
- The mask configuration or processing failure must be corrected
- Revalidate camera identity, 1920x1080 resolution, geometry and retained area
- It must be confirmed that masking is applied before all downstream processing
- Affected-data deletion must be completed
- `mask_reverified` must be recorded

### Camera stream loss
- It must be confirmed that no stale frame was accepted as current
- Local video-only H264 path must be restored with no audio
- Camera identity, mode and mask state must be rechecked
- `stream_recovered` must be recorded

### ESP-A1 or ESP-A2 loss
- It must be confirmed that affected node has returned with correct identity and schema
- Fresh sequence, boot and receive-time behaviour must be confirmed
- It must be confirmed that independent operation of the other node and Camera A was maintained
- Explicit missingness must be preserved for affected windows
- `node_recovered` must be recorded

### Storage failure
- New writes must be stopped until approved local storage is writable and has sufficient capacity
- Existing outputs and writer accounting must be verified; the session must be aborted if integrity is uncertain
- `storage_recovered` must be recorded

### Equipment failure
- Make equipment and cable state physically safe
- Every affected placement, calibration, camera/mask or health check must be repeated
- `equipment_recovered` must be recorded

## Resume gate
Call lifecycle `resume()` only when:
- Every required recovery action for incident type has been verified
- All affected window IDs are excluded
- Required isolation and deletion are complete
- Manifest remains valid and paused
- Every writer can resume safely
- The approved Zone A state can be confirmed manually without relying on participant or customer identity information
When deletion is required, call recovery with `deletion_completed=True`. The lifecycle then records `affected_data_deleted`, the deletion timestamp, `recovery_verified: true`, the resolved SGT time and the resumed SGT time.

## Abort and stop rules
The session must be aborted instead of resumed if:
- Cause or affected interval cannot be established confidently
- Required deletion cannot be completed
- Required camera/mask or equipment recovery cannot be verified
- A writer cannot apply an exclusion or resume safely
- Incident or manifest evidence cannot be persisted
- Output integrity is uncertain
When a paused session with an open incident is aborted, the incident must be retained as open and the approved action `session_aborted` must be added; recovery and deletion evidence must not be invented. A session must not be marked completed while an incident is open. On clean stop, all writers must be closed through the lifecycle controller, and valid file, observed, written, excluded-record and gap accounting must be reported. An `aborted` manifest is kept unusable until reviewed and resolved under the approved data-handling rules.

## Post-session review
- Every incident ID linked from the manifest must be reviewed
- It must be confirmed that incident files are validated against schema version 5
- It must be confirmed that excluded windows cannot be included in annotations, training or evaluation
- It must be confirmed that every required deletion is complete and timestamped
- Final manifest status and writer-owned accounting must be confirmed
- `docs/data_collection/post_session_checklist.md` must be completed
- Only non-identifying summaries must be included in Phase 8 or assessment evidence
This procedure does not authorise participant collection. Phase 8 must finish with an explicit GO decision before participant sessions begin.