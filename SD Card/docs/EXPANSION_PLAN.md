# Luma expansion and guided setup plan

Updated September 29, 2026. This is the durable implementation plan and current source-status index; it is not a claim of physical-device acceptance. The owner selected features **1, 2, 3, 4, 5, 7, 8, 9 and 10**; feature 6 (meeting/focus-mode integration) is excluded. Guided onboarding and the optional setup cards are implemented in source.

Current source is newer than every generated image candidate. See
[CURRENT_STATUS.md](../CURRENT_STATUS.md) for the active release gate. Older
image archives are historical and must not be flashed as this source build.
The scene editor permits explicit reauthorization of a stale remote grant
after current purifier review; physical touch and account acceptance remain open.

## Current acceptance ledger

| Scope | Source state | Software evidence | Still outstanding |
| --- | --- | --- | --- |
| Guided onboarding, core hub, native voice questions, calendar tasks, timer, leave-soon, weather hints, night clock/wake, countdowns and transit | Integrated in r9; the USB-inventory fix is included | GitHub Actions passed on commit 7a5a918 (Linux backend, frontend tests/build, image-builder/recovery/packaging); local backend 957 Windows passed/32 Linux-only skipped | Actual Pi/account/provider checks remain |
| Purifier, local/automatic scenes, voice scene actions and separately consented iPhone scene allowlist | Implemented in source; scenes deliberately empty/off until owner configures them | Mocked adapter/runtime/API/scene tests and partial rendered browser checks; see [ROOM_DEVICES.md](ROOM_DEVICES.md) and [SCENES.md](SCENES.md) | Remaining all-theme/error/reconnect/touch review; real VeSync/phone/network acceptance |
| Optional Levoit internet-forwarding Wi-Fi AP | `Luma-Devices` 2.4 GHz WPA2 hotspot included, off by default; shared subnet/NAT via NetworkManager | Unit/API security checks, fixed profile and dependency audit; runtime fails closed without live upstream and a second AP-capable physical radio | Stanford/venue permission, compatible USB adapter, campus NAT policy, and actual Levoit/VeSync onboarding and forwarding |
| Encrypted settings-only USB backup/restore | Source flow and protected root broker; discovery accepts actual USB transport/sysfs identity even when a flash drive reports `RM=0`, and excludes all partitions on the physical system disk; included in r9 | Encryption/schema/security tests plus regressions for false `RM` and USB system-disk sibling exclusion; exact r9 QEMU overlay received `{"volumes":[]}` as authorized Luma UID | Actual removable media/export/restore and power-loss recovery |
| Signed in-place application updater | Implemented in source and included in r9; this is app-only, not an OS updater | Windows/Linux signature/tamper/rollback tests and exact staged-broker audit; see [UPDATE_DEPLOYMENT.md](UPDATE_DEPLOYMENT.md) | GitHub release publication and Pi deployment/recovery check |
| Fresh Pi image | r9 candidate built from the USB-inventory-fixed source and current campus policy warning | Source fingerprint, byte-identical raw/archive check, 170-file map, package audit, XZ/checksum, raw partition checks and exact r9 backup/Pi Connect QEMU assertions passed. Manifest says `boot_verified=false`; image audit says `hardware_qualified=false` | Owner-directed physical bring-up; no card was changed |
| Physical acceptance | Not qualified; test timing remains owner-controlled | No r9 physical-device pass claimed | Display/touch/DDC, ReSpeaker/audio/wake range, iPhone/ANCS, campus Wi-Fi/portal/eduroam and NAT, compatible USB AP, Levoit, power-loss, 2-GB performance/thermal, appliances and USB |

Do not treat an onboarding “configured” marker, synthetic test or successful image build as a hardware/provider pass. Preserve private keys and credentials outside source, image and CI. Do not flash until the owner explicitly asks to begin hardware testing.

## Non-negotiable constraints

- Owner addition implemented in source: free native [voice question library](VOICE_LIBRARY.md) for weather, next/today/tomorrow calendar, ongoing events, outstanding/due tasks, timer status, time/date and help. No AI tokens/cloud fallback; preserve privacy and existing offline speech stack. Included in final-image scope alongside selected numbered features.

