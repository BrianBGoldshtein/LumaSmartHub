# iPhone, Siri, and notifications

## The deliberate audio boundary

iOS does not expose a supported Bluetooth profile that routes only Siri microphone/output to a Raspberry Pi while leaving calls and media on the phone. Bluetooth HFP couples call/assistant input and output; advertising it would also make Luma a call-audio device. The current installer explicitly disables WirePlumber's Bluetooth audio/MIDI monitors in both main and Bluetooth profiles (`80-luma-no-bluetooth-audio.conf`), while keeping ALSA/HDMI/ReSpeaker available. Luma's own services do not register HFP/A2DP endpoints. This closes a distro-default gap: installing PipeWire audio alone would otherwise enable Bluetooth audio. See [WirePlumber Bluetooth policy](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html). A read-only check confirmed this configuration is present in the delivered OAuth candidate. Actual advertised services and iPhone audio routing still require verification on the assembled Pi; file presence alone is not acceptance evidence.

Siri stays on the iPhone. The command API supports an authenticated Apple Shortcut; calls, music, videos, and Siri's voice remain on the iPhone or its chosen headphones/speaker, while Luma performs hub commands.

This differs from the original Siri-only microphone/speaker request. On September 25 the owner accepted this boundary and requested **Hey Luma as the default**. Fresh installs now enable the local wake-phrase service; saved microphone-off settings are preserved across upgrades/restarts. Siri itself is not running on the Pi. Hardware/audio acceptance remains deferred until assembly.

### Tailscale private commands (optional, owner-approved)

Tailscale creates encrypted connections between enrolled devices across different networks, giving your iPhone a private route to the restricted command gateway when campus Wi-Fi prevents direct connections. The owner approved implementation on September25. The source now includes pinned ARM64 binaries, a scoped firewall, and touch-screen enrollment/status/disconnect. Follow the [Tailscale setup and Shortcut recipes](TAILSCALE.md). The delivered `image/tailscale-20260926/` candidate includes it and passed an offline ARM64 service/broker smoke test; owner enrollment remains. Actual campus reachability remains untested.

