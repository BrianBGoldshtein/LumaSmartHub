# Luma Smart Hub

Luma is a custom, privacy-conscious wall dashboard for a Raspberry Pi 4. It is
designed around a square-ish 4:3 touchscreen and a glanceable, large-type
interface—not a general-purpose desktop. The app combines themed time, weather,
Google Calendar and tasks with optional local voice, phone presence, timers,
sleep-aware display behavior and room automations.

> **Project status: development / pre-release — not v1.** `main` remains the
> untouched starter release until the owner has completed hardware testing,
> reviewed the results, and approved publishing v1. The Pi, display, touch,
> audio, campus network, phone and appliance paths still require physical
> acceptance. Software tests and images marked `UNVERIFIED` do not satisfy
> that gate.

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
  restarts. The Settings screen can check the latest stable GitHub Release,
  verify its image-pinned signature and show release notes before install.
  App-only releases use health checks and automatic rollback; they do not
  replace the operating system or database schema. Pi Connect remains the
  recovery route.
- Includes software paths for scenes and the Levoit purifier integration.
  Actual Levoit model/API behavior must be confirmed on hardware before
  promising appliance control.

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
- Optional Levoit internet sharing: a second, Linux-supported USB Wi-Fi
  adapter with AP mode on its own physical radio. The Pi's built-in Wi-Fi
  stays connected to Stanford as the upstream; its one radio cannot safely
  provide this AP at the same time. Adapter compatibility must be verified
  before buying or relying on the feature.
- A ventilated enclosure with Pi clearance for the HAT, cable bends, cooling
  and a secure wall mount is required for permanent installation. It is not
  required for initial bench bring-up.

No extra GPU, cloud-AI subscription, Home Assistant server or second Pi is part
of the current design. Optional later room-device hardware is documented in
[`SD Card/docs/HARDWARE_ADDITIONS.md`](SD%20Card/docs/HARDWARE_ADDITIONS.md);
that document is research/compatibility guidance, not a verified purchase list.

## Getting started

For an owner setting up the appliance:

1. Read the [r11 candidate handoff](SD%20Card/docs/R11_HANDOFF.md), its
   SHA-256 and build manifest. The source folder by itself is **not** a bootable
   SD image. If the card already contains your Google/Tailscale setup, first
   make and verify a private full-card backup or explicitly accept setting up
   those accounts again; flashing does not migrate saved state.
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
   The current r11 development image candidate includes NetworkManager's Wi-Fi
   supplicant backend and screen-based [Raspberry Pi Connect recovery
   access](SD%20Card/docs/PI_CONNECT.md), which remains off until the owner
   enrolls it. It also includes the optional, PIN-gated `Luma-Devices` hotspot
   for a compatible Levoit: upstream must already work and a separate AP
   adapter must be installed. Stanford's approval and real campus forwarding
   have not been verified. See
   [`SD Card/docs/CAMPUS_NETWORK.md`](SD%20Card/docs/CAMPUS_NETWORK.md).
5. Verify the assembled hardware with synthetic data first, then use the
   acceptance checklist in
   [`SD Card/docs/HARDWARE_VALIDATION.md`](SD%20Card/docs/HARDWARE_VALIDATION.md)
   before adding private accounts or mounting the hub unattended.

Physical qualification is owner-controlled. Do not flash a card or represent
an emulator/checklist result as a real-device test. Detailed first-run
instructions are in [`SD Card/docs/FIRST_BOOT.md`](SD%20Card/docs/FIRST_BOOT.md).

## Development and maintenance

The runtime is a local FastAPI/Python service, React/TypeScript kiosk UI and
SQLite-backed state. Image construction uses the project Linux builder; tests
run on GitHub Actions for the backend (including Linux-only integration tests),
frontend, production UI build and image-manifest tools. Required public assets
are regenerated from checksum-pinned sources in CI. **CI has no updater signing
private key and does not publish a trusted image or update bundle.**

The newest full-image candidate is [r11](SD%20Card/docs/R11_HANDOFF.md),
SHA-256 `585e06340ac8001de20d62ea71460ee8aac8073d09737d1df2e4beed0be00f62`.
Its source passed [hosted CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36636971459):
996 backend, 131 frontend and 47 image-builder checks, plus the production UI
build. XZ/checksum, source fingerprint, raw partition and package checks, an
exhaustive 171-file image audit, and disposable QEMU checks of the backup and
Pi Connect setup brokers passed. The image manifest still says
`boot_verified=false` and its audit says `hardware_qualified=false`: these are
software checks, not physical Pi/campus/Levoit acceptance.

Newer source fixes scene cancellation reporting and protects unsaved private
Shortcut permissions in the editor. It is not in r11; see
[`SD Card/CURRENT_STATUS.md`](SD%20Card/CURRENT_STATUS.md) before choosing an
image for testing.

The device checks signed releases targeted to `main`, not raw branch files;
the private signing key stays on the Linux build machine and outside GitHub.
Development changes are pushed to `codex/luma-r7-levoit`; `main` must remain
untouched until hardware acceptance and explicit owner approval. No signed
application release has been published or installed on the Pi yet.
In-place update scope, release publishing, verification, rollback and recovery are documented in
[`SD Card/docs/UPDATE_DEPLOYMENT.md`](SD%20Card/docs/UPDATE_DEPLOYMENT.md).
Build-host setup is in
[`SD Card/docs/BUILDING_THE_IMAGE.md`](SD%20Card/docs/BUILDING_THE_IMAGE.md).

The intended image sequence is: owner reviews the current image handoff and
chooses when to flash it, then completes hardware acceptance. Later
ordinary application changes should use signed in-place updates, preserving
settings and Pi Connect enrollment; OS/security or platform changes may still
require an image. After the owner approves v1, merge the feature branch to
`main` and tag that release. Until then, all builds remain development/
commissioning candidates, not production.