- Raspberry Pi 4 / existing memory and hardware budget; keep FastAPI, React, SQLite and one kiosk browser. No additional Home Assistant server, MQTT stack or cloud language model required.
- Hardware exists, but physical test timing is owner-controlled. Do not flash, purchase equipment, enroll accounts or claim device acceptance until the owner asks. Configuration and software tests are separate from physical qualification.
- Preserve saved games, scores, settings, account tokens, privacy and microphone-off choices. **Tetris timing is frozen.** Do not retune it during this work.
- Local Hey Luma is default-on for new installs; optional phrase checks assess recognition/levels, not personalized voice-model training. Audio remains local/in-memory. Siri stays on the iPhone; Shortcuts are supported commands, not Siri-exclusive Bluetooth audio routing.
- Stanford Visitor requires owner acceptance of portal terms; eduroam uses the Stanford SUNet certificate profile. Never bypass certificate checks or automatically accept terms. Do not assume campus peer-to-peer or IoT connectivity works.
- Phone/PIN presence gates private information. Tailscale transport, a remote command, restored settings or a completed setup step never count as physical presence.

## 0. Guided first-run setup — implemented foundation

### Flow and visual contract

Four stages: **Welcome → Essentials → Make it yours → Ready**.

1. Welcome: live theme choice, clear local/privacy explanation, current Hey Luma state and immediate microphone-off control.
2. Essentials: network (including offline continuation), location/timezone/display/speaker, optional fallback PIN. Each is its own page; save changed fields before continuing.
3. Optional connections: Google Calendar, nearby iPhone, local voice check, private Siri Shortcut transport. Each has Continue, Set up later, and Finish the rest later. Pairing/calibration must finish or be cancelled before advancing.
4. Review: actual saved configuration status, deferred steps and revisit controls. Finishing only dismisses onboarding; it does not manufacture provider health or hardware-test passes.

Reuse existing setup panels and real APIs rather than duplicate account/network logic. Keep large titles, readable short instructions, minimum 48px wizard actions, consistent theme tokens and the existing Google calendar colors. Hearth uses its serif headings, Glass its existing clean typography, Neon Grid its pixel typography and integer spacing. Setup scrolls vertically for touch entry; the normal kiosk does not. No new gameplay styling or timing changes.

### Persistence, privacy and recovery

- Local-only `GET/POST /api/v1/onboarding`; versioned SQLite cache record contains only a whitelisted current step and `reviewed`/`later` statuses. It stores no form drafts, passwords, PINs or account data. Existing providers own successful credential persistence.
- Save after each navigation transition; restore after restart. Reopening does not erase configuration. Existing completed installations are not forced through setup again; All settings exposes guided setup.
- Changed location/PIN/calendar fields warn before leaving, including on-screen keyboard edits. Explicit save clears the warning. Browser reload/exit warns about unsaved edits; secrets remain memory-only until submitted to their dedicated secure local endpoint.
- Errors remain on the current step, with retry or offline/defer choices. Only explicitly finishing Review sets `onboarding_completed`. Skipping voice calibration does not mute an enabled microphone; mute is a separate, explicit action.
- Google consent returns through the existing callback page, then **Continue guided setup** restores the saved step. Portal terms and account consent belong to the owner. Do not put tokens in URL parameters or progress records.
- Demo is isolated: preview navigation uses a separate localStorage key and no real configuration writes. It says sample preview rather than connected/verified. Real progress uses SQLite, not browser storage.

### Extension contract for all future features

After the essentials, add a single **Choose your extras** screen with short, optional categories: Daily rhythm; Dates & travel; Room devices; Recovery. Do not lengthen the mandatory flow as features grow. The owner selects categories, then sees one configuration task at a time. Keep **Set up later** throughout. Existing users get a dismissible **New features available** entry in settings, never a forced first-boot replay.

Each feature declares: stable ID/schema version; availability/capabilities; prerequisites; local vs cloud disclosure; public/private default; durable non-secret settings; validation; setup status; optional connection check; retry/defer and disconnect route. Statuses distinguish **Not set up / Saved for later / Configured / Connection checked / Needs attention / Unavailable on this device**. Avoid a single misleading green tick.

