# Development ledger

The current implementation and remaining acceptance gates are maintained in [CURRENT_STATUS.md](CURRENT_STATUS.md). Git history retains earlier development checkpoints; this file records only the active release path.

- r14 source is developed on `codex/luma-r14-game-polish`; `main` is held for owner-approved v1 after hardware testing.
- Updates are intended as signed app-only GitHub Releases, verified against the public key pinned in the image. The private signing key stays offline.
- Preserve local accounts, settings, Bluetooth bonds and game checkpoints across app updates. Test rollback and hardware behavior on the owner's Pi before calling the updater production-ready.
- The owner is running the [r13 SD image](image/r13-final-71d91b5-20260930/README.md), with saved Google Calendar and network configuration. Do not reflash or discard that state merely to apply app changes. The signed `0.2.2` candidate passed its disposable offline ARM64 [no-flash FAT BOOT recovery](docs/R14_NO_FLASH_RECOVERY.md) check. Owner-led physical installation and testing are next.
- Observed r13 issues: Pi Connect sign-in fails after roughly 20 seconds despite working Internet and correct time; iPhone shows Luma connected while Luma says paired but disconnected; Bluetooth notification sharing is enabled on iPhone. The `0.2.2` candidate improves Connect timeouts/diagnostics and Bluetooth resolution/retry diagnostics, but real radio and campus-network behavior are not proven by QEMU.
- Owner-requested offline female speech remains a follow-on asset/runtime project, not present in `0.2.2`. See [R14_VOICE_PLAN.md](docs/R14_VOICE_PLAN.md). Preserve the offline signing key and avoid publishing a stable `main` release before physical acceptance.
