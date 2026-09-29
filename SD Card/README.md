# Luma Smart Wall Screen

**Local voice library:** say “Hey Luma, what time is it?”, “What's the weather today?”, or “When is my next event?” See [all supported questions](docs/VOICE_LIBRARY.md), also available under Hey Luma → Things you can ask in setup. Recognition, answers and speech use no cloud AI or tokens; existing weather/calendar sync supplies the data. Included in the r10 candidate.

**Night & wake** is connected end-to-end: themed dim clock, saved preferences, silent five-minute scheduled sunrise and explicit20-second wake, with privacy-safe recovery. Its software checks are separate from physical panel tests. Included in the r10 candidate. Newer source-only room-device work fixes nested setup scroll, immediately disables stale purifier controls after a provider failure, keeps unknown IR outcomes visible and permits explicit review of stale iPhone scene grants. It is **not in r10**; another image build is needed before testing that UI on the Pi.

**Development/update workflow:** Settings can check the latest stable GitHub Release, verify its signature, show release notes, and install through a rollback-capable updater. GitHub carries versioned `.lup` release assets; the Pi does not run `git pull` or trust raw branch files. The Ed25519 signing key stays on the Linux build machine and is not in GitHub Actions. The r10 candidate includes this UI and its protected root broker. No signed release has been published or tested on the Pi. See [signed updates](docs/UPDATE_DEPLOYMENT.md).

Luma is an appliance-style, wall-mounted dashboard for a Raspberry Pi 4, a 2048x1536 touchscreen, and a ReSpeaker 2-Mics Pi HAT.

**Current delivery state:** the newest full-image candidate is r10 at `image/r10-candidate-a79f7f4-20260929/luma-pi4-UNVERIFIED.img.xz` in the user-visible output folder; the archive is intentionally excluded from GitHub. Read the [candidate handoff and receipts](image/r10-candidate-a79f7f4-20260929/README.md). SHA-256: `a00f122c34f02a6d83ca08b78dad9f5cd62a590eb2d89c4fa99acfbad8b3c278`. XZ/checksum, source fingerprint, raw partition/package checks and a 170-file exact-image audit passed. Two disposable QEMU-overlay checks passed: the backup socket returned an empty USB inventory to authorized `luma`, and Pi Connect's local broker reported a fresh, unsigned-in device after API/database health. This is not full/physical boot acceptance; the manifest remains `boot_verified=false` and the audit `hardware_qualified=false`. The Levoit AP stays off until the actual Stanford/venue network owner approves it, and requires a second AP-capable USB Wi-Fi adapter. Physical boot, touch, audio, USB media, campus forwarding, adapter compatibility and Levoit enrollment remain untested. See [current status](CURRENT_STATUS.md) and [hardware validation](docs/HARDWARE_VALIDATION.md).

The r10 image includes resumable, theme-matched guided setup, [focus timers](docs/FOCUS_TIMER.md), opt-in [weather hints](docs/WEATHER_NUDGES.md), private [leave-soon reminders](docs/DEPARTURES.md), and [two-way calendar-backed to-dos](docs/TODO_CALENDAR.md) with explicit optional Google edit permission. See [first boot](docs/FIRST_BOOT.md) and the [expansion/onboarding plan](docs/EXPANSION_PLAN.md). Hardware/provider acceptance remains owner-directed and outstanding.

This directory contains the source package and preserved historical delivery artifacts. The r10 file is a development candidate, not a production release. It predates the source-only room-setup fix above. Physical acceptance remains owner-controlled. If/when the owner authorizes the test, write the exact handed-off image using Raspberry Pi Imager's **Use custom** workflow after reading the [flashing precautions](docs/FLASHING.md). Copying these source files onto a blank card cannot make it bootable.

## Contents

- `source/`: dashboard, backend, hardware services, and tests.
- `image-builder/`: pinned Raspberry Pi OS build recipe and provenance checks; future upstream package downloads are not bit-for-bit pinned.
- `docs/`: flashing, onboarding, Google, iPhone, operation, recovery, and troubleshooting guides.
- [Raspberry Pi Connect recovery access](docs/PI_CONNECT.md): r10 includes the screen-based setup flow; it remains unlinked with remote shell off until owner enrollment.
- `image/`: generated compressed image, checksum, and build manifest.
- `CURRENT_STATUS.md`: concise current restart point, active build, constraints and remaining gates.
- `docs/REQUIREMENTS_STATUS.md`: requirement-by-requirement implementation inventory and remaining software versus owner-deferred physical checks.
- `docs/SOFTWARE_AUDIT.md`: completed non-hardware review, exact-file evidence, device-specific concerns and optional next-feature ideas.
- `PROGRESS.md`: durable engineering ledger and restart point.

Do not put Wi-Fi passwords, Google tokens, API keys, PINs, or personal calendar data in this folder. Those are collected on the device during first-boot onboarding.
