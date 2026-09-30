# Luma development status — 2026-09-30

Luma is a pre-v1 Raspberry Pi 4 appliance. The owner's Pi currently runs the
**0.2.3 application**, installed through the no-flash microSD recovery path;
the saved device and account settings remain on that card. Google Calendar and
weather have worked on the Pi, and Hey Luma now responds, but physical
acceptance is **not complete**. The owner reports an iPhone that reconnects
according to iOS while Luma waits for Bluetooth services and remains in
privacy standby. The existing spoken reply still sounds mechanical. Pi Connect
sign-in, USB browsing/backup and the GitHub update path have not yet received
successful owner acceptance after the latest fixes.

## Current 0.2.4 candidate

[Draft PR #2](https://github.com/BrianBGoldshtein/LumaSmartHub/pull/2) is a
feature-branch candidate, **not** a published GitHub Release. It includes
the previously prepared 0.2.3 application work plus these follow-ons:

- Active recovery of a stalled bonded iPhone Bluetooth/ANCS connection, with
  bounded LE discovery and a selected-phone-only service reset. Private
  information remains hidden until ANCS subscription authorizes. See
  [Bluetooth recovery](docs/V024_BLUETOOTH_RECOVERY.md).
- A separately signed, SHA-256-pinned offline Piper/Kristin female voice
  asset, a warm local speech worker, a fallback to the original voice, and
  on-screen install status and sample. The approximately 158 MB asset stays
  outside the app-only bundle and the saved settings database. See
  [offline voice](docs/V024_OFFLINE_VOICE.md).
- More everyday voice phrasings and a safe typed phrase preview for the
  existing offline neural intent matcher. Negated or informational wording
  must never accidentally operate the hub.
- More legible calendar event titles and times at the wall-screen size,
  retaining Google colors, duration-based placement and the themed grid.
- A real-signed-bundle Linux qualification utility for both successful
  switch and health-failure rollback with a saved-state sentinel.

The last committed candidate passed GitHub's software workflow, 1,014 local
Linux backend tests, 130 frontend tests and 43 image-builder tests. A signed
app bundle verified against the image-pinned public key; the ARM64 offline
speech worker produced a valid WAV under emulation. Edits after that CI run
need another full test/build/sign/CI cycle. These software checks do not prove
native Pi Bluetooth, speaker quality, update timing or physical persistence.

## Next release gates

1. Finish the remaining [0.2.4 ledger](docs/V024_PROGRESS.md), rerun the full
   suites and review three-theme/portrait screen captures.
2. Build the exact signed 0.2.4 application and voice assets using the private
   key kept offline; validate the real archive's switch/rollback and retained
   settings. Do not put the key or account credentials in GitHub.
3. Promote to `main` and publish a stable GitHub Release only when the candidate
   is qualified for an owner-supervised updater trial. This is not v1 approval.
4. On the Pi, verify update progress and rollback, Bluetooth off/on and
   out-of-range return, ANCS/privacy, new voice audibility/latency, normal
   microphone wake, and reboot/power-loss persistence. Record failures before
   treating 0.2.4 as accepted.

The prior 0.2.2 publication was a narrow exception to the original `main`
hold. v1 remains unpublished until the full [hardware validation
checklist](docs/HARDWARE_VALIDATION.md) passes. See [requirements
status](docs/REQUIREMENTS_STATUS.md), [the iPhone guide](docs/IPHONE_AND_SIRI.md),
and [update deployment](docs/UPDATE_DEPLOYMENT.md) for standing contracts.
