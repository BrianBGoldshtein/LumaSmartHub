# On-device qualification checklist

Run this checklist on the assembled Pi before wall mounting, when the owner requests physical testing. The r11 candidate remains hardware-unverified; its QEMU probes do not count as this checklist.

## Read-only startup preflight

The delivery includes `source/tests/device_smoke.py`, a standard-library Linux checker. The r11 candidate installs it root-owned at `/opt/luma/qualification/device_smoke.py`; it is a manual tool, not an always-running service. Once physical testing is requested, run it from the approved administrator account:

```sh
sudo -u luma python3 /opt/luma/qualification/device_smoke.py
```

Wait for the Luma desktop to start first. The checker selects the `luma` user's actual runtime bus; do not run it as root or the administrator user. It makes only a fixed loopback health GET and read-only system/service/filesystem queries. It never starts/stops services, changes settings, records audio, invokes sign-in or reads tokens/account data. Its JSON report includes Pi 4/ARM64 detection, API/database health, required system/desktop services, private data-directory permissions, free storage, and the disabled/inactive command-gateway default. Run this initial-default check **before enrolling/enabling Tailscale**. After intentional enrollment, a non-dormant gateway is expected; use the transport acceptance checks below instead of treating that default-only check as an operational failure.

Exit 0 means these automated preflight checks passed, **not that the hardware is qualified**. The report always says `hardware_qualified: false` and lists the manual gates below. A running browser service alone does not prove a visible kiosk; a healthy database does not prove SD power-loss safety. Preserve this report with the exact image checksum and subsequent manual results. Do not publish backups, account data or raw system logs with it.

Host-side regression tests for this helper use mocked services and synthetic health responses:

```sh
python3 -m unittest discover -s source/tests -p 'test_device_smoke.py' -v
```

## Display and touch

- Cold boot reaches Luma without a desktop, dialog, cursor, or browser chrome.
- Native 2048×1536 mode is selected and remains stable for 30 minutes.
- Landscape, clockwise portrait, and counter-clockwise portrait all fit with no clipping.
- Touch coordinates follow each rotation; all corner targets and sliders respond.
- Sleep Time turns HDMI off; one touch wakes for five minutes; Good Morning remains awake.
- If DDC/CI is supported, brightness tracks 0/25/50/75/100. If unsupported, diagnostics says so explicitly.

## Audio and voice

- Both ReSpeaker microphones record cleanly at 48 kHz mono through `luma_mic`.
- HDMI and HAT outputs can each be selected and survive reboot.
- Echo cancellation prevents Luma's own speech from retriggering the wake phrase.
- “Hey Luma” works at 1 m and 3 m in a quiet room and at 1 m during normal playback.
- The ReSpeaker LEDs show idle/listening/thinking/speaking/error without remaining bright at night.

## Privacy and phone

- Paired iPhone presence reveals private cards only after the selected bonded/trusted Bluetooth device authorizes ANCS. VPN connectivity or a Shortcut token alone must never unlock it.
- Airplane mode or walking away returns to privacy standby after the configured grace period.
- Reboot never restores private mode until the phone is proven present again.
- Wrong PIN attempts do not unlock; correct PIN expires at the configured time.
- Only allowed notification apps appear; notification content vanishes in privacy standby.

## Reliability

- On a backed-up qualification SD with synthetic settings/calendar data first, disconnect power during settings save, weather refresh, and calendar refresh; database integrity remains `ok` after each reboot. Archive recoverable images before physical power-cut testing; host process-crash tests do not prove SD/controller behavior.
- With WAN disconnected, the last weather/calendar cache remains available and is marked stale.
- With Wi-Fi disconnected, clock, local controls, privacy, sleep, and cached pages continue working.
- Run the host test suite and the on-device smoke tests; archive their logs with the build manifest.

## Optional Levoit 2.4 GHz sharing