- Daily rhythm: timer defaults → leave-soon calendar/buffers → weather-nudge thresholds → night clock/brightness → exact morning ramp behavior. Preview day/night without silently changing real display power.
- Dates & travel: manual countdowns first; Google-linked dates only when connected; transit token entered locally, then agency/stop/direction picker and optional live-data check. Missing feeds get honest fallback copy.
- Room devices: explain campus network prerequisite → VeSync enrollment → discover/select Core 300S → supported controls → build scenes → review triggers. No scene is enabled by connecting the purifier alone.
- Recovery: explain settings-only scope → choose a verified removable USB → set an export passphrase in memory → review exclusions → export/verify/eject. Backups never require surrendering accounts or contain raw database exports.
- Final review: which information is public, which account connections work, which features are deferred, which scenes are **disabled**, and which tests await hardware. Start the dashboard even when every optional feature is skipped.

Acceptance: fresh/offline boot, restart every step, return from OAuth/portal, invalid input, provider failures, secret-free progress, saved mute, keyboard-only/touch flow, portrait/landscape and all three themes; deferred hardware checks remain explicit. Save progress at transitions, not every keystroke.

## Shared runtime and UI architecture

### Core to-do calendar refinement — September 26, implemented in source

Owner confirmed that tasks are titles of all-day, possibly multi-day events in one specified Google calendar; every outstanding task occupying today must appear. The last visible Google day is due (API exclusive end minus one day). Default color is outstanding; **only the chosen completed color**, not every custom color, is done. Latest owner preference: hide completed tasks from the rotating to-do slide immediately after confirmed completion or the next Google sync; they remain colored in Google and can be reopened there. Hub completion uses conditional color-only Google patches; manual recoloring syncs back. All outstanding tasks remain reachable with large-type pagination. Setup includes a live event-palette picker and explicit optional write-consent upgrade; privacy/local-only/ETag/offline guards apply. See [TODO_CALENDAR.md](TODO_CALENDAR.md). This source is included in r7; no real-account or hardware acceptance is claimed.

Backend owns timers, reminders, sleep/ramp decisions and integrations; frontend renders timestamps against a clock anchor. Persist meaningful transitions, not each second or animation frame. Use bounded provider timeouts, isolated workers, quotas and backoff. Extend snapshots with timer, departure, nudge, display-mode, countdown, transit and appliance capability state.

Reuse one notification/island design. Priority: active touch controls → timer completion → leave-soon → phone notification → routine status. Do not stack floating widgets. Timer readouts appear on information pages; ambient games stay immersive, except an actual completion may briefly interrupt without resetting game state. Add Transit and Countdowns pages only when configured and populated. Preserve existing cycle durations by default.

Fonts, layout, margins, border treatment and color tokens stay consistent within each theme. Arcade aligns to the master pixel grid. Large numbers and minimal labels; calendar event colors remain provider-authentic. Private pages are redacted on lost presence/control connection. Bound voice/remote commands to named actions and allowlisted device IDs, never arbitrary code, raw IR, credentials or backup paths.

## 1. Focus timer

**Implemented in source and included in r7:** timer runtime, durable state, themed controls, local voice/Shortcut actions, presets in optional setup, and at-most-once sound bridge. Sleep/night-clock/display-off do not suppress a timer the owner explicitly started; explicit hub volume zero does. See [FOCUS_TIMER.md](FOCUS_TIMER.md). Physical speaker audibility and output routing remain for owner testing.

One active timer, Focus 25 / Break 5 presets; touch duration 1–240 minutes. Starting over requires confirmation. Voice durations: 5/10/15/20/25/30/45/60 minutes, plus pause/resume/cancel/show. Freeform labels are touch-only. Ordinary cycling continues. On completion show one island and play one local chime—even in scheduled Sleep/display-off; timer alarms are not deferred or replayed after restart.

Use monotonic time while running and a persisted UTC deadline for restart. Do not replay a late chime after reboot. With an untrusted system clock, pause recovery until time is verified. Test pause/resume, power loss, clock jumps, completion deduplication and replacement confirmation.

## 2. Leave-soon reminders

**Source implemented:** opt-in calendar/buffer setup, private themed notice and per-occurrence edit/snooze/dismiss controls, restart-safe bounded records, freshness/privacy guards and existing-poller integration. See [DEPARTURES.md](DEPARTURES.md). No new permissions, Google writes or travel-time claims. New image and eventual physical acceptance remain outstanding.

Opt-in calendars; departure time = event start minus preparation minus travel. Defaults: 5-minute preparation and 10-minute travel, editable per occurrence. No implicit GPS or route-time claim. Exclude cancelled, declined, all-day, Sleep Time, already-started and virtual-only events unless explicitly included. Retain only minimal virtual/declined booleans needed from Google, not an attendee dossier.

