# Beta — Luma 0.2.9

This is a Beta application update for the existing Luma Pi, not a new SD image or hardware-accepted v1. Publication and exact artifact evidence are tracked in the working notes.

## Changes

- A new offline phonetic “Hey Luma” detector checks the wake sounds independently of how speech-to-text spells the name. Protected defaults migrate to it; an explicitly chosen more-sensitive setting is preserved. Settings → Voice shows which listener is selected and whether it is actually running. No silent sensitivity fallback is used.
- One separately signed wake-model download (about 46 MB) prepares automatically on the supported Pi. The model/runtime lives outside the app environment and saved settings. Download, install, repair and failure state are visible; commands wait until the selected model is ready. Model installation is not microphone, pronunciation or speaker-identity acceptance.
- Voice checks and the no-wake call trial use the selected detector. Missing model, worker failure and incomplete audio do not count as successful negative checks. A changed listener clears older trial evidence.
- Automatic iPhone reconnect cancels a stuck, still-disconnected BlueZ connection request before a later bounded retry. Competing scan auto-connect is disabled; an already completed/manual connection and the saved bond are preserved. Authorized notification access is still required to leave privacy standby.
- Unsupported commands display **Unknown command** briefly in the themed corner, with no spoken reply or chime. Valid replies and safety explanations are unchanged. No command transcript or notice is saved.

## Update and test

Use Settings → Luma software → Check for updates → review **Beta 0.2.9** → Install. Keep power and internet connected through the update and its automatic reboot. No SD flash or re-pairing should be needed. Settings, Google links, Wi-Fi, PIN and saved games remain on the Pi.

Then open Settings → Voice. Wait for the signed wake model to finish preparing and for **Phonetic listener running** before testing. If you previously chose the more-sensitive listener, deliberately select the phonetic listener here. Try four normal-distance “Hey Luma, what time is it” requests, then the guided voice check and repeated 90-second no-wake call checks. Test hesitant phrasing separately; actual recognition may still miss speech.

For Bluetooth, keep iPhone Bluetooth enabled in Settings and Share System Notifications enabled for Luma. Leave range and return without pressing Connect; repeat three times, including after a Pi reboot. If automatic connection still stalls, report the exact hub/phone status and use Pi Connect diagnostics. Preserve the bond rather than forgetting the phone first.

## Qualification boundaries

Software, signed payload and isolated ARM64-emulation checks do not prove real Pi audio, radio, timing or thermal behavior. Synthetic speech sets are development regressions, not owner/accent accuracy estimates. Current public read-speech replay has zero guarded false wakes in 1,991 valid clips / 2.737 hours; 712 clips exceeding the nine-second input limit are excluded. The raw spotter still has two detections in the full 2,703-clip replay; the onset/bounds guards reject them.

This is not an owner-identity gate, and an actual “Hey Luma” spoken on a call can activate it. Microphone-off remains the reliable choice during such calls. No speech recording, transcript, private signing key or public speech corpus is included in the release.
