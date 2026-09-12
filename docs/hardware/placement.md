# ARIA Zone A Current Placement Specification
## Status and scope
The repeatable placement of the active ARIA deployment is defined in this document. It consolidates the accepted dated placement evidence without replacing those records.
Active components:
- ESP-A1 in Zone A with `A_PIR_US_MIC`
- ESP-A2 in Zone A with `A_PIR_MIC`
- One DJI Osmo Action 5 Pro identified as `camera_a`
ESP-B, ESP-T, Zone B, Zone T and a second camera are historical only and must not be installed or used for current collection. This specification contains no participant identity or participant-facing photograph.

## Authoritative evidence
- `docs/calibration/results/2026-07-30_zone_a_placement_record.md`
- `docs/calibration/results/2026-07-30_camera_a_placement_record.md`
- `docs/calibration/results/2026-07-31_camera_a_mask_calibration.md`
- `config/masks.batamfast.yaml`
If this summary conflicts with a newer dated acceptance record, the newer record controls and this document must be updated.

## ESP-A1 placement
| Item | Current specification |
|---|---|
| Fixed landmark | right half of staff-side counter, between fourth and fifth monitors |
| Height | approx 13 cm above counter surface |
| Mounting | freestanding on its side against a fixed counter edge on a stable staff-side surface |
| PIR direction | inward toward main staff workstation/service position |
| Microphone direction | inward toward staff working area and away from direct airflow or vibration |
| Ultrasonic direction | inward toward normal staff torso/chair position; never intentionally toward customers or a public route |
| Ultrasonic target conditions | no glass, angled, moving, soft or unstable target in intended path |
| Voltage divider | required between HC-SR04 ECHO and D6; insulated and inaccessible during normal operation |
| Power | USB from a staff-side desktop USB port |
| Cable route | along rear of counter behind monitors, secured with ties and clear of drawers, liquids, heat and moving equipment |

ESP-A1 must use local UDP port `4210` and must provide ultrasonic distance fields in addition to PIR and numerical-audio features.

## ESP-A2 placement
| Item | Current specification |
|---|---|
| Fixed landmark | left half of staff-side counter, between first and second monitors |
| Height | approx 13 cm above counter surface |
| Mounting | freestanding on its side on a stable staff-side surface using its enclosure/base |
| PIR direction | inward toward left staff workstation/service position |
| Microphone direction | inward toward staff working area and away from direct airflow or vibration |
| Ultrasonic sensor | absent; do not attach, configure or emulate one |
| Power | USB from a staff-side desktop USB port |
| Cable route | along rear of counter behind monitors, secured with ties and clear of drawers, liquids, heat and moving equipment |

ESP-A2 must use local UDP port `4211` and must omit `distance_cm` and `distance_valid` from its telemetry.

## Camera A placement
| Item | Current specification |
|---|---|
| Fixed landmark | right corner of staff-side front counter, immediately beside kiosk |
| Support | monopod with magnetic clamp tightened to kiosk |
| Lens-centre height | approx 1.2 m above counter surface |
| Orientation | diagonally downward toward staff work surface |
| Capture mode | 1920x1080 at approximately 30 FPS |
| Camera identity | `camera_a` only |
| Mask | `config/masks.batamfast.yaml`, version `batamfast-v2`, `verified: true` |
| Power and cables | camera battery; any charging cable follows fixed structure and remains clear of staff movement, customer access and equipment controls |

The retained masked view may include the approved staff work surface, keyboard/processing area, immediate staff standing position, torso, arms and short movement area behind the counter. It must exclude customers, public waiting areas, payment areas, customer documents and sensitive monitor content.

## Pre-session repeatability check
Before every Phase 8 test or later authorised session:
- It must be confirmed that both boards match their fixed monitor landmarks and approximate heights
- It must be confirmed that each board is stable and all cables remain secured
- It must be confirmed that ESP-A1 is still fitted with an insulated ultrasonic voltage divider and that its intended target path is clear;
- It must be confirmed that ESP-A2 still has no ultrasonic sensor
- It must be confirmed that camera clamp, height, orientation and 1920x1080 mode have not changed
- Load accepted mask and confirm `camera_a`, `batamfast-v2` and `verified: true`
- Inspect only masked preview and confirm no prohibited area is retained
- Any correction must be recorded in Phase 8 acceptance evidence before continuing

## Movement and change control
Any movement, remounting, rotation, height change, sensor-direction change, zoom change, resolution change or cable instability invalidates affected placement check.
- Collection must be paused or refused immediately
- Change must be recorded without participant or customer identity
- After ESP-A1 or ESP-A2 movement, affected sensor calibration and packet-health checks must be repeated before reuse
- After Camera A movement, the mask must be treated as unverified, the masked-only preview must be reopened, every retained boundary must be rechecked, and a new verified mask version must be saved before collection is resumed
- A new dated placement/calibration record rather than overwriting historical evidence must be created
- Link any affected windows to corresponding incident and complete required exclusion or deletion actions
Placement acceptance does not itself authorise participant collection. Phase 8 must finish with an explicit GO decision.