Do not attempt this until Stanford or the local network administrator confirms that sharing the upstream connection through a personal access point is allowed. The image needs a separate, Linux-supported USB Wi-Fi adapter that supports 2.4 GHz AP mode; the built-in Pi radio remains the eduroam/Visitor client. A compatible in-kernel Realtek adapter may use the bundled `firmware-realtek`, but verify the exact adapter/chipset and NetworkManager capabilities rather than assuming firmware alone is sufficient.

- First confirm Luma's Wi-Fi status is online and, for Visitor, accept the portal manually on Luma. Enable `Luma-Devices` only after checking the local approval box. Prefer a unique passphrase of at least 16 characters; only use the Luma PIN as the key if it is eight digits and you accept that every Wi-Fi user then knows the Luma PIN.
- Confirm the AP uses WPA2 on 2.4 GHz, the phone can join it, and a phone browser can reach the internet through it. Do not treat the AP's `active` status as proof that NAT, DNS, campus policy or upstream internet is working.
- With VPN disabled on the iPhone, use VeSync to enroll the purifier onto `Luma-Devices`. Then return the phone to eduroam and confirm the purifier stays online in VeSync. Do not put the Wi-Fi key in test logs or screenshots.
- Reboot the Pi and confirm the AP automatically returns and the purifier reconnects. Separately verify that Visitor expiry requires a human to accept terms again on Luma; Luma must not auto-accept a captive portal.
- Turn the hotspot off from Luma and confirm only the `Luma-Devices` profile is removed and the Pi's eduroam profile remains connected. Re-enable only if the campus permission and security tradeoffs remain acceptable.

These are owner-run qualification steps, not results already obtained. If Stanford denies AP sharing or Visitor blocks the purifier's required traffic, do not work around those controls; use an approved IoT network or another authorized upstream.

## Phone commands (transport approved; enrollment and physical testing deferred)

- Before any opt-in, `luma-shortcut-gateway.service` is disabled/inactive and port 8743 is not listening; the main API remains loopback-only on 8742.
- Before enrollment, `luma-tailscaled.service` is disabled/inactive, while `luma-tailscale-setup.socket` is enabled. Follow docs/TAILSCALE.md for touch QR enrollment, private HTTPS and account-policy setup; never enroll the build host as a substitute.
- After opt-in, confirm `luma-ts` is a kernel interface, the dedicated nft table is loaded, and only private HTTPS application ingress is reachable from the phone. Direct22/8742/8743 and forwarded destinations must fail for IPv4 and IPv6. Check both an authorized phone and a different/unapproved device. No Funnel/public access.
- Verify Disconnect disables gateway/daemon across reboot without losing saved identity. Reconnect and explicitly re-enable commands. Verify token replacement invalidates the previous token and persists across reboot. Account/key expiry should request reauthentication, not disable privacy.
- After an approved private encrypted transport is configured, its proxy targets the restricted gateway only, never the main API. Verify access controls from an unauthorized campus device as well as the owner's phone; do not send real tokens over plaintext campus Wi-Fi.
- Qualify the shipped gateway sandbox on the Pi kernel: dynamic non-root identity, no capabilities, inaccessible home/appliance data, read-only system/runtime files, and blocked non-loopback destinations. Build-host/emulator evidence is not physical enforcement evidence.
- Missing/wrong token is denied; `/api/v1/settings`, PIN, account setup, microphone, arbitrary URL and presence commands are unavailable through the gateway. Valid brightness/theme/night commands still work after a reboot without re-entering the token.
- Morning summaries respect nearby-phone/PIN policy and expiry, including after a disconnect, reboot and explicit privacy command. A remotely connected VPN phone that is not nearby does not reveal plans.
- Test Siri/Shortcut phrases on the actual iPhone, including theme and brightness/volume sliders, good night and morning. Audio stays on the phone or its chosen headphones; Luma never becomes a call/media audio sink.
- Record actual campus isolation/reachability, TLS validity, reconnect behavior and service resource usage. Tailscale is approved and implemented; this feature remains physically unqualified until the device tests pass.
