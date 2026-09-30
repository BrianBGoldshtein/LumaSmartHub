# 0.2.4 working ledger

As of 2026-09-30, this branch is **unreleased**. The owner's Pi is still on 0.2.3. Do not call any source-only change a physical fix.

## Implemented locally

- `bluetooth_runtime.py`: bounded trusted-phone LE reconnect/service repair for stalled `ServicesResolved` **and** resolved-without-ANCS; accepts ANCS source appearing before BlueZ's flag; optional data failure no longer discards mandatory notification authorization; privacy still requires successful Notification Source subscription. See [Bluetooth recovery](V024_BLUETOOTH_RECOVERY.md).
- Local phrase matching: “what time is it,” “what is the time,” and “what's the time” converge on the same `time` answer. The existing offline neural intent matcher is now visible through a local no-execution phrase preview in Hey Luma setup. This preview does not calibrate the microphone.
- Version declaration raised to 0.2.4.
- Bluetooth and voice targeted tests passed on Linux. The expanded held-out command tests include everyday variants and explicit negation/informational cases, so a phrase such as “don't set brightness to zero” cannot accidentally execute. The full Linux backend suite passed **1,039 tests** on 2026-09-30. Frontend tests passed **130/130**, image-builder tests passed **43/43**, and the production build succeeded (with a non-blocking bundle-size warning).
- The separate offline Kristin voice asset is source-included, SHA-256 pinned and Ed25519 signed in a local test package. Its signature and all 12 entries verified against the image-pinned public key. The image's ARM64 Python 3.13 imports its runtime; the real persistent worker accepted a JSON request and produced a valid 22.05-kHz mono WAV under emulation. This is not a physical speaker or latency test.
- An **unpublished** 0.2.4 `.lup` test bundle was rebuilt from the latest local source and signed with the offline key: version 0.2.4, 31 entries, 1,187,607 bytes, SHA-256 `11de5f78cc8a80edafb621f0553df4ccc56229fc17b76df6c97e2f8a5a7b92e5`. Nothing has yet been offered to the owner's Pi.
- A new update-bundle qualification tool exercised that exact signed bundle with a synthetic, credential-free 0.2.3 installation: signature verification, copy/install/switch/health success, and forced health-failure rollback all passed; the saved-state sentinel survived both paths. The tool is not a substitute for a physical Pi update.
- The local release helper now runs image-builder tests, qualifies the exact newly signed `.lup` from the owner's actual 0.2.3 starting version, and verifies every signed voice file against the image public key before asking for final publish confirmation. Its Bash syntax and branch safety gate passed locally; the helper still needs a clean, green `main` checkout and authenticated GitHub CLI to publish.
- Calendar short-card layout was visually checked at 1024×768 with the demo short-event fixture. Full event title and time now fit in the arcade theme without breaking its pixel grid; other themes and portrait layouts received representative visual checks.

## Still required before a stable GitHub release

- Finish ARM64 worker/install/preview and fallback qualification for the separately signed offline female voice; the physical speaker, latency and memory/thermal behavior cannot be accepted remotely.
- Exercise phrase preview and spoken command variations with the real microphone and speaker.
- Repeat bundle qualification after any further source changes; do not assume the physical GitHub updater works merely because it found a version.
- Build and sign the exact `.lup` with the **offline** Ed25519 key. Push a feature branch, run CI, then publish stable `main`/GitHub Release only after all release gates. Record release checksums and Pi acceptance.
- On hardware, repeat phone Bluetooth off/on, out-of-range/return, Pi reboot, and ANCS authorization tests. The owner should report the exact status and recovery time if privacy does not reopen.

The user explicitly authorized a narrow stable `main` exception for an earlier 0.2.2 update; do not treat that as an automatic waiver of test gates for 0.2.4. The owner subsequently asked for 0.2.4 via the GitHub updater; ensure the release is actually safe before publishing.
