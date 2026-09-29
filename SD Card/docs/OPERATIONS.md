# Local operation and recovery

## Setup

Open the controls icon → **Device setup** on the Pi. Set city coordinates, timezone, orientation and a fallback PIN. A city-level location is sufficient. Weather is requested from Open-Meteo every 15 minutes; failed requests retain the saved forecast and mark it stale. Coordinates must be entered or cleared as a pair. Account setup is separate: [Google Calendar](GOOGLE_CALENDAR.md).

The **Device check** button reports database integrity, free storage, provider status, Bluetooth state, and hardware-control results. A control marked unavailable is not silently treated as successful. Brightness depends on the panel supporting DDC/CI. Orientation also needs touch calibration on the real display.

## Backups

Settings and tokens are committed immediately in SQLite, not only periodically. Seven daily backup slots are stored under `/var/lib/luma/backups`. They are on the same card, so they protect against some software failures, **not card failure**. Copy a verified backup to secure off-device storage periodically. Backups contain Google refresh tokens and the LAN command token; never publish them or include them in an image.

On the Pi, with an administrator account:

```sh
sudo -u luma /opt/luma/venv/bin/luma-maintenance check
sudo -u luma /opt/luma/venv/bin/luma-maintenance backup --file /var/lib/luma/manual-backup.db
```

To restore a trusted backup, stop the API (which also stops calendar/weather/Bluetooth workers), then restore and restart. The device bridge and voice service may report connection errors until the API is back; neither writes the database.

```sh
sudo systemctl stop luma-api.service
sudo -u luma /opt/luma/venv/bin/luma-maintenance restore --offline --file /absolute/path/to/trusted-backup.db
sudo systemctl start luma-api.service
```

Restore validates the schema and uses SQLite's backup API, including WAL handling. Never overwrite just `luma.db` while the service is running. Phone connectivity is never restored as proof of presence. Notifications are session-only and are not restored.

### Recovery evidence and limits

`source/backend/tests/test_crash_recovery.py` uses only temporary databases and fake tokens. A child process pauses immediately before or after the actual SQLite commit; the parent forcibly kills it (SIGKILL on Linux, TerminateProcess on Windows), with no graceful rollback/cleanup. Cases cover first database creation, settings plus their audit row, token replacement, and a 2 MiB cache update that demonstrably spills WAL frames. After restart, the database must be intact, values must be wholly old or committed—not partial—and cached weather/events must remain while phone-based private access is cleared. Two additional cases interrupt backup replacement and then restore the surviving verified snapshot.

These tests establish **process-crash recovery**, not physical power-loss immunity. The OS page cache, storage controller and SD card remain powered during them. They do not simulate torn sectors, dishonest flush behavior, filesystem damage, card wear or hardware failure. Physical power-cut tests remain mandatory before wall mounting; keep an off-device backup regardless of test results. Data that had not committed before a failure may legitimately retain its previous value.

## Hey Luma — default local voice

The implementation uses Vosk and sounddevice for local recognition, plus espeak-ng for local speech. This is not Siri and does not change iPhone audio routing. No raw audio or transcripts are persisted by Luma. Recognition runs continuously in RAM when enabled. The owner requested it **on by default for new installs**; the older OAuth image predates this change. A saved off preference survives upgrades/restarts, and older saved settings without a voice field stay off until explicitly enabled.

