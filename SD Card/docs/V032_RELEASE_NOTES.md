# Beta — Luma 0.3.2

[Luma 0.3.2 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.2). It restores cohesive, glanceable layouts and makes future phone-started updates visible on the wall. This is a signed application update for the existing Pi, not a new OS image or hardware-accepted v1.

## Changes

- Home appointments use a clear time column beside large titles. To-do rows fill the available width instead of forming a narrow centered stack. A sole viewer's name stays in the corner roster rather than appearing as a second large heading. Shared panels retain compact names so information remains attributable.
- Hearth, Luma Glass and Neon Grid share consistent layout hierarchy while retaining their own fonts, tones and shapes. Arcade task typography and spacing follow the pixel unit. Dense four- and five-user task panels show two entries per slide; every task remains in the cycle, with outstanding tasks ordered by due date and completed-only slides cycling faster.
- Calendar hour rulers reserve the actual width of the loaded theme font, including after resizing or late font loading. Events no longer cover the hour labels. Exact-minute placement, Google colors and all simultaneous overlaps remain intact.
- An independent wall progress screen observes installation initiated from the primary phone remote, even outside Settings or during guided setup. Progress survives a temporary API restart and stays readable during night/display-off mode. Only the temporary update output is brightened; saved brightness and Sleep settings are unchanged, and private account information is hidden behind the progress screen.
- A successfully installed, health-checked release requests one graceful Pi reboot. A durable marker prevents repeated reboots after ordinary starts or a denied reboot request. Failed updates do not reboot as successful installations. The wall also reloads fresh dashboard HTML after verified completion if a reboot cannot be requested.
- Ordinary phone changes, such as themes and brightness, update live without rebooting. Updates and global room settings still require primary authorization; secondary remotes do not gain those privileges.
- Remote settings tabs wait for an in-progress save response, preventing a fast tab change from being lost when the form refreshes. A delayed-response browser check covers the gap between the wall receiving a change and the phone receiving confirmation.

Game motion, rules and speeds are unchanged. Existing users, Google credentials, calendar/task choices, timers, saved games, Bluetooth bonds and optional remote enrollment remain on the Pi. There are no dependency or database-schema changes.

## Install from 0.3.1

For this first upgrade, use the **wall screen's Settings → Luma software → Check for updates → review 0.3.2 → Install**. The already-running 0.3.1 wall does not yet have the independent progress monitor, so do not initiate this particular upgrade from the phone if you want continuous wall feedback. Once 0.3.2 is installed, future phone-started updates use the new monitor.

Keep power and internet connected through installation and reboot. Verify **Current version: 0.3.2** afterward. Do not reflash the SD card, clear accounts or erase phone bonds. If a failure is reported, record its exact text and version rather than repeatedly pressing Install.

## Qualification and owner checks

Qualification passed 2,163 backend, 203 frontend and 43 packaging tests, both production UI builds and exact-main GitHub CI. The offline-signed archive passed installation and forced health-failure rollback with both the candidate updater and the published 0.3.1 updater. Every synthetic SQLite row was unchanged, including four secondary profiles, scoped Google tokens/caches, paused personal timers, browser grants, settings and games. The production GitHub client independently downloaded, signature-verified and matched the released bytes to that qualified archive.

Synthetic Chromium checks cover 168 multi-user layouts, 120 theme/scene cases, authenticated phone-to-wall setting changes, and global progress during normal, sleeping, display-off and setup views. They do not prove the physical Pi's reboot, screen power handoff, audio, radio or Safari behavior.

After installation, confirm the new Home/Calendar/To-do layouts on your screen, preserved accounts and timers, phone theme changes appearing on the wall, and the post-install reboot returning to the dashboard. On the next release, also check a phone-started update while the wall is outside Settings. See [release evidence](https://github.com/BrianBGoldshtein/LumaSmartHub/blob/main/SD%20Card/docs/V032_WORKING_NOTES.md).
