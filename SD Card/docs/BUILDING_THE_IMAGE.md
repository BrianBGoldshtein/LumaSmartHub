# Building the flashable image

The application source and configuration are portable, but producing a Raspberry Pi disk image requires Linux namespace/mount support and ARM package execution. The current pinned rpi-image-gen runs as a normal user; installing its host dependencies requires an administrator.

## Supported build host

- Preferred: native 64-bit Raspberry Pi OS/Debian on ARM64. Debian/Ubuntu AMD64 with QEMU is an upstream-described cross-build route, but not formally supported. This project has generated candidate images successfully under Debian WSL2 as `luma-build`; this does not establish physical Pi qualification.
- At least 20 GB free space and 4 GB RAM.
- `git`, `xz-utils`, and the dependencies required by Raspberry Pi's official `rpi-image-gen` release.

## Process

1. Build and test `source/frontend` with `pnpm install --frozen-lockfile && pnpm run build`.
2. Test `source/backend` with `python -m pytest`.
3. The build script pins upstream commit `dbd775d191a2e2cafec95bb218f2002213eff2ff`. Install that checkout's host dependencies (`sudo ./install_deps.sh`); AMD64 also requires QEMU/binfmt and Debian archive keys. Keep the Linux build workspace on Linux storage, not OneDrive or `/mnt/c`.
4. Run `bash image-builder/build-image.sh` as a normal Linux user. It invokes the actual `build -S ... -c ... -B ...` interface, uses a custom Trixie/Pi 4 layer, and runs `hooks/customize90-luma` inside the generated root. It copies only application source, built frontend, and system files—not host virtualenvs, credentials, or node_modules.
5. The script compresses the completed raw image with `xz -T2 -6`. Qualification is separate: boot the raw image under the diagnostic runner or on a Pi and verify `/api/v1/health`. `image-builder/qemu-smoke.sh <completed-image-directory> --api-check` adds an emulation-only health request while preserving graphical-target startup. It uses a disposable overlay/copied DTB; never flash these diagnostic copies. Emulator success cannot qualify missing physical peripherals.
6. The script initially emits `image/luma-pi4-UNVERIFIED.img.xz`, a SHA-256 file, and a manifest explicitly saying boot verification is false. Only promote it to `luma-pi4.img.xz` after boot and hardware qualification. Archive package versions and test results with that qualification.

The owner-approved dedicated administrator public key is included in Linux staging; its private key stays outside the image. Password/root SSH login is disabled and host keys are generated per appliance. Vosk, the WM8960 overlay, and the overlay-layer native keyboard source/build recipe are bundled. Current source also includes touch Wi-Fi/Stanford eduroam/portal and Bluetooth setup; older candidates may predate these changes. Use the newest authoritative staging/build record in `PROGRESS.md`, not an old candidate, when assessing included features.

The `tailscale-20260926` candidate completed image integration, checksum-verified delivery and isolated software boot checks, including the real offline Tailscale daemon/firewall/setup broker. Immutable Linux staging is `/home/luma-build/luma-tailscale-20260926`. The pinned Tailscale archive and license are prepared by `prepare-assets.sh`; the installer never starts/enrolls its daemon. Still required before production release: actual Wi-Fi onboarding, Tailscale account/campus/iPhone checks and Bluetooth authorization, qualified voice/HAT/audio/touch behavior, and power-loss/reboot acceptance. The kiosk user intentionally has no sudo access and no shared login password. Candidate generation is achieved; the full appliance is **not yet qualified**. Source fingerprints and the packaged software inventory record this build; apt/pip dependency ranges mean a later build is not guaranteed bit-identical.

The new `qemu-smoke.sh <completed-image-directory> --tailscale-check` mode starts the otherwise-disabled daemon/firewall and gateway only in the disposable, network-disconnected VM. It checks API/database health, unauthenticated gateway rejection and a `NeedsLogin` response through the real UID-checked Tailscale setup broker. It never runs `tailscale up`, signs in, issues certificates, enables a service in the base image or contacts a tailnet. Keep this fresh-image test separate from actual campus acceptance. Never run the emulator alongside CPU-heavy compression.

Use `qemu-smoke.sh <completed-image-directory> --pi-connect-check` for the local Pi Connect recovery route. It enables the setup socket only in the disposable overlay, checks API/database health, and makes the installed Luma user ask the real screen-side broker for fresh-device status. It does not sign in or enable shell access. This is not a substitute for owner-approved enrollment on the Pi itself.

Do not call an unbooted or unverified filesystem archive a Raspberry Pi image. The final artifact is complete only after actual image generation and boot validation.

## Diagnosing an emulator timeout

Preserve the failed run's serial log; do not treat a timeout as success or rebuild the image without evidence of a source problem. The normal smoke window is 180 seconds. After other CPU-heavy build work has finished, a targeted retry can use `qemu-smoke.sh <completed-image-directory> --gateway-check --diagnostics`: a fresh disposable overlay, a bounded 360-second window and journal forwarding to the diagnostic serial console. Use this only with a fresh, unprovisioned image; never collect account-bearing appliance logs this way. This follows systemd's documented [console-forwarding diagnostic option](https://wiki.freedesktop.org/www/Software/systemd/Debugging/).

A longer run can expose an actual Python/service failure or establish delayed startup, but it does not retroactively pass the original timing window or qualify real Pi boot performance. Resolve the cause, record both runs, and repeat the normal smoke check without competing compression work if the evidence indicates resource contention. Neither mode changes the base image or enables the gateway in its shipped filesystem.

## Interrupted compression only

If the raw image was fully generated and checked, but the builder stopped during XZ compression, first confirm the previous process is actually gone. Do not restart because an observation timed out. Preserve the original `.partial` archive; it cannot be flashed and XZ compression cannot simply continue from it.

Run `bash image-builder/finish-candidate.sh /absolute/path/to/immutable-staging` only for that completed raw image. This recovery helper refuses existing final/recovery outputs, checks the original source fingerprint and pinned generator revision, hashes the raw image before/after, creates a separate `.recovery.partial`, and tests XZ integrity before publishing an UNVERIFIED archive. It generates a portable checksum and marks `compression_recovered=true` and `boot_verified=false` in the manifest. It never rebuilds the OS, modifies runtime inputs, removes the original partial archive, or qualifies the appliance. Finish isolated emulator diagnosis before restarting CPU-heavy compression.
