# Beta — Luma 0.3.0

Private iPhone remote for the existing Luma Pi. [0.3.0 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.0) after exact-commit CI, offline signing, installation and rollback qualification. This is an application update, not a replacement OS image or hardware-accepted v1.

## New

- A minimal **Safari/Home Screen remote** at the hub's private Tailscale HTTPS address under `/remote/`. Hearth, Glass and Neon use the hub's fonts/colors, large time, concise cards and thumb-sized controls. No games, ambient animations or additional native companion app.
- **Hub:** time/weather, upcoming calendar events, tasks, leaving summary, named timers and wall page/sleep controls. Task completion uses Google's revision checks and the same selected completed color.
- **Settings:** appearance, brightness/volume, weather/timezone, quiet-night/chime options, timer defaults, weather warning thresholds, wall cycle, multi-calendar agenda, task/sleep calendars and leaving-reminder preferences.
- **Software:** verified release review, explicit install confirmation, progress and final-version/rollback feedback. An accepted request or dropped connection is never shown as a successful update.
- Local **PIN-protected enrollment QR**, matching six-digit approval, and browser revocation. Safari and Home Screen windows enroll separately. Only the nonexportable signing key, public key and browser ID persist on the phone; no offline calendar/settings cache.
- Private requests require fresh signed proofs and the selected iPhone's live **authorized Bluetooth notification session**. Disconnect, subscription loss, revoked enrollment or a selected-phone change denies access. Hidden/offline windows clear private content and stop polling. Tailscale is transport, not presence authorization or physical phone attestation.
- Optional **Google Web-client sign-in from the phone**, with exact private callback, PKCE and bounded single-use consent. Existing Desktop credentials are unchanged; failed remote consent retains existing grants. Calendar management works with your current Google account without configuring this optional client.

No public Funnel, arbitrary API proxy, cloud AI, new database schema, dependency changes, phone-bond reset or automatic OS reboot. This release keeps settings, Google grants, saved games, installed voice/wake assets and Pi Connect enrollment. The updater restarts an already owner-enabled private gateway after installation; it never enables private ingress without your setup action.

## Install and enroll

On the hub, **Settings → Luma software → Check for updates → review 0.3.0 → Install**. Keep power/internet connected and verify the installed version. No SD reflash is needed. The accepted 0.2.11 updater was qualified against this exact signed package; its verifier/installer source is also unchanged from 0.2.10.

Then keep Tailscale connected on the phone and its selected Bluetooth connection authorized. On Luma, enable the private HTTPS connection if needed, open **Settings → iPhone remote**, enter your PIN and create a QR. Enroll the intended Safari/Home Screen window, compare the codes and approve on the hub. See [complete iPhone setup](https://github.com/BrianBGoldshtein/LumaSmartHub/blob/main/SD%20Card/docs/IPHONE_REMOTE.md), including optional Google Web-client consent and revocation.

## What still needs owner testing

Safari/Home Screen storage and installation, real phone range/disconnect/reconnect, live Google Web consent and task changes, timer/control behavior and an actual hardware update with saved state retained. Build-host Chromium, synthetic BlueZ/provider/broker tests and signed disposable-tree rollback do not prove these physical/account behaviors. The private remote intentionally locks when the phone's notification session is not authorized; it cannot be used to bypass that gate from afar.
