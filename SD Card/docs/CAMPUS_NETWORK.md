# Stanford network deployment

The intended location has **Stanford Visitor** or **eduroam**, not an assumed home LAN or Ethernet connection. The owner confirmed a **Stanford SUNet account** for eduroam. Never request a SUNet password in chat, store one in source, or bundle one in the image.

The image configuration now explicitly sets the pinned generator's `ieee80211.regdom` to `US` for Stanford, California. Its wireless-regulatory layer writes `options cfg80211 ieee80211_regdom=US` in `/etc/modprobe.d/cfg80211_regdomain.conf`; older candidates used the worldwide `00` default. Confirm the effective radio domain on the real Pi before testing campus channels. This is not a bypass of firmware/regulatory limits. Before deploying outside the US, rebuild with the actual installation country's setting.

## Wi-Fi scanning image defect found during hardware testing

The first Luma candidate's SBOM confirmed that it included NetworkManager and Broadcom firmware but omitted `wpasupplicant`. Debian lists that Wi-Fi backend as a **recommended**, not required, NetworkManager package; Luma's minimal image intentionally disables recommended packages. This is the leading, source-evidenced cause of the Pi OS-versus-Luma difference: Raspberry Pi OS could see the networks, while the Luma scan returned none. The image recipe now installs `wpasupplicant` explicitly. The Luma scanner also now waits for NetworkManager's `LastScan` timestamp to advance before reporting an empty result; earlier it suppressed scan-request failures and waited a fixed two seconds. See the upstream [NetworkManager wireless D-Bus API](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.Device.Wireless.html).

This explains the software-image defect but is not a physical retest. The updated image must be built and flashed, then **Device setup → Wi-Fi → Find networks** should list the same visible networks as standard Raspberry Pi OS. Record whether Stanford Visitor and eduroam appear, and whether a scan completes. A previously built candidate does not gain packages from source edits.

## Stanford Visitor

