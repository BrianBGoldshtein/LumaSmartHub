# Luma Smart Wall Screen — source and image handoff

This folder contains the Raspberry Pi 4 application source, image builder, documentation and historical build archives. It is not itself a bootable SD card; use Raspberry Pi Imager with a fully built `.img.xz` after confirming the exact target card.

The current source is newer than every archived image in `image/`. **Do not flash an older archive as the current application.** Build and audit a fresh candidate, then conduct owner-led hardware testing. See [CURRENT_STATUS.md](CURRENT_STATUS.md), [flashing precautions](docs/FLASHING.md), and [hardware acceptance](docs/HARDWARE_VALIDATION.md).

Luma provides a large-type themed dashboard, weather, Google Calendar agenda and tasks, scheduled Sleep behavior, privacy standby based on the paired phone, local Hey Luma commands, timers, optional Levoit purifier control and deliberately opt-in scenes. The Settings area also covers campus networking, Pi Connect, Tailscale private iPhone Shortcuts, encrypted removable settings backups and signed app-only updates. Siri remains on the phone. Account, network and device behavior still need real Pi qualification.

Optional room-device controls support the Levoit Core 300S/300S-P only when discovery confirms the model and capabilities; connecting a purifier does not enable automation. See [room devices](docs/ROOM_DEVICES.md), [scenes](docs/SCENES.md), [campus network](docs/CAMPUS_NETWORK.md) and [signed updates](docs/UPDATE_DEPLOYMENT.md).

Personal credentials and the private release-signing key do not belong in GitHub or this source folder. Application settings are designed to survive in-place app updates, but hardware recovery and rollback must be verified on the owner's Pi. `main` remains reserved for the owner's approved v1 after physical testing.