Show from 15 minutes before departure until event start; minimal “Leave in…” / “Time to leave.” Five-minute snooze or dismiss applies to that occurrence. Refreshes honor reschedules/cancellations; earliest qualifying overlapping reminder wins. Private and visual-only by default; remote connectivity cannot reveal it.

## 3. Weather nudges

**Source implemented:** opt-in hint preferences, threshold validation, nullable forecast extensions, DST-safe provider timestamps, pure prioritized rules, themed inline display and optional one-task setup. See [WEATHER_NUDGES.md](WEATHER_NUDGES.md). No additional polling or per-tick writes. A saved preference is not a successful connection test. Old image unchanged.

Extend the existing Open-Meteo 15-minute fetch with hourly apparent temperature, precipitation amount/probability and gusts. Initial editable rules: rain probability ≥50% in the next six hours; gusts ≥25mph; apparent high ≥90°F or low ≤45°F. Prefer rain, then wind, then temperature, with stable wording and one qualified nudge at a time.

Place within Home/Weather, not another floating notification. Missing or stale data means no claim, never “all clear.” This is convenience guidance, not emergency or medical advice. Reuse cached forecasts and do not add a separate frequent network poll.

## 4. Dim night clock

**Implemented in source; image and physical qualification pending:** timing/recovery, verified DDC handoff, service/API/desktop bridge, clock-only themed UI and Night & wake Extras/review. The software headless compositor probe and isolated real HTTP/WebSocket browser wake checks passed; these do not qualify the Pi's physical output. See [NIGHT_DISPLAY_IMPLEMENTATION.md](NIGHT_DISPLAY_IMPLEMENTATION.md) for evidence and remaining gates.

Explicit display modes: day / night-clock / off / waking. During effective Sleep Time show large hours/minutes only, black background, subdued theme text, no seconds, calendar or animated cycling. Initial night brightness 5%, adjustable separately from daytime brightness. Good night enters night-clock; explicit screen-off remains available.

Overlapping sleep events form one effective sleep interval. Never brighten before its end automatically. Preserve darkness/private startup during reboot/reconnect; no sudden private-content flash. Describe software dimming honestly if physical panel brightness is unsupported.

## 5. Gentle wake

Owner decisions: **Good morning explicitly overrides sleep early and ramps over 20 seconds. Scheduled waking starts at the actual end of Sleep Time and takes five minutes; never before.** An explicit command during a ramp starts a 20-second ramp from current brightness; repeated commands must not keep extending it. Good night or off cancels it; manual brightness cancels automatic ramp control.

Scheduled wake is silent. Explicit morning may give one privacy-safe local briefing. Serialize and bound physical DDC updates; use compositor dimming between supported hardware updates, not DDC at animation-frame rate. Test boundaries, DST, overlaps, cancellations and reboot recovery separately from physical panel acceptance.

## 7. Important-date countdowns

**Source and local software integration qualified; included in r7.** Durable dates, private/public snapshots, exact Google pin refresh, slide/picker/Extras/voice and real browser/HTTP/WebSocket persistence/privacy checks are complete. Read [COUNTDOWNS.md](COUNTDOWNS.md) for evidence. Real account/device acceptance remains outstanding.

Up to 12 pinned items: manual date/optional time or specific Google event. Manual annual February 29 uses February 28 in non-leap years. Show days / Tomorrow / Today; timed items use hours during the last day. Maximum three entries per view, paginated with consistent large type.

Google colors and event changes remain intact; stale/deleted links show an honest state. Use on-demand future selection and separate pinned-reference refresh, not bulk year-long calendar synchronization. Private by default, public per item only after opt-in. Voice shows countdowns; touch edits them.

## 8. Transit

Source and local software integration are qualified and included in r7: backend, themed slide/setup, native voice, cycling, onboarding review, real browser/HTTP/WebSocket persistence/privacy/disconnect and error recovery. Read `TRANSIT.md` for contracts/evidence. Real provider access requires owner setup; physical acceptance remains outstanding.

Prioritize Stanford Marguerite and Caltrain; also support available BART, VTA and SamTrans data. Up to six favorite stop/direction groups, three departures per view, large minutes and route badges. Private by default; explicit public opt-in per favorite.