Stanford documents a browser terms page, a 12-hour session limit, limited bandwidth and restricted services. See [Wireless Access for Stanford Visitors](https://uit.stanford.edu/service/wirelessnet/access). A remembered Wi-Fi profile cannot prevent the university's portal session from expiring.

The current source provides **Device setup → Wi-Fi → Find networks** and **Open network sign-in**. Choose Stanford Visitor (an open network), join, then open sign-in. The desktop bridge launches a separate, non-kiosk Chromium profile with a visible address bar and close button. It opens `http://neverssl.com/` to provoke the campus redirect. Review the real destination and terms yourself; Luma does not click Accept, suppress certificate warnings, inject login forms or replay consent. Close that browser window to return to the dashboard.

The portal profile lives locally in the desktop account's `.config/luma-portal`; it is separate from the dashboard browser. The launcher is local-only, requires a live desktop bridge, expires unhandled requests after 30 seconds and avoids duplicate launches. Captive-portal completion on Stanford's actual network and touch-window return behavior remain **unverified** until hardware testing.

When network access expires, saved settings and cached calendar/weather remain subject to the usual privacy rules. The normal informational screens show a compact, themed **Network sign-in**, **Offline · Saved view**, or **Limited internet** link into Wi-Fi setup. It stays out of full-screen ambient animations and never wakes a sleeping display. A portal indication is a connectivity heuristic, not proof that Stanford's terms have expired.

The image installer configures NetworkManager's standard credential-free HTTP probe at `http://network-test.debian.org/nm` once per minute (10-second timeout). The response was checked during development; it returned HTTP 200 and the expected `NetworkManager is online` text. HTTP is intentional so captive redirects can be detected; this probe sends no Luma account credentials, calendar data or device identifier. Like any network request, its destination can observe the source public IP. It is not a security test or a guarantee that every internet service is reachable. See [NetworkManager connectivity configuration](https://networkmanager.dev/docs/api/latest/NetworkManager.conf.html).

The API reads NetworkManager's cached status every 30 seconds without scanning Wi-Fi or changing a connection. Two consecutive trouble readings are required before showing a warning; recovery clears it immediately. Status older than 100 seconds becomes unknown. Disabled/unavailable probing never falsely claims internet access or asks the user to sign in. In Wi-Fi setup, **Check internet access** explicitly triggers NetworkManager's check after the portal window is closed. No credentials or network status are stored by this monitor. Actual Stanford expiry/recovery behavior still needs testing on campus.

## Eduroam with Stanford credentials

[Stanford's eduroam guide](https://uit.stanford.edu/service/wirelessnet/eduroam) specifies `SUNetID@stanford.edu` and the SUNet password as an alternative to Cardinal Key. It identifies `radius-cert.stanford.edu` for server authentication. The [Android guide](https://uit.stanford.edu/service/wirelessnet/eduroam/Android) additionally documents certificate/domain handling, but is **not a complete Linux configuration specification**.

Current source implements **Device setup → Wi-Fi → Find networks → eduroam** for Stanford SUNet accounts. Enter your full `SUNetID@stanford.edu` and SUNet password **only on the Pi**, then choose **Join network**. The touch keyboard supports both fields. Successful activation saves credentials in NetworkManager's local root-managed profile, not Luma's database/backups. Field values clear after submission/cancel. Other institutions remain unsupported; never enter another university's credentials here. This implementation is not yet included in older image candidates or tested against campus RADIUS.

### Verified profile and trust scope

On 2026-09-25, the official [geteduroam discovery catalog](https://discovery.eduroam.app/v3/discovery.json), sequence `2026092502`, listed **Stanford University**, provider `cat_idp_7154`, profile `cat_profile_8130`, “eduroam TTLS”. Its advertised [EAP configuration endpoint](https://cat.eduroam.org/user/API.php?action=downloadInstaller&device=eap-generic&profile=8130) supplied the settings below. The downloaded snapshot is retained as `source/backend/src/luma/assets/stanford-eduroam.eap-config`, SHA-256 `f10db53312b2ba95697480608edd4da7197c571aa6b165ebf388855a9f30973f`. The application never downloads or executes a live installer.

The first/preferred method is **EAP-TTLS (21)** with inner **EAP-MSCHAPv2 (26)**. NetworkManager therefore uses `phase2-autheap=mschapv2`, **not** TTLS's non-EAP `phase2-auth`. The SSID is exactly `eduroam`; connections require RSN and CCMP. Exact certificate name matching permits only `radius-cert.stanford.edu` and `radius-cert1.stanford.edu` through `radius-cert4.stanford.edu`. No broad suffix matching, TOFU, disabled time checks, global system CA fallback, or certificate bypass is provided. See [NetworkManager 802.1X settings](https://networkmanager.dev/docs/api/latest/settings-802-1x.html) and [wireless security settings](https://networkmanager.dev/docs/api/latest/settings-802-11-wireless-security.html).

Two public certificates were extracted without modification:

| Certificate | DER SHA-256 | Expires (UTC) |
| --- | --- | --- |
| Stanford University MyDevices Root CA | `38b9a448072ba750faef663affbbb0aec4a8270a4b38bdbdaedef8fe66f5a607` | 2038-01-09 16:20:44 |
| Stanford University MyDevices Intermediate CA | `17d431f9d968f1907a415c4f5c9e13b827f15f7027eff83cdb75f77d95dd9113` | 2028-01-09 17:20:45 |

The installer copies their PEM bundle to root-owned `/etc/luma/stanford-eduroam-ca.pem` (0644, parent 0755). It does **not** add either certificate to OS or browser trust. Before enrollment, the broker checks the bundle hash (`e659812ac49e4400e189115c507cf7d7d8f586adca642f8205d4815e939770e8`, LF-normalized) and fails closed if missing or changed. The root broker's read-only filesystem policy allows reading but not replacing this file. Later autoconnections use the saved certificate path and name constraints; administrative changes to that file must preserve this trust boundary.

The official snapshot specifies no anonymous outer identity, so this implementation does not invent one. The account identifier may be visible in outer EAP exchange; the password is inside the verified TLS tunnel. Authentication logs managed by NetworkManager may contain the account identifier, even though Luma does not log credentials. Wi-Fi credentials are not encrypted against someone who physically steals the SD card; root-only file access is not disk encryption.

Keep the Pi's clock correct. Before the intermediate expires in January 2028—or if Stanford changes its configuration—re-verify the official catalog/profile, review certificate/name changes, update the pinned assets and tests, and rebuild. Never “fix” authentication by disabling verification or silently replacing trust from a runtime download. Visitor sign-in is the fallback while a legitimate profile change is reviewed.

## Shared-network security and iPhone connectivity

The API now binds to loopback (`127.0.0.1`) by default. The display, device bridge, voice and Bluetooth integrations continue locally. This intentionally prevents unencrypted API/token traffic on campus Wi-Fi. Do not set `LUMA_LISTEN_HOST=0.0.0.0` on Stanford Visitor or eduroam.

Siri Shortcut remote commands use the optional owner-approved [Tailscale private connection](TAILSCALE.md). Implementation is delivered in the software-checked `image/tailscale-20260926/` candidate; owner enrollment remains. Campus port restrictions and possible device isolation must be tested rather than assuming the iPhone can reach the Pi. Bluetooth presence does not require phone-to-Pi Wi-Fi reachability; a VPN connection never unlocks privacy. No account has been enrolled, HTTPS certificate issued or campus-network exception created during development.

## Wi-Fi implementation and test limits

The non-root API accepts bounded local-only setup requests and calls a UID-authenticated Unix socket. A constrained root broker uses [NetworkManager's D-Bus API](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html). It can scan, enable Wi-Fi, join visible open/WPA2/WPA3 personal networks or the fixed Stanford eduroam profile, read status, and recheck connectivity. No arbitrary probe URL, CA path, server name, EAP settings, shell command or NetworkManager settings dictionary comes from the browser. Passwords are sent in memory; failed profiles are removed, and successful connections are saved by NetworkManager after activation. NetworkManager credentials are not part of Luma's SQLite backups.

Tests cover validation, local-only API access, credential-safe errors, activation-before-save, failed-profile cleanup, profile/certificate provenance, downgrade rejection and portal request/launch logic. `image-builder/eduroam-smoke.py` additionally validates the actual settings through Debian's libnm without contacting a daemon; OpenSSL verifies the root self-signature, intermediate chain and validity dates. They do **not** prove real Wi-Fi association, captive portal compatibility, regulatory-region setup, malicious-RADIUS rejection by the real supplicant, or campus eduroam authentication/reconnection. Those remain explicit acceptance gates. On hardware, also verify saved profiles are root-only, reboot reconnection succeeds without re-entry, and no insecure alternate profile is selected.
