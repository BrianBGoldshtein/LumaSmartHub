# First boot and onboarding

This guide describes first boot of the [r13 hardware-test candidate](../image/r13-final-71d91b5-20260930/README.md). It passed software and emulated checks, but its Pi boot, screen, touch, network, audio, microphone, phone and integrations remain physically unverified. Start with display, local input and recovery connectivity; wait to enter personal Google or device-account details until those work. Follow the [r13 test sequence](R13_TEST_SEQUENCE.md) and [current status](../CURRENT_STATUS.md).

In the **Hey Luma** setup section, expand **Things you can ask** for local weather, calendar, tasks, timer and time/date questions. Try “Hey Luma, what time is it?” No AI account or token is needed. Internet is only needed to refresh the existing weather/calendar data; private answers still require your nearby phone or PIN. See [voice library](VOICE_LIBRARY.md).

Luma is designed so account setup happens once and survives normal reboots and sudden loss of power.

### Night & wake (included in the flashed candidate; physical behavior unverified)

In **Choose your extras → Night & wake**, choose a dim clock or a fully-off screen during the timed `Sleep` events from your selected sleep calendar, and save a separate night brightness (initially 5%). Existing saved daytime brightness is unchanged. Without a saved night preference, the dim clock is enabled; disable it here to retain fully-off sleep.

Scheduled wake starts **when the selected `Sleep` event ends**, over five minutes. “Hey Luma, good morning” overrides sleep and brightens over 20 seconds; repeated commands do not extend the ramp. Tap the clock or say “wake screen” for a temporary five-minute wake. “Screen off” stays off until an explicit wake. These commands never unlock private information.

A configured hub stays black until its clock is trustworthy after reboot; explicit touch/voice wake remains available. First-run network setup is exempt so you can connect offline. LCD backlight glow and actual power-off/wake still require the deferred assembled-device check. Software dimming is not a claim of backlight control.

## Guided first-run flow (included in the flashed candidate)

New installations on the flashed image open **Welcome → Essentials → Make it yours → Ready**. Choose a theme, then work through Wi-Fi, location/display/speaker and a fallback PIN. Google Calendar, nearby-phone pairing, Hey Luma calibration and private Siri Shortcut transport follow as optional steps. Use **Set up later** or **Finish the rest later** instead of configuring everything at once. Network access is not required to finish the local setup; online features remain unavailable until connected.

Save changed fields within their panel before Continue. Unsaved location/PIN/calendar edits warn before leaving, including touch-keyboard edits. Finish or cancel pairing/calibration before advancing. Successful settings saves and the current step survive restarts in SQLite. Password/PIN drafts are not checkpointed. Skipping voice calibration does **not** turn off an already enabled microphone; use the explicit microphone-off control.

The final review distinguishes stored settings from physical checks. It does not claim that a selected phone is currently nearby or that display/audio/campus access have passed hardware testing. **Open my dashboard** finishes onboarding. Reopen it from **Device setup → Open guided setup** without deleting existing configuration. Google consent returns to Google setup; its **Continue guided setup** link resumes your saved place. Completed older installations are not forcibly sent through the new wizard.

**Extras → Leave soon** adds optional private reminders from selected Google calendars. Connect Calendar first, then choose calendars and your preparation/travel estimates (initially 5/10 minutes). These are not route estimates. Save preferences; sync failure is reported separately. Details on a reminder lets you snooze, dismiss or adjust that occurrence without editing Google. See [leave-soon behavior and limits](DEPARTURES.md).

The local preview uses `/?demo=1&setup=onboarding`; it cannot connect accounts or change device settings. Its progress is separate from production. The plan for adding optional feature categories without increasing mandatory setup is in [EXPANSION_PLAN.md](EXPANSION_PLAN.md).

Older image candidates are not a substitute for r13; do not infer hardware qualification from a software preview or QEMU check.

## First-run setup checklist

1. Select landscape or either portrait rotation and confirm touch alignment.
2. This deployment uses Stanford Visitor or Stanford eduroam. The r13 image includes a local Wi-Fi picker, on-screen keyboard and manual **Open network sign-in** button; physical verification remains required. Follow [Stanford network setup](CAMPUS_NETWORK.md). For eduroam, select its Stanford SUNet profile and enter your full `SUNetID@stanford.edu` and password on the Pi; its official CA/server settings are built in and cannot be bypassed. Visitor terms are accepted by you in the separate browser. Ethernet is an optional recovery route, not assumed available here.
3. Choose the home location and timezone. Coordinates are stored locally and sent only to Open-Meteo for forecasts.
4. Create a 4–8 digit fallback PIN.
5. Import a Google OAuth desktop-client JSON file, sign in, and approve read-only Calendar access.

   **r13 USB retest:** The image includes and audits Debian's `polkitd`, which r12 omitted. Insert the stick and try opening it in the native file chooser. If “polkit authority not available and caller is not uid 0” still appears, report it; do not apply the old r12 install workaround blindly or post the OAuth JSON.
6. Select all calendars shown on the agenda, the calendar used for to-dos, and your separate sleep calendar containing daily timed events named `Sleep`. No sleep calendar selected means no automatic sleep schedule. The sleep event title is case-insensitive and must match `Sleep`.
   For the to-do calendar, choose a completed event color and save. Only that color means complete. All-day tasks appear on each day they occupy; the last visible day is due. Optionally choose **Enable task updates with Google** for explicit event-edit consent, allowing Luma checkboxes to recolor tasks. Existing read-only access still reads completion colors. See [to-do details](TODO_CALENDAR.md).
