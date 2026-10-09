# Beta — Luma 0.3.1

Multi-user Luma for one primary and up to four secondary users. [0.3.1 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.1) and its downloaded package is signature-verified. This is an application update for the existing Pi, not a new OS image or hardware-accepted v1.

## What's new

- Separate named profiles, registered iPhones, Google accounts, calendar/task choices and personal timers. Existing primary settings and credentials remain canonical for rollback.
- Primary-PIN-protected Users setup: approve a new person once, then let them pair their phone, optionally connect Google and choose wall sharing through a saved, guided flow. The primary need not remain nearby for their personal setup.
- Independent live Bluetooth notification authorization and coordinated reconnect attempts. Paired, connecting or cached presence does not expose private information. A disconnected person's information hides immediately.
- All present, configured users have synchronized Calendar and To-do panels: one full panel, two/three columns, four in a two-by-two layout, five as three above two. Timed events retain exact minute positions, hourly rulers and all overlap columns inside the visible panel. Short cards prioritize titles; tap for full details.
- A named connected-user roster, coalesced five-second themed arrival/departure screens and chimes. Quiet display/Sleep/update periods suppress those announcements; stale transitions do not replay after boot.
- Independent personal timers and a shared room timer. Every user may set timers without the primary PIN. Completion alarms last five seconds and remain audible during Sleep unless explicitly muted. Absent owners' private timer names are redacted. Finished timers no longer indefinitely hide later notifications.
- Account-specific spoken calendar/weather briefings use the sole present user, an explicit name or a touch chooser. A spoken name is not an identity credential or permission to change another person's account.
- Own-account Safari/Home Screen remotes and saved personal setup progression. Secondary remotes have no room settings, user administration or software-update controls. Global settings and updates require the primary PIN even on the primary remote.
- A primary-only remote fallback if secondary Tailscale access is impractical. Restricting remotes revokes secondary browser access but keeps their wall profiles, Bluetooth, Google setup and timers. Reenabling requires new browser enrollment.
- Administration rechecks after slow provider work, locks, streamed inputs and cryptographic operations. Expired/locked/rotated approval cannot silently commit a late privileged change. Background workers and independent personal timers remain available.
- Measured clock fitting preserves large themed typography without cutting off wide times on narrow screens. Arcade fitting retains the master pixel unit.

The primary Sleep calendar remains room-wide, including when the primary phone is absent. Google colors, the chosen completed-task color, task ordering/deadline orbs, installed voice/wake assets and existing Pi Connect enrollment are retained. No public Funnel, cloud AI, new database schema, dependency changes or automatic bond reset is introduced.

## Install

**Settings → Luma software → Check for updates → review 0.3.1 → Install**. Keep power and internet connected. A dropped connection or accepted installation request is not success; verify the final installed version is **0.3.1**. Do not reflash the SD card or erase working bonds/accounts.

Release qualification passed 2,151 backend, 201 frontend and 43 packaging tests, both production UI builds and exact-main CI. The same offline-signed archive passed successful installation and forced health-failure rollback using both the current and deployed 0.3.0 updater, retaining synthetic saved settings, secrets, browser grants and games. Luma's production GitHub fetcher downloaded and verified bytes identical to that qualified archive. These checks do not replace the owner hardware tests below.

See [multi-user setup](https://github.com/BrianBGoldshtein/LumaSmartHub/blob/main/SD%20Card/docs/MULTI_USER_SETUP.md) for primary approval, optional Google, private phone access and the primary-only fallback.

## Owner hardware acceptance

Build-host tests do not prove the Pi's radio, audio, real Google consent, Safari storage or actual update behavior. After installation, test saved primary settings, adding one secondary account, automatic disconnect/range return, simultaneous independent authorization, privacy when a user leaves, task edits to the correct account, personal/room timers and alarm sound. Expand to all five phones and reboot recovery before claiming full hardware acceptance. Report the exact version/status if anything fails; do not repeatedly update or erase the card.
