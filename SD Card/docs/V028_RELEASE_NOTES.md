# Luma 0.2.8 Beta

This beta addresses accidental Hey Luma activation and manual-only iPhone reconnection. Install through Settings → Software → Check for updates when this version is published. This is an application update, not an SD reflash. Saved accounts, settings, bonds and games remain on the Pi.

## Changes

- Conversation protection is now the default, including for existing installs. Both final offline transcripts must hear “Hey Luma” near the start before the listening orb or a command activates. Partial guesses, quoted wakes and incomplete/overlong recordings are rejected. A clearly labelled more-sensitive option is available in Voice settings if protection misses your pronunciation.
- Luma advertises an ANCS notification-accessory solicitation while its selected trusted iPhone is absent, allowing an iPhone-initiated BLE connection alongside periodic bonded retries. Explicit LE connection attempts keep discovery active rather than stopping the scan first. Advertising cleans up on connection, forget, shutdown and BlueZ reset. Its status is shown on the iPhone settings panel.
- Privacy still unlocks only after authorized Apple notification access, never from proximity or advertising alone. No Bluetooth calls/music profiles are added. No recordings are saved or uploaded; no paid AI is used.

## What to test

Check clear real wake phrases and normal/Zoom speech separately. The protected filter is not speaker identification: a real wake phrase spoken by someone on a call can still activate Luma. For those calls, turn off the microphone in Voice settings.

Test walk-away/return reconnection with iPhone Bluetooth left on in Settings and Share System Notifications enabled for Luma. Avoid Control Center's accessory-disconnect control during this test. iOS controls whether it reconnects; this beta improves the missing accessory protocol path but cannot promise proximity-only connection on every iPhone.

Software tests do not prove Pi microphone/radio behavior. Report the installed version, wake misses/false activations, and the selected phone's connection/advertising status after returning to range. Do not repeatedly update, forget the phone or erase the SD in response to a failed test.
