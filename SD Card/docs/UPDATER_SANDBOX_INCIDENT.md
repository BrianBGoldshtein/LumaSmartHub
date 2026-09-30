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
