# Luma development status

Luma remains a pre-release Raspberry Pi 4 appliance. The owner has not completed the physical acceptance suite, and `main` must remain untouched until that review and explicit v1 approval. The current source on the feature branch is newer than the last generated SD image; do not flash an older image as if it contains these changes.

## Implemented in source

- Large-format themed dashboard with time, Open-Meteo weather, Google Calendar agenda, selected-calendar tasks and sleep scheduling; privacy standby follows authenticated phone presence.
- Local Hey Luma command path, local timers with audible completion, phone pairing controls, Tailscale private Shortcuts, Pi Connect recovery route, and guarded network setup.
- Optional Levoit Core 300S/300S-P setup and conservative VeSync control, subject to actual model/account/network qualification.
- Morning, Night, Arrive and Away scenes, disabled by default, with purifier-only bound actions, durable one-shot execution, separate remote consent, and no startup replay.
- Portable encrypted settings-only USB backup/restore and the signed, app-only updater design. The signing key remains offline.
- Full-screen themed ambient animations and game checkpoints. Existing Tetris timing and score ramp remain unchanged.

## Release gates

Run the complete backend, frontend, image-builder and exact-image checks after source changes. A newly built ARM64 Pi image, not an older archive, must be flashed and boot-tested by the owner. Verify screen/touch orientation, audio alarm during sleep, microphone wake phrase, campus Wi-Fi, Google OAuth, Bluetooth presence/re-pairing, Tailscale Shortcuts, Pi Connect, USB detection/backup, purifier enrollment and scene safety, reboot/power-loss persistence, and signed update rollback. Synthetic tests and QEMU are not physical evidence. Do not publish v1 or merge to `main` before acceptance.

See [README.md](README.md), [REQUIREMENTS_STATUS.md](docs/REQUIREMENTS_STATUS.md), [ROOM_DEVICES.md](docs/ROOM_DEVICES.md), [SCENES.md](docs/SCENES.md), and [CAMPUS_NETWORK.md](docs/CAMPUS_NETWORK.md) for current contracts.
