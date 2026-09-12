# Zone A annotations

> **Historical schema-v2 contract:** Participant collection was closed on 10 August 2026. The earlier record format and annotation procedure are retained below for traceability; new collection is not authorised by them. The schema appropriate to each retained record version must be used for current validation.

## Purpose and current status
This directory is reserved for pseudonymised Zone A activity-annotation records produced under the approved data-collection and annotation procedures. Only structured labels may be retained in this directory; raw audio, video, still images, names, employee identifiers, customer details and intelligible speech must never be stored here.
Generated annotation files are protected by a directory-wide rule in `.gitignore`, while this README remains visible. 
Only a version-control safeguard is provided by that rule: under the historical procedure, approved local storage, access, retention and sharing controls must be confirmed before the first participant annotation is written, and ignored content must never be treated as automatically safe.
The schema-version-2 record format and four-label vocabulary used during the earlier collection period are documented below as historical audit material. The current schema is version 3 in `schemas/annotation.schema.json`, and the three-class labelling procedure is defined in `docs/data_collection/annotation_protocol.md`. Historical source labels must remain unchanged.

## Eligible material
Only completed, approved Zone A sessions involving consenting Counter Agents may be annotated. The source material must already have been accepted through the session-manifest, privacy-mask and incident checks.

The following must not be annotated:
- Customers or any other non-participant;
- Station Manager roles or role attribution of any kind;
- Material from retired zones, cameras or sensor nodes;
- An aborted session as usable data;
- A window affected by an unresolved privacy, mask, stream or equipment incident; or
- Unmasked imagery, raw audio or intelligible speech.

Camera-local track IDs are temporary tracking references, not identities. They must not be used for biometric identification or linked to a person's real identity.

## Record format
Annotations must be stored as UTF-8 JSON Lines with one complete JSON object per line. A suitable local filename is `<session_id>_annotations_v2.jsonl`. Names or staff identifiers must not be used in filenames.

Under this historical contract, every record was required to be validated against the then-current version 2 of `schemas/annotation.schema.json`, with the following included:
- `schema_version`, `annotation_id` and `session_id`;
- `zone`, which must be `A`;
- Pseudonymous `participant_id` and camera-local `local_track_id`;
- One or more `window_ids`;
- `interval_start_sgt` and `interval_end_sgt` in SGT;
- `label_status`, `activity`, `exclusion_reason` and `usable_for_modelling`;
- Pseudonymous `annotator_id`; and
- `created_at_sgt`.

The following four activity labels were approved under the historical schema-v2 contract:
- `Serving`
- `Typing/Processing`
- `Idle/Waiting`
- `Reaching/Handling`

The status fields must be internally consistent:
| `label_status` | `activity` | `exclusion_reason` | `usable_for_modelling` |
| --- | --- | --- | --- |
| `labelled` | one approved activity | `null` | `true` |
| `uncertain` | approved activity or `null`, as permitted by the schema | required | `false` |
| `excluded` | `null` | required | `false` |

Only these exclusion reasons must be used:
- `ambiguous_activity`
- `occluded_pose`
- `missing_modality`
- `non_participant`
- `privacy_incident`
- `mask_failure`
- `stream_gap`
- `equipment_failure`
- `outside_approved_scope`

## Annotation procedure
1. It must be confirmed that session manifest is complete, approved privacy mask was active and any linked incident records have been resolved
2. Only approved masked staff region and permitted numerical sensor features must be reviewed
3. Records must be split whenever activity, local track, validity or exclusion state changes. A label must not be stretched across a transition merely to create longer or more balanced samples
4. Ambiguous material must be marked as `uncertain`; labels must not be guessed. If a disagreement cannot be resolved by reviewers, the material must be retained as non-usable
5. Affected material must be marked as `excluded` when it is outside the approved scope or is affected by privacy, mask, modality, stream or equipment problems
6. Every output file must be validated against the schema appropriate to its recorded version before it is admitted to downstream processing; the historical version 2 contract must not be confused with the current version 3 of `schemas/annotation.schema.json`

## Privacy and handling
Names, employee numbers, exact shift details, customer descriptions and other information that could identify a person must not be included in annotation text or free-form notes. Imagery and audio must not be copied into this directory. Annotation files must not be uploaded to public repositories, shared notebooks or unapproved cloud services.
Only schema-valid records marked `labelled` and `usable_for_modelling: true` may proceed to model preparation. Records marked `uncertain` or `excluded` remain non-usable and must never be reintroduced for class balancing, demonstrations or evaluation.