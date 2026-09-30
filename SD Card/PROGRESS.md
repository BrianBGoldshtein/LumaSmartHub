# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- Source is developed on `codex/luma-r7-levoit`; `main` is held for owner-approved v1 after hardware testing.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- The last generated SD image predates current source. Build and audit a new image, then use the owner's flashing workflow. Never describe an old image as final.
