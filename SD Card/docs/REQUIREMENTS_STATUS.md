# Requirements and remaining delivery work

## Current source and delivery state — September 29, 2026

The selected source feature set is integrated into the r9 development image:
guided setup, local voice, calendar and tasks, timers, reminders, night display,
transit, room devices/scenes, encrypted settings backup, signed app-only
updater, Pi Connect enrollment and the optional Levoit `Luma-Devices` hotspot.
The hotspot is off unless explicitly enabled, requires active upstream internet
plus a separate AP-capable USB radio, and uses a private NetworkManager
shared/NAT subnet. Campus policy, adapter compatibility and real Levoit
onboarding are not established; see [CAMPUS_NETWORK.md](CAMPUS_NETWORK.md).
Feature 6 remains excluded. Tetris timing remains frozen.

Current source evidence: **989 Linux backend tests and 957 Windows backend
tests (32 Linux-only skipped)**; the focused Linux USB inventory module passed
8/8. Frontend: **124 tests** and the TypeScript/production build passed. The
Windows image-builder suite passed **25** and skipped **14** requiring native
Linux tools. The r9 candidate at
`image/r9-campus-network-20260929/luma-pi4-UNVERIFIED.img.xz` has source
fingerprint `42fbff0042504530c6dc0651a82fe30ef893009c2f059dca4390c330d8052`
and SHA-256
`77de4675402120626c167a7b393d595398d5facb44d5b23e0170626b9f0ba147`.
Windows independently hashed the artifact. XZ integrity, raw partition and
wireless/recovery package checks, and all **170** mapped application/configuration
file hashes passed. The r8 QEMU backup-socket and Pi Connect checks are
historical and were not repeated for r9. These checks do not prove physical
boot, screen/touch/audio, removable-media, or live network/provider behavior.
The build manifest says `boot_verified=false`; the exact raw-image audit says
`hardware_qualified=false`.

An isolated feature branch is prepared for publication; hosted CI has not run.
No GitHub Release was created and no Pi was updated or reflashed. The existing
Pi state remains untouched.

### Remaining gates

- Owner-controlled final-image flashing and physical acceptance. Do not flash or
  change connected hardware until the owner explicitly starts that test.
- Resolve whether Stanford/venue IT permits a personal NAT access point on
  the chosen upstream, then provide a compatible second USB Wi-Fi adapter.
  Test campus internet availability, isolated DHCP/NAT, upstream continuity,
  reboot recovery and actual Levoit/VeSync pairing. Visitor portal sessions
  and service restrictions may prevent cloud setup.
- Complete any remaining room-device/scene review and test the real purifier,
  independently controlled fans, phone, USB media, power-loss recovery,
  physical screen/touch/audio, memory and thermal behavior.
- Restore Git history/remote reachability and publish the already-authorized
  development branch; run hosted CI. Keep `main` untouched until the agreed
  hardware acceptance and v1 approval. Preserve the release-signing key off
  GitHub.
- Finish owner setup later: calendars and Google write consent, transit
  choices/token, Levoit model/enrollment, exact Woozoo models/remotes, scene
  choices and backup passphrase. Enter credentials only on the Pi/provider.

See [EXPANSION_PLAN.md](EXPANSION_PLAN.md) for the source-versus-acceptance
matrix. The remaining sections below are a historical implementation
chronology; the current status checkpoint in [CURRENT_STATUS.md](../CURRENT_STATUS.md)
and this dated summary are authoritative.

## Historical: September 29 GitHub-backed Settings updater

The source provides a local-only Settings check for the latest
stable GitHub Release. It downloads the exact versioned `.lup` asset, validates
release metadata/checksum and the image-pinned Ed25519 signature, presents the
release notes for review, then sends it to a root-owned socket broker that uses
the existing atomic install/health-check/rollback path. It never installs raw
branch files. The private signing key remains on WSL, not GitHub. `main` remains
the accepted release channel after owner-approved hardware acceptance; CI on
feature branches does not publish or sign releases. The UI/API and systemd
broker are included in r7. No GitHub Release was created and no Pi was updated.

