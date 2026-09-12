# ESP-T — Transition Zone Sensor Node
## Retirement status
**ESP-T and Zone T have been retired from the active ARIA deployment as of 29 July 2026.** This node must not be built, flashed or deployed for current tests, and its telemetry must not be expected. Only `ESP-A1` and `ESP-A2` are accepted by the UDP receiver; ESP-T packets are rejected.
This directory and the technical information below are retained for historical reference only.

## Purpose
ESP-T was designated as the ARIA sensor node for **Zone T**, the transition area between the front counter and back-office zones. Brief movement through the corridor or doorway was detected, and one JSON telemetry packet per second was sent to the laptop over Wi-Fi using UDP.
Transition evidence was provided by ESP-T for use in cross-zone movement analysis. Direction and identity were not determined independently.

## Hardware
- ESP8266 NodeMCU
- HC-SR501 PIR motion sensor
- USB cable and power source
A microphone and ultrasonic sensor were not used by ESP-T.

## Wiring
### HC-SR501 PIR
| PIR pin | ESP-T connection |
|---|---|
| VCC | VIN |
| GND | GND |
| OUT | D1 |

## Firmware
Main firmware:
```text
ESP-T_v1.ino
```
Under the historical naming procedure, a repository file still named `ESP-C_v1.ino` was to be renamed to `ESP-T_v1.ino`. The node is already identified as `ESP-T` in Zone `T` by the firmware itself.

The following behaviour was implemented in the historical firmware:
- A connection was established to the configured Wi-Fi network
- The hostname used was `aria-esp-t`
- UDP packets were sent to the laptop on port `5005`
- The local UDP port used was `4212`
- The PIR sensor was sampled
- The same JSON packet was printed to the serial monitor
- Wi-Fi was retried using an explicit credential-based association attempt every 15 seconds
- The Wi-Fi radio was fully reset after three unsuccessful attempts
- ESP-T was automatically restarted if a second three-attempt recovery cycle also failed; the new boot ID was used by the receiver to distinguish a recovery restart from out-of-order telemetry

## Timing configuration
| Setting | Value |
|---|---:|
| Packet interval | 1,000 ms |
| Wi-Fi retry interval | 15,000 ms |
| Attempts before Wi-Fi radio reset | 3 |
| Radio resets before automatic ESP restart | 2 |
| PIR recent-activity hold | 5,000 ms |
The five-second hold period is shorter than the Zone A and Zone B hold periods because Zone T represents brief passage rather than prolonged activity.
The PIR should be allowed approximately **30–60 seconds to stabilise** after power-up.

## Telemetry fields
The following fields were transmitted by ESP-T:
| Field | Meaning |
|---|---|
| `schema_version` | JSON schema version |
| `firmware_version` | ESP-T firmware version (`1.0.0`) |
| `sensor_config` | ESP-T sensor arrangement (`T_PIR`) |
| `boot_id` | identifier generated once at startup to distinguish restarts |
| `node_id` | `ESP-T` |
| `zone` | `T` |
| `sequence` | incrementing packet number |
| `timestamp_ms` | ESP uptime in milliseconds |
| `wifi_connected` | current Wi-Fi state |
| `wifi_rssi_dbm` | Wi-Fi signal strength |
| `pir_motion` | current PIR output |
| `pir_recent_activity` | whether PIR motion occurred within five-second hold period |

Example:
```json
{
  "schema_version": 1,
  "firmware_version": "1.0.0",
  "sensor_config": "T_PIR",
  "boot_id": 12319,
  "node_id": "ESP-T",
  "zone": "T",
  "sequence": 83,
  "timestamp_ms": 84410,
  "wifi_connected": true,
  "wifi_rssi_dbm": -59,
  "pir_motion": true,
  "pir_recent_activity": true
}
```

## Upload and test procedure
1. `ESP-T_v1.ino` must be opened in Arduino IDE
2. Correct ESP8266 NodeMCU board and COM port must be selected
3. Wi-Fi and laptop network configuration must be confirmed in sketch
4. Firmware must be uploaded
5. Serial Monitor must be opened at `115200` baud
6. Wi-Fi connection and PIR stabilisation must be awaited
7. It must be confirmed that one valid JSON packet is printed each second
8. It must be confirmed that laptop UDP receiver receives packets from ESP-T
9. The transition zone must be traversed in both directions
10. Movement beside transition zone must be tested to identify false triggers
11. It must be verified that recent activity returns to false after approximately five seconds without motion
12. Wi-Fi recovery must be verified by turning the access point off for 60 seconds and then restoring it without ESP-T being restarted manually
13. It must be confirmed that Serial Monitor either reports `Wi-Fi reconnected` with same boot ID, or reports an automatic ESP-T restart with a new boot ID, and that UDP telemetry resumes automatically

## Expected startup output
```text
ARIA ESP-T starting
Wi-Fi connected
ESP-T sensor:
PIR: D1
Allow PIR 30-60 seconds to stabilise.
```

## Placement
ESP-T is intended for the corridor or doorway between Zones A and B:
- The PIR must be mounted so that the intended transition path is crossed by its detection field
- Direct orientation into the main activity areas of Zone A or Zone B must be avoided
- It must be kept clear of heat sources, direct sunlight and moving air where possible
- The USB cable must be secured along a wall, frame or nearby fixed surface
- It must be confirmed that ordinary activity within A or B does not repeatedly trigger sensor
Exact placement should be recorded in the deployment documentation and verified again during calibration.

## Interpretation
A transition event can be supported by ESP-T when it is combined with camera and zone evidence, for example:
```text
Track disappears from Zone A
→ ESP-T detects recent activity
→ a track appears in Zone B
```

The following cannot be established by a PIR activation alone:
- Who crossed
- Which direction they travelled
- Whether one or multiple people crossed
- Which activity they were performing

## Known limitations
- Movement direction cannot be determined by a single PIR
- Only one sustained activation may be produced when two people cross together
- Recent activity may be triggered repeatedly by someone standing near the doorway
- False positives may be caused by motion close to the transition boundary
- Board uptime, rather than global time, is represented by ESP timestamps
- Identity and direction must be inferred by laptop-side multimodal pipeline