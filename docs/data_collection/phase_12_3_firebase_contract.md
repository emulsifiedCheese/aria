# ARIA Zone A Phase 12.3 Firebase contract
## Status and authority
**Contract ID:** `zone-a-phase12.3-firebase-v1`  
**Contract SHA-256:** `48e3cb907c7586e43dcf9bc956331408df557c739c2e1f581b55e30b2bbb2afb`  
**Date frozen:** 24 August 2026  
**Status:** Frozen before implementation; Phase 12.3 complete

The machine-readable authority is `config/phase_12_3_firebase.json`. Firebase Realtime Database project `aria-e906f`, Singapore region `asia-southeast1`, the non-identifying upload schema, restricted database rules, credential boundary, durable retry policy and acceptance matrix are pinned by this configuration.
Firebase integration is required for the final product. Firebase availability is not required for local inference or dashboard operation: an approved record must be queued locally during cloud failure, and a Phase 12.1 prediction must never be stopped, delayed or altered.
New participant collection and participant-data upload are not authorised by this contract. Only synthetic or approved non-research records are used for development and live cloud acceptance. Separate approval is required for runtime cloud retention and any later participant use.

## Frozen cloud boundary
The only permitted product is Firebase Realtime Database at:
`https://aria-e906f-default-rtdb.asia-southeast1.firebasedatabase.app`
`aria/schema_version_1/predictions/{prediction_id}` is used for version 1 prediction summaries. A separate ephemeral `aria/schema_version_1/acceptance/{acceptance_id}` path is provided only for the synthetic live write/read/delete acceptance check.
Firestore, Firebase Storage and Firebase Hosting are outside this contract. Raw or masked video, camera frames and raw audio therefore have no Firebase storage path.

## Permitted record
Only the following are permitted by `schemas/firebase_prediction.schema.json`:
- Opaque prediction ID
- Emitted and uploaded SGT timestamps
- Zone A
- Frozen model and preprocessing versions
- Prediction availability
- Activity and unchanged model confidence when available
- Fixed unavailable reason when unavailable
- Camera A, pose, ESP-A1 and ESP-A2 availability booleans
JSON properties whose values are `null` are removed by Realtime Database. `predicted_activity` and `confidence` are therefore omitted from the cloud schema for unavailable predictions, and `unavailable_reason` is omitted for available predictions.
Session ID, window ID, local track ID, participant identifiers, names, participant-code keys, roles, raw or derived feature vectors, network addresses, arbitrary exception text, audio and all video are rejected at the boundary. The historical proposal's feature-vector retraining loop is not implemented because the selected Camera-only model was frozen in Phase 11 and post-result tuning and cloud model-weight replacement are prohibited.

## Authentication and rules
Credentials are read only from the `ARIA_FIREBASE_CREDENTIALS` environment variable. The credential path and contents must not appear in configuration, logs, fixtures, documentation or version control.
`databaseAuthVariableOverride.uid` must be set to `aria-phase12-3-sync` by the Admin SDK. Only the required versioned paths are granted to that identity by `config/firebase_realtime_database.rules.json`. Prediction records are kept immutable: a new prediction ID may be created once; identical application retries are treated as delivered after a read-back match, while conflicting reuse of an ID is reported as an error.
The currently deployed database remains locked until the versioned rules pass emulator tests. Rules deployment and the live synthetic acceptance remain later acceptance steps.

## Offline and retry policy
Schema-valid records are placed in a durable local outbox under ignored `outputs/firebase_outbox/`. Delivery is performed oldest-first with bounded exponential backoff up to 60 seconds. A record is removed from the outbox only after verified delivery.
Inference and the dashboard must not be blocked by Firebase failure. The retry is completed idempotently when an identical remote record is found. Different content under the same prediction ID is rejected and kept available for local diagnosis without record contents or credentials being exposed in logs.

## Acceptance gate
Available and unavailable prediction delivery, local rejection of forbidden or invalid fields, identical and conflicting retries, offline queuing and recovery, continued inference and dashboard operation, denial of unauthorized database access, credential scanning and one synthetic live write/read/delete check are covered by acceptance.
No participant data or Phase 11 external-test data may be used. The live acceptance record must be deleted immediately after verification.

## Implemented local delivery boundary
The frozen contract and every pinned input hash are verified before use by `src/aria/cloud/firebase_sync.py`. Each complete local prediction is validated, only the schema-approved summary is projected, Realtime Database null fields are omitted, and the projected object is validated again. The source session ID, window ID and local track ID are never placed in the outbox.
One atomic JSON envelope is written per deterministic prediction ID by the outbox, the original queued payload is preserved across an identical local retry, records are scanned oldest-first, and the frozen bounded backoff is applied. The local record is removed after a successful Firebase transaction only when the remote result matches. A different remote value under the same ID is treated as an immutable conflict and kept queued.
Only projection and the durable local write are performed by `FirebasePredictionSync.on_prediction`; queue errors are contained and no network call is made. Local state is updated first by the dashboard integration, and the isolated callback is then invoked. Firebase transactions are performed separately by the retry worker or `scripts/sync_firebase_predictions.py`, so inference and dashboard state cannot be blocked by Firebase connection, authentication or transaction failures.
Both payload states, forbidden-field rejection, durable/idempotent queuing, verified removal, immutable conflicts, offline backoff and recovery, and continued inference/dashboard operation during a Firebase failure are covered by the focused local implementation tests.
All ten synthetic scenarios have now been passed by the Realtime Database Rules Emulator gate against the hash-pinned rules using the local-only `demo-aria-phase12-3` project. Valid available and unavailable records, unauthorized denial, immutable predictions, rejection of identifying/media/extra fields, conditional-field enforcement, frozen IDs/versions/classes/confidence, the synthetic-only acceptance path, immediate acceptance-record deletion and denial outside the versioned paths are verified by the gate. Evidence is recorded in `outputs/acceptance/phase_12_3/rules_emulator.json`. No live Firebase, participant data or external-test data was accessed.
The emulator-tested rules were deployed only to Realtime Database instance `aria-e906f-default-rtdb`. The rules syntax was accepted by Firebase and the rules were released successfully. No Hosting, Storage, Firestore, Functions or application data deployment was performed.
During guarded live acceptance, one four-field synthetic marker was written to the dedicated acceptance path, the exact marker was read back, the marker was deleted during cleanup, and its absence was verified. HTTP 401 with permission denied was returned for a separate unauthenticated live read. No participant identifier, participant data, external-test data, feature vector, audio or video was used or retained. Evidence is recorded in `outputs/acceptance/phase_12_3/live_firebase.json` and the aggregate `outputs/acceptance/phase_12_3/acceptance.json`.
All twelve frozen acceptance scenarios are now satisfied. Phase 12.3 is complete.