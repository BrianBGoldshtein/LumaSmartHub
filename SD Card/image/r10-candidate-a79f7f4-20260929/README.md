# Luma Raspberry Pi 4 image candidate

**Status: ready for the next owner-run hardware test; not hardware-qualified or an official v1 release.** Physical display, touch, audio, Wi-Fi, Pi Connect enrollment, and power-loss testing have not been performed.

## Image

- File: `luma-pi4-UNVERIFIED.img.xz` (644,437,784 bytes; local output only, not committed)
- SHA-256: `a00f122c34f02a6d83ca08b78dad9f5cd62a590eb2d89c4fa99acfbad8b3c278`
- Application source: feature branch `codex/luma-r7-levoit`, commit `a79f7f4e52a6d06214925c1cee2c230e2b5ef210`
- Staged source fingerprint: `f5ca66d44610bd922f3c008ae5801b770772e683b678919e3174d6b0c4d7fcac`
- Pi image generator: `dbd775d191a2e2cafec95bb218f2002213eff2ff`
- Base image version: `0.2.0`

Use Raspberry Pi Imager's **Use custom image** option and select the `.img.xz` file. Do not copy the folder onto the SD card. Imager will erase the selected card; verify the card identity first. The private SSH key is not included in this image.

## Software evidence

- GitHub Actions passed for the source commit: [run 36619440617](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36619440617).
- Host suites passed: 996 backend tests, 127 frontend tests, and 47 image-builder tests.
- XZ archive integrity and the builder SHA-256 check passed.
- Raw-image inspection confirmed the root partition matches its ext4 sidecar and verified the installed package/configuration set, including Stanford Wi-Fi support, both PipeWire echo-cancellation modules, Pi Connect setup, protected updater, and first-boot SSH host keys.
- Exhaustive static audit matched all 170 shipped Luma files against this build's staged source.
- Disposable QEMU checks passed for the offline USB-backup broker (authorized Luma user received an empty inventory) and the fresh Pi Connect setup socket (authorized Luma user received fresh-device status). Both tests use a temporary overlay; neither enrolled an account nor changed the image.

These checks do not certify a Pi boot, screen/touch behavior, microphone/speaker quality, campus Wi-Fi acceptance, Bluetooth privacy, connected-device hotspot policy, or SD-card power-loss safety. Follow [`HARDWARE_VALIDATION.md`](../../docs/HARDWARE_VALIDATION.md) after flashing. Preserve this image and its checksum with test results; do not call it hardware-qualified until those checks pass.

## Evidence files

- `build-manifest.txt` — build time, generator, source fingerprint, and explicit `boot_verified=false`.
- `source-manifest.json` — per-input source fingerprints.
- `raw-image-check-a79f7f4.json` — raw image, package, service, and configuration checks.
- `image-audit-a79f7f4.json` — exhaustive 170-file and ARM64 binary audit.
- `luma-pi4-UNVERIFIED.img.xz.sha256` — builder-generated archive checksum.
