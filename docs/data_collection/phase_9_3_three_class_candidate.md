# Phase 9.3 Three-Class Method

> **Historical status:** The ACTIVE designation below applied under v5 during the completed collection period. Participant collection closed on 10 August 2026; no new pilot or participant sessions are authorised. The original methodology and approval record are retained.

## Status
**ACTIVE — confirmed in Ethics Pack Version 4.4 and frozen by `zone-a-collection-v5`.**
The merger of the two visually similar labels `Serving` and `Typing/Processing` was approved as a research decision. The resulting three-class methodology is recorded in Ethics Pack Version 4.4. The required confirmation, issue and participant acknowledgement were reported as recorded under approved secure controls on 4 August 2026. The implementation is frozen by the fully hashed `zone-a-collection-v5` profile.

## Active classes
1. `Serving/Processing`
2. `Idle/Waiting`
3. `Reaching/Handling`
These three choices are presented independently on each participant card in the live annotation interface. A card can be added during a running session only after a valid unused pseudonym and explicit consent confirmation are supplied, with a timestamped manifest audit entry. Schema version 3 is used for new annotations and predictions; schema version 8 is used for new manifests.

## Historical data mapping
Historical schema-version-2 records are preserved without modification. A
derived three-class dataset is produced using this deterministic mapping:
| Historical label | Candidate label |
|---|---|
| `Serving` | `Serving/Processing` |
| `Typing/Processing` | `Serving/Processing` |
| `Idle/Waiting` | `Idle/Waiting` |
| `Reaching/Handling` | `Reaching/Handling` |

The mapping is implemented in `src/aria/collection/activity_labels.py`. Historical schemas remain available as `schemas/annotation.v2.schema.json` and `schemas/prediction.v2.schema.json`.

## Activation record
The Version 5 activation gate was completed on 4 August 2026:
- Three-class definition is incorporated into Ethics Pack Version 4.4
- Participant-facing material was generated, visually verified, issued and acknowledged under approved secure controls
- v5 settings and artifacts are frozen under a new profile checksum
- Every intended session remains subject to a fresh pre-session and masked-preview acceptance check against v5
The historical v4 artifact verification remains failed after the method change, preventing an accidental formal run with mixed label definitions.