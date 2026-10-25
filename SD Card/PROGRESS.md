# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.11 Beta](docs/V0311_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. The owner's 0.3.9 attempt failed health verification and restored 0.3.8; do not retry it. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.11 prioritizes readable/strong-signal devices and removes the top-40 pairing cutoff. Shared themed search/paging reaches every returned eligible device; secondary snapshots avoid per-row database reads and still exclude other registered phones. The 0.3.10 load/standby fixes, health deadline, primary authorization and secondary privacy remain intact. See [qualification evidence](docs/V0311_WORKING_NOTES.md).
- Final software gates passed: 2,351 backend / 219 frontend / 43 packaging tests, both builds, exact-source CI, three signed switch/rollback paths, production download equality from 0.3.8/0.3.10, 12 crowded-pairing cases, the complete remote fixture and 24 themed shared-settings cases. Physical Pi acceptance remains unproven; a one-shot startup stack diagnostic retains further failure evidence.
- Owner acceptance needs physical USB power in standby and prompt actual iPhone return. Those checks are not proven by the private Linux fixture. Earlier cursor/radio/speaker checks remain owner-led. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
