# Pre-Session Checklist
> **Historical checklist:** Participant collection was closed on 10 August 2026.
> The gate applied to retained sessions is recorded in this checklist, which must not be
> used to authorise a new pilot or participant session.

- [ ] Participant-facing Ethics Pack Version 4.4 PDF generated and visually verified
- [ ] Version 4.4 received and the required acknowledgement completed by every participating Counter Agent
- [ ] Only consenting Counter Agents are scheduled to enter the retained Zone A region
- [ ] Station Managers and all other non-participants kept outside the retained region
- [ ] Participant IDs assigned
- [ ] `zone-a-collection-v7` confirmed as the approved frozen profile and its pinned SHA-256/artifact checks passed
- [ ] DJI Camera A position checked
- [ ] Zone A mask checked
- [ ] `camera_a`, `batamfast-v2` and `verified: true` reported by the mask
- [ ] Customer-facing area excluded
- [ ] Screens, payment areas and sensitive documents excluded
- [ ] Laptop microphone disabled
- [ ] DJI and MediaMTX recording disabled
- [ ] MediaMTX ingest audio-removal relay running
- [ ] ARIA-facing `live/camera_a` stream verified as one H264 track with no audio
- [ ] ESP-A1 connected
- [ ] ESP-A2 connected
- [ ] UDP telemetry received from all expected nodes
- [ ] Laptop clock checked
- [ ] Available storage checked
- [ ] Cables secured
- [ ] Pause/stop control tested
- [ ] Session log opened
- [ ] Fail-closed Phase 7.2 preflight passed
- [ ] Validated `planned` manifest created before any writer is started
- [ ] Collection profile `zone-a-collection-v7` and its SHA-256 recorded in the planned manifest
- [ ] Firmware version `1.1.1` reported in fresh ESP-A1 and ESP-A2 packets
- [ ] Manifest-backed start gate and shared pause/stop controller used by every writer
- [ ] Localhost masked track-ID preview supplied by the session camera writer and blanked on pause/stop
- [ ] Browser preview kept open throughout the retained session
- [ ] Masked display and tools shown on the left with participant cards positioned at the top right in the desktop preview
- [ ] Manual track input and selected activity preserved through at least two one-second status polls
- [ ] Only manifest participant pseudonyms and current local track IDs listed in the preview annotation panel
- [ ] Only assigned pseudonyms accepted by the dynamic participant control after explicit consent confirmation
- [ ] Annotator pseudonym selected and one test transition timestamped automatically
- [ ] Incident output directory confirmed as local and writable, with no participant identities included
- [ ] Closure and provision of file/count/gap accounting verified for every writer
