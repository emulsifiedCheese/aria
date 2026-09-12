# ARIA Three-Node Integration Test
> Historical test record. This predates the Zone A-only deployment adopted on 29 July 2026 and is not the acceptance test for ESP-A1, ESP-A2 and the DJI Camera A stream.

## Current applicability
The measurements below describe ESP-A, ESP-B and ESP-T firmware version 1.0.0 and must not be presented as evidence that the current deployment passed. Zone B, Zone T, ESP-B and ESP-T are retired, and the legacy `ESP-A` identity is rejected by the current receiver.
`docs/testing/zone_a_integration_test.md` must be used for the active ESP-A1/ESP-A2/DJI test, and `docs/testing/live_site_acceptance_test.md` must be used for final collection readiness. Historical results below are intentionally preserved.

## Test summary
| Item | Result |
|---|---|
| Test date | 28 July 2026 |
| Formal start | 18:34:38 SGT |
| Formal end | 19:30:28 SGT |
| Formal duration | 55 minutes 50 seconds |
| Nodes | ESP-A, ESP-B and ESP-T |
| Laptop UDP port | 5005 |
| Firmware version | 1.0.0 on all nodes |
| Overall result | Pass with observations |

Simultaneous telemetry from all three ESP8266 nodes, packet logging, sequence monitoring, deliberate node interruptions, restart detection and recovery were exercised during the test. The receiver remained running throughout the formal interval and was stopped manually after the end marker.
The intervention log was recorded in SGT. Times in this report were converted to Singapore Time (SGT, SGT+08:00) to match the receiver records and the ARIA pipeline timing convention.

## Test evidence
The assessment used:
- `data/raw/esp_packets.jsonl`
- `outputs/logs/three_node_test_events.log`
- `outputs/logs/udp_receiver.log`
- `outputs/logs/esp_a.log`
- `outputs/logs/esp_b.log`
- `outputs/logs/esp_t.log`
The receiver did not create `data/raw/invalid_packets.jsonl` during this run, indicating that no invalid packets were recorded.

## Configuration verified
| Node | Zone | Source port | Firmware | Sensor configuration |
|---|---|---:|---|---|
| ESP-A | A | 4210 | 1.0.0 | `A_PIR_US_MIC` |
| ESP-B | B | 4211 | 1.0.0 | `B_PIR_MIC` |
| ESP-T | T | 4212 | 1.0.0 | `T_PIR` |

All formal-run packets contained the expected firmware version, sensor configuration and boot identifier.

## Metric calculation
Only packets whose laptop receive timestamps fell between the formal start and end markers were included.
For each node and boot identifier, expected packets were calculated from the inclusive sequence range:
```text
expected = maximum sequence - minimum sequence + 1
```
Received packets were counted using unique sequence numbers within each boot. Missing packets were the difference between expected and received packets. This sequence-based calculation measures delivery while a boot was observable; it does not count time when a deliberately unplugged node was not powered.

## Packet results
| Node | Expected | Received | Missing | Delivery | Loss |
|---|---:|---:|---:|---:|---:|
| ESP-A | 3,213 | 3,139 | 74 | 97.697% | 2.303% |
| ESP-B | 3,343 | 3,281 | 62 | 98.145% | 1.855% |
| ESP-T | 3,221 | 3,177 | 44 | 98.634% | 1.366% |
| **Total** | **9,777** | **9,597** | **180** | **98.159%** | **1.841%** |

The aggregate delivery rate exceeded the planned 98% pass threshold. ESP-A was slightly below 98% when assessed individually and should be monitored in later
site and stability testing.

## Sequence and receiver integrity
| Check | Result |
|---|---:|
| Invalid packets | 0 |
| Duplicate packets | 0 |
| Out-of-order packets within the same boot | 0 |
| Receiver crashes | 0 |
| Receiver shutdown | Normal user-requested stop |

Sequence gaps were detected without crashing the receiver. Across all nodes, 180 sequence values were missing from the observed per-boot ranges.

