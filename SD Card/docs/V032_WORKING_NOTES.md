# Luma 0.3.2 visual cohesion and remote update behavior

Status: [0.3.2 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.2), signed offline and independently verified through the production download client. Software release gates are complete. Actual Pi reboot, display handoff and hardware acceptance remain owner-led.

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

## Browser and safeguard checks

203 frontend tests pass; wall and remote TypeScript/Vite builds pass. The synthetic Chromium layout suite passes 168 cases across three themes, one through five configured users, 1024×768 and 2048×1536 wall layouts, evening calendar rulers matching the reported collision, and 320/390px mobile clock cases. New assertions cover actual ruler glyphs, full-width tasks, task contents staying within their cards, and identity attribution. Rendered Hearth, Glass and Neon examples were visually inspected, including dense five-user tasks. These checks do not constitute owner hardware acceptance.

The focused reboot/display set passes 12 tests, covering one-time success reboot, failure/installing/idle suppression, active-release matching, denied reboot without rollback or retry loops, unsafe-marker/unmanaged-path rejection and temporary night output with private-data redaction. The complete suite also covers the existing protected installer and API behavior. Actual Pi reboot and systemd permissions still require owner hardware confirmation.

The isolated production wall monitor passes simulated external installation during guided setup, malformed/outage status retention, failure dismissal, verified completion, and fresh-HTML navigation. No update, real account, radio operation or hardware reboot occurs in this browser test.

## Final candidate checks

The final clean-main publisher passed all 2,163 backend tests in 336.33 seconds, all 203 frontend tests and 43 packaging tests, plus both production UI builds. The latest 168-case layout run is `/tmp/luma-031-user-setup.tC5q3ATV`.

The broader audit passed 120 cases across all themes and every ambient scene, plus weather, countdowns, transit, controls, presence and voice islands (`/tmp/luma-031-user-setup.UBwFckDM`). Selected rendered controls, games and primary/secondary remotes were visually reviewed. Game rules and speeds were not changed.

The authenticated synthetic remote lab passed live phone theme changes reaching the separate wall browser and phone-started installation appearing on that wall (`/tmp/luma-030-mobile.B5MByQi1`). Expanded progress checks passed normal, night-clock, display-off and setup views, outage/malformed-status retention, failure restoration and completion refresh (`/tmp/luma-031-user-setup.x3yzp8L3`). Temporary physical brightness/display output and privacy redaction are covered by four backend cases; saved Sleep/brightness settings remain unchanged.

Release metadata is 0.3.2. Publisher qualification now pins the deployed 0.3.1 tag to `9ca2299074d913829a41d601314082ac1fcf5ed1`, rather than falling back to the old full-image version. Synthetic preservation checks compare the entire SQLite dump, including four secondary users, Google tokens/caches, personal paused timers, grants and games.

The first clean-main remote repeat exposed a settings-tab race: the wall snapshot can arrive before the phone's PATCH response, and changing tabs during that gap was overwritten by the save-triggered form remount. Publication was stopped before signing. Settings tabs now disable while saving. The remote lab injects a 1.5-second response delay before the client captures its transport, checks the disabled controls, then exercises normal calendar navigation. The complete delayed-response run passed with no runtime errors (`/tmp/luma-030-mobile.FhU8iaqe`), followed by a successful repeat against final clean main. Both UI builds and all 203 frontend tests passed after this fix.

## Published package qualification

The signed source/tag is `383552f5f545551f97e6df26574f770bacdc7b1f`; exact-main [CI 37889097051](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/37889097051) passed. Clean Linux signing checkout: `/home/luma-build/luma-032-release.yb2gMYwd/repo`. The existing publisher completed its full local test/sign/qualification path while CI ran independently; log `/home/luma-build/luma-032-release.yb2gMYwd/publish.log`. Both current and exact deployed 0.3.1 installers passed successful switch and forced health-failure rollback with every synthetic SQLite row unchanged. Service controls and health replies in this lab are synthetic, not Pi acceptance.