Its [Personal plan](https://tailscale.com/pricing) currently offers free non-commercial use. No account has been created/enrolled and no public tunnel has been configured during development. Touch, local Hey Luma, calendar/weather sync and Bluetooth privacy do not depend on it. Tailscale does not accept Visitor terms, replace eduroam or prove that your phone is nearby.

**Account setup and actual device testing remain.** Luma still binds its privileged API to `127.0.0.1`. Do not expose8742 or send the token over campus HTTP. After assembly, enroll both devices, configure private HTTPS/access rules, and qualify campus/iPhone operation. See [Campus network setup](CAMPUS_NETWORK.md).

Shortcut protocol (after private connection setup):

1. Create a named Shortcut with an explicit supported command. Free-form dictated text is not accepted by this endpoint.
2. Get Contents of the approved private HTTPS address ending in `/command` using POST and JSON `{ "name": "…", "value": … }`. That address does not exist yet; do not substitute the main API or a shared-campus HTTP address. Omit `value` for commands that take no argument. Do not send `source`.
3. Add header `X-Luma-Token` with the token displayed in Device setup → Connections → Show Shortcut token.
4. For brightness/volume without a number, send `show_brightness` or `show_volume`; Luma opens the large touch slider.

Recommended phrases include “Change hub brightness,” “Change hub volume,” “Good night,” “Good morning,” “Show my agenda,” and “Change Luma theme to Hearth.”

### Restricted command gateway (implemented, dormant)

The `luma-shortcut-gateway` entry point binds only to `127.0.0.1:8743`. Its service ships **disabled** until the owner's private HTTPS setup enables it. Tailscale Serve targets this gateway only, **never** port8742: the main API intentionally gives the physical loopback UI privileges that a remote proxy must not inherit.

Only `POST /command` exists, with a mandatory `X-Luma-Token` header and `application/json` body. Brightness and volume accept integer percentages 0–100; themes are `luma-glass`, `hearth`, `neon-grid`; pages are `home`, `agenda`, `weather`, `todos`, `ambient`. The no-value commands are `show_brightness`, `show_volume`, `good_night`, `good_morning`, `wake`, `next_page`, `previous_page`, `pause_cycle`, `resume_cycle`, and `privacy_now`. The sole parameterized appliance command is `run_remote_scene`, with exactly one of `morning`, `night`, `arrive`, or `away` as its value, and it works only after that exact locally reviewed scene/action bundle is separately allowlisted. All other fields/commands are rejected, including orientation, free-form/cloud questions, PIN unlock, phone presence, network settings, Google setup, microphone activation, arbitrary URLs and caller-selected command sources.

The gateway has no database access of its own. It forwards only a normalized command and token to the fixed loopback `/api/v1/shortcut-command` route; that route independently verifies the token even for a loopback caller. Replies contain only `accepted` and `message`, never a settings/state snapshot. Morning summaries use the existing privacy-filtered snapshot after expired presence/PIN grace has been evaluated. Remote scene requests receive a generic acknowledgement and do not return device, calendar or presence state. A VPN connection or command token is **not** proof that the phone is nearby and cannot unlock the dashboard. Calendar text can appear in a morning summary only while the existing nearby-phone or local PIN policy allows it.

Requests are bounded to 1 KiB and three seconds; duplicate JSON fields, compressed bodies, browser Origin headers, query strings and ambiguous tokens are rejected. Forwarding has a fixed deadline, bounded response, no redirects and no cookies/forwarded-header passthrough. Environment proxies are explicitly disabled using [HTTPX's documented `trust_env=False` option](https://www.python-httpx.org/environment_variables/). A single-process budget permits six requests per second and thirty per minute; the launcher caps concurrent connections, disables forwarded-IP trust and request access logs. Replies use `Cache-Control: no-store`. These limits supplement, not replace, private encrypted transport and its access policy. Tests use disposable fake credentials and an in-process real API; no campus listener or account was activated.

The opt-in systemd service uses a separate dynamic user without capabilities, read-only system/runtime paths, hidden home/appliance-data directories, private temporary files/devices, restricted syscalls/address families, loopback-only IP policy, and bounded CPU/memory/process counts. The Debian build-host smoke test verifies actual denials and a real HTTP command round trip in a disposable network namespace; it does not enable the appliance service or prove Pi-kernel enforcement. The network policy deliberately allows loopback, so this is defense in depth, not an isolation boundary against arbitrary code execution that could call other local API routes. No claim is made that an already compromised host or gateway process is safe.

Remaining before phone use: enroll the owner's account/devices, configure private access controls, qualify the packaged sandbox on the actual Pi, verify campus reachability, make the Shortcuts on the owner's iPhone, then test Siri, TLS, reboot/reconnect and locked/privacy behavior end to end. Hardware testing waits for the owner. Keep the token private; do not put it in URLs, screenshots or shared Shortcut exports.

## Presence and notifications

A selected, bonded/trusted BlueZ connection plus successful subscription to the authorized ANCS characteristics is the privacy key. Advertisements and RSSI never unlock it. Once the link drops beyond the grace period, calendar, to-dos, and notifications are removed from the rendered snapshot. A PIN gives a temporary local unlock. This implementation has protocol tests but still requires qualification with your iPhone; ANCS may be unavailable until iOS grants notification sharing.

### Touch pairing

1. Open **Settings → Bluetooth** on your iPhone and keep that screen open nearby.
2. On Luma, open **Device setup → Your iPhone → Find my iPhone**. This explicitly turns on the Pi Bluetooth radio and starts a discovery window of up to 45 seconds. Select your phone by name; names/addresses alone are not identity proof.
3. Compare the six-digit code on both screens. Select **Codes match — pair** only if they match, and confirm the iPhone's own prompt. Use **Doesn't match — reject** or **Cancel pairing** otherwise. Confirmation expires after 45 seconds; the whole setup session is bounded to three minutes.
4. On iPhone, enable **Share System Notifications** for Luma if offered. The selected phone address is saved automatically only after successful bonding and trust. Private content remains hidden until an authorized ANCS connection is established.

The pairing wizard registers its own temporary [BlueZ DisplayYesNo agent](https://bluez.readthedocs.io/en/latest/agent-api/), never the global default agent. It refuses unsolicited, legacy PIN and silent Just Works pairing, and does not authorize unrelated services. Discovery is released on success, failure, cancellation or timeout; only this wizard's discovery session is stopped. No bond is automatically removed. Existing bonded **and trusted** phones can be selected without repeating the code. An unfinished/untrusted bond must be explicitly removed and paired again rather than silently promoted to trusted. A failed attempt leaves the previous phone selection unchanged; if the other device already completed part of the bond, manual cleanup can be necessary.

This touch flow is implemented and tested with simulated BlueZ devices, including a full API confirmation/persistence test. Actual Pi radio discovery, iPhone numeric comparison, ANCS permission prompts and reconnection remain unverified without the hardware.

### Administrator recovery

Use `bluetoothctl` only if touch pairing cannot complete. Run `devices` to identify the exact phone. For an unfinished bond, verify that address and explicitly `remove AA:BB:CC:DD:EE:FF` for **that phone only**; also choose **Forget This Device** for Luma on the iPhone, then restart touch pairing. Removing a bond requires pairing again and cannot be undone without doing so. Do not remove unrelated devices.

For manual pairing, enable an agent, scan, pair the iPhone address, compare/confirm the code on both devices, trust only that phone, and stop scanning. Enter its address under **Device setup → Connections → Advanced phone selection**. That advanced field selects an existing bond; it never pairs or trusts one. Clear it to disable phone-based presence. Pairing consent is always an on-device action.

The monitor reconnects only the selected already-bonded phone. No HFP or A2DP service is registered. Notification requests are read-only; Luma does not send ANCS answer/decline actions. Notifications expire from the visible island after 45 seconds and are cleared on disconnect. The island reports incoming-call notifications, not an inferred ongoing-call status.

ANCS notifications are best effort. iOS decides whether previews and sender text are exposed, and Luma honors its selected-app allowlist. Incoming-call notifications may identify the caller when iOS supplies that attribute, but ANCS is not an authoritative system-wide active-call API. The UI must never claim call state it cannot prove.
