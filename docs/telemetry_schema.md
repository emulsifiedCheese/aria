# ARIA ESP Telemetry Schema
## Overview
Two ESP8266 sensor nodes are used in the current ARIA deployment:
- ESP-A1 in Counter Zone A
- ESP-A2 in Counter Zone A
ESP-B and ESP-T are retired from the current deployment. Packets using those identities, or the legacy `ESP-A` identity, are rejected by the live receiver.
Telemetry is sent by each node to the laptop on destination port `5005`.
| Node | Zone | ESP local UDP port | Laptop UDP port |
|---|---|---:|---:|
| ESP-A1 | A | 4210 | 5005 |
| ESP-A2 | A | 4211 | 5005 |

A semantic `firmware_version` and a node-specific `sensor_config` are included in every packet:
| Node | `firmware_version` | `sensor_config` |
|---|---|---|
| ESP-A1 | `1.1.1` | `A_PIR_US_MIC` |
| ESP-A2 | `1.1.1` | `A_PIR_MIC` |

PIR, HC-SR04 ultrasonic and numerical microphone features are included by ESP-A1.
Only PIR and numerical microphone features are included by ESP-A2. `distance_cm` and `distance_valid` are omitted from ESP-A2 packets; placeholder readings must not be invented for a sensor that is not fitted.
Captured telemetry can be traced through these fields to the firmware and physical sensor arrangement by which it was produced.
A numeric `boot_id` is also included in every packet. This identifier is generated once by a node during startup and is kept unchanged for that boot. If a
new `boot_id` is received for the same node, a restart is recorded rather than the lower sequence number being treated as an out-of-order packet. Valid boot IDs are defined as unsigned 32-bit integers from `0` through `4294967295`.
The transmitted packet payload schema is stored at:
```text
schemas/esp_packet.schema.json
```
Each validated payload is stored by the laptop inside a local receive envelope with the SGT receive timestamp and source endpoint. That complete JSONL row is validated against:
```text
schemas/esp_record.schema.json
```
The packet rules are not weakened by the receive envelope: its nested `payload` must still be validated as ESP-A1 or ESP-A2 telemetry.