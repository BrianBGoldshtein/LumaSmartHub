# Luma 0.3.5 Beta

This [signed application update](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.5) adds the full primary iPhone settings experience, optional USB fan switching and an idle mouse cursor. Keep the existing SD card and saved configuration; no reflash is needed. Install from Settings → Luma software → Check for updates → review 0.3.5 → Install. Keep power connected through the successful-update reboot, then verify the installed version and saved state.

## Primary iPhone settings

Open the private remote → Settings and unlock with your primary PIN. All hub settings now use the same screens as the wall, including guided setup, secondary users, Google calendar choices, voice calibration, Bluetooth pairing and forgetting, private networks, extras, backups and signed updates. Quick display and calendar controls remain available below the shared settings.

Sensitive changes need a recently entered PIN and explicit review. Network, phone or PIN changes may disconnect the remote. Reconnect and check the result before retrying; uncertain changes are never automatically replayed. A secondary remote retains only that user's personal controls and timer.

Google consent on a phone uses a Google Web application client and the exact private HTTPS redirect URI shown in setup. The existing Pi Desktop client and Google links are preserved. Each secondary user signs into Google on their own enrolled remote; their consent is separate from the primary account. Voice checks listen through the Pi microphone, not Safari. USB backups use the drive and game saves on the Pi, not the phone.

## Optional USB fan cooling

USB power stays on by default. This is coarse on/off control, not variable voltage or fan-speed PWM. On a compatible Pi 4, all four USB ports switch together; the mouse and other USB peripherals stop working while off.

1. Set the fan's physical switch to a quiet speed and provide an inlet and exhaust through the enclosure.
2. Open Settings → USB cooling from the primary remote. Remove USB storage before testing.
3. Run the five-second test. Confirm only if the fan physically stopped and restarted and USB devices recovered.
4. Enable Automatic only after that confirmation. Use Keep USB on whenever you need uninterrupted peripherals.

Automatic power comes on at 60°C and can turn off at 50°C or lower after at least sixty powered seconds. Off periods last at most sixty seconds, followed by a powered discovery window. Detected USB storage, backup work, an update, missing temperature or expired API heartbeat keeps or restores power. Switching errors disable automatic mode and attempt restoration. A newly plugged drive cannot be detected until USB power returns.

Firmware and real switching remain hardware checks. Reported hub power bits are not fan RPM or a physical voltage measurement. A hard-killed controller or kernel/hardware failure cannot guarantee power restoration. If the test fails, keep the fan powered continuously. Changing the fan requires repeating the physical test.

## Mouse cursor

The wall cursor disappears after twenty seconds of mouse inactivity. Movement, clicking or scrolling brings it back. This applies to Luma's window, not separate operating-system applications.

## Owner checks

After installation and the automatic successful-update reboot, confirm version 0.3.5, saved Google calendars, all user profiles, Bluetooth presence, voice replies, games and timer sound. On the primary iPhone, check guided setup and secondary-user enrollment; verify that secondary remotes cannot open administrator settings. Test physical cooling last, with storage removed and the phone remote ready.