7. Use **Device setup → Your iPhone → Find my iPhone** with iPhone **Settings → Bluetooth** open. Compare and confirm the code on both screens; enable notification sharing if iOS offers it. See the [pairing guide](IPHONE_AND_SIRI.md). Touch pairing is packaged but still needs real-device qualification.
8. Pick HDMI or the ReSpeaker HAT as the speaker output, then run the microphone and echo-cancellation test.
   **Hey Luma is on by default on new installs.** Audio is processed locally in memory, not recorded or uploaded. In **Device setup → Hey Luma**, inspect **ReSpeaker capture** and use its saved gain control (start at `39`), then select **Check my voice** and say the three displayed phrases from your usual room distance. These test phrases never change actual volume, brightness or theme. A check lasts up to two minutes and allows retries. Quiet/clipped signals prompt capture-gain or placement adjustments; repeat afterward. This is a recognition/level check, not personalized model training. Only aggregate results and levels are saved. **Turn microphone off** disables voice and preserves that choice across restarts/upgrades; older saved configurations lacking a voice setting remain off until enabled. The desktop bridge stops the microphone service on its next polling cycle (normally about two seconds); the API immediately rejects late voice commands and cancels calibration. Touch remains available; remote Siri Shortcuts require the separate secure transport. Real HAT capture, speaker routing, range and mute behavior still need hardware testing.
9. Optional remote Siri Shortcuts: follow [Private iPhone commands](TAILSCALE.md) to enroll with the free Personal plan using the hub's touch setup. The r13 image contains the Tailscale setup components, but no account or device is enrolled. Do not use shared-network HTTP or expose the loopback API on Stanford Wi-Fi. Local touch and Hey Luma are independent of Tailscale. Account sign-in and actual iPhone/campus checks happen after assembly.

Settings, refresh tokens, cached weather/calendar data, and the PIN verifier live in `/var/lib/luma/luma.db`. The directory is readable only by the `luma` service account. SQLite uses WAL journaling and full synchronous commits. No Google password is ever stored.

### Touch input and theme

Current source includes themed on-screen entry for location name, decimal coordinates, timezone, new/unlock PIN, advanced paired-phone address and sleep-event title. Tap the field or **Type on screen**. Use **Clear**, backspace and **Done**; text keys edit at the cursor or replace selected text. PINs use a digit-only keypad, remain masked, and are cleared from the field after submission. Coordinates require both values or two blanks. Device/Google setup inherit the selected dashboard theme; original Google calendar colors remain unchanged.

These in-app keyboards do **not** operate Google's sign-in page, the external captive-portal browser, or native file dialogs. Current source also includes **Open system keyboard / Close system keyboard** in Wi-Fi and Google sign-in setup, backed by Debian's `wvkbd` in the non-root desktop session. Tap Open and wait for the keyboard to appear **before** opening an external sign-in page or file chooser. Tap the target field before typing. Luma passes no credentials or text through this control API and disables keyboard output/debug logging. It does not accept terms or submit forms for you.

Close the portal window (or return from Google to setup), then tap **Close system keyboard**. You may use the keyboard's own hide control; opening it again from setup uses a fresh explicit request. Sessions close after 15 minutes or when Luma sleeps; returning to setup lets you reopen one. Colors follow the current Luma theme, with system sans/serif/monospace fonts. A keyboard launch failure appears in device diagnostics. The keyboard is packaged in r13, but native display, focus, touch targets and external-page behavior still require Pi validation. Keep a temporary USB keyboard available until touch-only end-to-end onboarding is qualified.

Upstream references: [Debian wvkbd package](https://packages.debian.org/trixie/wvkbd), [keyboard manual](https://manpages.debian.org/trixie/wvkbd/wvkbd.1.en.html), [version 0.15 command options](https://github.com/jjsullivan5196/wvkbd/blob/v0.15/main.c). The image compiles Debian's checksum-pinned 0.15 source with one documented change: using the Wayland **overlay** layer so the keyboard can appear above the fullscreen kiosk. The executable is `/opt/luma/bin/luma-keyboard`; original source, patch, build recipe and license notices ship in `/opt/luma/third-party/wvkbd`. Do not replace it with the stock top-layer binary without requalifying fullscreen visibility. This is a GPL-3.0 derivative with corresponding source, not a new proprietary keyboard implementation.

## Temporary network recovery route

After booting with Ethernet on the same trusted home LAN, use the dedicated key from this Windows computer's Debian build environment:

```powershell
wsl -d Debian -u luma-build -- ssh -i /home/luma-build/keys/luma-pi-admin luma-admin@luma.local
```

This route still requires a physically booted image and network validation. If `luma.local` does not resolve, use the Pi's address from your router. Check the SSH host fingerprint on the Pi before accepting it; do not disable host-key checking. The private key stays on this computer and is not included in the image.

From that administrator session, `sudo nmtui` opens NetworkManager's interactive network setup. Select **Activate a connection**, select your home Wi-Fi and enter its password there, not in a shell command or this chat. Confirm Wi-Fi connectivity before unplugging Ethernet. NetworkManager saves the connection on the Pi. This is a recovery/workaround path, **not** completion of the planned touch-first onboarding.

## Google token longevity

Detailed setup and calendar-color behavior: [Google Calendar setup](GOOGLE_CALENDAR.md). The preview's sample calendar selector does not authorize an account.

For a personal installation, publish the Google OAuth consent screen to Production after adding yourself as the user. A project left in Google's Testing status may issue refresh tokens that expire after seven days. An unverified personal app may show a warning during sign-in; it can still be used by its owner under Google's user limit.
