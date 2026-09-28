# Luma Smart Wall Screen

**Local voice library:** say “Hey Luma, what time is it?”, “What's the weather today?”, or “When is my next event?” See [all supported questions](docs/VOICE_LIBRARY.md), also available under Hey Luma → Things you can ask in setup. Recognition, answers and speech use no cloud AI or tokens; existing weather/calendar sync supplies the data. This source addition will ship in the next image.

**Latest source addition:** [Night & wake](docs/NIGHT_DISPLAY_IMPLEMENTATION.md) is connected end-to-end: themed dim clock, saved preferences, silent five-minute scheduled sunrise and explicit20-second wake, with privacy-safe recovery. Its software checks are separate from the deferred physical panel tests. This too must be included in the next image build.

**Development/update workflow:** source for the signed, rollback-capable app updater is ready for the next fresh image (version0.2.0). It keeps releases separate from durable settings and refuses dependency or database-schema changes. See [signed updates](docs/UPDATE_DEPLOYMENT.md). The old commissioning image predates it. A Linux GitHub Actions workflow is prepared at the repository root, but awaits connecting this local repository to GitHub; no signing key is put in CI.

Luma is an appliance-style, wall-mounted dashboard for a Raspberry Pi 4, a 2048x1536 touchscreen, and a ReSpeaker 2-Mics Pi HAT.

**Current delivery caution:** the full expansion is being implemented. Live testing also found a missing WebSocket runtime dependency, now fixed in source. The historical image below predates that fix, guided setup and timers; **do not use it as the final build**. The next image must be rebuilt and qualified with a real WebSocket check, not only HTTP health. Hardware testing remains deferred.

**Source update, September 26:** the source and local preview now include resumable, theme-matched guided setup, [focus timers](docs/FOCUS_TIMER.md), opt-in [weather hints](docs/WEATHER_NUDGES.md), private [leave-soon reminders](docs/DEPARTURES.md), and [two-way calendar-backed to-dos](docs/TODO_CALENDAR.md) with explicit optional Google edit permission. See [first boot](docs/FIRST_BOOT.md) and the [expansion/onboarding plan](docs/EXPANSION_PLAN.md). These changes are **not yet in the image below**; a new image build and qualification must package them. The full expansion is still in progress.

This directory contains the source package and delivery artifacts. The latest [software-checked candidate](image/tailscale-20260926/README.md) is `image/tailscale-20260926/luma-pi4-UNVERIFIED.img.xz`, with matching checksum and validation records. It includes default-on Hey Luma, optional private iPhone commands through Tailscale, and the manual device checker. Older voice/OAuth images remain preserved. Physical testing is deferred until the owner's prompt; this is not a physically qualified production release. When ready, write the exact image using Raspberry Pi Imager's **Use custom** workflow after reading the [flashing precautions](docs/FLASHING.md). Copying these source files onto a blank card cannot make it bootable.

## Contents

- `source/`: dashboard, backend, hardware services, and tests.
- `image-builder/`: pinned Raspberry Pi OS build recipe and provenance checks; future upstream package downloads are not bit-for-bit pinned.
- `docs/`: flashing, onboarding, Google, iPhone, operation, recovery, and troubleshooting guides.
- `image/`: generated compressed image, checksum, and build manifest.
- `CURRENT_STATUS.md`: concise current restart point, active build, constraints and remaining gates.
- `docs/REQUIREMENTS_STATUS.md`: requirement-by-requirement implementation inventory and remaining software versus owner-deferred physical checks.
- `docs/SOFTWARE_AUDIT.md`: completed non-hardware review, exact-file evidence, device-specific concerns and optional next-feature ideas.
- `PROGRESS.md`: durable engineering ledger and restart point.

Do not put Wi-Fi passwords, Google tokens, API keys, PINs, or personal calendar data in this folder. Those are collected on the device during first-boot onboarding.
