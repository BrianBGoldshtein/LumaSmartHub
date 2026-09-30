# 0.2.4 working ledger

As of 2026-09-30, this branch is **unreleased**. The owner's Pi is still on 0.2.3. Do not call any source-only change a physical fix.

## Implemented locally

- `bluetooth_runtime.py`: bounded trusted-phone LE reconnect/service repair for stalled `ServicesResolved` **and** resolved-without-ANCS; accepts ANCS source appearing before BlueZ's flag; optional data failure no longer discards mandatory notification authorization; privacy still requires successful Notification Source subscription. See [Bluetooth recovery](V024_BLUETOOTH_RECOVERY.md).
- Local phrase matching: “what time is it,” “what is the time,” and “what's the time” converge on the same `time` answer. The existing offline neural intent matcher is now visible through a local no-execution phrase preview in Hey Luma setup. This preview does not calibrate the microphone.
- Version declaration raised to 0.2.4.
- Bluetooth and voice targeted tests passed on Linux. After the reconnect-race additions, the full Linux backend suite passed **1,014 tests** on 2026-09-30. Frontend tests passed **130/130**, and the production build succeeded (with a non-blocking bundle-size warning).
- The separate offline Kristin voice asset is source-included, SHA-256 pinned and Ed25519 signed in a local test package. Its signature and all 12 entries verified against the image-pinned public key. The image's ARM64 Python 3.13 imports its runtime; the real persistent worker accepted a JSON request and produced a valid 22.05-kHz mono WAV under emulation. This is not a physical speaker or latency test.
- An **unpublished** 0.2.4 `.lup` test bundle was rebuilt after the Bluetooth race fix and verified against the image-pinned key: version 0.2.4, 31 entries, 1,187,444 bytes. Nothing has yet been offered to the owner's Pi.

## Still required before a stable GitHub release

- Finish ARM64 worker/install/preview and fallback qualification for the separately signed offline female voice; the physical speaker, latency and memory/thermal behavior cannot be accepted remotely.
- Audit the expanded offline command library/held-out phrasing variations and privacy rules; exercise phrase preview with the real microphone and speaker.
- Complete any committed UI visibility/harmony work included in 0.2.4 scope, with all-theme visual checks.
- Verify the full 0.2.3→0.2.4 update and rollback against a disposable Pi image, including preserved settings and successful/failed progress; do not assume the physical GitHub updater works merely because it found a version.
- Build and sign the exact `.lup` with the **offline** Ed25519 key. Push a feature branch, run CI, then publish stable `main`/GitHub Release only after all release gates. Record release checksums and Pi acceptance.
- On hardware, repeat phone Bluetooth off/on, out-of-range/return, Pi reboot, and ANCS authorization tests. The owner should report the exact status and recovery time if privacy does not reopen.

The user explicitly authorized a narrow stable `main` exception for an earlier 0.2.2 update; do not treat that as an automatic waiver of test gates for 0.2.4. The owner subsequently asked for 0.2.4 via the GitHub updater; ensure the release is actually safe before publishing.
