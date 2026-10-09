# Private iPhone remote

[0.3.2 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.2). For the first upgrade into 0.3.2, use the wall's **Settings → Luma software → Check for updates → review 0.3.2 → Install**. Keep power connected through the verified reboot. Afterward, future phone-started installations show independent wall progress, including during night/display-off mode. Ordinary settings changes refresh live without rebooting. Do not reflash your card or reset a working phone bond. Separate secondary remotes are described in [multi-user setup](MULTI_USER_SETUP.md).

## What you need

Your existing Luma Pi, the selected paired iPhone with **Share System Notifications** enabled, and Tailscale connected on both devices in the same private tailnet. No Mac, App Store account, developer mode or native companion app is needed. The remote follows the hub theme and has no games or animation loop.

On Luma, enable its existing **private Tailscale HTTPS connection** in Settings. If HTTPS setup is missing, follow [private connection setup](TAILSCALE.md). Do not enable public Funnel. The remote uses the same opt-in, restricted gateway; it does not open a public port.

## Enroll Safari or a Home Screen window

1. Connect the selected iPhone to Luma and verify the hub leaves privacy standby. A pending Bluetooth connection is not enough: notification authorization must be live.
2. Open **Settings → iPhone remote** on the hub. Enter the hub PIN and tap **Create enrollment QR**. Scan it privately with the phone. It expires in five minutes and can be used once.
3. If you want a Home Screen app, first open the private `/remote/` address in Safari, use **Share → Add to Home Screen**, then open that Home Screen window. Open the enrollment link in that window, or paste it under **First time here? → Enrollment link**. Install before enrolling: Safari and Home Screen have separate keys.
4. Tap **Enroll this browser**. Compare the six-digit approval code on both screens. On the hub, confirm the match and tap **Approve matching browser**. Enrollment approval uses the hub PIN on the hub, not on the phone. After enrollment, the official primary remote separately requires that PIN for global settings and software updates; secondary remotes cannot unlock those controls.
5. The phone shows **Hub**, **Settings** and **Software**. Calendar/task data is available only while the selected iPhone's Bluetooth notification session remains authorized.

If a QR expires, request another. If the phone or hub code differs, do not approve; generate a fresh QR. Clearing browser storage or changing the selected phone requires new enrollment. Keep the enrollment link private; don't send it to a chat or put it in a screenshot.

## Controls

- **Hub:** large time/weather, upcoming events, tasks, named timers, leaving summary and wall page/sleep controls. Tasks use the same completed color and Google's event revision checks as the wall hub.
- **Settings:** theme, brightness/volume, weather/timezone, night/voice/chime options, wall cycle and agenda/task/sleep/leaving calendar selections. Microphone calibration, pairing, network setup, PIN and privileged recovery stay on the physical hub.
- **Software:** the primary remote checks the signed GitHub release, shows its notes and requires explicit installation confirmation. From installed 0.3.2 onward the wall also shows independent progress, retains it through temporary API outages, and requests one graceful reboot only after verified success. Acceptance is not success: check the final installed version. If the link drops during reboot, keep Pi power connected and reconnect before deciding whether to retry.

The browser saves only its nonexportable signing key, public key and browser ID. It does not save an offline calendar/settings preview. Hidden/offline windows clear private contents and stop polling; iOS can suspend a window, so this cannot promise erasure of screenshots or OS app snapshots. Tailscale alone does not unlock private synchronization.

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

If locked, first verify Tailscale is connected, the correct private URL is open, and the selected iPhone has authorized Bluetooth notifications. If the key was cleared, enroll again. Do not repeatedly replay an uncertain task change or update: check the hub/Google state first. Pi Connect remains the recovery tool.

## Owner acceptance

Test Safari and, separately, Home Screen installation; all three themes; timer start/pause/resume/cancel; calendar selections and task completion in Google; disconnect/reconnect and revoked-browser lockout; optional actual Google Web consent; and a real signed update with saved settings retained. Build-host tests do not prove iOS storage, the Pi radio, live Google consent or a physical update.
