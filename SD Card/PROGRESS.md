# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Source is developed on `codex/luma-r7-levoit`; `main` is held for owner-approved v1 after hardware testing.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- The [r12 SD image](image/r12-current-916b5d7-20260930/README.md) was built and audited from feature commit `916b5d7`; its physical hardware acceptance is next. Preserve or knowingly replace the existing personalized card before flashing. Older archives are obsolete flash candidates.
