# Luma 0.3.10 — responsive Bluetooth observation and update recovery

## Owner evidence and boundary

The owner's 0.3.9 installation failed the actual local health check and restored 0.3.8. The new API reached startup complete, accepted a WebSocket, then did not stop within systemd's SIGTERM window and was killed. This was not an import failure or low disk space: the expanded root has 99 GB free. Current restored 0.3.8 database is 671,744 bytes and its real health request returned HTTP 200 in 0.209721 seconds. Do not retry 0.3.9 or bypass health verification. Its immutable tag/assets remain historical evidence, not accepted hardware.

## Reproduced defect and correction

The 0.3.9 global BlueZ observer dispatched empty link deltas for irrelevant RSSI/manufacturer changes. Its receiver synchronously queried and validated SQLite profiles for every nearby phone. Before the fix, a regression produced 2,000 callbacks for 2,000 irrelevant messages, and an unrelated phone signal reached the forbidden synchronous registry lookup. Both regressions failed as expected.

The observer now drops irrelevant property changes before dispatch and only unwraps whitelisted link metadata. The receiver uses an in-memory registered-address map, refreshed by the existing one-second supervisor, and never opens SQLite or creates workers in the D-Bus reader. Unknown phones are ignored. The cache is a wake/revocation hint, not authority: fresh profile, bond, link and role-specific checks remain mandatory. Tests cover replaced/removed users during the cache refresh race. Primary ANCS authorization and secondary notification isolation are unchanged.

This is a proven source-level performance defect consistent with the Pi symptoms, not conclusive proof that it caused that physical installation failure. A one-shot CPython watchdog now emits thread stacks to the API journal after 30 seconds if startup never reports healthy. It records no locals, transcripts, tokens or calendar contents, does not exit the process, and cancels on actual healthy database response or process exit. The existing 45-second installation deadline and two-second health request budget are unchanged.

## Retained behavior

All 0.3.9 standby power and recognition improvements remain: USB stays on without any verified registered phones; saved Automatic resumes 70°C on / 60°C off after verified return; no USB discovery cycling; presence events wake cooling; incoming signals bypass retry/radio-queue waits; optional notification details do not block verified presence. Keep existing accounts, bonds, profiles, timers, games and browser grants. No dependency, schema, OS package, root protocol or service unit change is required.

## Qualification checkpoint — 2026-10-25

- Focused Bluetooth, presence and cooling suite: 87 passed.
- Startup watchdog, observer and real private-bus flood: 17 passed, including the two stale-cache regressions. Initial measured flood: 4,000 signals, zero profile lookups, 47 health probes, maximum request 0.0514 seconds and shutdown 0.0006 seconds. The final fixture also accounts for pre-request event-loop scheduling delay; full-run results supersede this initial timing.
- Real private D-Bus sends 4,000 mixed RSSI and unregistered link signals across 40 nearby devices while the production health route is probed. No synchronous registry lookups, health under the unchanged two-second request budget, and shutdown within two seconds are required. This is a Linux fixture, not a physical Pi timing claim.
- Next gates: complete backend/frontend/packaging suites, exact-source main CI, production builds, browser regression, offline signature, exact-archive switch and forced rollback using candidate plus pinned published 0.3.8 and 0.3.9 installers, then production GitHub download equality. Do not claim published/ready before these gates finish.

## Continuation and owner acceptance

Repository is the `LumaSmartHub-0.2.4` subdirectory. Sign only through the existing local publisher; never read or upload the private signing key. Publish a new immutable v0.3.10 Beta, not replacement 0.3.9 files. Owner currently runs restored 0.3.8 and uses Pi Connect because the old standby fan policy can switch the mouse off. Terminal installation must use the luma user and existing signed update broker, not an unverified pull or force-install.

After software gates, ask owner to install 0.3.10, retain power through reboot, and verify installed and running versions, actual fan/mouse power with all phones absent, saved Automatic preference on return, and iPhone-to-wall delay. If it rolls back again, collect the startup stack in the failure interval rather than retrying blindly. Do not declare physical acceptance without these observations.