Plan against 511 Transit JSON StopMonitoring/ScheduledStop feeds using an owner-entered token. Enforce a global rolling budget of 55 requests/hour including retries, tests and manual refreshes (under the usual 60/hour allocation; verify actual token terms at integration). Share agency responses where possible; favor the visible Stanford/Caltrain group, rotate the others, cache metadata and pause routine night polling. Discover supported agency IDs from provider metadata.

Clearly distinguish predicted, scheduled and stale. Remove expired departures; after five minutes stale, fall back to still-valid schedules or Unavailable. Marguerite live-feed availability is a capability gate: use available schedules and an official live-map handoff if required, never scraping or fabricated live ETAs. Voice: show transit / next departure. References: [511 transit data](https://511.org/open-data/transit), [Stanford live map](https://transportation.stanford.edu/getting-stanford/marguerite/marguerite-live-map).

## 9. Room appliances and scenes

**Source implementation is integrated, but feature 9 is not fully software-qualified or hardware-qualified.** The pinned pyvesync3.4.2 adapter, durable stores, conservative purifier polling, owner-local bounded APIs, themed setup/control, non-secret onboarding review, local voice scene actions and separately consented remote-scene allowlist exist. “Run … scene” and “cancel scene” use the same owner/device/clock guards; “Good morning” remains the briefing. Remote appliance control stays off unless the owner locally grants exact saved scenes/actions; any edit or device relink invalidates review. Remaining all-theme/keyboard/error UI checks, packaged trigger/integration qualification, Linux/exact-image/real-WS gates and owner hardware/provider acceptance are detailed in [ROOM_DEVICES.md](ROOM_DEVICES.md) and [SCENES.md](SCENES.md). No real provider/account/device acceptance inferred.

### Levoit

Owner clarified **Core 300S / 300S-P**, not yet set up in VeSync. Enroll in the vendor app first, on a permitted network. The source uses a pinned direct pyvesync adapter rather than running Home Assistant on the Pi. This remains a cloud-dependent, unofficial library: handle expiry and breaking changes explicitly; prefer persisted sessions over storing a password. The exact returned API model must still match discovery.

Select the specific purifier; expose only discovered capabilities (power, speed, supported sleep/auto/display options and reported air-quality/filter values). Poll conservatively with backoff. Distinguish command acceptance from reported device state. No queued offline commands that execute hours later. Network compatibility is a prerequisite, not an assumption or permission to bypass campus policy. The r7 source/image also provides the separate optional Levoit 2.4 GHz NAT hotspot documented in [CAMPUS_NETWORK.md](CAMPUS_NETWORK.md); campus permission, AP adapter and VeSync setup still require owner qualification. References: [pyvesync](https://github.com/webdjoe/pyvesync), [VeSync integration capabilities](https://www.home-assistant.io/integrations/vesync), [Stanford student networking](https://uit.stanford.edu/students).

### Scenes

Morning, Night, Arrive and Away editors start empty and disabled. Owner chooses actions and enables triggers explicitly. Distinguish a manual command from optional calendar-triggered scenes. Presence debounce: arrival 30 seconds authenticated nearby; departure three minutes; five-minute cooldown. Boot, token refresh, PIN unlock and Tailscale alone never trigger arrival. Manual device control suppresses that device's scene changes for one hour. Never replay missed scene runs; show partial failures. Remote appliance control is a separate opt-in with an allowlist.

## 10. Settings-only USB backup and restore

Local guided flow: select verified removable USB → scope review → passphrase twice → export → read-back verify → eject. Export only allowlisted appearance/location/timezone/cycles/night settings, presets, local dates, reminder preferences, transit favorites, non-secret scene definitions and validated game checkpoints. Do not export raw SQLite or Chromium profiles. The encrypted serializer, transactional settings-only database apply, USB identity inventory, peer-checked root broker/socket, owner-gated API, expiring preview/apply workflow, browser-local game-checkpoint bridge and themed UI are implemented in source and included in r7; QEMU confirmed an authorized empty-inventory broker response. See [PORTABLE_BACKUPS.md](PORTABLE_BACKUPS.md). Real removable-media discovery/export/restore and power-loss recovery remain outstanding.

Exclude OAuth/VeSync/511/Luma tokens, Wi-Fi credentials, Bluetooth bonds, Tailscale/SSH material, PIN verifiers, client JSON/account metadata, cached private calendar/notification data and audio. Google-linked items restore unlinked; device actions restore disabled pending rediscovery. Keep existing private same-card recovery backups clearly separate from this portable format.

Use versioned authenticated encryption with bounded schema/size checks; passphrase stays in memory. Broker validates actual removable transport and excludes system/boot disks; no arbitrary destination path or formatting. Write a new temporary file, flush, verify and atomically rename without replacing the last good export. Handle removal/full media/failed eject honestly.

Import authenticates and validates before preview/apply. Apply transactionally; preserve current accounts and the most restrictive mic-mute state, never restore presence or fire automations. Optional local reminder after 30 days; no automatic USB writes. Test tampering, wrong passphrase, schema mismatch, interrupted writes and sentinel-secret absence.

## Delivery sequence and acceptance

Owner's final-handoff addition: deliver a clear hardware-to-first-boot guide based on the finalized parts. Cover powered-off wiring, screen/touch/microphone/speaker connections and power requirements, connecting a microSD reader to this Windows laptop, identifying and confirming the exact removable card before flashing, safe eject/first boot, campus network setup, and connecting this laptop to the Pi for supported diagnostics. Clearly separate software-qualified results from owner-authorized physical checks. Include recovery and rollback instructions; never overwrite a card or change hardware before explicit owner readiness. Verify exact wiring against the final hardware revision/manuals before publishing it. This remains a final deliverable.

1. Current source overlay fixes preview-mode “Forget this iPhone”: the demo clears synthetic state without calling the Bluetooth API. Continue the remaining room-device theme, error, reconnect, keyboard and touch review; rerun the full suite after every release change.
2. Validate Levoit hotspot on real hardware only after confirming campus/network-owner permission and selecting a compatible second Wi-Fi radio. Test upstream continuity, isolated DHCP/NAT, restart behavior and actual purifier cloud onboarding.
3. Retain the fresh r9 candidate and its exact-image audit. Do not represent QEMU or synthetic results as physical boot/provider evidence.
4. Code and CI for the current source overlay are published on the authorized feature branch. After owner-approved hardware acceptance, build and sign the app-only `.lup` release using the local Ed25519 key; releases are attached only to stable GitHub Releases.
5. The owner decides when to flash/test. Preserve current Pi configuration and data; do not write a card or change hardware before explicit owner direction.

Remaining owner inputs are configuration, not reasons to invent defaults: permitted purifier network and VeSync enrollment, transit favorites/token, selected calendars and travel buffers, dates, scene actions and backup passphrase. Enter credentials only on the device or official provider, never in chat.

## Arcade animation refinements

Preserve the existing persistent game checkpoints, natural-looking play, gradual/smooth movement, bounded autonomous-player imperfections, and shared theme typography, colors, spacing and layout. Keep the Arcade theme on its single master pixel grid. Tetris must continue its existing gradual score-based speed ramp; this work does not change its established timings or curve.

- Completed in source: Pong's ball is 8% faster on serve and has a correspondingly raised speed ceiling; the current smooth paddle tempo, acceleration, reaction, turn-taking and scoring are unchanged. Versioned checkpoint migration preserves scores and applies the small pace lift once to old saved games. Software tests and rendered themed preview pass; hardware acceptance remains owner-prompt-gated.
- Completed in source: Arcade Snake now overlays its exact 32×20 movement-cell subdivisions in Neon Grid, so the playable cells remain clear when the viewport-scaled game grid differs from the background/Tetris master-grid pitch. The lines share the board's origin, span and theme pixel styling; game rules and other themes are unchanged. Rendered at 1280×720, 2048×1536 and 390×844 without horizontal overflow.
- Completed in source: Space Invaders now appears in each theme's ambient cycle and can be opened directly for preview. The formation moves in rows, reverses and descends at the walls; the ship tracks firing lanes while gliding at constant speed, with direction changes spaced by a cooldown. Evasion compares both headings across each incoming shot's full ship-height crossing window, after normal steering, so a cooldown turn cannot send the ship into a bullet and equal-risk lanes do not trigger pointless reversals. Invaders fire back; hits award classic row-weighted score and cleared waves retain score. A formation breach redeploys only remaining invaders and the player ship, preserving score, wave and lives. Only zero lives ends the run; the restart keeps best score. State is checkpointed, included in encrypted portable backups, and validated by browser and backend schemas. Neon Grid draws the complete 32×20 playfield subdivision in its theme pixel style; all three themes share the same score rail and scene framing.
