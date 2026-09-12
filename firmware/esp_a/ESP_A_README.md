# ESP-A1 and ESP-A2 — Zone A Sensor Nodes
## Purpose
ESP-A1 and ESP-A2 are designated as the two active ARIA sensor nodes for **Zone A**, the front service-counter workspace. PIR, ultrasonic and microphone sensors are fitted to ESP-A1. Only PIR and microphone sensors are fitted to ESP-A2. One JSON telemetry packet per second is transmitted to the laptop by each node, with distinct node IDs, hostnames, sensor configurations and local UDP ports.

## Hardware
| Component | ESP-A1 | ESP-A2 |
|---|---|---|
| ESP8266 NodeMCU | Yes | Yes |
| HC-SR501 PIR | Yes | Yes |
| HC-SR04 ultrasonic | Yes | No |
| MAX4466 microphone | Yes | Yes |
| HC-SR04 voltage divider | Yes | No |

## Wiring
### HC-SR501 PIR
| PIR pin | ESP-A connection |
|---|---|
| VCC | VIN |
| GND | GND |
| OUT | D1 |

### HC-SR04 ultrasonic sensor - ESP-A1 only
| HC-SR04 pin | ESP-A connection |
|---|---|
| VCC | VIN |
| GND | GND |
| TRIG | D5 |
| ECHO | D6 through voltage divider |

The HC-SR04 ECHO output must not be connected directly to D6 because the sensor can output approximately 5 V while the ESP8266 uses 3.3 V logic.
Voltage-divider arrangement:
```text
HC-SR04 ECHO
    |
   1 kΩ
    |
    +------ D6
    |
   2 × 1 kΩ in series
    |
   GND
```

### MAX4466 microphone
| MAX4466 pin | ESP-A connection |
|---|---|
| VCC | 3V3 |
| GND | GND |
| OUT | A0 |

## Firmware
Firmware sketches:
```text
ESP_A_v1/ESP_A_v1.ino    # ESP-A1
ESP_A2_v1/ESP_A2_v1.ino  # ESP-A2
```
The following behaviour is implemented in both sketches:
- A connection is established to the configured Wi-Fi network
- Hostnames `aria-esp-a1` and `aria-esp-a2` are used
- UDP packets are sent to the laptop on port `5005`
- Local UDP ports `4210` and `4211` are used, respectively
- PIR and microphone readings are sampled
- The same JSON packet is printed to Serial Monitor at `115200` baud
- Wi-Fi is retried using an explicit association attempt every 15 seconds
- The Wi-Fi radio is fully reset after three unsuccessful attempts
- The affected board is automatically restarted if a second recovery cycle also fails; a new boot ID is used by the receiver to distinguish a recovery restart from out-of-order telemetry
The HC-SR04 ultrasonic sensor is additionally sampled by ESP-A1. No ultrasonic pin setup, readings or telemetry fields are included in ESP-A2.

### Current firmware configuration
| Setting | ESP-A1 | ESP-A2 |
|---|---|---|
| Firmware version | `1.1.1` | `1.1.1` |
| Node ID | `ESP-A1` | `ESP-A2` |
| Zone | `A` | `A` |
| Sensor configuration | `A_PIR_US_MIC` | `A_PIR_MIC` |
| Wi-Fi network | `YOUR_WIFI_SSID` (open) | `YOUR_WIFI_SSID` (open) |
| Wi-Fi hostname | `aria-esp-a1` | `aria-esp-a2` |
| ESP local UDP port | `4210` | `4211` |
| Laptop destination | `10.100.6.173:5005` | `10.100.6.173:5005` |

`10.100.6.173` is the Mac laptop's IPv4 address currently compiled into both sketches. Network addresses may be changed. Before reflashing or deployment startup, the Mac's active IPv4 address from `ipconfig getifaddr en0` must be compared with `LAPTOP_IP` in both sketches. `YOUR_WIFI_SSID` is configured as an open network, so `WIFI_PASSWORD` is empty and `WiFi.begin(WIFI_SSID, WIFI_PASSWORD)` is called by the sketches.

