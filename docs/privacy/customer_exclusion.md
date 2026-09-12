# Customer and Non-Participant Exclusion Procedure
## Purpose and operating context
Customers are not permitted behind the service counter. Only the behind-counter staff workspace is retained by the approved `camera_a` configuration, so ordinary customer presence in the public-facing area outside the retained mask is expected and is not an incident.
Staff who enter the retained region during authorised participant collection are expected to be consenting Counter Agents who have received Ethics Pack Version 4.4 and completed the required acknowledgement. Their ordinary entry does not require exclusion. ARIA does not infer or record employment roles.
This procedure is a fail-safe contingency for an unexpected customer or other person outside the approved participant scope entering the retained region, or for customer-facing information becoming visible because the physical or software privacy boundary fails.

## What is not an incident
- Customer remains in normal public area outside retained mask
- Consenting Counter Agent enters or leaves retained staff workspace
- Normal activity occurs entirely inside verified staff-side region
- Person is visible only in an unretained area that is blacked out before display, detection, tracking, pose estimation or feature output
Customer observations, counts, descriptions or identity records must not be created for these ordinary conditions.

## Exclusion triggers
Collection must be paused or refused when any of the following conditions are observed:
- Customer crosses into behind-counter retained region
- Any person outside approved participant scope enters retained region
- Camera movement, mask failure or incorrect framing exposes a customer-facing or public area
- Payment area, customer document, private screen or other sensitive surface enters retained region
- The presence of participants only in the retained view cannot be confirmed manually
`non_participant_entry` must be used when the retained region is physically entered by a customer or other non-participant. `privacy_boundary_breach` must be used when a customer-facing or sensitive area is exposed through framing, masking or the environment without the approved staff workspace being entered by the person.
Both incident types are privacy-critical. They cannot be downgraded and always require deletion of affected retained data before recovery.

## Immediate response
1. The lifecycle must be paused immediately; if writers have not been started, collection must be refused and no participant output may be created
2. Incident start must be noted using system's timezone-aware SGT clock
3. A schema-version-5 incident must be opened with no name, appearance description, customer detail, employee detail or free-text identity information
4. Identify every affected multimodal-window ID conservatively - include whole uncertain interval rather than shortening it to preserve data
5. Call `exclude_windows()` so affected records remain unusable for annotation, modelling, evaluation and demonstration
6. Affected local records and any permitted temporary masked video must be isolated
7. A screenshot must not be captured, and identifying material must not be copied into a log, incident record, filename or evidence document

## Isolation and deletion
- Every affected window must be treated as invalid even if its numerical features appear usable
- An affected interval must never be moved back into the usable dataset to improve duration or class balance
- Affected temporary video and privacy-invalid derived records must be deleted as soon as they are identified
- Only incident ID, session ID, affected window IDs, SGT deletion time and operator role must be recorded
- An image, name, physical description or reason for a customer's presence must not be retained as deletion evidence
- `docs/privacy/retention_schedule.md` and `docs/privacy/data_handling.md` must be followed

## Recovery after non-participant entry
For `non_participant_entry`:
1. It must be confirmed that customer or other non-participant has left retained region
2. It must be confirmed that only eligible consenting Counter Agents remain in retained workspace
3. It must be confirmed that affected windows are excluded and required deletion is complete
4. Required recovery action `retained_region_cleared` must be recorded
5. It must be verified that camera position, resolution and mask status have not changed
6. Collection may be resumed only through the lifecycle controller with verified recovery and `deletion_completed=True`

## Recovery after a privacy-boundary breach
For `privacy_boundary_breach`:
1. The exposed sensitive surface must be removed or covered, or the physical boundary must be restored
2. If Camera A has been moved or the mask has become invalid, collection must be kept paused and the camera/mask reverification procedure must be followed before continuation
3. It must be confirmed that affected windows are excluded and required deletion is complete
4. Required recovery action `privacy_boundary_restored` plus any additional camera or mask recovery evidence that applies must be recorded
5. Inspect masked-only view and confirm all public/customer-facing areas are again excluded
6. Collection may be resumed only through the lifecycle controller with verified recovery and `deletion_completed=True`

## Abort conditions
The session must be aborted instead of resumed if
- Affected interval cannot be bounded confidently
- Required deletion cannot be completed or evidenced
- Retained region cannot be confirmed clear
- Camera or mask validity is uncertain
- Incident evidence cannot be written and validated safely
An aborted or unresolved session must not be treated as completed participant data. Complete the post-session checklist and review all local outputs before reuse or deletion.

## Related controls
- `docs/privacy/privacy_incident_procedure.md`
- `docs/privacy/masking_procedure.md`
- `docs/data_collection/session_protocol.md`
- `docs/data_collection/pre_session_checklist.md`
- `docs/data_collection/post_session_checklist.md`
- `schemas/incident.schema.json`
This procedure does not authorise participant collection. Phase 8 must finish with an explicit GO decision before participant sessions begin.