## September 29 Pi Connect recovery update

The full-image source includes touch/mouse-based Pi Connect
enrollment, with an owner-approved Raspberry Pi account, a local short-lived
QR, explicit remote-shell opt-in, disabled screen sharing and a dedicated
admin user. The isolated QEMU setup broker check passed; physical boot and
enrollment remain unqualified. The signed app-only updater cannot add its
required OS package/account/systemd units. See [PI_CONNECT.md](PI_CONNECT.md).

## Archived implementation chronology (historical; current status is above)

Native free voice questions are implemented; see [voice library](VOICE_LIBRARY.md). Earlier test counts below describe prior checkpoints only. Real microphone/speaker qualification remains required.

### September 26 source additions (written before r6)

These earlier notes describe source additions made on September 26. Focus timers, weather hints, leave-soon reminders, night clock/wake, guided extras and the calendar-backed to-do refinements are all included in r7; physical display/provider acceptance remains outstanding.

At that checkpoint, resumable guided onboarding had passed 272 backend and 72 frontend tests. Its current implementation is in r7. Details: [onboarding QA](ONBOARDING_QA.md); see the top of this file for the current full-suite totals.

The selected expansion features and their future setup cards are specified in [EXPANSION_PLAN.md](EXPANSION_PLAN.md). The plan is not an implementation-completion claim. Older “complete non-hardware review” language below applies to the prior delivered candidate, not this expanded backlog.

Checkpoint: September 25, 2026. This is the implementation inventory. The completed non-hardware review is in [SOFTWARE_AUDIT.md](SOFTWARE_AUDIT.md); physical acceptance remains deferred. The owner's latest direction is to finish non-hardware work and defer physical testing until explicitly prompted. Earlier blocked/hardware-wait entries in the historical ledger no longer control the work.

## Implemented and image-integrated software, awaiting real-device acceptance

| Requirement | Current implementation and evidence location | Remaining evidence |
| --- | --- | --- |
| Pi 4 appliance OS and boot-to-dashboard | `image-builder/luma.yaml`, installer, LightDM/labwc and systemd services; previous exact image passed isolated ARM64 API/database boot smoke | Latest voice/Tailscale image and software checks passed; visible Pi kiosk/performance later |
| Time, weather/current-day forecast, Google agenda/current event and calendar-derived tasks | Frontend `main.tsx`; backend calendar logic and Google/Open-Meteo adapters; integration/domain tests | Owner Google consent and actual forecast/account checks on device |
| Google calendar/event colors | Direct Google Calendar integration retains calendar colors and event overrides; frontend agenda uses them | Actual account visual confirmation |
| Sleep Time plus touch/voice morning/night overrides | State-machine/calendar/runtime/command tests; device power bridge and touch wake | Panel HDMI-off/wake behavior and actual sleep events |
| Cohesive large typography and three complete themes | Local Manrope/Space Grotesk/Newsreader/Pixelify assets, theme styles, prior landscape/portrait visual checks recorded in ledger | Exact panel rendering and distance legibility |
| Full-screen themed interludes and real autoplay games | Interludes, physics, classic games and falling-block engines; 67 frontend regression tests | Physical frame pacing under the whole appliance workload |
| Persistent games, scores, bounded levels and natural paddle behavior | Checkpoint/classics/blocks tests cover resume, losses, rotations, collisions and motion | Tetris pacing is frozen; do not retune during delivery work |
| Pendulum initialization and collision physics | Physics tests cover vertical starts, varied lengths/velocities and isolated elastic conservation | Rendered device performance; constraints/gravity can exchange momentum with supports |
| Default local Hey Luma, guided calibration and wake LEDs | Default-on new Settings, bounded Vosk grammar/audio queue, calibration tests, SPI LED encoder; mute/start/restart regressions | ReSpeaker capture/AEC/far-field accuracy and actual LEDs |
| Siri audio stays on phone | Owner explicitly accepted separate local Hey Luma; Bluetooth audio profiles disabled in installer | Actual advertised services/phone route verification later |
| Nearby-phone privacy and call notification islands | Selected authenticated ANCS subscription, expiring notifications, privacy state machine/PIN, Bluetooth tests | Actual iPhone bonding, range/reconnect and preview permissions; ANCS cannot guarantee cross-app active-call state |
| Surviving reboots/outages without repeated configuration | SQLite FULL/WAL settings/tokens, atomic OAuth state, rolling backups, crash-recovery tests | SD controller/power-cut test later; refresh-token revocation still requires sign-in |
| Stanford Visitor/eduroam onboarding | Manual portal acceptance; pinned Stanford SUNet CA/server profile; touch/native keyboard and status UI; offline NM/profile checks | Actual association/captive portal, external-browser focus and reconnect on campus |
| Recovery and ongoing maintainability | Key-only administrator SSH with per-device host keys; documented backup/restore; source/manifests/SBOM; read-only device checker | Bundled checker verified in the new image; actual recovery/device checks later; no private SSH key in delivery |
| Private iPhone/Siri hub commands | Owner-approved optional Tailscale Personal integration, touch QR enrollment, restricted HTTPS gateway, scoped firewall, disconnect and local token rotation;255backendtests including23transport/token cases | Delivered Tailscale candidate passed offline ARM64 daemon/broker checks; account/certificate/campus/iPhone acceptance after assembly |

