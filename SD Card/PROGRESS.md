# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.7 Beta](docs/V037_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.7 separates secondary presence from notification permission and uses three bell strikes for arrivals versus one for ordinary notifications. The primary's notification authorization and per-user sharing/privacy gates remain intact. See [qualification evidence](docs/V037_WORKING_NOTES.md).
- Owner acceptance still needs secondary connection with notification sharing off, independent disconnect privacy, iOS background return and physical bell playback. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
