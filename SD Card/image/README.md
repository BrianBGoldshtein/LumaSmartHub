# Luma image delivery — physical testing deferred

> The [r13 image candidate](r13-final-71d91b5-20260930/README.md) is the
> current software-checked artifact for owner-led hardware testing. It is not
> hardware-qualified or v1. Older image archives and receipts below are
> historical and obsolete for the current source revision.

**Current candidate:** local archive `r13-final-71d91b5-20260930/luma-pi4-UNVERIFIED.img.xz` (644,189,136 bytes), SHA-256 `8c81312502fd29504c62f898ca7a9f398056c6eb036925a0db6743cf1aca68d3`, built from feature commit `71d91b5`. See its [handoff](r13-final-71d91b5-20260930/README.md) for test evidence and erasure precautions. No physical Pi acceptance has been claimed.

The r12 handoff records its missing `polkitd` package. The r13 image includes and audits the package, but native USB file browsing must be tested on the Pi. The immutable r12 archive remains historical.

**Historical r10 candidate (2026-09-29):** local archive `r10-candidate-a79f7f4-20260929/luma-pi4-UNVERIFIED.img.xz` (large binaries are excluded from GitHub), with its [handoff and hardware gates](r10-candidate-a79f7f4-20260929/README.md), build/source manifests, raw-image and exhaustive file-audit receipts, and [USB backup](r10-candidate-a79f7f4-20260929/qemu-backup-check-a79f7f4.txt)/[Pi Connect](r10-candidate-a79f7f4-20260929/qemu-pi-connect-check-a79f7f4.txt) emulator assertions. SHA-256: `a00f122c34f02a6d83ca08b78dad9f5cd62a590eb2d89c4fa99acfbad8b3c278`. Built from feature-branch commit `a79f7f4e52a6d06214925c1cee2c230e2b5ef210`. It is obsolete for current-source testing.

**Previous candidate:** local archive `r9-campus-network-20260929/luma-pi4-UNVERIFIED.img.xz` (large image binaries are excluded from GitHub), with its [handoff](r9-campus-network-20260929/README.md), [build manifest](r9-campus-network-20260929/build-manifest.txt), [source manifest](r9-campus-network-20260929/source-manifest.json), [raw-image/package receipt](r9-campus-network-20260929/raw-image-check-20260929.json) and [170-file audit](r9-campus-network-20260929/image-audit-20260929.json). SHA-256: `77de4675402120626c167a7b393d595398d5facb44d5b23e0170626b9f0ba147`. It includes the explicit network-owner approval wording for the opt-in Levoit hotspot; checksum/XZ, root-partition/sidecar, package checks and exact-source audit passed. The prior r8 QEMU assertions are historical, not r9 results. The AP stays off by default, needs a separate supported USB Wi-Fi adapter, and must not share Stanford/venue internet without explicit network-owner approval. The build manifest says `boot_verified=false`; the image audit says `hardware_qualified=false`. Owner-directed physical testing remains deferred.

The r7, r6 and earlier candidates and their matching receipts remain preserved
in versioned local folders; large image binaries are excluded from GitHub.

The previous [Tailscale candidate](tailscale-20260926/luma-pi4-UNVERIFIED.img.xz) is preserved with its handoff details. Earlier candidates and their receipts remain below and in their versioned folders.

## Preserved older OAuth candidate

The `luma-pi4-UNVERIFIED.img.xz` directly in this folder is the **older OAuth candidate**, not the latest delivery. It is preserved with its original evidence and is not qualified for unattended wall-mounted use.

Default-on Hey Luma and mute safeguards are not in this older archive; they are included in the newer versioned candidate linked above. Preserve this older candidate and its matching evidence.

- Archive size: 545,644,144 bytes (about 520 MiB).
- SHA256: `fcd64357dfeae08c41114cca9451d361fd40bd665c7e9e5a3f9a9e0b192264c2`.
- Archive completed: 2026-09-25 21:49:57 UTC; interrupted compression was recovered without rebuilding or changing the raw image.
- `build-manifest.txt` retains `boot_verified=false`. Emulator success is not physical boot qualification.
- `source-manifest.json` fingerprints the exact staged application, system configuration and assets; it is not a promise of bit-identical future package downloads.

## Evidence included

The original raw image passed read-only checks against staged OAuth/calendar, network/eduroam, API/gateway, frontend and SSH files. The root partition matched its ext4 sidecar. Stanford trust is scoped, the wireless domain is US, the command gateway is disabled, the approved administrator public key matches, and no shared SSH host keys are shipped.

Isolated normal 180-second and diagnostic 360-second ARM64 emulator runs returned real API/database health and rejected an unauthenticated gateway command. The earlier attempt under concurrent compression timed out; that failure is retained in the normal-test receipt. Missing emulated peripherals are not treated as real-hardware passes.

XZ integrity passed, source/raw hashes remained unchanged during recovery, and the delivered Windows archive's SHA256 was independently checked. See `qualification-oauth-20260925/` for the raw-image and boot-check receipts.

That folder also contains `software-inventory.spdx.json`, the builder's SPDX 2.3 inventory (2,576 package records and 37,569 file records), copied with checksum verification. It records discovered components/versions; it is not a vulnerability audit, license clearance, or hardware certification.

## Next steps

Follow [flashing instructions](../docs/FLASHING.md), then [first boot](../docs/FIRST_BOOT.md) and the [physical qualification checklist](../docs/HARDWARE_VALIDATION.md). Back up any data on the intended SD card and confirm its identity before erasing it. Use Raspberry Pi Imager's custom-image workflow; copying this folder onto a card will not make it bootable. Skip Imager OS customisation for this preconfigured appliance.

Still unproven: real display/touch/orientation, sleep/wake/brightness, microphones/speaker/echo cancellation, Hey Luma calibration, campus Wi-Fi and certificate checks, Google consent/refresh persistence on the Pi, iPhone Bluetooth/ANCS privacy and physical power-loss behavior. Optional secure remote Shortcut transport is now implemented in the latest versioned candidate; owner account enrollment and real-device acceptance remain. Its gateway ships off. Siri stays on the iPhone; local Hey Luma is separate, not Siri-only Bluetooth audio routing.

Do not rename this archive to the production release or mark the hardware qualified based on these software checks. Keep private account data and backups out of this delivery folder.
