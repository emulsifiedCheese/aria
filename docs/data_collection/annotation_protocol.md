# Zone A Role-Neutral Annotation Protocol
## Purpose and scope
Activity labels for consenting Counter Agents in the approved Zone A retained camera region are defined in this protocol. Its application is restricted to valid, pseudonymised sessions using `camera_a`, ESP-A1 and ESP-A2.

Station Manager roles, employment roles, customers, non-participants, Zone B, Zone T, a second camera, ESP-B and ESP-T must not be annotated. An interval must be excluded rather than an identity or activity being inferred outside the approved scope.

## Privacy rules
- Pseudonymised participant IDs matching `P0000`-style codes must be used
- The participant-code key must be kept outside this repository and research dataset
- Only camera-local track IDs must be used; they are not designated as persistent identities
- Only approved masked staff-zone view and numerical features must be reviewed
- Names, employee numbers, exact shifts, customer details, intelligible speech, raw audio or unmasked imagery must never be recorded
- Every interval affected by a non-participant, privacy incident, mask failure or prohibited surface must be marked as excluded and unusable for modelling

## Annotation unit
One camera-local track is described by each record over one or more consecutive
multimodal windows. The following must be recorded:
- Versioned session, annotation and window identifiers
- Pseudonymised participant ID and camera-local track ID
- Timezone-aware SGT start and end timestamps
- One label status and, when valid, one approved activity
- An explicit exclusion reason for every uncertain or excluded record
- A pseudonymised annotator ID

Track IDs may be changed after full exit and re-entry. Appearance, biometrics and personal knowledge must not be used to join tracks. An annotation must be split when track, activity, validity or exclusion state changes.
During live observation, the camera-local track ID must be read only from the localhost masked preview produced by the manifest-owned camera writer. One tracker instance is shared by that preview and the JSONL writer. Unrelated or absent IDs are provided by the separate mask alignment preview and any second CV process; these sources must not be used for annotation. An interval boundary must be recorded immediately when the displayed local track ID is changed, even if the same pseudonymised participant is believed by the observer to be present.
Under the historical pilot and participant procedure, the annotation controls on that same localhost preview were required. A persistent card is provided for each manifest participant, with a current-track selection, activity buttons, uncertainty/exclusion controls, active state and end control. The participant's current visible track must be selected within the card, followed by the dominant activity; clock timestamps must not be transcribed manually. Each click is aligned by the local server to a two-second multimodal-window boundary. The participant's prior interval is closed and a new interval is started by a new activity or track selection. `End annotation` must be used when the participant leaves or no new label should be started. An interval shorter than one complete window is not accepted as a usable annotation and is not written.
At the desktop collection viewport, the complete masked display is retained on the left. The annotation heading, instructions, add-participant control and notice are displayed below it. The independently scrolling participant-card grid is positioned at the top right, so activity controls can be used without the masked display being scrolled out of view. A single stacked column is used on narrow screens.
Status updates are received by the browser once per second. Under the active v7 interface, a manual track draft and its keyboard focus are preserved while it is edited, and the selected activity is kept highlighted across ordinary polls. Card rendering is resumed immediately when an activity is clicked. The lifecycle writer is not overridden by this UI persistence: when a track is absent for a complete two-second window, the annotation is still closed and the explicit replacement-track warning is shown, with the previous activity retained for reference.
Under the historical procedure, `Add consenting participant` was required when an additional consenting Counter Agent arrived during a running session. Only the assigned `P0000`-style pseudonym may be entered, and the consent confirmation must be selected before the card is created. Duplicate or malformed IDs are rejected by the control, and the addition time and annotator pseudonym are recorded in the session manifest. Consent is not established by the control: consent and acknowledgement must be verified manually before it is used. For a non-participant or anyone whose consent cannot be confirmed, the pause, exclusion and privacy-incident procedure must be followed instead of a card being created.
Numerical track presence is monitored by the lifecycle writer across completed two-second windows. An annotation is not split because of a missed frame alone. If the selected track is absent from every processed frame in a complete window, the annotation is closed before that window and a replacement prompt is displayed inside that participant's card. The participant's new visible track must be selected, followed by the current activity or `Continue previous activity` when it is still correct. A replacement track is never selected and identity is never asserted automatically by the control.

## Approved activity labels
| Label | Apply when observable dominant activity is | Do not infer |
|---|---|---|
| `Serving/Processing` | directly attending to a service interaction, operating the workstation, or processing a transaction/task | customer identity, conversation content, screen contents, payment details, typed information or employment role |
| `Idle/Waiting` | remaining available without an observable processing or handling action | motivation, attentiveness or role seniority |
| `Reaching/Handling` | reaching for, moving or handling approved work items | document contents, ownership or customer identity |

The dominant activity in the interval must be selected. If no single approved label is defensible, `uncertain` must be used with `ambiguous_activity`; a new class must not be created during collection.

## Label status and usability
| Status | Activity value | Exclusion reason | Usable for modelling |
|---|---|---|---|
| `labelled` | exactly one approved activity | `null` | `true` |
| `uncertain` | approved activity or `null` | required | `false` |
| `excluded` | `null` | required | `false` |

Permitted non-usable reasons are:
- `ambiguous_activity`
- `occluded_pose`
- `missing_modality`
- `non_participant`
- `privacy_incident`
- `mask_failure`
- `stream_gap`
- `equipment_failure`
- `outside_approved_scope`

## Boundary and quality procedure
1. It must be confirmed that session manifest is valid and interval is not already excluded by an incident record
2. Start of a stable observable activity must be located on a multimodal-window boundary
3. The annotation must be continued through consecutive windows while track, activity and validity remain unchanged
4. Annotation must be ended before an activity transition, track change, data gap or exclusion interval
5. Record must be validated against `schemas/annotation.schema.json`
6. Disagreements must be resolved through a second review of the masked view and numerical evidence. If a disagreement remains unresolved, the interval must be kept uncertain
Records are validated by the lifecycle-owned writer before they are appended to the session's local `annotations.jsonl`. Active annotations are closed and new input is disabled during a pause. Any annotation containing an affected window is removed through incident exclusion rather than a partially trusted interval being retained. Remaining active annotations are closed during a clean session stop, and annotation file/count accounting is included in the final manifest.
An uncertain or excluded interval must never be changed to usable merely to improve class balance.

## Schema and version control
Schema version 3 is used for annotation records. A new schema/protocol version and a documented dataset rebuild are required for any change to labels, required fields, privacy rules or boundary rules. Schema-valid records are required, but the session manifest, incident log and exclusion decisions are not overridden by schema validity. Schema-version-2 records are retained as immutable historical source data. For a derived three-class dataset, both `Serving` and `Typing/Processing` must be mapped to `Serving/Processing`; `Idle/Waiting` and `Reaching/Handling` must be retained unchanged. The transformation must be recorded and the source records must be kept so that the mapping can be audited. Original JSONL files must not be relabelled or overwritten.