# Luma r9 development image — campus sharing approval clarification

This is the newest full-image candidate. It preserves the r8 source and USB
inventory fix, and tightens the Levoit hotspot setup screen to require explicit
network-owner approval before sharing an upstream connection. It is not a v1
release and has **not** been flashed or hardware-qualified. The owner deferred
physical testing; do not flash it until asked.

## Candidate and provenance

- Archive: `luma-pi4-UNVERIFIED.img.xz` (645,716,756 bytes)
- SHA-256: `77de4675402120626c167a7b393d595398d5facb44d5b23e0170626b9f0ba147`
- Source fingerprint: `42fbff0042504530c6dc0651a18294fe30ef893009c2f059dca4390c330d8052`
- Pinned image-generator commit: `dbd775d191a2e2cafec95bb218f2002213eff2ff`
- Build time: `2026-09-29T16:19:09Z`
- Build manifest: `build-manifest.txt` (`boot_verified=false`)

The XZ stream and checksum passed. The raw root partition matches its ext4
sidecar; required wireless/recovery packages are installed; all **170** mapped
Luma application, frontend, model, license and system files match the staged
source. Windows independently hashed the copied archive to the same SHA-256.
Receipts: `source-manifest.json`, `raw-image-check-20260929.json`, and
`image-audit-20260929.json`. The r8 QEMU checks are historical evidence only;
no new QEMU or physical boot assertion is claimed for r9.

## Levoit internet-forwarding network

The optional `Luma-Devices` 2.4 GHz WPA2 hotspot is included, but stays off by
default. NetworkManager uses a separate private DHCP/DNS subnet with shared/NAT
forwarding to the Pi's active upstream route; it does not bridge the Levoit to
Stanford's LAN. The Pi's built-in Wi-Fi remains the eduroam/Visitor client. A
second Linux-supported USB Wi-Fi adapter with 2.4 GHz AP support is required.
Runtime checks require a separate physical Wi-Fi radio and live Wi-Fi uplink.

The setup is protected by the local Luma PIN. A matching Wi-Fi key is possible
only when that PIN is exactly eight digits (WPA2's minimum); use a separate,
stronger passphrase if not. Anyone given a matching key also learns the Luma
PIN. The key is kept in NetworkManager's root-managed profile, outside Luma's
SQLite backups.

**Do not enable this on Stanford/venue Wi-Fi without explicit network-owner
approval.** Stanford residential rules say routers/DHCP/NAT are generally not
allowed, and Stanford Medicine explicitly prohibits Internet Connection
Sharing/personal APs in its covered space. Rules depend on the actual location;
the in-app confirmation is not Stanford authorization. See
[campus networking and policy notes](../../docs/CAMPUS_NETWORK.md),
[Stanford residential policy](https://thehub.stanford.edu/find-software-and-computers/computer-usage-policies),
and [Stanford Medicine network policy](https://med.stanford.edu/irt/personal-computing/network-access/policies).

The Levoit app setup also requires the purifier model that supports VeSync
Wi-Fi (verify the label; Core 300 and Core 300S are not interchangeable). A
captive portal cannot be completed by the purifier; accept any Visitor terms
manually on Luma first. Adapter driver support, Stanford permission, actual NAT,
VeSync enrollment, recovery and power-loss behavior remain unverified.

## Verification and remaining gates

- Frontend: **124 tests passed**; TypeScript and production bundle build passed.
- Network API/profile suite: **31 tests passed**.
- The previous full backend evidence remains **989 Linux tests passed** and
  **957 Windows tests passed, 32 Linux-only skips**; backend files did not
  change for r9.
- XZ, SHA-256, source fingerprint, package and 170-file exact-image audits
  passed.
- `hardware_qualified=false`; real boot, display/touch/audio, campus policy,
  adapter, Levoit/VeSync, USB media, provider accounts and power recovery remain
  owner-directed physical tests.

Do not treat a successful build or emulator result as hardware acceptance.
The older r8 archive and its receipts remain preserved separately.

