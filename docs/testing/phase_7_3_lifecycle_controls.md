# Phase 7.3 Lifecycle-Control Evidence
## Status
**Complete**  
Date: 1 August 2026
Deterministic software coverage for pause, exclusion, incident linkage, verified recovery and clean stop has been established for Phase 7.3. The same controls were subsequently exercised in the completed Phase 7.4 non-research dry run.

## Implemented controls
- The shared `PauseStopController` is received by every writer through its `WriterContext`
- `StartedSession.pause()` immediately sets the shared pause signal and writes a schema-valid, non-identifying incident linked from the paused manifest
- Lifecycle-created privacy-critical incidents cannot be downgraded or configured to bypass required deletion.
- `exclude_windows()` records affected multimodal-window IDs, atomically deletes matching persisted rows, blocks later matching writes and verifies their absence while collection remains paused.
- `resume()` requires at least one schema-approved recovery action. It refuses privacy-critical recovery until required deletion is recorded complete.
- `stop()` closes every writer before atomically completing the manifest
- Every writer's relative local file path, observed, written and excluded record counts, gap count and longest gap are recorded in a completed manifest
- The Phase 7.3 accounting contract was accepted in session-manifest schema version 3 and is preserved here as historical evidence. Schema version 5 is used for the active formal collection contract; the frozen collection profile ID and SHA-256 hash were introduced in version 4, and the superseding v3 profile is identified by version 5. The lifecycle accounting rules below are unchanged, and `observed = written + excluded` is required; earlier manifests are rejected.
- Explicit retained-region, privacy-boundary or equipment recovery actions are required where applicable by incident schema version 5, and privacy-critical severity or deletion requirements are prevented from being downgraded. Earlier versions are rejected.
- An `aborted` manifest is produced after writer-close or final-accounting failure; a false `completed` result is never produced
- Final accounting is obtained only from the started writer handles; caller- supplied summaries are not accepted

## Automated evidence
Command:
```bash
PYTHONPATH=src python3 -m pytest tests/unit -q
```
Current regression result after the SGT, exclusion and accounting migration: **245 passed**. Fourteen existing third-party Matplotlib/pyparsing deprecation warnings were reported; no project test failed.
The following are included in focused collection and schema coverage:
- Unusable pause-controller startup rejection;
- Privacy and operational pause paths;
- Affected-window exclusion and incident persistence;
- Deletion-gated verified recovery;
- Clean writer shutdown and completed-manifest accounting;
- Refusal to stop with an unresolved incident;
- Writer-close failure and invalid-accounting abort paths; and
- Rejection of unsafe or duplicate output paths, negative counts and any
  summary where observed does not equal written plus excluded.

## Review-defect regression checks
The four defects found during the collection-package audit are fixed and have dedicated regression coverage:
- Recovery actions must match the incident type;
- The persisted deletion requirement is kept canonical after failed writer exclusion;
- Stop-time clock failure occurs before writers or the controller are stopped; and
- A reported writer output must resolve to an existing local file beneath the approved output root.

## Final review status
During the completion review, all identified lifecycle contract defects were confirmed as fixed with regression coverage:
- Privacy-critical incident severity and deletion requirements are enforced by both lifecycle code and incident schema version 5;
- Completed deletion must be recorded for resolved privacy incidents;
- Final accounting is obtained only from writer-owned `session_summary()` results;
- Existing incident evidence cannot be overwritten through duplicate incident IDs;
- An open incident cannot be resolved through a tampered non-paused manifest;
- Callable pause, resume and stop methods must be implemented by pause/stop controllers; and
- Writer outputs must be stored beneath the session root with unique paths, and internally consistent counts must be reported
Phase 7.3 is **Complete**. The same lifecycle was exercised in Phase 7.4 with the real Zone A components in an empty/researcher-only scene on 1 August 2026.