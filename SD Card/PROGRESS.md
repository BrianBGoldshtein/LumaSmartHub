# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.9 Beta](docs/V039_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.9 keeps USB/fan/mouse power on without verified phones, preserves the selected cooling preference, and removes incoming-phone delays from retry backoff, queued/pending radio jobs and optional notification setup. Primary authorization and secondary notification privacy remain intact. See [qualification evidence](docs/V039_WORKING_NOTES.md).
- Final software gates passed: 2,306 backend / 214 frontend / 43 packaging tests, both builds, exact-source CI, two signed switch/rollback paths, production download equality, the complete remote fixture and 24 themed shared-settings cases. The earlier local candidates were not published.
- Owner acceptance needs physical USB power in standby and prompt actual iPhone return. Those checks are not proven by the private Linux fixture. Earlier cursor/radio/speaker checks remain owner-led. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
