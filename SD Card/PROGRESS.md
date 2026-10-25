# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.10 Beta](docs/V0310_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. The owner's 0.3.9 attempt failed health verification and restored 0.3.8; do not retry it. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.10 removes synchronous database work for irrelevant/unregistered Bluetooth signals, retaining standby USB power and incoming-phone improvements from 0.3.9. The health deadline, primary authorization and secondary notification privacy remain intact. See [qualification and recovery evidence](docs/V0310_WORKING_NOTES.md).
- Final software gates passed: 2,317 backend / 214 frontend / 43 packaging tests, both builds, exact-source CI, three signed switch/rollback paths, production download equality, the complete remote fixture and 24 themed shared-settings cases. Physical Pi acceptance remains unproven; a one-shot startup stack diagnostic retains further failure evidence.
- Owner acceptance needs physical USB power in standby and prompt actual iPhone return. Those checks are not proven by the private Linux fixture. Earlier cursor/radio/speaker checks remain owner-led. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
