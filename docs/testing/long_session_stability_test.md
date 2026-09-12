# ESP-B Long-Session Memory Stability Test
> Historical test record. ESP-B is no longer part of the live deployment.

## Current applicability
This result must not be used as the stability acceptance for the active deployment. ESP-B, Zone B and its 3,000-sample buffer are retired. The active boards are:
- ESP-A1: `A_PIR_US_MIC`, 500-sample microphone buffer, local UDP 4210
- ESP-A2: `A_PIR_MIC`, 500-sample microphone buffer, local UDP 4211
The current 90-minute stability and isolation test is `docs/testing/zone_a_integration_test.md`. It must run ESP-A1, ESP-A2 and the single DJI Camera A together. The historical measurements below are retained unchanged as development evidence only.

## Purpose
Phase 2.2 of the ARIA pipeline is to be verified: a stable ESP-B microphone sample buffer must be maintained during a long run without resets, watchdog triggers or sustained packet interruption.
A buffer of 3,000 `uint16_t` microphone samples is allocated by the firmware, occupying 6,000 bytes of static RAM. It prints the reset reason at boot, a startup memory record, and a memory record every 60 seconds.

## Required evidence
- ESP-B serial output captured for the complete test
- Laptop-side `outputs/logs/esp_b.log`
- Laptop-side `outputs/logs/udp_receiver.log`
- Laptop-side `data/raw/esp_packets.jsonl`
- Start and end times in Singapore Time
- Any intentional restart, power interruption or network interruption noted
  separately from unexpected failures
Raw audio must not be recorded. Only numerical audio features are included in the firmware and test evidence.

## Firmware output to verify
At boot:
```text
Reset reason: <ESP8266 reset reason>
[MEMORY] context=startup uptime_ms=<value> free_heap_bytes=<value> minimum_free_heap_bytes=<value> audio_buffer_bytes=6000
```
Once per minute:
```text
[MEMORY] context=periodic uptime_ms=<value> free_heap_bytes=<value> minimum_free_heap_bytes=<value> audio_buffer_bytes=6000
```
The `minimum_free_heap_bytes` field is the lowest free-heap reading observed
since boot. The startup reset reason must be checked for a watchdog or exception reset.

## Procedure
1. `firmware/esp_b/ESP_B_v1/ESP_B_v1.ino` must be uploaded to ESP-B
2. The Serial Monitor must be opened at 115,200 baud, and its output must be saved
3. The laptop UDP receiver must be started, and the formal test-start time must be recorded
4. It must be confirmed that the serial output includes the reset reason and startup memory record
5. ESP-B must be run continuously for at least 60 minutes, with the PIR and microphone sampled and one packet transmitted per second
6. ESP-B must not be restarted or disconnected during the baseline interval. If an intentional intervention is required, its exact time must be recorded and it must be excluded from the unexpected-reset assessment
7. At the formal test end, stop the receiver normally and save the complete serial output
8. The serial timeline must be compared with ESP-B packet sequences and receive times
9. The results tables below must be completed

## Test record
| Item | Result |
|---|---|
| Test date | 28 July 2026 |
| Formal start | 20:23:00 SGT |
| Formal end | 21:23:53 SGT |
| Duration | 60 minutes 53 seconds |
| Firmware version | `1.0.0` |
| Maximum audio samples | 3,000 |
| Static audio-buffer size | 6,000 bytes |
| ESP-B serial-log path | `outputs/logs/esp_b_serial_memory_test.log` |
| Overall result | Pass for Phase 2.2 memory stability, with Wi-Fi recovery observation |

## Memory results
| Metric | Result |
|---|---|
| Startup free heap | Startup line not captured; first periodic reading was 43,152 bytes |
| Lowest free heap | 43,152 bytes |
| End free heap | 44,040 bytes |
| Change from first periodic reading to end | +888 bytes |
| Periodic records expected | Approximately 63 for the captured serial duration |
| Periodic records captured | 63 |

## Stability results
| Check | Result |
|---|---|
| Unexpected ESP resets | 0; boot ID `37505610` remained constant |
| Watchdog or exception during run | None recorded |
| ESP-B packets stopped unexpectedly | UDP receipt stopped after Wi-Fi loss near 21:18:02 SGT |
| Longest unexplained receive gap before Wi-Fi loss | 2.286 seconds |
| Final Wi-Fi outage before receiver shutdown | 353.590 seconds |
| Receiver crashes | 0; normal user-requested shutdown |
| Malformed ESP-B packets | 0 |

