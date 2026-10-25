# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Current release is [0.3.12 Beta](docs/V0312_RELEASE_NOTES.md), published through the offline-signed GitHub updater on the owner-approved `main` Beta channel. The owner's 0.3.9 attempt failed health verification and restored 0.3.8; do not retry it. V1 hardware acceptance remains separate.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- 0.3.12 fixes the faulted fan-test button deadlock, permits bounded USB3 status settling, rejects duplicate active probes and ignores stale pre-action polls. Observed faults durably disarm saved qualification; automatic off requires a fresh acknowledged test and explicit physical confirmation. Primary/secondary privacy, standby power, 70°C on / 60°C off and crowded-pairing fixes remain intact. See [qualification evidence](docs/V0312_WORKING_NOTES.md).
- Final software gates passed: 2,364 backend / 222 frontend / 43 packaging tests, both builds, exact-source CI, three signed switch/rollback paths, production download equality from 0.3.8/0.3.11, nine cooling cases, 12 crowded-pairing cases, the complete remote fixture and 24 themed shared-settings cases. Physical Pi acceptance remains unproven.
- Owner acceptance needs updating to 0.3.12, refreshing the phone remote, then personally observing the fan's five-second stop/restart before confirming and choosing Automatic. Hub bits do not measure physical voltage/RPM. Earlier standby/cursor/radio/speaker checks remain owner-led. Preserve working bonds; do not reflash for this update.
- Older image, Connect, voice and recovery checkpoints remain in Git history and historical sections of CURRENT_STATUS; they do not describe the current release.
