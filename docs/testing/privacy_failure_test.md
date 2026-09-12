# Zone A Privacy-Failure and Recovery Test
## Status
**Phase 8.2 complete — Pass.** The dated consolidation record is `docs/testing/results/2026-08-02_phase_8_2_privacy_failure_recovery.md`.

## Purpose
It must be verified that the single-camera Zone A deployment stops, refuses to start, or excludes affected data when camera placement, masking, consent or stream integrity no longer satisfies the approved privacy controls.
Non-research test conditions must be used for deliberate failure scenarios. Customers, non-participating staff, real documents, payment screens and other sensitive information must not be placed in test footage.

## Active scope
- One DJI Osmo Action 5 Pro identified as `camera_a`
- One verified mask retaining only the approved Zone A staff-side region
- Only supporting numerical telemetry is provided by ESP-A1 and ESP-A2
- No Camera B, Zone B or Zone T collection

## Failure scenarios
| Scenario | Expected response |
|---|---|
| Mask configuration missing | Pipeline refuses to start |
| Mask marked unverified | Participant collection refuses to start |
| Mask coordinates outside 1920x1080 | Configuration is rejected |
| Retained area empty | Configuration is rejected |
| Camera identity is not `camera_a` | Deployment diagnostic is rejected |
| Camera resolution differs from 1920x1080 | Camera diagnostic fails |
| DJI camera is moved after verification | Collection pauses; mask is reverified |
| Customer-facing or sensitive area enters mask | Affected interval is excluded and deleted |
| Non-participating staff enters retained region | Collection pauses or affected interval is excluded |
| DJI/MediaMTX stream drops | Gap is logged; no stale frame is treated as current |
| Masking fails during processing | Unmasked frame is not stored or uploaded |

## Procedure
1. It must be confirmed that the valid `camera_a` configuration starts with approved non-research test footage
2. One failure scenario must be triggered at a time
3. The exact SGT time, triggering condition and observed system response must be recorded
4. It must be verified that no unmasked frame is written to persistent storage
5. It must be verified that no raw or masked video is sent to Firebase or a cloud notebook
6. The valid configuration must be restored
7. Camera identity, 1920x1080 mode, final position and mask coordinates must be rechecked
8. A new mask verification must be required before collection is resumed after movement or mask failure
9. It must be confirmed that the incident/exclusion record identifies the affected interval without including participant or customer identities

## Acceptance criteria
- Every invalid startup configuration is rejected
- Movement or privacy-boundary failure causes an immediate pause or exclusion
- No affected frame is used for annotation, training or evaluation
- Affected local video is deleted according to the incident procedure
- The correct DJI Camera A identity and a reverified mask are required for recovery
- ESP-A1 and ESP-A2 telemetry may continue for diagnostics, but it must not be fused with excluded camera intervals as valid participant data
- No raw audio, raw video or masked video reaches Firebase or cloud notebooks

## Result record
| Scenario | Pass/Fail | Evidence | Recovery verified |
|---|---|---|---|
| Missing mask | Pass | `test_missing_configuration_is_rejected` | Valid mask restored |
| Unverified mask | Pass | Unit test plus two live fail-closed runs before and after movement; no output files created | Final-position mask reverified |
| Invalid coordinates | Pass | Invalid geometry and out-of-bounds unit tests | Valid coordinates restored |
| Empty retained area | Pass | `test_empty_mask_is_rejected` | Non-empty retained region restored |
| Wrong camera identity | Pass | Privacy-mask and deployment-camera unit tests | `camera_a` retained |
| Wrong resolution | Pass | `test_wrong_resolution_is_rejected` | 1920×1080 retained |
| Camera moved | Pass | Collection remained blocked after deliberate movement | Final position reviewed in masked-only preview and reverified |
| Privacy boundary breached | Procedural pass | All final retained boundaries were reviewed manually; a real breach was not staged | Stop/exclude/delete procedure retained |
| Non-participant enters | Procedural pass | No non-participant was deliberately exposed to the retained view | Stop/exclude procedure retained |
| Stream drop | Pass | Phase 3.4 controlled publisher interruption and recovery record | Video-only stream recovered |
| Runtime masking failure | Pass | Unit test verifies no detection or output occurs when masking raises | Valid verified mask restored |

Final result: **Pass for the Phase 4.4 and Phase 8.2 configuration, movement, fail-closed, live failure and recovery scenarios.** Privacy-boundary and non-participant controls remain mandatory operational checks for every collection interval; they were not staged using real non-participants.