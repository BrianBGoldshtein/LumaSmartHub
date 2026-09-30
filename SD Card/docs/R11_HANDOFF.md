# r11 Raspberry Pi 4 image candidate

> Historical artifact only. This image predates the current source and must
> not be used for the next flash. Its checks describe the old build, not the
> current application.

**Status: software-checked for owner-run hardware testing, not hardware-qualified or v1.** The Pi, display/touch, microphone/speaker, campus networks, USB media, phone, appliances and power-loss recovery still need physical acceptance.

## Exact artifact

- User-visible local folder: `SD Card/image/r11-candidate-74d1f71-20260929`
- Raspberry Pi Imager custom image: `luma-pi4-UNVERIFIED.img.xz` (644,461,532 bytes)
- SHA-256: `585e06340ac8001de20d62ea71460ee8aac8073d09737d1df2e4beed0be00f62`
- Source: `codex/luma-r7-levoit` at `74d1f7172ab32e483481cffe29b52b6db5f9d994`
- Staged source fingerprint: `cdc43d4325eab4609ab8afaa274d2c65df5b398978e4fceda3fea6ef6ec0ca84`
- Pi image generator: `dbd775d191a2e2cafec95bb218f2002213eff2ff`
- Base application version: `0.2.0`; built 2026-09-29 22:34:13 UTC

The r11 image contains the post-r10 room-device UI corrections: embedded setup step scroll recovery, immediate removal of stale Levoit controls after provider failure, durable display of uncertain IR sends, and explicit re-review of remote scene permission. r10 does not contain these changes.

## Software evidence and limits

- [Hosted source CI run 36636971459](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36636971459) passed. Host checks passed: 996 backend, 131 frontend, and 47 image-builder tests, plus frontend production build.
- Builder-tested XZ integrity, staged source fingerprint and SHA-256; the copied Windows output archive was independently SHA-256 checked against the same value.
- Raw partition/package inspection passed. An exhaustive static audit matched **171 shipped Luma files** against the staged source and retained `hardware_qualified=false`.
- Disposable QEMU-overlay checks passed for the protected offline backup socket and the Pi Connect setup broker. The former returned an empty USB inventory to authorized `luma`; the latter reported a fresh, unenrolled Pi Connect state after API/database health. Neither check exercised real USB media or signed in to an account. QEMU times out by design and is not a hardware boot assertion.
- The image build manifest records `boot_verified=false`. No real Pi or SD card was touched by these checks.

The local candidate folder includes `build-manifest.txt`, `source-manifest.json`, `raw-image-check.json`, `shipped-files-audit.json`, `qemu-backup.log`, `qemu-pi-connect.log` and the archive checksum. The binary and machine-generated receipts are intentionally excluded from GitHub.

## Owner handoff

Use Raspberry Pi Imager **Use Custom**, selecting the exact `.img.xz` archive, **only after** reading [flashing precautions](FLASHING.md). A flash erases the currently personalized card and does not migrate Google/Tailscale tokens or settings. Before writing, make and verify a recoverable whole-card backup or explicitly decide to configure accounts again. The backup contains credentials; keep it private. Then follow [hardware validation](HARDWARE_VALIDATION.md) on the real Pi before treating r11 as accepted. The app-only signed updater can preserve settings for later application releases, but no signed release has been published or Pi-tested, and OS/firmware changes may still require a future image.
