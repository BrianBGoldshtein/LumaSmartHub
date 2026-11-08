# Private iPhone remote

[0.4.0 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.4.0). Install through **Settings → Luma software → Check for updates → review 0.4.0 → Install** and keep power connected through the verified reboot. Confirm the installed version and refresh the enrolled remote. The primary remote's **All hub settings → Device → Fan cooling** now includes guided migration to an optional BCM12 inline USB fan switch. USB Wi-Fi, mouse and drives stay powered; a new wiring acknowledgment and observed fan-only test are required. Keep the existing connection until the board is wired. See [ordering/wiring](GPIO_FAN_SETUP.md) and [0.4.0 evidence](V040_WORKING_NOTES.md).

The themed **Connected now** list remains on every authenticated page for both primary and secondary users, including those without calendars. It shares only names/roles/You markers and clears when hidden, offline or unauthorized. Normal preview polling refreshes it about every five seconds, ten in Settings; no presence history is saved. Other accounts' contents remain private.

If an unpowered mouse prevents access, use the [0.4.0 Pi Connect signed-update procedure](V040_WORKING_NOTES.md#install-via-pi-connect). Do not retry 0.3.9. Reopen the enrolled primary remote → Settings → unlock → All hub settings for shared settings and guided setup. Phone-started installations show wall progress; ordinary settings changes refresh live. Standby USB power and saved cooling preference are retained. A USB network adapter holds the hub on; a direct USB fan runs continuously unless moved to its separate GPIO switch. Use Keep USB on before adapter insertion in original hub-switch mode. See [room Wi-Fi instructions](ROOM_WIFI_SETUP.md). Settings and working bonds are preserved. Physical Pi installation, RF discovery, USB power and actual iPhone timing remain owner checks. Separate secondary remotes are described in [multi-user setup](MULTI_USER_SETUP.md).

## What you need

Your existing Luma Pi, the selected paired iPhone, and private Tailscale transport to Luma. The primary phone requires **Share System Notifications**. From 0.3.7, secondary phones need only their registered live trusted Bluetooth connection, not notification permission; Luma never accesses their notifications. No Mac, App Store account, developer mode or native companion app is needed. The remote follows the hub theme and has no games or animation loop.

On Luma, enable its existing **private Tailscale HTTPS connection** in Settings. If HTTPS setup is missing, follow [private connection setup](TAILSCALE.md). Do not enable public Funnel. The remote uses the same opt-in, restricted gateway; it does not open a public port.

## Enroll Safari or a Home Screen window

1. Connect the registered iPhone to Luma and verify its nickname appears. A pending connection is not enough: the primary needs live notification authorization; a secondary needs its live trusted bond with Bluetooth services resolved. A user without configured/shared calendars may still leave the wall in public standby.
2. Open **Settings → iPhone remote** on the hub. Enter the hub PIN and tap **Create enrollment QR**. Scan it privately with the phone. It expires in five minutes and can be used once.
3. If you want a Home Screen app, first open the private `/remote/` address in Safari, use **Share → Add to Home Screen**, then open that Home Screen window. Open the enrollment link in that window, or paste it under **First time here? → Enrollment link**. Install before enrolling: Safari and Home Screen have separate keys.
4. Tap **Enroll this browser**. Compare the six-digit approval code on both screens. On the hub, confirm the match and tap **Approve matching browser**. Enrollment approval uses the hub PIN on the hub, not on the phone. After enrollment, the official primary remote separately requires that PIN for global settings and software updates; secondary remotes cannot unlock those controls.
5. The primary phone shows **Hub**, **Settings** and **Software**; secondary controls remain personal-only. Calendar/task data is available only while that user's role-specific Bluetooth session remains authorized.

If a QR expires, request another. If the phone or hub code differs, do not approve; generate a fresh QR. Clearing browser storage or changing the selected phone requires new enrollment. Keep the enrollment link private; don't send it to a chat or put it in a screenshot.

## Controls

- **Hub:** large time/weather, upcoming events, tasks, named timers, leaving summary and wall page/sleep controls. Tasks use the same completed color and Google's event revision checks as the wall hub.
- **Settings:** from 0.3.5, the primary's **All hub settings** contains the actual wall settings and guided setup, including Users, Google, voice calibration, networks, Bluetooth, PIN/token changes, backups and updates. Unlock with the primary PIN. Sensitive changes require a fresh PIN and explicit review; changing network, PIN or phone access may disconnect you. Secondary remotes retain only their own controls and timers.
- **Software:** the primary remote checks the signed GitHub release, shows its notes and requires explicit installation confirmation. From installed 0.3.2 onward the wall also shows independent progress, retains it through temporary API outages, and requests one graceful reboot only after verified success. Acceptance is not success: check the final installed version. If the link drops during reboot, keep Pi power connected and reconnect before deciding whether to retry.

The browser saves only its nonexportable signing key, public key and browser ID. It does not save an offline calendar/settings preview. Hidden/offline windows clear private contents and stop polling; iOS can suspend a window, so this cannot promise erasure of screenshots or OS app snapshots. Tailscale alone does not unlock private synchronization.

The shared settings use Safari's keyboard, not the wall keyboard. Voice calibration listens through the **Pi microphone**; speak near the hub even though the controls are on your phone. Backups write to the **Pi's USB drive**, using the wall browser's game checkpoints. Personal setup stays saved on the Pi; reopen it through Users after an application restart. For a secondary user's Google consent, that person signs in through **their own** enrolled remote → My calendars.

**Fan cooling** is optional. In the original USB-hub connection, all onboard USB ports may turn off together during its five-second test, temporarily disabling the mouse; remove storage/network adapters first. Automatic uses 70°C on / 60°C off with no discovery windows. Before using an unpowered mouse or inserting a drive, select **Keep USB on · mouse & drives**. The optional BCM12 switch changes only fan power; USB remains on and thermal control can continue in standby. Both connections require actual stop/restart observation before Automatic. The new board is normally off during boot before its controller starts and is not a hardware fail-on thermostat. See [current fan instructions](GPIO_FAN_SETUP.md).

From **0.3.12**, a latched cooling fault no longer disables its own recovery button. After updating, refresh this remote, connect the registered phone and unlock primary settings. Open USB cooling → Verify physical fan switching, remove drives, acknowledge and retry. Wait for power restoration, then check the separate observation acknowledgment and confirm only if the actual fan stopped and restarted. Persistent faults keep automatic cooling disarmed even across a controller restart. No simulated test qualifies your physical fan; see [0.3.12 evidence and recovery instructions](V0312_WORKING_NOTES.md).

## Optional Google sign-in on the phone

Already-linked Google accounts work without a new client: change calendar selections or tap **Sync now**. To renew Google directly from this phone, configure an additional **Web application** OAuth client. The existing Desktop client and tokens are not deleted.

1. In the same Google Cloud project as your existing Calendar setup, keep the Calendar API enabled and the consent configuration appropriate for your account.
2. In OAuth clients, create **Web application**. In **Authorized redirect URIs**, paste the exact address shown under remote **Settings → Calendars → Enable Google sign-in from this phone**. It is `https://<your-private-host>.ts.net/remote/google/callback`. Do not substitute localhost or add a wildcard.
3. Download its JSON and select it in that phone panel. It is sent over authenticated private HTTPS and stored on the Pi, never in GitHub or browser storage. Do not share that file.
4. Tap **Sign in with Google** or **Reconnect Google**, complete Google's normal consent, then return to the remote. Use **Enable task updates** only if you want Luma to recolor tasks; Google grants event-edit permission, while Luma limits edits to the selected task calendar.
5. On a Home Screen app, Google may open Safari. After consent, return to the enrolled Home Screen window and refresh. That window keeps its own key; approval in one window does not enroll another.

The pending sign-in expires after fifteen minutes. Stay near the hub with Bluetooth authorized throughout consent. Disconnect, revocation, restart, mismatched state or failed consent retains the existing Google grant rather than reporting a false success. Google's [Web-server OAuth requirements](https://developers.google.com/identity/protocols/oauth2/web-server) explain the Web-client redirect contract.

## Revoke or troubleshoot

On the hub, **Settings → iPhone remote → Manage enrolled browsers** requires the PIN. Revoke the browser you no longer use; its next private request is denied. Normal application updates retain grants, but restoring a backup removes them so an old backup cannot silently restore access.

If locked, first verify Tailscale is connected, the correct private URL is open, and the registered iPhone has a live connection (plus notification authorization for the primary). If the key was cleared, enroll again. Do not repeatedly replay an uncertain task change or update: check the hub/Google state first. Pi Connect remains the recovery tool.

## Owner acceptance

Test Safari and, separately, Home Screen installation; all three themes; timer start/pause/resume/cancel; calendar selections and task completion in Google; disconnect/reconnect and revoked-browser lockout; optional actual Google Web consent; and a real signed update with saved settings retained. Build-host tests do not prove iOS storage, the Pi radio, live Google consent or a physical update.
