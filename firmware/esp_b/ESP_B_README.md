# ESP-B — Back Zone Sensor Node
## Retirement status
**ESP-B and Zone B have been retired from the active ARIA deployment as of 29 July 2026.** This node must not be built, flashed or deployed for current tests, and its telemetry must not be expected. Only `ESP-A1` and `ESP-A2` are accepted by the UDP receiver; ESP-B packets are rejected.
This directory and the technical information below are retained for historical reference only.

## Purpose
ESP-B was designated as the ARIA sensor node for **Zone B**, the back-office or manager workspace. Motion and numerical ambient-audio features were provided for historical station-manager activity recognition, and one JSON telemetry packet per second was sent to the laptop over Wi-Fi using UDP.

## Hardware
- ESP8266 NodeMCU
- HC-SR501 PIR motion sensor
- MAX4466 analogue microphone module
- USB cable and power source
An ultrasonic sensor was not used by ESP-B.

## Wiring
### HC-SR501 PIR
| PIR pin | ESP-B connection |
|---|---|
| VCC | VIN |
| GND | GND |
| OUT | D1 |

### MAX4466 microphone
| MAX4466 pin | ESP-B connection |
|---|---|
| VCC | 3V3 |
| GND | GND |
| OUT | A0 |

## Firmware
Main firmware:
```text
ESP-B_v1.ino
```
The following behaviour was implemented in the historical firmware:
- A connection was established to the configured Wi-Fi network
- The hostname used was `aria-esp-b`
- UDP packets were sent to the laptop on port `5005`
- The local UDP port used was `4211`
- PIR and microphone readings were sampled
- The same JSON packet was printed to the serial monitor
- Wi-Fi connection was retried automatically using an explicit credential-based association attempt every 15 seconds
- The Wi-Fi radio was fully reset after three unsuccessful attempts
- ESP-B was automatically restarted if a second three-attempt recovery cycle also failed; the new boot ID was used by the receiver to distinguish this recovery restart from out-of-order telemetry

## Timing configuration
| Setting | Value |
|---|---:|
| Packet interval | 1,000 ms |
| PIR recent-activity hold | 10,000 ms |
| Microphone sampling window | 900 ms |
| Maximum microphone samples | 3,000 |
| Microphone sample-buffer size | 6,000 bytes |
| Memory log interval | 60,000 ms |
The PIR should be allowed approximately **30–60 seconds to stabilise** after power-up.

## Telemetry fields
The following fields were transmitted by ESP-B:
| Field | Meaning |
|---|---|
| `schema_version` | JSON schema version |
| `firmware_version` | ESP-B firmware version (`1.0.0`) |
| `sensor_config` | ESP-B sensor arrangement (`B_PIR_MIC`) |
| `boot_id` | identifier generated once at startup to distinguish restarts |
| `node_id` | `ESP-B` |
| `zone` | `B` |
| `sequence` | incrementing packet number |
| `timestamp_ms` | ESP uptime in milliseconds |
| `wifi_connected` | current Wi-Fi state |
| `wifi_rssi_dbm` | Wi-Fi signal strength |
| `pir_motion` | current PIR output |
| `pir_recent_activity` | whether PIR motion occurred within hold period |
| `audio_peak_to_peak` | difference between maximum and minimum microphone samples |
| `audio_activity` | mean absolute deviation from microphone sample mean |
| `audio_rms` | root-mean-square deviation from microphone sample mean |

Example:
```json
{
  "schema_version": 1,
  "firmware_version": "1.0.0",
  "sensor_config": "B_PIR_MIC",
  "boot_id": 12319,
  "node_id": "ESP-B",
  "zone": "B",
  "sequence": 117,
  "timestamp_ms": 118409,
  "wifi_connected": true,
  "wifi_rssi_dbm": -63,
  "pir_motion": true,
  "pir_recent_activity": true,
  "audio_peak_to_peak": 61,
  "audio_activity": 8.42,
  "audio_rms": 10.37
}
```
## Upload and test procedure
1. `ESP-B_v1.ino` must be opened in Arduino IDE
2. Correct ESP8266 NodeMCU board and COM port must be selected
3. Wi-Fi and laptop network configuration must be confirmed in sketch
4. Firmware must be uploaded
5. Serial Monitor must be opened at `115200` baud
6. Wi-Fi connection and PIR stabilisation must be awaited
7. It must be confirmed that one valid JSON packet is printed each second
8. It must be confirmed that laptop UDP receiver receives packets from ESP-B
9. PIR movement and microphone response must be tested separately
10. ESP-B Serial Monitor output during long-session stability test must be captured
11. It must be confirmed that startup output contains reset reason and a `[MEMORY] context=startup` line
12. It must be confirmed that a `[MEMORY] context=periodic` line appears once per minute
13. Starting and minimum free-heap values, any reset or watchdog reason, and any packet interruption must be recorded in `docs/testing/long_session_stability_test.md`
14. Wi-Fi recovery must be verified by turning the access point off for 60 seconds and then restoring it without ESP-B being restarted
15. It must be confirmed that Serial Monitor either reports `Wi-Fi reconnected` with same boot ID, or reports an automatic ESP-B restart with a new boot ID, and resumes UDP telemetry without pressing hardware reset button

## Expected startup output
```text
ARIA ESP-B starting
Boot ID: 12319
Reset reason: External System
[MEMORY] context=startup uptime_ms=512 free_heap_bytes=42128 minimum_free_heap_bytes=42128 audio_buffer_bytes=6000
Wi-Fi connected
ESP-B sensors:
PIR: D1
MAX4466: A0
Allow PIR 30-60 seconds to stabilise.
```
## Placement
ESP-B is intended for the back-office workspace:
- PIR positioned near manager desk or wall to observe movement within Zone B
- MAX4466 positioned near manager workspace
- Board powered by USB
- Sensor direction adjusted to reduce triggering from activity outside Zone B
- Wiring secured away from drawers, cabinets and walking paths
Exact placement should be recorded in the deployment documentation and verified again during calibration.

## Known limitations
- Movement is detected by PIR, but desk work, walking and conversation cannot be distinguished by it alone
- Only sound intensity is measured by microphone features; speech is neither stored nor recognised
- Audio features may be affected by background televisions, drawers, office equipment and nearby conversations
- A total of 6,000 bytes of static RAM is occupied by the 3,000-sample microphone array; a captured long-duration serial run is still required to verify its free-heap stability
- Board uptime, rather than global time, is represented by ESP timestamps
- Activity labels must be produced by laptop-side multimodal pipeline, not by ESP-B alone