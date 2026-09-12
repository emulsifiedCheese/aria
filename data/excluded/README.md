# Excluded data quarantine
## Purpose
This directory is designated as a temporary local quarantine for Zone A files that must be isolated while exclusion and deletion are completed. It is not an archive, dataset, evidence store, annotation source or backup location. Only this README is expected to be retained in the steady state.

Ordinary customer presence outside the approved retained camera region is not a privacy incident. Customers are not permitted behind the counters. If a customer, non-participant or other out-of-scope person nevertheless enters the retained region, or if the privacy boundary or mask fails, collection must be paused and the affected interval excluded and deleted under `docs/privacy/privacy_incident_procedure.md`.

## What may be placed here temporarily
Only the minimum affected local files needed to complete controlled deletion may be quarantined here. Examples include a session fragment linked to a privacy incident, an invalid capture produced during a mask failure, or a file from an aborted collection session.

This directory must not be used to retain:
- Customer-identifiable or non-participant footage longer than necessary for deletion
- Raw audio or intelligible speech
- Unmasked participant footage as a permanent record
- Copies kept for model training, evaluation, demonstrations or troubleshooting
- Files awaiting later reconsideration for inclusion
Canonical privacy-incident records belong under `data/raw/incidents/` and must validate against `schemas/incident.schema.json`. Moving affected material here does not replace the incident record, window exclusion or deletion confirmation.

## Exclusion and deletion workflow
1. Collection must be paused or refused as soon as an incident or invalid interval is identified
2. The linked privacy-incident record must be created or updated, and the affected session and window IDs must be identified without a person's identity being recorded
3. Every affected annotation/window must be marked as non-usable using applicable schema-defined exclusion reason
4. Only minimum affected local files must be isolated in this directory if immediate deletion from source location is not possible
5. All affected copies must be deleted from capture, interim, processed, cache, export and quarantine locations. They must not be uploaded to Firebase, cloud notebooks or other cloud storage
6. Incident record's deletion and recovery fields, including `affected_data_deleted`, `deletion_completed` and any required safe-resumption action must be completed
7. Collection may be resumed only when the recovery conditions in the incident procedure are satisfied; otherwise, the session must be aborted
Operational records may refer only to pseudonymous incident, session and window identifiers, SGT timestamps, data category and operator role. They must not contain names, employee identifiers, images, customer descriptions or other identifying narrative.

## Rules for quarantined material
- Quarantined content is excluded immediately and is never usable for modelling
- It must not be annotated, sampled, transformed, restored, shared or copied into another dataset
- Deletion covers every duplicate and derivative, not merely the file in this directory
- Completion must be documented in the incident record using non-identifying metadata; prohibited material must not be retained as proof
- If deletion cannot be confirmed, the incident remains unresolved and collection must not resume on the assumption that quarantine is sufficient
Generated contents of `data/excluded/` are excluded by `.gitignore`, while this README is retained. Ignore rules are only a safeguard: they do not authorise retention and do not prove that a file was deleted from all locations.