## Delivery completion and deferred owner/device setup

1. **Completed:** fresh immutable staging and image with default-on voice, mute safeguards and bundled read-only preflight. New delivery: `image/voice-20260925/`. Older OAuth candidate and evidence preserved.
2. **Completed at the stated software scope:** selected installed runtime/configuration files and the root partition matched staging, isolated 180-second ARM64 smoke returned API/database health and unauthenticated gateway rejection, XZ integrity passed, and the Windows-delivered archive hash matches its portable checksum. Receipts: `image/qualification-voice-20260925/`. These checks do not establish all-files compatibility or physical acceptance.
3. Tailscale approved: optional free Personal transport now implemented in source with touch enrollment/status/disconnect, pinned ARM64 package, scoped firewall and private Serve to the restricted gateway. Tests and fresh image/offline qualification passed in `image/tailscale-20260926/`; owner account/device enrollment remains. No public listener, account creation or hardware testing during development. Local voice/touch/calendar/weather do not depend on it.
4. Exact remote Siri Shortcut recipes are documented in TAILSCALE.md; installing/configuring them requires the owner's iPhone after assembly. Connection/disconnection appliance automations also require actual appliance selection and iPhone configuration. Do not claim an installed companion app, working remote command or appliance automation. A campus VPN connection must never count as nearby presence.
5. **Completed after image integration:** final non-hardware file/software compatibility review in SOFTWARE_AUDIT.md.112 shipped files matched staging; ARM64 binaries/libraries, kernel drivers, installed versions, service/privacy boundaries, notices and documentation were reviewed. Consequential device-specific concerns and optional additional-feature proposals are recorded there. This is not a physical acceptance or blanket upstream vulnerability audit.

## Explicitly deferred, not failed or passed

All actual Pi/display/touch/ReSpeaker/iPhone/campus/power-loss testing waits for the owner's prompt. In particular, panel EDID/DDC behavior, touch rotation/calibration, supported microphone/speaker routes, memory/thermal/frame-rate behavior on the 2 GB Pi, voice range, and campus/iPhone authorization cannot be established by host tests. The existing image is an UNVERIFIED candidate, not a production release. Flashing requires confirmation of the exact target card; copying the source folder onto an unprepared microSD cannot boot it.

Do not turn these deferred gates into repeated status-only blocked turns while independent software/delivery work remains.
