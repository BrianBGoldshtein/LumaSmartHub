# Private iPhone commands with Tailscale

Optional, owner-approved September 25, 2026. The integration is included in the current [r9 candidate](../image/r9-campus-network-20260929/README.md); older Tailscale-only artifacts are historical and excluded from GitHub. No account has been created or enrolled on this computer, and no hardware has been tested.

## What you get and what it costs

Tailscale connects your iPhone privately to Luma even when they cannot communicate directly over campus Wi-Fi. Siri Shortcuts can change the theme, brightness or volume, show the touch sliders, switch pages, run morning/night commands, and—only after a separate local owner grant—run an allowlisted room scene. Siri's voice stays on the phone. Local Hey Luma does not need Tailscale.

The [Personal plan](https://tailscale.com/pricing) is currently $0 for personal/non-commercial use and covers these two devices. Choose a personal account, not a Stanford-managed organization account. No paid add-ons, subscriptions, exit nodes or public tunnels are needed or configured. This is a third-party service: its coordination infrastructure knows enrolled-device/account metadata. It is not a way to bypass campus policies, and it cannot accept Visitor terms for you. Both devices need working internet access. Campus operation will be checked after assembly.

## First connection — when the Pi is assembled

1. Finish Visitor or eduroam setup on Luma. Install the official [Tailscale iPhone app](https://tailscale.com/download/ios), sign in on the free Personal plan, and approve its VPN configuration. Other VPN apps can conflict; do not disable required university security software to make this work.
2. On Luma, open **Device setup → Private iPhone connection → Connect / sign in**. Scan its QR with your iPhone camera and approve **luma** in the same personal Tailscale account. Never share a screenshot of the QR. No account password is typed into Luma. If scanning fails, type the displayed official `https://login.tailscale.com/a/…` address on the phone.
3. The screen refreshes while waiting. If the account requires device approval, approve Luma in the Tailscale admin console. A disconnected/expired login may need this step again. Displayed enrollment data hides after five minutes; this is not a claim that the provider has revoked that link.
4. In the [Tailscale admin DNS settings](https://login.tailscale.com/admin/dns), enable MagicDNS and HTTPS certificates. Read Tailscale's notice: the device's `luma.<tailnet>.ts.net` certificate name is published in certificate-transparency logs, but the service remains private. Do not use a sensitive device name. [HTTPS documentation](https://tailscale.com/docs/how-to/set-up-https-certificates).
5. Keep this tailnet limited to your own devices. Review **Access controls** to permit only your phone/account to Luma on TCP443, and remove broader rules that would override that intention. Grants are additive: adding a narrow rule does not cancel an existing allow-all rule. Do not replace an existing tailnet's policy blindly. See the policy example below.
6. Tap **Enable private commands** on Luma. It displays the private **HTTPS command address** only after checking the exact proxy configuration and running gateway. This checks local configuration, not end-to-end iPhone connectivity. Do not substitute a campus IP, plain HTTP, or port8742.
7. In **Connections → Show Shortcut token**, read the token and use it only in your own Shortcut. Hide it afterward. Treat a synced/shared Shortcut containing it as a credential.

## Apple Shortcuts recipes

In Shortcuts on iPhone, create one shortcut per phrase. Add **Get Contents of URL**, paste the exact private HTTPS `/command` address displayed by Luma, choose **POST**, and set **Request Body → JSON**. Add one JSON field for a brightness-slider test: **Key** `name`, type **Text**, value `show_brightness`. In the action's separate **Headers** dictionary add **Key** `X-Luma-Token`, with **Text/value** set to the private token shown on Luma under **All settings → Connections → Show Shortcut token**. The token is not the Tailscale QR, sign-in URL, or account password; never put it in the JSON body or URL. Percentage values are **Number**; theme/page values are **Text**. Do not add `source`. Run it once manually to grant iOS permissions, then use its name with Siri. Apple's [API request guide](https://support.apple.com/guide/shortcuts/request-your-first-api-apd58d46713f/ios) explains the POST/JSON controls.

| Shortcut name / Siri phrase | JSON body |
| --- | --- |
| Change hub brightness | `{"name":"show_brightness"}` |
| Change hub volume | `{"name":"show_volume"}` |
| Good night Luma | `{"name":"good_night"}` |
| Good morning Luma | `{"name":"good_morning"}` |
| Run an allowlisted scene | `{"name":"run_remote_scene","value":"night"}` |
| Luma arcade | `{"name":"set_theme","value":"neon-grid"}` |
| Luma cabin | `{"name":"set_theme","value":"hearth"}` |
| Luma glass | `{"name":"set_theme","value":"luma-glass"}` |
| Show my agenda | `{"name":"show_page","value":"agenda"}` |
| Dim Luma | `{"name":"set_brightness","value":25}` |

For the morning shortcut, add **Get Dictionary Value → message**, then **Speak Text**. The message uses the current privacy policy: if your phone is away and no local PIN unlock is active, it must not disclose private events. Commands cannot assert phone presence or unlock with a PIN. A theme or brightness change can work remotely without revealing calendar content.

For a room scene, the `value` must be exactly `morning`, `night`, `arrive`, or `away`. Before using this Shortcut, unlock Luma locally and grant that exact scene in **Device setup → Room scenes → Private iPhone actions**. The scene must already be enabled and locally reviewed. A scene edit or device relink invalidates the grant until you review it again. The command sends no device state or calendar data back to the phone.

The on-screen token is required even though Tailscale already encrypts/authenticates the connection. Never share the shortcut publicly with your token embedded. Luma does not ship signed `.shortcut` files: Apple's signing/import workflow and device permissions require your iPhone; these are exact manual recipes, not claims of an installed shortcut or companion app. See [all allowed commands](IPHONE_AND_SIRI.md).

## Narrow account policy example

For a **new, dedicated two-device tailnet only**, use the admin console's actual phone and hub Tailscale IPv4/IPv6 addresses in place of the placeholders below. This is a template, not a file to paste unchanged. The UI does not silently edit your account policy.

```json
{
  "grants": [
    {
      "src": ["PHONE_TAILSCALE_IPV4", "PHONE_TAILSCALE_IPV6"],
      "dst": ["HUB_TAILSCALE_IPV4", "HUB_TAILSCALE_IPV6"],
      "ip": ["tcp:443"]
    }
  ]
}
```

Preserve unrelated existing rules if this is not a new dedicated account; remove/adjust only conflicting broad access after reviewing its effects. Do not grant `funnel`, Tailscale SSH, routes or exit-node access. Re-enrolling a device may change its address, requiring a policy update. Verify both allowed access and rejection from a different device after assembly. [Official grants syntax](https://tailscale.com/docs/reference/syntax/grants).

## Persistence, stopping and recovery

- **Disconnect** stops/disables both gateway and dedicated Tailscale daemon, including after reboot. It preserves the node identity and configuration; **Connect / sign in**, followed by **Enable private commands**, reconnects without an unnecessary new account login while the identity remains valid.
- When enabled, background Serve and systemd startup survive normal reboots. Keys/certificates live in root-only `/var/lib/luma-tailscale`, separate from Luma's settings/backups. No node identity, account token or certificate is baked into the image. Physical SD access can still expose secrets: file permissions are not disk encryption.
- Tailscale key expiry or provider revocation can require sign-in again. Keep expiration enabled unless you deliberately review the security tradeoff in the admin console. Enrollment persistence is not a promise of permanent authorization. [Key expiry](https://tailscale.com/docs/features/access-control/key-expiry).
- To revoke a lost phone, remove that specific phone in Tailscale's admin console; do not delete unrelated devices. If a Shortcut token leaks, disconnect Luma, open **Device setup → Replace Shortcut token**, confirm revocation, and update your own Shortcuts with the replacement displayed in Connections. All old-token commands are rejected immediately after replacement. Deleting a device from Tailscale requires re-enrollment later.
- If commands fail, check campus internet, the iPhone VPN connection, device approval/expiry, DNS/HTTPS settings, access rules and the token. Use **Refresh**; do not expose8742 or fall back to HTTP. A stopped gateway also prevents commands if HTTPS setup fails.

## Implementation and maintenance

Pinned official ARM64 Tailscale1.102.4, archiveSHA256 `9dd1e6a592a014bbaea0103167ffe299adeda4ba14e078ce9c2895364f6c4c3f`; upstream BSD license included. [Official packages](https://pkgs.tailscale.com/stable/). Static binaries are deliberately not self-updating: review security releases, update the pinned version/checksums, rebuild and rerun qualification before deploying an update. Do not run a remote `curl | sh` installer over this dedicated configuration.

The root-only daemon uses kernel interface `luma-ts`, not userspace mode (which can forward arbitrary host loopback ports). A dedicated nftables table, loaded before the daemon, drops non-HTTPS tunnel ingress and all forwarding. It never flushes campus/host rules. Kernel-mode Serve terminates private HTTPS and targets only `http://127.0.0.1:8743`. The main8742 API remains loopback-only; SSH is not offered through this integration. No subnet routes, exit node, DNS takeover, SOCKS proxy, Tailscale SSH or Funnel is configured. Tailscale's own control-plane/diagnostic networking is separate from application ingress.

Only the Unix-socket setup broker is enabled in a fresh image. The daemon, enrollment and command gateway remain off until the physical UI requests them. Requests allow exactly status/connect/enable/disconnect, with peer-UID checks, fixed executable arguments, size/time limits and no submitted URLs/credentials. Account/peer details and command output are not returned or logged by Luma; enrollment QR/URL live only briefly in process/UI memory. The upstream service has its own diagnostic behavior.

Tests cover input restrictions, local-only API access, enrollment URL filtering/expiry, command proxy restrictions, rollback and disconnect. Actual IPv4/IPv6 connections in isolated Linux network namespaces confirmed that443 works and22/8742/8743 fail; unrelated rules survive reload. An offline ARM64 boot of the delivered image exercised the real daemon/firewall and UID-checked setup broker, returning NeedsLogin with no command URL. These do not establish campus/iPhone reachability, certificate issuance, real boot persistence, or physical-device performance. Complete those checks only after the owner requests hardware testing.