After both gates passed, publication rechecked clean main, exact head, latest successful CI for that head, ascending unused version/tag, notes matching the committed file, archive signature/hash and current whole-source fingerprint. The qualified archive was uploaded without rebuilding it. The annotated tag remains pinned to that exact source; subsequent documentation-only commits do not move it. No previous asset was replaced and the offline private key was not uploaded.

Final exact-main production wall/remote browser labs passed: `/tmp/luma-031-user-setup.bxc6ksbt` and `/tmp/luma-030-mobile.DEAPjMA4`, logs `/tmp/luma-032-final-main-progress.log` and `/tmp/luma-032-final-main-remote.log`; session `17052` is finished. Both tested the exact compiled candidate from the clean signing checkout. The remote response-delay regression, independent wall progress, primary/secondary authorization and clearing all passed with no runtime errors.

The stable GitHub metadata targets `main`, with title **Luma 0.3.2 Beta**, draft/prerelease flags false. Publication time: **2026-10-09 05:42:00 UTC** (October 8 in the owner's timezone). The production `latest_release('0.3.1')` downloaded and signature-verified bytes identical to the qualified local archive; that fetcher is unchanged from deployed 0.3.1. Checking from 0.3.2 reports current.

- Archive: `luma-update-0.3.2.lup`, **1,920,700 bytes**, **81 signed files**.
- Archive SHA-256: `8571197c8a25b4a0a3a5071bc690ff0ad3c457c6d80fac6606fb9e8391c71ade`.
- Source-input SHA-256: `2e2bedb9ceafdd58d9e171f9bf1eb4350a50a3158d3857c2d232275887458880`.
- Qualified local archive: `/home/luma-build/luma-032-release.yb2gMYwd/luma-update-0.3.2.lup`.
- Production-download report: `/home/luma-build/luma-032-release.yb2gMYwd/download-report.json`.

Session `71688` completed successfully; `17052` is also finished. The earlier aborted publication wait `31726` made no tag or release and must not be resumed. No owner's Pi, settings, account, bond or hardware was modified during qualification.

## Next owner checks

Install through the wall's Settings → Luma software, keep power connected through reboot, verify 0.3.2 and preserved accounts/timers/games. Confirm the new Home/Calendar/To-do spacing and readable rulers on the physical screen, plus phone settings changes appearing live. On a subsequent release, check phone-started progress outside Settings and during Sleep, followed by exactly one reboot and normal return. Report exact version/status on failure; do not repeatedly install, erase the card or infer v1 hardware acceptance from build-host tests.

## Resume paths

Source checkout: `LumaSmartHub-0.2.4` in the project workspace. Disposable frontend build/QA directory: `/home/luma-build/luma-031-release.DG78RE3K/repo/SD Card/source/frontend`; its current files are a copied 0.3.2 development UI, not the immutable published 0.3.1 source. Use the Git tag for baseline qualification.

Qualified Python: `/home/luma-build/luma-030-release.1Wvmksze/venv/bin/python`. Development logs: `/tmp/luma-032-ui-tests.log`, `/tmp/luma-032-ui-build.log`, `/tmp/luma-032-layouts-final.log`, `/tmp/luma-032-progress.log`, `/tmp/luma-032-backend.log`. Final layout output: `/tmp/luma-031-user-setup.39sVHqLI`; reviewed screenshots: `/tmp/luma-031-user-setup.BPFvPWfm`. Progress QA: `/tmp/luma-031-user-setup.PIEDEukD`. Owner previews are saved outside the repo under `SD Card/previews/0.3.2`. The offline signing key remains local and must never be printed or uploaded.

Important first-upgrade limitation: the already-running 0.3.1 wall lacks the global update monitor. Start its upgrade from the hub settings page to retain the existing visible progress surface. After 0.3.2 loads, future phone-started installations can use the always-mounted monitor. Do not claim that existing 0.3.1 clients gain this UI before they install it.
