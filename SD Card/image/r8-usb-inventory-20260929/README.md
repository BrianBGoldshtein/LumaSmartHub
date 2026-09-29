# Luma r8 development image — awaiting owner-directed hardware testing

This is the newest full-image candidate, rebuilt after the USB backup inventory
compatibility/safety fix. It is a development image, not a v1 release, and it
has **not** been flashed or hardware-qualified. The owner asked to defer device
testing until a later prompt; do not flash it yet.

## Candidate and provenance

- Archive: `luma-pi4-UNVERIFIED.img.xz` (646,393,832 bytes; about 617 MiB)
- SHA-256: `b98feb293b431a360cb4240020250125f8b0133c5fb58e9341450e04054516b1`
- Source fingerprint: `8ca82e2bc5ba71f9b3a882f6568d4fe8977d4e8c3b945880c47cffde930f796d`
- Pinned Raspberry Pi image-generator commit: `dbd775d191a2e2cafec95bb218f2002213eff2ff`
- Build time: `2026-09-29T15:06:00Z`
- Build manifest: `build-manifest.txt` (`boot_verified=false`)
- Exact staged-input hashes: `source-manifest.json`

The archive checksum and XZ integrity passed on the Linux builder; Windows
independently hashed the copied archive to the same SHA-256. The raw image root
partition matches its ext4 sidecar (`57153e49c0515d0224a67c89885a57f88483633f2e40fa404fc6b3307469a447`).
The raw-image/package receipt confirms required wireless and recovery packages,
including `wpasupplicant`, `dnsmasq-base`, `firmware-realtek`, `rpi-connect`,
and the USB file-manager backends. The exhaustive audit compared **170**
installed Luma files, models, frontend assets, licenses and mapped system files
against this exact source fingerprint and verified the shipped native binaries
are AArch64. Receipts: `raw-image-check-20260929.json`,
`image-audit-20260929.json`, `qemu-backup-check-20260929.txt` and
`qemu-pi-connect-check-20260929.txt`.

The Linux backend suite passed **989 tests**; Windows passed **957 tests with
32 Linux-only skips**; the focused Linux USB inventory module passed **8/8**.
The unchanged frontend and image-builder suites most recently passed 124 tests
and 39 checks, respectively, with a successful TypeScript/production build.
The inventory fix accepts USB storage using transport plus USB sysfs ancestry
even when a controller reports `lsblk RM=0`; it also excludes every partition
on the physical disk containing `/`, `/boot` or `/boot/firmware`.

Two bounded disposable-QEMU checks passed against this exact raw image: the
authorized Luma account received an empty result from the packaged backup
socket, and the screen-side Pi Connect setup broker returned fresh-device
status without signing in. API/database health also responded. QEMU ended at
the planned 180-second timeout after the checks; the marker assertions, not
that timeout, are the software results. These runs do **not** prove boot on a
real Pi or test the screen, USB media, touch, Wi-Fi, sound or power-loss
behavior. The exact audit records `hardware_qualified=false`.

The optional `Luma-Devices` 2.4 GHz internet-sharing AP is included but off by
default. It requires an AP-capable second USB Wi-Fi adapter while the Pi's
built-in radio stays on eduroam/Visitor, and permission from Stanford or the
local network administrator before sharing that upstream. The AP and real
Levoit onboarding have not been tested.

Large image archives are intentionally excluded from GitHub. When the owner
authorizes hardware testing, follow [the flashing guide](../../docs/FLASHING.md)
and then [the acceptance checklist](../../docs/HARDWARE_VALIDATION.md). Do not
rename this archive as a production image, and do not treat emulator or host
tests as physical acceptance.
