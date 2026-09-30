# Luma Pi 4 r12 image candidate

**Flashable for owner-led hardware testing, not hardware-qualified or v1.** This image has not booted on your physical Pi. Do not merge it to `main` or treat it as a production release until the hardware checklist passes.

## Exact artifact

- Raspberry Pi Imager → **Use Custom** → select `luma-pi4-UNVERIFIED.img.xz` in this folder (643,937,920 bytes).
- SHA-256: `c9d3478319ddf6bbfe78b75f9f00df85f89920a061147063a86e3e036766d4e8`.
- Source: feature branch `codex/luma-r7-levoit`, commit `916b5d7`; source fingerprint `506a6e45fc30f7fbe670e96e590bd6e005407ab1b56cfeec2bc002853e6248eb`.
- Pi image generator: `dbd775d191a2e2cafec95bb218f2002213eff2ff`; built 2026-09-30 00:53:59 UTC. The manifest explicitly says `boot_verified=false`.

This candidate includes the optional Levoit purifier integration. Earlier image archives are obsolete for this source revision and remain only as recoverable historical candidates.

## Checks completed

- Fresh Linux test runs: 889 backend and 43 image-builder tests passed. Windows runs: 864 backend passed (25 skipped), 126 frontend tests passed, and the production frontend built.
- XZ and SHA-256 integrity passed. A second Windows hash of this copied archive matched the value above.
- The raw root partition matched its ext4 sidecar; an audit matched all 161 shipped Luma files byte-for-byte to the staged source. A negative image audit confirmed nine retired fan/IR paths absent.
- Disposable ARM64 QEMU checks passed API/database health, fresh-device Pi Connect broker access, and authorization of the protected USB backup broker with an empty offline inventory. These checks did not exercise real display, touch, Wi-Fi, microphone, speaker, USB media, accounts, or SD-card persistence.
- `shipped-files-audit.json` records `hardware_qualified=false`. No physical Pi or SD card was written during the build.

Machine-generated receipts and checksum sit beside the archive. Keep personal credentials, backups, and Google OAuth client files out of this folder and GitHub.

## Before flashing

**A full-card reflash erases existing Luma settings, tokens, Bluetooth bonds, and other data on the selected microSD.** This image does not automatically migrate an older card. If those details must be kept, make and verify a private whole-card backup first, or explicitly choose to set them up again. A backup itself contains sensitive credentials.

Read [flashing instructions](../../docs/FLASHING.md), then [first boot](../../docs/FIRST_BOOT.md) and [hardware validation](../../docs/HARDWARE_VALIDATION.md). Select this exact `.img.xz` in Raspberry Pi Imager; copying files onto a FAT partition does not install the OS. Skip Imager's OS customisation for this preconfigured appliance.

The signed GitHub updater is app-only and has not yet been proven on the physical Pi. It cannot guarantee that future OS/security/firmware changes will never require another full image. Pi Connect still requires your account enrollment after first boot.
