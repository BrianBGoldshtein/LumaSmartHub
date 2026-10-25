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

## Final local qualification

Exact source is `ad16d72969e2af19cfdc099666c6ffd1c7fb4a9f`. Clean Linux lab: `/home/luma-build/luma-0310-release.ML3KdCGJ`. The full local publisher passed **2,317 backend tests** in 295.61 seconds, **214 frontend tests**, **43 packaging tests** and both production builds. The final private-bus fixture includes scheduling delay: 4,000 signals, zero profile lookups, 46 health probes, maximum latency 0.0810 seconds and shutdown 0.0008 seconds. As a negative control, the identical fixture against unchanged published 0.3.9 failed at 4,000 synchronous profile lookups; the earlier irrelevant-property regression also failed before correction. These are fixture measurements, not owner Pi measurements.

The same exact archive passed switch and forced health-failure rollback with candidate code and pinned published 0.3.8 and 0.3.9 installers. The full private TLS remote browser fixture passed. All 24 themed shared-settings cases passed on the unchanged final rerun after local build load ended. Two earlier runs failed the known transient 320-pixel onboarding layout measurement; both failure logs are preserved, and no assertion, timeout or production layout was changed to obtain the pass. Three cooling-settings screenshots were visually checked. Evidence is retained under workspace `qa/0.3.10-radio-load`; do not copy synthetic TLS keys or browser profiles.

Published archive: **2,147,999 bytes**, **92 files**, SHA-256 `3d035d81e8ab7fd1c36789b7c55384498b472615d59a27a79e21c1c7d1ecbe2a`; source fingerprint `5018c0281059b35a70e02b8d2b6ab8800297843e743995d3f76292aed146f76e`. Inspection of the signed wheel confirms both the dispatch-map fix and startup diagnostic are actually packaged. [Exact-source CI run 40174042631](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/40174042631) succeeded before publication. [v0.3.10 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.10) targets main and is not a draft/prerelease, as required by the installed updater. The production `latest_release('0.3.8')` verified metadata, signature and every payload file, then matched these exact qualified bytes. The private signer stayed offline and no existing tag or asset was replaced. Owner acceptance remains pending.

## Pi Connect installation from restored 0.3.8

Run once in Pi Connect's remote shell. This uses the existing luma-user broker and pinned signature verifier, not a direct Git pull, forced install or health bypass. An accepted request is not installation success.

```sh
sudo -u luma /opt/luma/venv/bin/python - <<'PY'
import asyncio, base64, json
from importlib.metadata import version
from luma.github_updates import latest_release
from luma.update_broker import update_request
current = version('luma-smart-screen')
print('Downloading and verifying the signed update...', flush=True)
release = latest_release(current)
if release.get('state') != 'available':
    raise SystemExit('No newer release available. Installed: ' + current)
if release['version'] != '0.3.10':
    raise SystemExit('Unexpected release; stopped without installing.')
result = asyncio.run(update_request({'action': 'install',
    'bundle': base64.b64encode(release['bundle']).decode()}))
print(json.dumps(result, indent=2))
PY
```

Keep power connected through the update and reboot. Then reopen Pi Connect and run:

```sh
curl --max-time 15 -fsS http://127.0.0.1:8742/api/v1/health
```

Require version `0.3.10`, status `ok`, database `ok`. Then test actual standby USB power and phone return. If it restores 0.3.8 again, do not retry: retain `/opt/luma-releases/.luma-update-status.json` and the update/API journal for that failure interval, including the new startup stack if emitted. Neither success on another Linux computer nor a successful download proves real Pi acceptance.
