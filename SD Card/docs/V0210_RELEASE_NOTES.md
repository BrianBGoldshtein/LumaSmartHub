# Beta — Luma 0.2.10

Application update for the existing Luma Pi. Not a new SD image or a hardware-accepted v1.

## Changes

- Reconnect Google remains accessible even when an expired/revoked authorization prevents calendars or colors from loading. Saved selections render first; incomplete catalogs cannot overwrite them.
- A structured rejected Google grant or unauthorized API response now shows a renewal-required status. Temporary sync failures retain saved events without falsely declaring a revoked grant. Successful consent or event sync clears the error. Calendar refresh remains every five minutes.
- Bluetooth retries no longer disconnect another pending operation after a terminal BlueZ rejection. Own timed-out/cancelled attempts are still bounded; existing authorized links, bonds and the ANCS privacy gate remain protected.
- Pong now reflects off flat paddle faces at the reflected incident angle rather than replacing it with random/offset steering. Wall and paddle penetration is mirrored; existing pace, smooth paddles, scores, themes and saved games are retained. Normal head-on contact legitimately returns along the same horizontal path.
- Privacy-filtered developer probes and a documented, reversible BlueZ LE experiment are included in the source repository. They are not silently installed OS changes.

## Update

Settings → Luma software → Check for updates → review **Luma 0.2.10 Beta** → Install. Keep power and internet connected through installation and the application service restart. Correction: this version does not automatically reboot the operating system. No SD flash. Google credentials, Wi-Fi, PIN, calendar selections and saved games remain on the Pi. The existing separately signed voice/wake assets are unchanged.

If Google still requests renewal, open Google Calendar setup → **Reconnect Google**, complete consent using the existing OAuth client, then verify the calendar sync succeeds. Do not replace your client JSON or erase saved configuration to recover an expired grant.

## Bluetooth recovery evidence and limits

The owner's Pi established an LE link but failed encryption with **PIN or Key Missing**. A one-time, explicitly confirmed two-sided Bluetooth forget and fresh pairing resolved the owner's automatic-return test. That recovery happened on the device before this release; installing an application cannot repair an iPhone's saved keys. The working new bond should be retained. Luma never automatically forgets, re-pairs or bypasses notification authorization.

The owner's manually enabled BlueZ experimental D-Bus interface is an OS setting and remains outside this app-only update. Do not enable kernel experiments, delete Bluetooth directories or repeat pairing without diagnostic evidence. iOS retains control over accessory reconnection.

## Owner checks after installation

1. Confirm Settings reports **0.2.10** after reboot and saved configuration remains intact.
2. Reconnect Google once if renewal is requested; confirm saved calendars/colors and current events return. A real future refresh-token renewal still needs observation.
3. With iPhone Bluetooth enabled in Settings and Share System Notifications enabled, repeat automatic return without tapping Connect, including after reboot. Report any recurrence; do not reset the working bond first.
4. Watch Pong's oblique and head-on paddle/wall contacts in your preferred themes; verify points continue and saved matches resume.

Source, synthetic SDK/private-D-Bus tests and signed installation/rollback qualification do not prove real microphone, speaker, radio or visual behavior on the Pi. The owner's reported reconnect recovery is one successful hardware test, not a guarantee across all iPhone states.
