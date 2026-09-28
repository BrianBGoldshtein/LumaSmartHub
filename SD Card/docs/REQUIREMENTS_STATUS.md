# Requirements and remaining delivery work

## Current source and delivery state — September 28, 2026

The complete selected feature set is present in the current source: guided
setup, native offline voice questions, calendar-backed tasks, timers,
leave-soon reminders, weather nudges, Sleep/night display and wake ramps,
countdowns, transit, room devices/scenes, settings-only encrypted USB
backup/restore, and the signed app-only updater. This statement means source
implementation, not a blanket qualification: room-device UI/package review
and the backup broker's final-image checks are still open. Feature 6 remains
explicitly excluded. Tetris/game persistence and frozen timing are unchanged.

Software evidence currently recorded: **942 backend tests passed on Linux
in hosted CI; 912 passed / 30 Linux-only skipped on Windows; 112 frontend
tests passed; TypeScript/Vite build passed.** The current Windows results are
from a fresh complete run against this working copy. CI for authorized
feature-branch commit `c613252` is green (run 36488243784). No private signing
or SSH key is in GitHub or source.

A corrected r4 Raspberry Pi 4 image is being built from source fingerprint
`770906ac80b3efc86dfea19bcee93b2b7e7930d7966c22ab65a577a0e6908921` after a
static image audit caught that the rejected r2 candidate lacked the approved
public recovery SSH key. r2 must not be flashed. The r4 build is not complete
until raw-image/file audits and offline ARM64/API/WebSocket checks pass; the
candidate is not yet ready for reflash. No physical flash or hardware test is
being performed.

### Remaining gates

- Finish and record room-device/scene UI checks for errors, reconnects,
  long names, all three themes, narrow/portrait layouts, keyboard and touch;
  then complete Linux/package/real-WebSocket checks for those paths.
- Qualify the settings-only backup broker on the exact image: systemd socket
  activation, installed service UID/peer authorization, packaged API round
  trip, and archive restore/mute/account-preservation behavior. Synthetic
  temporary-media tests have passed; this does not establish real USB-device
  compatibility.
- Complete r4 static/raw-file audit, compressed-image SHA/XZ verification,
  offline ARM64 boot/API/database and denied-gateway smoke, real packaged
  WebSocket push/disconnect, and update the immutable candidate/checksum
  handoff. Never overwrite or flash the owner's card without explicit prompt.
- Hardware remains untested: Pi/display/touch/DDC and power behavior,
  ReSpeaker/AEC/voice range, iPhone/ANCS, Stanford Visitor terms and eduroam,
  authorized Google/VeSync/511 accounts, Woozoo IR independence, USB media,
  2-GB performance/thermal and real power-cut recovery.
- Owner setup inputs are still needed at commissioning: calendar selections
  and optional Google write consent, transit token/stops/directions, VeSync
  enrollment/model discovery, exact Woozoo labels/remotes, scene choices and
  removable-media/passphrase choice. Enter secrets only into the on-device
  setup/provider, never into chat or GitHub.

See [EXPANSION_PLAN.md](EXPANSION_PLAN.md) for the source-versus-acceptance
matrix and the per-feature acceptance contracts. Historical entries below
are chronology and may describe earlier source or image states; this section
and the newest dated [CURRENT_STATUS.md](../CURRENT_STATUS.md) checkpoint are
authoritative.

Native free voice questions are implemented in source; see [voice library](VOICE_LIBRARY.md).516backend/85frontend tests pass; TypeScript/build pass. Real microphone/speaker qualification and inclusion in the final image remain required.

## September 26 source-only addition (not in current image)

Source now includes [focus timers](FOCUS_TIMER.md), opt-in [weather hints](WEATHER_NUDGES.md), private [leave-soon reminders](DEPARTURES.md), [night clock/gentle wake](NIGHT_DISPLAY_IMPLEMENTATION.md), guided extras, and the owner's [calendar-backed to-do refinement](TODO_CALENDAR.md): today-active all-day titles, due dates, one completion color, conditional two-way Google recoloring, explicit permission upgrade and large-type pagination. Night/wake software integration includes exact20-second/5-minute ramps, overlap/DST handling, private recovery, nonblocking verified DDC handoff and browser/API checks. These are not physical display qualification. Complete expansion remains active: features7/8/9/10 and a new qualified image remain, plus explicitly deferred hardware acceptance.

Resumable guided onboarding is implemented and software-tested: themed first-run steps, essential/optional separation, SQLite progress, review/revisit, unsaved touch-edit warnings, local-only API and preserved mute/privacy. Backend 272 tests and frontend 72 tests pass. Details: [onboarding QA](ONBOARDING_QA.md). A new immutable image build/software qualification is still required to include it; physical acceptance stays deferred.

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
