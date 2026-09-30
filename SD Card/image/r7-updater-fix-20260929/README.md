# Luma r7 development image

This is the current full-image candidate. It is **not** a production release
and is not yet boot- or hardware-qualified. The owner controls when flashing
and physical tests begin; no SD card was changed during this build.

- Local image archive: `luma-pi4-UNVERIFIED.img.xz` (large disk images are excluded from GitHub; this candidate is retained in the owner's workspace, not published as a release)
- SHA-256: `ceb97a0140433765bd7d48bcc44a57fea66788b55af07fd3705af6dd7d6c9f1a`
- Source fingerprint: `aba921d1de6d6c3fffbe685ae5fc09dc824f0ade324a561fbec252714fd22c7d`
- Build: 2026-09-29; pinned `rpi-image-gen` commit `dbd775d191a2e2cafec95bb218f2002213eff2ff`

The XZ stream and checksum passed; Windows independently hashed the copied
646,317,768-byte archive. The root partition matched its ext4 sidecar and all
170 mapped Luma application/configuration files matched source. The build
manifest reports `boot_verified=false`; the exact raw-image audit reports
`hardware_qualified=false`. QEMU smoke assertions passed for the authorized
empty USB-backup inventory and fresh-device Pi Connect setup status; these
isolated software checks do not prove physical boot, display, touch, audio,
Wi-Fi or account enrollment. See `raw-image-check.json` and `file-audit.json`
for detailed receipts, plus [`../../CURRENT_STATUS.md`](../../CURRENT_STATUS.md).

## Optional Levoit network

The image includes the off-by-default `Luma-Devices` 2.4 GHz WPA2 access point.
It routes through NetworkManager's shared/NAT mode; it is not a bridge into the
campus LAN. To use it, Luma first needs working upstream internet and a second
Linux-supported, AP-capable USB Wi-Fi adapter. The Pi 4's built-in Wi-Fi stays
connected as the eduroam/Visitor client; the software will not accept a
virtual AP interface on that same physical radio.

In Device setup → Wi-Fi, review the adapter status, confirm permission from
Stanford or the network owner, then enable `Luma-Devices`. The same Luma PIN
can be the Wi-Fi key only if it is exactly eight digits; that is a weak shared
secret. A separate stronger Wi-Fi passphrase is preferred. Stanford Visitor
terms must be accepted on Luma itself first, and its service restrictions may
still block VeSync/cloud pairing. Actual forwarding and Levoit enrollment are
not hardware-tested. Check the purifier model label: the implementation targets
Core 300S; the plain Core 300-P appears not to have the smart/VeSync feature.

For eventual owner-authorized testing, compare this file's checksum and use
Raspberry Pi Imager's **Use Custom** flow described in
[`../../docs/FLASHING.md`](../../docs/FLASHING.md). Do not flash until the owner
explicitly asks to begin hardware testing.