## Timing configuration
| Setting | Value |
|---|---:|
| Packet interval | 1,000 ms |
| Wi-Fi retry interval | 15,000 ms |
| Attempts before Wi-Fi radio reset | 3 |
| Radio resets before automatic ESP restart | 2 |
| PIR recent-activity hold | 10,000 ms |
| ESP-A1 ultrasonic timeout | 30,000 µs |
| Microphone sampling window | 900 ms |
| Maximum microphone samples | 500 |
The PIR should be allowed approximately **30–60 seconds to stabilise** after power-up.

## Telemetry fields
The common and audio fields below are transmitted by both boards. The ultrasonic fields are transmitted only by ESP-A1.
| Field | Meaning |
|---|---|
| `schema_version` | JSON schema version |
| `firmware_version` | zone A firmware version (`1.1.1`) |
| `sensor_config` | `A_PIR_US_MIC` for ESP-A1; `A_PIR_MIC` for ESP-A2 |
| `boot_id` | identifier generated once at startup to distinguish restarts |
| `node_id` | `ESP-A1` or `ESP-A2` |
| `zone` | `A` |
| `sequence` | incrementing packet number |
| `timestamp_ms` | ESP uptime in milliseconds |
| `wifi_connected` | current Wi-Fi state |
| `wifi_rssi_dbm` | Wi-Fi signal strength |
| `pir_motion` | current PIR output |
| `pir_recent_activity` | whether PIR motion occurred within hold period |
| `distance_cm` | ESP-A1 only: HC-SR04 distance reading |
| `distance_valid` | ESP-A1 only: whether ultrasonic reading is valid |
| `audio_peak_to_peak` | difference between maximum and minimum microphone samples |
| `audio_activity` | mean absolute deviation from microphone sample mean |
| `audio_rms` | root-mean-square deviation from microphone sample mean |

Example:
```json
{
  "schema_version": 1,
  "firmware_version": "1.1.1",
  "sensor_config": "A_PIR_US_MIC",
  "boot_id": 12319,
  "node_id": "ESP-A1",
  "zone": "A",
  "sequence": 222,
  "timestamp_ms": 226082,
  "wifi_connected": true,
  "wifi_rssi_dbm": -64,
  "pir_motion": false,
  "pir_recent_activity": true,
  "distance_cm": 206.16,
  "distance_valid": true,
  "audio_peak_to_peak": 52,
  "audio_activity": 7.31,
  "audio_rms": 9.21
}
```
ESP-A2 example:
```json
{
  "schema_version": 1,
  "firmware_version": "1.1.1",
  "sensor_config": "A_PIR_MIC",
  "boot_id": 39124,
  "node_id": "ESP-A2",
  "zone": "A",
  "sequence": 222,
  "timestamp_ms": 226082,
  "wifi_connected": true,
  "wifi_rssi_dbm": -62,
  "pir_motion": false,
  "pir_recent_activity": true,
  "audio_peak_to_peak": 48,
  "audio_activity": 6.84,
  "audio_rms": 8.73
}
```
`distance_cm` and `distance_valid` are omitted by ESP-A2. An invalid ESP-A1 ultrasonic measurement is represented by a negative `distance_cm` value and `distance_valid: false`.

