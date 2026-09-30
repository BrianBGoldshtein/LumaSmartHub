# Luma development status

Luma remains a pre-release Raspberry Pi 4 appliance. The owner has not completed the physical acceptance suite, and `main` must remain untouched until that review and explicit v1 approval. The [r12 image candidate](image/r12-current-916b5d7-20260930/README.md) contains the current application source at `916b5d7` and is ready for owner-led hardware testing, not production use. Earlier images are obsolete for this revision.

## Implemented in source

- Large-format themed dashboard with time, Open-Meteo weather, Google Calendar agenda, selected-calendar tasks and sleep scheduling; privacy standby follows authenticated phone presence.
- Local Hey Luma command path, local timers with audible completion, phone pairing controls, Tailscale private Shortcuts, Pi Connect recovery route, and guarded network setup.
- Optional Levoit Core 300S/300S-P setup and conservative VeSync control, subject to actual model/account/network qualification.
- Morning, Night, Arrive and Away scenes, disabled by default, with purifier-only bound actions, durable one-shot execution, separate remote consent, and no startup replay.
- Portable encrypted settings-only USB backup/restore and the signed, app-only updater design. The signing key remains offline.
- r12 hardware finding: the native file chooser enumerates USB media but cannot mount it because `polkitd` was omitted by the minimal package install. An in-place Pi Connect admin repair is documented in [first boot](docs/FIRST_BOOT.md); future image source now requires and audits `polkitd`. This does not claim physical USB backup/export acceptance.
- Full-screen themed ambient animations and game checkpoints. Existing Tetris timing and score ramp remain unchanged.

## Release gates

The r12 candidate passed software/image checks. It must still be flashed and boot-tested by the owner. Follow the [ordered r12 owner test sequence](docs/R12_TEST_SEQUENCE.md), then the full [hardware acceptance checklist](docs/HARDWARE_VALIDATION.md). Outstanding physical gates include screen/touch orientation, audio alarm during sleep, microphone wake phrase, campus Wi-Fi, Google OAuth, Bluetooth presence/re-pairing, Tailscale Shortcuts, Pi Connect, USB detection/backup, purifier enrollment and scene safety, reboot/power-loss persistence, and signed update rollback. Synthetic tests and QEMU are not physical evidence. Do not publish v1 or merge to `main` before acceptance.

See [README.md](README.md), [REQUIREMENTS_STATUS.md](docs/REQUIREMENTS_STATUS.md), [ROOM_DEVICES.md](docs/ROOM_DEVICES.md), [SCENES.md](docs/SCENES.md), and [CAMPUS_NETWORK.md](docs/CAMPUS_NETWORK.md) for current contracts.
