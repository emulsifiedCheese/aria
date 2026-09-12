# ARIA Privacy Masking Procedure
## Purpose
A fail-closed privacy mask is applied before any frame is used for detection, tracking, pose extraction, visualisation or temporary storage. Only the approved staff-side region is retained. Everything outside that region is replaced with black pixels.

## Processing order
```text
Camera frame
→ validate camera identity
→ validate frame resolution
→ validate mask configuration
→ apply privacy mask
→ detection
→ tracking
→ pose extraction
→ temporary masked storage where required
```
Raw unmasked frames must not be passed to later pipeline stages.

## Configuration
The active deployment mask is stored in:
```text
config/masks.batamfast.yaml
```
`config/masks.example.yaml` is an unverified template. The full-frame `config/masks.development.yaml` is permitted only for non-research test video
and must never be supplied to a pilot or participant session.
Each camera requires:
- `camera_id`
- `mask_config_version`
- `expected_width`
- `expected_height`
- `x`
- `y`
- `width`
- `height`
- `excluded_polygons` (optional list of three-or-more-point polygons)
- `verified`
The rectangular coordinates define the base retained region. Optional exclusion polygons black out additional areas inside that region. Each polygon point is an `[x, y]` pixel coordinate for the configured frame resolution.

## Fail-closed conditions
The system must refuse to continue when:
- Mask configuration is missing
- Camera identity does not match configuration
- Frame resolution differs from configured resolution
- Retained width or height is zero or negative
- Mask coordinates fall outside frame
- Retained region extends beyond frame boundary
- An exclusion polygon has fewer than three points, zero area, or a point outside frame
- `verified` is `false`
For pilot and participant sessions, the mask must also be the approved `camera_a` deployment configuration and version. A geometrically valid development or example mask is not collection authority.

## Development-mask boundary
The masking code and validation tests can be completed without the deployment camera using non-research test video only. The final values for `x`, `y`, `width`, and `height` must be set only after viewing the real camera feed in its final mounting position. Until live-site verification is complete, the deployment mask must remain:
```yaml
verified: false
```

## Verification procedure at the deployment site
1. Mount camera in its intended final position
2. The final capture resolution must be set
3. A live preview must be displayed
4. Retained rectangle and exclusion polygons must be adjusted so only approved staff-side zone remains visible
5. It must be confirmed that customer-facing regions are fully excluded
6. It must be confirmed that retained region is not empty
7. Normal staff movement must be tested at edges of retained zone
8. Final coordinates must be recorded
9. `verified: true` must be set
10. Privacy mask unit tests and the camera diagnostic must be run again

## Failure handling during collection
If the mask fails, shifts, exposes an unintended area, or no longer matches configured resolution:
1. Call Phase 7.3 lifecycle `pause()` immediately using `mask_failure` or `camera_movement`, as applicable
2. The shared pause signal must be kept active so that no further records are admitted as usable data
3. Link every affected multimodal-window ID through `exclude_windows()` and record schema-valid privacy incident
4. Every affected copy and derivative must be isolated and deleted under `docs/privacy/privacy_incident_procedure.md`
5. The documented physical position must be restored where necessary, only the masked preview must be inspected, geometry must be corrected, and a new mask version must be assigned whenever the accepted geometry is changed
6. Re-run mask, camera-mode and video-only checks - camera movement requires both `camera_reverified` and `mask_reverified`; a mask failure requires `mask_reverified`
7. Resume only through lifecycle controller after required deletion is confirmed and every incident-specific recovery action is verified
8. Session must be aborted if exclusion, deletion or safe recovery cannot be completed - an aborted or unresolved session is unusable