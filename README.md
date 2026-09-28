# Luma Smart Hub

Luma is a custom, privacy-conscious wall dashboard for a Raspberry Pi 4. It is
designed around a square-ish 4:3 touchscreen and a glanceable, large-type
interface—not a general-purpose desktop. The app combines themed time, weather,
Google Calendar and tasks with optional local voice, phone presence, timers,
sleep-aware display behavior and room automations.

> **Project status: development / pre-release. This is not v1.** The working
> software is on a feature branch; `main` is intentionally left at its initial
> README until the owner has completed hardware testing and is happy to publish
> v1. The Pi, display, touch, audio, campus network, phone and appliance paths
> still require physical acceptance. Do not treat a successful software test
> or an `UNVERIFIED` image as that acceptance.

## What it does

- Cycles through high-contrast, themed glance screens, with a full day agenda
  that can fit a busy schedule. The dashboard supports several coordinated
  visual themes and full-screen ambient scenes/games.
- Reads weather forecasts from Open-Meteo and Google events from the selected
  calendars. A separate Google Calendar can supply all-day tasks; a chosen
  event color marks completion and, with explicit Google edit consent, Luma can
  recolor a task when it is checked off. A user-selected calendar supplies
  timed events titled `Sleep` for night display behavior.
- Offers **Hey Luma** as a local, bounded voice command system. It does not
  need AI tokens or a cloud language model; wake phrase and command audio are
  processed on the Pi. Siri remains on the iPhone; optional Apple Shortcuts
  send approved hub commands to Luma.
- Uses nearby-phone presence as a privacy gate for personal dashboard details.
  When the phone is away, the intended standby view is time and weather without
  private calendar/task information.
- Keeps settings and integration tokens in local SQLite storage across normal
  restarts. App-only releases use a signed updater with health checks and
  automatic rollback; the updater does not replace the operating system or
  database schema.
- Includes software paths for scenes and supported room-device integrations.
  Actual Levoit model/API behavior and the exact Woozoo models, remotes and IR
  hardware must be confirmed and tested before promising appliance control.

See [`SD Card/README.md`](SD%20Card/README.md) for the software overview and
[`SD Card/docs/REQUIREMENTS_STATUS.md`](SD%20Card/docs/REQUIREMENTS_STATUS.md)
for implementation boundaries and unverified hardware gates.

## Hardware

The project is designed for this owner-selected set:

- **Raspberry Pi 4 Model B**, USB-C powered. The appliance image targets Pi 4
  ARM64 hardware, not a Pi 5 or a desktop PC.
- **Thinlerain 9.7-inch 2048×1536 4:3 touchscreen monitor**, with its own
  display power. Video needs the correct Pi **micro-HDMI** to monitor
  **mini-HDMI** cable/adapter path; touch uses a separate USB data connection
  from the Pi to the monitor's touch port.
- **Seeed ReSpeaker 2-Mics Pi HAT V1 / WM8960** on the Pi's 40-pin header. The
  image uses the V1 device-tree overlay; the TLV320-based V2 is not compatible
  with that configuration. Fit or remove the HAT only with the Pi powered off.
- **128 GB SanDisk High Endurance microSD** for the operating system and local
  application data. Keep backups separate; no SD card is immune to failure.
- Suitable Pi USB-C supply (the hardware brief specifies at least **5 V / 3.5
  A**), the display's independent power supply, video cable/adapter, and touch
  USB cable. An audio speaker/amp is needed if the selected HDMI/HAT output
  does not feed a suitable speaker. Check total USB/power load before wall
  mounting.
- A ventilated enclosure with Pi clearance for the HAT, cable bends, cooling
  and a secure wall mount is required for permanent installation. It is not
  required for initial bench bring-up.

No extra GPU, cloud-AI subscription, Home Assistant server or second Pi is part
of the current design. Optional later room-device hardware is documented in
[`SD Card/docs/HARDWARE_ADDITIONS.md`](SD%20Card/docs/HARDWARE_ADDITIONS.md);
that document is research/compatibility guidance, not a verified purchase list.

## Getting started

For an owner setting up the appliance:

1. Wait for an explicitly handed-off image that matches the current software
   and read its `README`, SHA-256 file and build manifest. The source folder by
   itself is **not** a bootable SD image.
2. Use Raspberry Pi Imager → **Choose OS → Use Custom** and select the exact
   `.img.xz` provided with that handoff. Select and verify the intended card
   carefully: writing erases it. Skip Imager's OS customization; Luma has its
   own user and key-only administration setup. See
   [`SD Card/docs/FLASHING.md`](SD%20Card/docs/FLASHING.md).
3. With power off, connect the ReSpeaker HAT, display video, touch USB, audio
   output and power. Boot with a temporary keyboard/monitor if needed while
   the final display cabling is unavailable.
4. Complete Luma's guided setup: choose a theme, connect a permitted network,
   set location/timezone and fallback PIN, then optionally connect Google,
   choose agenda/task/sleep calendars, pair the iPhone, and calibrate Hey Luma.
   Google and device accounts are not baked into the image. On Stanford
   Visitor, the owner accepts the network terms; Stanford eduroam uses the
   owner's SUNet identity. Follow
   [`SD Card/docs/CAMPUS_NETWORK.md`](SD%20Card/docs/CAMPUS_NETWORK.md).
5. Verify the assembled hardware with synthetic data first, then use the
   acceptance checklist in
   [`SD Card/docs/HARDWARE_VALIDATION.md`](SD%20Card/docs/HARDWARE_VALIDATION.md)
   before adding private accounts or mounting the hub unattended.

The owner has explicitly deferred physical hardware testing. Until prompted,
do not flash a card, assume SSH or Wi-Fi works, enroll an account, or represent
an emulator/checklist result as a real-device test. Detailed first-run
instructions are in [`SD Card/docs/FIRST_BOOT.md`](SD%20Card/docs/FIRST_BOOT.md).

## Development and maintenance

The runtime is a local FastAPI/Python service, React/TypeScript kiosk UI and
SQLite-backed state. Image construction uses the project Linux builder; tests
run on GitHub Actions for the backend (including Linux-only integration tests),
frontend, production UI build and image-manifest tools. Required public assets
are regenerated from checksum-pinned sources in CI. **CI has no updater signing
private key and does not publish a trusted image or update bundle.**

The feature branch currently under development is
[`codex/luma-updater-ci-20260928`](https://github.com/BrianBGoldshtein/LumaSmartHub/tree/codex/luma-updater-ci-20260928).
`main` remains untouched. In-place update scope, signing-key custody,
verification, rollback and recovery are documented in
[`SD Card/docs/UPDATE_DEPLOYMENT.md`](SD%20Card/docs/UPDATE_DEPLOYMENT.md).
Build-host setup is in
[`SD Card/docs/BUILDING_THE_IMAGE.md`](SD%20Card/docs/BUILDING_THE_IMAGE.md).

The intended release sequence is: finish software and image checks → owner-led
physical acceptance → resolve remaining issues and repeat checks → owner
approves a v1 → merge the feature branch to `main` and tag that release. Until
then, treat all builds as development/commissioning candidates, not production.