## Upload and test procedure
1. In Arduino IDE, `ESP_A_v1/ESP_A_v1.ino` must be opened for ESP-A1 or `ESP_A2_v1/ESP_A2_v1.ino` for ESP-A2
2. Correct ESP8266 NodeMCU board and COM port must be selected
3. It must be confirmed that wifi SSID is `YOUR_WIFI_SSID`, `WIFI_PASSWORD` is empty and sketch calls `WiFi.begin(WIFI_SSID, WIFI_PASSWORD)`
4. It must be confirmed that laptop IP, node ID, hostname and local UDP port match board
5. Firmware must be uploaded to one board at a time, and the flashed board must be labelled
6. Serial Monitor must be opened at `115200` baud
7. Wi-Fi connection and PIR stabilisation must be awaited
8. It must be confirmed that one valid JSON packet is printed each second with expected `node_id`
9. It must be confirmed that laptop receiver logs ESP-A1 and ESP-A2 separately
10. PIR movement and microphone response must be tested on both boards; counter proximity and invalid echoes must be tested only on ESP-A1
11. Packet loss, ESP-A1 invalid distance readings and public-network reassociation events must be recorded
12. With ESP-A2 kept powered and transmitting, ESP-A1 recovery must be tested either by pressing its restart/reset control or by powering only ESP-A1 off and back on
13. With ESP-A1 kept powered and transmitting, the same recovery test must be repeated for ESP-A2; the site's public access point must not be interrupted, replaced or reconfigured for either test
14. For each board, a new boot ID, successful reassociation with `YOUR_WIFI_SSID`, automatic UDP telemetry recovery and uninterrupted packets from the other board must be confirmed

Arduino CLI equivalents:
```bash
ARDUINO_CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"

"$ARDUINO_CLI" compile \
  --fqbn esp8266:esp8266:nodemcuv2 \
  firmware/esp_a/ESP_A_v1

"$ARDUINO_CLI" upload \
  --fqbn esp8266:esp8266:nodemcuv2 \
  --port /dev/cu.YOUR_ESP_A1_PORT \
  firmware/esp_a/ESP_A_v1
```
`firmware/esp_a/ESP_A2_v1` and ESP-A2's serial port must be used for the second board. `"$ARDUINO_CLI" board list` must be run immediately before each upload, and the physical board label must be verified rather than serial-port order being assumed.

## Expected startup output
```text
ARIA ESP-A1 starting
Wi-Fi connected
ESP-A1 sensors:
PIR: D1
Ultrasonic TRIG: D5
Ultrasonic ECHO: D6
MAX4466: A0
Allow PIR 30-60 seconds to stabilise.
```
Only the following must be listed for ESP-A2:
```text
ESP-A2 sensors:
PIR: D1
MAX4466: A0
```
For both boards, the following must also be shown in the connection output:
```text
Laptop IP: 10.100.6.173
Laptop UDP port: 5005
```
The local UDP port must be `4210` for ESP-A1 and `4211` for ESP-A2.

## Laptop receiver and separate node logs
The receiver must be started from the repository root:
```bash
PYTHONPATH=src python3 -m aria.ingestion.udp_receiver
```
The expected startup line is:
```text
UDP receiver started on 0.0.0.0:5005; accepting ESP-A1 and ESP-A2 only
```
To follow each board in a separate Terminal pane:
```bash
tail -f outputs/logs/esp_a1.log
```
```bash
tail -f outputs/logs/esp_a2.log
```
If `Address already in use` is reported by the receiver, the existing receiver must be located with `lsof -nP -iUDP:5005` and that process must be stopped before a replacement is started.

## Placement
Both boards are intended for the front counter area. Their distinct placements must be recorded so that the two sensor streams are not treated as interchangeable:
- Both PIR sensors positioned to detect their intended staff-side areas
- ESP-A1 HC-SR04 aimed across defined counter working area
- Both MAX4466 modules positioned near their intended staff-side areas
- Board powered by USB
- Wiring secured so that staff cannot catch or disconnect cables during normal work
Exact placement should be recorded in the deployment documentation and verified again during calibration.

## Known limitations
- Motion is indicated by PIR, but a person or activity is not identified
- ESP-A1 ultrasonic readings may be invalid because of angle, obstruction or reflective surfaces; no distance evidence is provided by ESP-A2
- Only sound intensity is measured by microphone features; speech is neither captured nor recognised
- Board uptime, rather than global time, is represented by ESP timestamps
- Activity labels must be produced by laptop-side multimodal pipeline, not by either ESP-A board alone