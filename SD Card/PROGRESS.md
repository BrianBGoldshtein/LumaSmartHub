# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.8 Beta](docs/V038_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.8 corrects twenty-second idle cursor hiding at both browser and native Wayland image layers, and parks the actual startup pointer at the far bottom-right boundary once per graphical session. All prior user/privacy/chime/cooling rules remain intact. See [qualification evidence](docs/V038_WORKING_NOTES.md).
- Owner acceptance needs physical startup placement, idle hiding while pages cycle and in Settings, and movement restoration. Earlier secondary-phone/radio/speaker checks remain owner-led. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
