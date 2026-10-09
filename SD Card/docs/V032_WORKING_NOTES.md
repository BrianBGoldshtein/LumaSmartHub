# Luma 0.3.2 visual cohesion and remote update behavior

Status: final 0.3.2 candidate on `codex/v032-visual-cohesion`; not yet signed or published. Keep 0.3.1 Beta as the current installable release until the remaining release gates pass.

## Required behavior

Restore the glanceable wall layout across Hearth, Luma Glass and Neon Grid. A sole viewer is already named in the corner roster: do not repeat a large name above their calendar or tasks. Shared screens retain compact names, including when several users are present but only one has calendars configured. Preserve all account isolation, authorization, Google colors, task completion and due-date ordering, deadline orbs, sleep behavior, and game rules and speeds.

Home appointments use a clear time column alongside a large title. Task rows fill their panel width instead of centering a narrow column. Four- and five-user task panels show two tasks per slide, retain all tasks across slides, and keep complete-only slides separate for faster cycling. Exact-minute calendar positions and every simultaneous overlap remain unchanged. Reserve the actual painted hour-label width after theme fonts load; event cards must not cover ruler glyphs.

Phone-started software installation must appear on the wall regardless of the current page, guided setup, or sleeping display. Retain progress during a temporary API outage, dismiss it after failure, and show verified completion before a graceful reboot. Only a committed health-checked release may request a reboot. A durable root-owned marker prevents repeating it after ordinary boots or a denied reboot. Ordinary remote settings changes use live snapshots and do not reboot the machine.

## Implemented

- Single-user identity suppression and compact shared identity, without changing corner timer access.
- Full-width task grid and paired time/title home rows. Removed excessive spacing from the new shared layout.
- Reduced dense shared task pagination to two rows; maintained outstanding-first and completed-only grouping.
- Theme-specific typography, warm Hearth cards, quiet Glass cards, and integer pixel typography/spacing for Neon Grid.
- Font-aware calendar gutters for shared and legacy timelines, with late font-load and resize handling.
- Always-mounted wall update monitor independent of the settings page or initiating browser, with outage retention and cache-busting navigation after verified completion.
- Guarded post-upgrade reboot handoff in the newly started protected broker. The existing 0.3.1 installer already restarts this broker after committing success, so this also covers the first upgrade into 0.3.2.

## Verified so far

203 frontend tests pass; wall and remote TypeScript/Vite builds pass. The synthetic Chromium layout suite passes 168 cases across three themes, one through five configured users, 1024×768 and 2048×1536 wall layouts, evening calendar rulers matching the reported collision, and 320/390px mobile clock cases. New assertions cover actual ruler glyphs, full-width tasks, task contents staying within their cards, and identity attribution. Rendered Hearth, Glass and Neon examples were visually inspected, including dense five-user tasks. These checks do not constitute owner hardware acceptance.

34 focused backend updater/API/reboot tests pass. They cover one-time success reboot, failure/installing/idle suppression, active-release matching, denied reboot without rollback or retry loops, and the existing protected installer and API behavior. The actual Pi reboot and systemd permissions still require owner hardware confirmation.

The isolated production wall monitor passes simulated external installation during guided setup, malformed/outage status retention, failure dismissal, verified completion, and fresh-HTML navigation. No update, real account, radio operation or hardware reboot occurs in this browser test.

## Final candidate checks

The full backend development run passed 2,161 tests; two additional reboot edge cases then passed with the focused reboot/display set (12 tests). The final clean-main publisher will rerun all 2,163 backend tests. Frontend tests pass 203 cases and packaging passes 43 cases; both production UI builds pass. The latest 168-case layout run is `/tmp/luma-031-user-setup.tC5q3ATV`.

The broader audit passed 120 cases across all themes and every ambient scene, plus weather, countdowns, transit, controls, presence and voice islands (`/tmp/luma-031-user-setup.UBwFckDM`). Selected rendered controls, games and primary/secondary remotes were visually reviewed. Game rules and speeds were not changed.

The authenticated synthetic remote lab passed live phone theme changes reaching the separate wall browser and phone-started installation appearing on that wall (`/tmp/luma-030-mobile.B5MByQi1`). Expanded progress checks passed normal, night-clock, display-off and setup views, outage/malformed-status retention, failure restoration and completion refresh (`/tmp/luma-031-user-setup.x3yzp8L3`). Temporary physical brightness/display output and privacy redaction are covered by four backend cases; saved Sleep/brightness settings remain unchanged.

Release metadata is 0.3.2. Publisher qualification now pins the deployed 0.3.1 tag to `9ca2299074d913829a41d601314082ac1fcf5ed1`, rather than falling back to the old full-image version. Synthetic preservation checks compare the entire SQLite dump, including four secondary users, Google tokens/caches, personal paused timers, grants and games.

The first clean-main remote repeat exposed a settings-tab race: the wall snapshot can arrive before the phone's PATCH response, and changing tabs during that gap was overwritten by the save-triggered form remount. Publication was stopped before signing. Settings tabs now disable while saving. The remote lab injects a 1.5-second response delay before the client captures its transport, checks the disabled controls, then exercises normal calendar navigation. The complete delayed-response remote run passed with no runtime errors (`/tmp/luma-030-mobile.FhU8iaqe`). Both UI builds and all 203 frontend tests also passed after this fix. Main CI for the preceding source commit passed; rerun exact-main CI for the final fix before signing.

## Remaining release gates

Commit the candidate, fast-forward the authorized main beta channel, pass exact-main CI, then run the clean-main publisher with the offline signing key. Qualify the same signed archive with both current and deployed 0.3.1 installers through success and forced rollback. Publish new assets without replacing 0.3.1, and independently download/verify the production release. Owner confirmation remains required for actual Pi reboot, screen power handoff and real phone/hardware behavior.

## Resume paths

Source checkout: `LumaSmartHub-0.2.4` in the project workspace. Disposable frontend build/QA directory: `/home/luma-build/luma-031-release.DG78RE3K/repo/SD Card/source/frontend`; its current files are a copied 0.3.2 development UI, not the immutable published 0.3.1 source. Use the Git tag for baseline qualification.

Qualified Python: `/home/luma-build/luma-030-release.1Wvmksze/venv/bin/python`. Development logs: `/tmp/luma-032-ui-tests.log`, `/tmp/luma-032-ui-build.log`, `/tmp/luma-032-layouts-final.log`, `/tmp/luma-032-progress.log`, `/tmp/luma-032-backend.log`. Final layout output: `/tmp/luma-031-user-setup.39sVHqLI`; reviewed screenshots: `/tmp/luma-031-user-setup.BPFvPWfm`. Progress QA: `/tmp/luma-031-user-setup.PIEDEukD`. Owner previews are saved outside the repo under `SD Card/previews/0.3.2`. The offline signing key remains local and must never be printed or uploaded.

Important first-upgrade limitation: the already-running 0.3.1 wall lacks the global update monitor. Start its upgrade from the hub settings page to retain the existing visible progress surface. After 0.3.2 loads, future phone-started installations can use the always-mounted monitor. Do not claim that existing 0.3.1 clients gain this UI before they install it.