The image installer includes the voice extra and the checksum-verified `vosk-model-small-en-us-0.15` model at `/opt/luma/models/vosk`. Its license is bundled in `/opt/luma/licenses`. Host-side recognition has been tested, but the real Pi microphone, room acoustics and wake accuracy still need physical qualification. The [official Vosk models page](https://alphacephei.com/vosk/models) documents other models; changing the model is an advanced maintenance operation.

Normal setup does not require downloading a model or installing Python packages. Open **Device setup → Hey Luma** and run **Check my voice**. If previously disabled, enable it first. During the check, the panel reports whether the voice service has checked in and displays a temporary microphone level meter. A service that never checks in indicates startup/capture failure; a live but quiet meter points toward mic selection, connection or capture gain; a strong live meter with no recognized phrase points toward recognition/phrase matching. Audio and transcripts remain in RAM and are not saved; numeric level telemetry exists only during the active check. **Turn microphone off** immediately rejects pending voice commands and cancels calibration; the desktop bridge stops capture on its next poll, normally about two seconds. A failed startup's retry delay does not delay a subsequent off request. This is a software mute, not a physical microphone disconnect.

### Removable USB media in the Google file chooser

Insert the USB drive into a Pi USB-A port before opening the OAuth client-file chooser, then wait several seconds for the desktop volume monitor to notice it. Choose its removable-volume entry in the chooser's sidebar. The image includes `udisks2` for block-device mounting and `gvfs-backends`/`gvfs-daemons` for desktop volume enumeration; listing `/media` in a generic file-browser location is not the normal picker workflow. If the removable drive still does not appear after the corrected image is installed, use **Device check** and report whether the drive appears there; do not reformat it or copy OAuth JSON to an untrusted/shared location.

### Everyday commands

Say “Hey Luma” followed by one of these phrases, or say the wake phrase and then the command within seven seconds:

- “Good morning” — time, available weather and a privacy-filtered day summary.
- “Good night” — put the display to sleep.
- “Show weather,” “show agenda,” “show tasks,” or “show home screen.”
- “Next page,” “previous page,” or “show ambient.”
- “Change brightness” or “change volume” — open the touch slider.
- “Set brightness to fifty” or “set volume to twenty” — set an exact supported level. Spoken levels in the restricted recognizer are zero, ten, twenty, thirty, forty, fifty, sixty, seventy, eighty, ninety and one hundred; use touch for values between them.
- “Change theme to glass,” “change theme to hearth,” or “change theme to arcade.”
- “Privacy” or “hide my calendar” — hide private details immediately.

Local recognition supports these bounded hub controls, not arbitrary questions, message dictation or a general Siri replacement. It never verifies identity or unlocks private data. If it does not understand, repeat a listed phrase or use touch. No phone/VPN/internet connection is needed to recognize these commands; fresh calendar/weather still needs internet access, and private summaries still require the existing nearby-phone/PIN policy.

In a terminal belonging to the **luma desktop session**, inspect devices:

```sh
/opt/luma/venv/bin/python -m sounddevice
```

For advanced capture troubleshooting only, create `/home/luma/.config/luma/voice.env` with the verified capture device and model path. The supplied service sets `PULSE_SOURCE=luma_mic` and `PULSE_SINK=luma_speaker`; verify that the selected PortAudio input actually uses the echo-cancelled source. Keep service enablement under the saved UI switch rather than enabling a second independent startup route.

```ini
LUMA_VOSK_MODEL=/opt/luma/models/vosk
LUMA_MIC_DEVICE=YOUR_VERIFIED_INPUT_DEVICE
LUMA_WAKE_PHRASE="hey luma"
```

The wake gate accepts a phrase plus a command, or a command within seven seconds of the phrase. This is recognizer-based, not a separately trained wake-word model. The bundled small English model includes “Luma”; a restricted grammar covers supported controls plus an unknown-speech alternative. Three synthesized phrases were recognized correctly with this grammar; this is not evidence of across-room accuracy or false-wake performance. Voice never unlocks privacy. Morning briefings use the privacy-filtered snapshot.

Device setup now has an explicit local-voice enable switch and a guided three-phrase check. The desktop bridge starts/stops the user service according to that saved setting; use the UI instead of independently enabling the service. Calibration checks recognition and signal levels, offers capture-gain/placement guidance, and suppresses command execution. Only aggregate results persist; no audio/transcripts do. A few phrases do not retrain the acoustic model. The service drives the three HAT LEDs at low brightness for listening/thinking/speaking, and clears them at shutdown; physical color/wiring qualification is still required.

With the HAT selected in `alsamixer` (F6), adjust its capture controls conservatively while checking the input meter and repeat the guided check. Do not change system-wide gain automatically based on one quiet phrase. Check that normal speech stays below clipping, distant commands are recognized, and speaker playback does not trigger false wake-ups. Recheck after mounting the enclosure.

## Services and security

- System service: `luma-api` owns persistence, periodic sync, backups, presence, and commands.
- Desktop user services: `luma-kiosk`, `luma-device`, optional `luma-voice`.
- The kiosk and bridge use the real desktop environment imported by labwc, not a hard-coded UID or Wayland socket.
- Remote LAN commands require `X-Luma-Token`. PIN, device reports, voice input, and token display are local-only. Browser cross-origin requests are rejected.
- The API defaults to loopback only because this deployment uses shared Stanford campus Wi-Fi. LAN HTTP is not encrypted; do not expose it there or port-forward it. Optional [Tailscale private commands](TAILSCALE.md) use HTTPS to the separate restricted gateway. Account enrollment and real campus/iPhone acceptance happen after assembly.
- [Raspberry Pi Connect](PI_CONNECT.md) is included in the upcoming full-image source as an optional owner-enrolled recovery path. The screen-side enrollment is not present on the card currently being tested. It stays unlinked and remote-shell-off until the owner enables it; it needs Internet access and cannot help before Wi-Fi works.
- Hardware, D-Bus authorization, touch wake, microphone quality, and the image's boot path remain subject to physical qualification.
