# Beta — Luma 0.2.11

Application update for the existing 0.2.10 Pi, not a new OS image or hardware-accepted v1.

## Changes

- Dashboard HTML is not cached. Future successful updates open a fresh, versioned dashboard URL rather than reusing an old entry point; failed updates do not take this navigation path.
- Google setup retains themed recovery controls when local settings fail, offers **Reload Google setup**, uses uncached/bounded requests, and still exposes reconnect when Google calendars cannot refresh. Saved selections cannot be overwritten by an incomplete catalog.
- Kristin preloads and silently warms before microphone capture. Speech plays sentence-by-sentence as audio is generated rather than waiting for a complete multi-sentence WAV. Native thread use is bounded for the Pi 4.
- The corner orb shows thinking while generating speech and speaking after audio is submitted. Interrupted audio is not replayed as a duplicate fallback.
- Settings → Voice → **Last reply timing** shows numeric voice preparation, speaker setup, first audio generation and playback-submission timings. No words or recordings are stored; submission is not proof of sound and total time includes playback.

The Kristin model and acoustic wake sidecars are unchanged and remain pinned to their existing signed releases. Wake protections, phone bonds, Google authorization, Wi-Fi, PIN, themes and saved games are preserved. No database migration, OS configuration change or SD flash is involved.

## Install

Settings → Luma software → Check for updates → review **Luma 0.2.11 Beta** → Install. Keep power and internet connected. Luma restarts its application services; **this release does not automatically reboot the operating system**.

The already-running 0.2.10 interface cannot gain the new navigation before installing it. If the old interface remains visible after successful installation, use the known Pi Connect fresh-window recovery once. Do not clear browser profiles, replace Google JSON, forget the phone, or reflash. Subsequent updates initiated from 0.2.11 use the new versioned navigation.

## Owner checks

1. Confirm software version **0.2.11** and your saved Google/settings/phone state.
2. Open Google Calendar setup from Settings normally; verify it is accessible and calendars sync without repeating already-completed consent.
3. After voice startup, ask “Hey Luma, what time is it?” twice, then try a longer greeting. Confirm Kristin is audible, note the delay, and check **Last reply timing** if it is still long. The first audio is still generated per sentence, not per phoneme.
4. Confirm the orb stays in thinking until playback submission, returns to idle, and does not falsely wake during ordinary speech. Test speaker continuity on longer replies.

Real-model and disposable-browser tests on the build host are not Pi microphone/speaker/radio acceptance. This update removes identified latency costs; it does not promise a measured owner-Pi response time before these checks.
