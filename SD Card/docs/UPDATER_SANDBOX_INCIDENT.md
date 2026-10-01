# 0.2.4 on-Pi updater incident — 2026-09-30

The owner's 0.2.3 Pi downloaded and signature-verified the stable 0.2.4
release, staged the new release and installed its Python wheel. At 10:30:22
local time it cleanly stopped the selected user services, backup socket, and
API, then failed at “Switching versions.” The screen stayed on a stale progress
overlay for about two hours. A power cycle returned the Pi to healthy 0.2.3;
the root-owned status file reported “Update failed and automatic rollback needs
local recovery,” and `/opt/luma-releases/0.2.4` remained staged.

Three one-shot read-only BOOT diagnostics captured the active pointer, status,
boot index and exact failure minute. No successful restart appears after the
service stop. Source inspection resolves the failure: `luma-update.service`
uses `ProtectSystem=strict` but `ReadWritePaths=/opt/luma /opt/luma-releases`.
`_atomic_link` must create `/opt/.luma.next-<pid>` and replace `/opt/luma`,
both of which require write access to parent `/opt`. Its sandbox did not
allow that. The rollback attempted the same operation even though the first
symlink creation never changed the pointer, so it failed before restarting
services. See [systemd's upstream `ProtectSystem`/`ReadWritePaths`
documentation](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml).

Remediation:

1. Pause 0.2.4 as a GitHub prerelease. The stable latest feed falls back to
   0.2.2, older than the installed 0.2.3, preventing accidental retry.
2. Deliver the narrow, one-shot no-flash SD repair in the owner's workspace:
   preserve the original unit, set `ReadWritePaths=/opt`, reload/restart only
   the update broker, and quarantine—not delete—the failed 0.2.4 release
   directory after verifying the active app remains 0.2.3. No settings or
   account data are read or changed.
3. Only after the BOOT repair report confirms healthy 0.2.3 and the corrected
   broker, restore the signed 0.2.4 stable feed for a supervised update.
4. Future updater source always attempts to restart the API, even when a
   sibling socket/user service fails, and skips the second atomic switch if
   the pointer never moved. Regression tests cover both cases.

The no-flash repair is OS-level because the existing app-only `.lup` cannot
replace the installed systemd unit. A synthetic Linux app switch passed before
release but did not reproduce the real service's mount sandbox. Future image
qualification must test atomic switching *inside the installed systemd
service* before publishing an update as stable.

## Second supervised attempt: installed modules unreadable

The first no-flash repair reported `SUCCESS` with healthy 0.2.3 and
`ReadWritePaths=/opt`. The signed 0.2.4 release was temporarily restored to
the stable feed. Two subsequent installation attempts completed pip's wheel
installation but rolled back. The second BOOT report showed a clean rollback,
and the narrow API journal captured the exact cause: the 0.2.4 API and device
scripts raised `ModuleNotFoundError` for `luma.api`, `luma.device_agent` and
`luma.mic_hardware` immediately after the switch. The published wheel's SHA-256
matched its GitHub asset digest and contains all three modules.

The installed update broker unit has `UMask=0077`. A disposable Linux copy of
the 0.2.3 environment followed by pip installation of the exact published
0.2.4 wheel under umask 0077 reproduced package directories mode `0700` and
Python files mode `0600`. The root broker can import them, but the `luma`
service user cannot. The same umask also makes freshly created frontend
directories and assets unreadable to the kiosk. This is why the prior
synthetic qualification, run under a normal build-host umask and checking only
package version rather than module visibility, passed.

0.2.4 is paused again. The next narrow no-flash repair changes only the
installed updater unit's `UMask` to `0022` after verifying the active release
is still 0.2.3. The prior unit is retained for recovery. Update status and
lock files explicitly use `0600`, and the signed bundle stays inside a private
temporary directory; no settings or account data are made public. The source
unit now carries this corrected umask. Qualification reads that exact unit
value, installs the signed bundle under it, and asserts the resulting API
module and frontend files are traversable/readable by a non-root process.
Only a successful BOOT repair report permits unpausing the signed release and
another supervised update attempt.
