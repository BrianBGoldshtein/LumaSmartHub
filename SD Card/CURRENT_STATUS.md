# Luma development status

Luma remains a pre-release Raspberry Pi 4 appliance. The owner has not completed the physical acceptance suite, and `main` must remain untouched until that review and explicit v1 approval. The physically tested [r12 image candidate](image/r12-current-916b5d7-20260930/README.md) revealed failures in Pi Connect enrollment, removable-drive file browsing and microphone input; do not treat it as accepted. The r13 correction is in source/build qualification. A compressed r13 artifact is not ready until the build, exact-image audit and boot diagnostic pass.

## Implemented in source

- Large-format themed dashboard with time, Open-Meteo weather, Google Calendar agenda, selected-calendar tasks and sleep scheduling; privacy standby follows authenticated phone presence.
- Local Hey Luma command path, local timers with audible completion, phone pairing controls, Tailscale private Shortcuts, Pi Connect recovery route, and guarded network setup.
- Optional Levoit Core 300S/300S-P setup and conservative VeSync control, subject to actual model/account/network qualification.
- Morning, Night, Arrive and Away scenes, disabled by default, with purifier-only bound actions, durable one-shot execution, separate remote consent, and no startup replay.
- Portable encrypted settings-only USB backup/restore and the signed, app-only updater design. The signing key remains offline.
- r12 hardware finding: the native file chooser enumerates USB media but cannot mount it because `polkitd` was omitted by the minimal package install. r13 source requires and audits `polkitd`; physical USB file access and backup still require retesting.
- r12 hardware finding: Hey Luma's calibration meter remains near zero even when the owner shouts. r13 source adds a ReSpeaker V1 hardware check, capture-only mixer initialization and persisted UI gain slider. Treat local voice as failed until the [ReSpeaker capture triage](docs/VOICE_HARDWARE_TRIAGE.md) and actual moving-meter test pass. The “live” virtual source alone does not prove a working microphone.
- r12 hardware finding: Pi Connect sign-in failed before requesting a QR because `vnc off` and `shell off` were called while unsigned. Exact-image QEMU preflight reproduced this. r13 source reorders the broker and uses shell-only Connect Lite. Real enrollment and reboot persistence still require owner retesting.
- The weather discrepancy was a location entry error: Stanford longitude is negative. The owner corrected the Pi's coordinates and reports weather is fixed. Setup now includes an explicit western-longitude hint.
- Full-screen themed ambient animations and game checkpoints. Existing Tetris timing and score ramp remain unchanged; Pong's ball receives a small, checkpoint-migrated speed lift without changing paddle speed.
- Post-freeze [r14 game polish](docs/R14_GAME_POLISH.md) in the feature branch addresses Pong's occasional retrace bounce and reduces Space Invaders rendering/simulation work. These changes are **not in the r13 image** and still need Pi-side visual qualification before release.

## Release gates

The r13 source passed 900 backend tests, 127 frontend tests, 43 image-builder regressions and frontend production compilation. The new image build/audit and physical tests are still pending. Follow the [focused r13 owner test sequence](docs/R13_TEST_SEQUENCE.md), then the full [hardware acceptance checklist](docs/HARDWARE_VALIDATION.md). Outstanding physical gates include screen/touch orientation, audio alarm during sleep, microphone wake phrase, campus Wi-Fi, Google OAuth, Bluetooth presence/re-pairing, Tailscale Shortcuts, Pi Connect, USB detection/backup, purifier enrollment and scene safety, reboot/power-loss persistence, and signed update rollback. Synthetic tests and QEMU are not physical evidence. Do not publish v1 or merge to `main` before acceptance.

See [README.md](README.md), [REQUIREMENTS_STATUS.md](docs/REQUIREMENTS_STATUS.md), [ROOM_DEVICES.md](docs/ROOM_DEVICES.md), [SCENES.md](docs/SCENES.md), and [CAMPUS_NETWORK.md](docs/CAMPUS_NETWORK.md) for current contracts.