## RSSI and receive gaps
| Node | Minimum RSSI | Maximum RSSI | Mean RSSI | Longest receive gap |
|---|---:|---:|---:|---:|
| ESP-A | -80 dBm | -56 dBm | -61.74 dBm | 138.049 s |
| ESP-B | -84 dBm | -61 dBm | -67.93 dBm | 8.313 s |
| ESP-T | -77 dBm | -60 dBm | -64.22 dBm | 129.687 s |

The longest ESP-A and ESP-T gaps include their deliberate disconnection periods. After all recovery interventions, the longest internal gap was approximately 3.1 seconds for each node. ESP-B briefly reached -84 dBm and should be observed during deployment-position testing.

## Baseline period
The uninterrupted baseline ran for 10 minutes 5 seconds.
| Node | Packets received | Longest internal gap |
|---|---:|---:|
| ESP-A | 582 | 3.058 s |
| ESP-B | 580 | 3.029 s |
| ESP-T | 590 | 2.998 s |

All nodes continued transmitting and the receiver remained active throughout the baseline.

## Controlled interventions
### ESP-A disconnection
- Disconnection marker: 18:45:05 SGT
- Reconnection marker: 18:47:20 SGT
- First packet with the new boot identifier: 4.884 seconds after reconnection
- ESP-B packets received during the marked interval: 133
- ESP-T packets received during the marked interval: 130
- Maximum internal gap for ESP-B: 2.052 seconds
- Maximum internal gap for ESP-T: 3.997 seconds
ESP-A became stale, then returned with a new boot identifier. ESP-B and ESP-T continued operating while ESP-A was unavailable.

### ESP-B restart
- Restart marker: 18:48:10 SGT
- New boot identifier detected: 6.903 seconds after the restart marker
- Recovery marker: 18:48:27 SGT
- ESP-A packets received during the marked interval: 16
- ESP-T packets received during the marked interval: 15
The receiver reported the ESP-B boot-identifier change as a restart rather than an out-of-order packet. ESP-A and ESP-T continued operating.

### ESP-T disconnection
- Disconnection marker: 18:48:44 SGT
- Reconnection marker: 18:50:48 SGT
- First packet with the new boot identifier: 4.361 seconds after reconnection
- ESP-A packets received during the marked interval: 120
- ESP-B packets received during the marked interval: 121
- Maximum internal gap for ESP-A: 2.148 seconds
- Maximum internal gap for ESP-B: 1.946 seconds
No ESP-T packets were received during the marked disconnection interval. ESP-A and ESP-B continued operating, and ESP-T recovered with a new boot identifier.

## Post-recovery stability
The post-recovery period ran for 39 minutes 40 seconds.
| Node | Packets received | Longest internal gap |
|---|---:|---:|
| ESP-A | 2,335 | 2.999 s |
| ESP-B | 2,351 | 3.074 s |
| ESP-T | 2,359 | 3.056 s |

All three nodes remained present through the end of the formal interval.

## Pass criteria
| Criterion | Outcome |
|---|---|
| At least 98% packets received | Pass: 98.159% aggregate |
| No receiver crashes | Pass |
| No malformed packets during normal operation | Pass |
| Automatic recovery after ESP restart | Pass |
| Other nodes continue when one node disconnects | Pass |

## Limitations and outstanding verification
- ESP-A achieved 97.697% delivery individually, below the 98% aggregate target
- Wi-Fi was not interrupted during the test while the boards were kept powered. Reconnection after a live network outage therefore remains to be verified.
- No ESP-B serial log was captured. Free-heap stability, watchdog output and Phase 2.2 memory acceptance cannot be concluded from the UDP logs
- Node disconnection and restart recovery were covered by the test; deployment-site range, interference and final sensor placement were not covered

## Conclusion
The formal three-node integration run passed its aggregate packet-delivery, receiver-stability, malformed-packet, restart-recovery and node-isolation criteria. Phase 1.4 is complete with ESP-A delivery recorded as an observation.
Boot identifiers were successfully verified on physical ESP-A, ESP-B and ESP-T restarts. Final closure of the wider Phase 2 verification still requires an ESP-B serial memory-stability run and a live Wi-Fi interruption/recovery test.