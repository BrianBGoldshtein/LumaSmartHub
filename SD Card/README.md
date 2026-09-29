# Luma Smart Wall Screen

**Local voice library:** say “Hey Luma, what time is it?”, “What's the weather today?”, or “When is my next event?” See [all supported questions](docs/VOICE_LIBRARY.md), also available under Hey Luma → Things you can ask in setup. Recognition, answers and speech use no cloud AI or tokens; existing weather/calendar sync supplies the data. Include it in the final planned full image.

**Latest source addition:** [Night & wake](docs/NIGHT_DISPLAY_IMPLEMENTATION.md) is connected end-to-end: themed dim clock, saved preferences, silent five-minute scheduled sunrise and explicit20-second wake, with privacy-safe recovery. Its software checks are separate from the deferred physical panel tests. Include it in the final planned full image.

**Development/update workflow:** the current source adds a Settings control that checks the latest stable GitHub Release, verifies its signature, lets you review release notes, and installs through the existing rollback-capable updater. GitHub carries versioned `.lup` release assets; the Pi does not run `git pull` or trust raw branch files. The Ed25519 signing key stays on the Linux build machine and is not in GitHub Actions. This UI and its protected root broker must be included in the next full-image rebuild; the older installed image cannot add their systemd broker through an app-only update. See [signed updates](docs/UPDATE_DEPLOYMENT.md).

Luma is an appliance-style, wall-mounted dashboard for a Raspberry Pi 4, a 2048x1536 touchscreen, and a ReSpeaker 2-Mics Pi HAT.

**Current delivery caution:** the final planned full-image candidate has not yet been rebuilt or handed off. Historical images predate the Wi-Fi fix, later app work and/or the complete Connect/updater setup; **do not reflash one as the final update**. The current source needs a fresh exact-image build and software qualification. Hardware testing remains owner-controlled.

**Source update, September 26:** the source and local preview now include resumable, theme-matched guided setup, [focus timers](docs/FOCUS_TIMER.md), opt-in [weather hints](docs/WEATHER_NUDGES.md), private [leave-soon reminders](docs/DEPARTURES.md), and [two-way calendar-backed to-dos](docs/TODO_CALENDAR.md) with explicit optional Google edit permission. See [first boot](docs/FIRST_BOOT.md) and the [expansion/onboarding plan](docs/EXPANSION_PLAN.md). These changes are **not yet in the image below**; a new image build and qualification must package them. The full expansion is still in progress.

This directory contains the source package and preserved historical delivery artifacts. None is the final planned image for the present update. The latest source candidate must be built and audited before a flashing handoff. Physical testing remains owner-controlled; a software-qualified candidate is not a physically qualified production release. When ready, write the exact image using Raspberry Pi Imager's **Use custom** workflow after reading the [flashing precautions](docs/FLASHING.md). Copying these source files onto a blank card cannot make it bootable.

## Contents

- `source/`: dashboard, backend, hardware services, and tests.
- `image-builder/`: pinned Raspberry Pi OS build recipe and provenance checks; future upstream package downloads are not bit-for-bit pinned.
- `docs/`: flashing, onboarding, Google, iPhone, operation, recovery, and troubleshooting guides.
- [Raspberry Pi Connect recovery access](docs/PI_CONNECT.md): the final planned full-image source includes a screen-based setup flow; the card currently being tested predates it, and the new image remains unlinked with remote shell off until owner enrollment.
- `image/`: generated compressed image, checksum, and build manifest.
- `CURRENT_STATUS.md`: concise current restart point, active build, constraints and remaining gates.
- `docs/REQUIREMENTS_STATUS.md`: requirement-by-requirement implementation inventory and remaining software versus owner-deferred physical checks.
- `docs/SOFTWARE_AUDIT.md`: completed non-hardware review, exact-file evidence, device-specific concerns and optional next-feature ideas.
- `PROGRESS.md`: durable engineering ledger and restart point.

Do not put Wi-Fi passwords, Google tokens, API keys, PINs, or personal calendar data in this folder. Those are collected on the device during first-boot onboarding.