## Packet results
The formal analysis window began at 20:23:00 SGT. ESP-B packets were received until 21:17:59.996 SGT.
| Metric | Result |
|---|---:|
| First observed sequence | 161 |
| Last received sequence | 3,460 |
| Expected from observed sequence range | 3,300 |
| Unique packets received | 3,258 |
| Missing sequence values | 42 |
| Delivery before Wi-Fi loss | 98.727% |
| Duplicate packets | 0 |

The serial capture continued after UDP receipt stopped. It contained 3,812 unique local sequences from 5 through 3,816 with one unchanged boot identifier. This shows that sensing and packet construction continued without a board restart while the Wi-Fi connection was unavailable.

## Acceptance criteria
- No unexpected ESP-B reset
- No watchdog or exception reset reason
- No unexplained stop in ESP-B telemetry
- Memory record present at startup and at approximately 60-second intervals
- Free heap does not show continuing unbounded decline across the run
- No malformed ESP-B packets
- Laptop receiver remains running until normal shutdown

## Result interpretation
Phase 2.2 passes for ESP-B memory stability:
- Free heap did not show continuing decline;
- The minimum observed free heap was 43,152 bytes;
- The 6,000-byte audio buffer remained allocated and reported throughout;
- The board did not restart;
- No watchdog or exception was recorded during the captured run; and
- Local sensor cycles continued through the end of the serial capture.
At approximately 57 minutes 47 seconds of board uptime, ESP-B logged a failed UDP send followed by `WARNING: Wi-Fi connection lost`. It continued producing local packets and attempted reconnection every five seconds, but it did not reconnect before the test ended. The packet stoppage is therefore explained by network loss rather than memory exhaustion.
The startup portion of the serial output was not included in the saved capture, so the startup reset-reason line and `context=startup` heap line are unavailable. The first periodic memory record, captured at approximately 65 seconds of uptime, is used as the memory baseline.
The failure to restore Wi-Fi during the remaining test interval is an observation for Phase 2.4 Wi-Fi reconnection handling and does not invalidate the Phase 2.2 memory result.

## Phase 2.4 Wi-Fi recovery follow-up
ESP-B was retested on 28 July 2026 after adding bounded Wi-Fi recovery. The firmware first makes explicit credential-based association attempts, then fully resets the Wi-Fi interface. If a second recovery cycle fails, it automatically restarts ESP-B.
The captured serial output showed two successful automatic recoveries without pressing the hardware reset button:
- Boot `37940609` exhausted both recovery cycles and restarted automatically;
- The new boot `3647323664` connected to `172.20.10.5` and started UDP;
- After a later disconnection, boot `3647323664` again exhausted both recovery cycles and restarted automatically; and
- The new boot `1157495492` connected to `172.20.10.5`, started UDP, and resumed one-second telemetry.
The laptop receiver independently confirmed the second recovery. It marked ESP-B stale at 22:38:17 SGT, then at 22:39:47 SGT reported the restart from boot `3647323664` to boot `1157495492` and received sequence 2. Later ESP-B packets continued to arrive.
Phase 2.4 therefore passes for ESP-B: loss is detected, recovery is automatic, the receiver distinguishes the recovery restart using `boot_id`, and UDP telemetry resumes without a manual ESP reset.
ESP-A and ESP-T were then tested with the same recovery implementation:
- ESP-A detected the outage on boot `37388584`, reconnected on its first explicit attempt after 7,994 ms, retained the same boot ID and packet
  sequence, reacquired `172.20.10.3`, and restarted UDP on local port `4210`
- ESP-T detected the outage on boot `38041457`, reconnected on its second explicit attempt after 23,470 ms, retained the same boot ID and packet
  sequence, reacquired `172.20.10.4`, and restarted UDP on local port `4212`
- The laptop receiver subsequently received both streams again. It reported the expected sequence gaps for packets generated locally during the outages:
  16 packets for ESP-A and 24 packets for ESP-T
Phase 2.4 passes across ESP-A, ESP-B and ESP-T. All three nodes detect Wi-Fi loss and restore UDP telemetry automatically. ESP-A and ESP-T recovered without restarting; ESP-B demonstrated the bounded automatic-restart fallback when ordinary association and radio reset were insufficient.

## Earlier integration evidence
The three-node integration test on 28 July 2026 received 3,281 ESP-B packets from 3,343 expected sequence values (98.145% delivery). ESP-B remained present through the end of the formal interval and recovered from one deliberate restart.