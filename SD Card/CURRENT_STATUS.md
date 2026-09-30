# Luma development status — 2026-09-30

Luma is a pre-v1 Raspberry Pi 4 appliance. The owner's Pi currently runs the
**0.2.3 application** with saved setup intact. Google Calendar, weather, and
Hey Luma have worked on-device, but hardware acceptance is incomplete.

The [signed 0.2.4 GitHub Release](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.2.4)
was published from the merged, CI-passing `main` branch as an explicitly
approved pre-v1 exception. Its app bundle passed Linux signature, install,
health, rollback, and saved-state qualification. In the first actual Pi
updater trial, however, the screen stalled at **Switching versions**. After
reboot the Pi returned to 0.2.3 and reported “Update failed and automatic
rollback needs local recovery.” The 0.2.4 release directory remains staged.
Do **not** press Update again until the failed service-control path is
diagnosed and a safe recovery is qualified.

The one-shot SD diagnostics confirmed the 0.2.3 app pointer and retained
update failure state. It captured the following boot's journal, not the
original failed-update boot. A second one-shot history collector has been
armed on the owner's SD BOOT volume; its output is pending. See the local
`SD Card/updates/v024-updater-diagnostics/` kit outside this Git repository.

The owner also requested a permanently available diagnostic log on the FAT
BOOT partition. A **future image** candidate now includes an independent,
bounded, privacy-safe service for this purpose; see
[BOOT diagnostics](docs/BOOT_DIAGNOSTICS.md). This system-level feature is not
present on the current 0.2.3 card and is not deliverable in an app-only `.lup`
archive. It must be qualified in a full image or separate no-flash OS-level
migration before being described as installed.

Next: obtain the earlier journal, correct and test the actual updater failure,
recover or supersede the staged 0.2.4 candidate without touching
`/var/lib/luma`, and re-test Bluetooth, voice, Pi Connect, USB, and update
progress on hardware. v1 and any further `main` promotion remain gated on
owner-observed hardware validation.
