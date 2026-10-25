# 0.3.12 — recover latched USB fan faults from the phone

## Owner evidence and task

Phone pairing is now working. Owner sees USB power on, Keep USB on, Switching failed / automatic disabled, and cannot use physical-test verification buttons on the phone remote. Owner recalls no flicker and requests autonomous diagnosis, simulations and a published fix while they sleep; no further live commands should be requested tonight.

Actual read-only Pi report: onboard USB2 bus 1/device 2 and USB3 bus 2/device 1 all four PORT_POWER bits true; USB storage absent and update inactive. This proves current reported hub power is on, not fan RPM/physical voltage, and excludes those two guards at that instant. No failure-time journal or transfer error is available, so the original hardware trigger is not conclusively known.

## Proven code defects and corrections

The backend latches a fault and only reinitializes on an explicit acknowledged probe. The shared frontend simultaneously disables that probe whenever available=false: a permanent recovery deadlock on both wall and phone. Enable acknowledged retry with a valid status and verified phone even while faulted; retain standby, busy, confirmation, admin and hardware guards. Never enable automatic cooling merely because power currently reads on.

The raw Linux switch writes both onboard hub views then immediately demands matching status. The upstream [uhubctl implementation](https://github.com/mvp/uhubctl/blob/master/uhubctl.c) allows a 150 ms USB3 settling delay before readback. Add one bounded 150 ms settling wait after successful writes, without repeated off requests, automatic off retries or changed ioctl authority. Simulate delayed readback to show why the old implementation could falsely latch a healthy switch. This is a plausible trigger, not proof of the owner's exact historical fault.

Keep-on restoration currently runs outside the controller's fault-handling path; failures can become generic backup errors. Route restoration failures through the existing fail-on path and expose only fixed fault codes (no raw paths/exception text), preserving first cause until successful deliberate reinitialization. Persistent mismatch/I/O failure must still keep USB on best-effort and disable automatic control.

## Required verification and continuation

Final-review safety addition: a root fault previously cleared only volatile qualification; API preferences could still contain automatic + the old topology, allowing a broker restart to revive automatic off. FanRuntime now durably disarms only an explicitly observed fault, retaining ordinary standby preferences. New signed-remote test restarts the controller after a fault and proves old qualification cannot revive off; explicit automatic is rejected until a fresh test/confirmation. All earlier provisional archives must remain unpublished. The nine themed cooling browser cases passed in final lab `/home/luma-build/luma-0312-final.3PqhHiRI` at `90152b64eb0f66e76c60b8bc7cf065796b4f118f`; qualify this safety addition on exact new source before publishing.

Focused result: 222 frontend tests and both production builds passed. All four signed-remote recovery tests passed after correcting the disconnect test to sign its request before revoking the link (the challenge correctly refused an already-disconnected phone). Published 0.3.11 versus candidate negative control on identical 100 ms delayed hub status: old code falsely faults with eight writes/no wait; candidate succeeds with exactly eight writes/one 150 ms wait. Persistent mixed bits still fail. Initial browser runs corrected a test-fixture middleware Response and a transient-message assertion; all six themed mobile cases then passed. The simulated wall phone lacked the continuous synthetic ANCS heartbeat provided by TLS middleware, so its presence correctly expired and safely cancelled the wall probe. The opt-in fixture now maintains that heartbeat; product presence/security checks are unchanged. The first publisher attempt stopped before signing because the new legacy check was ordered before archive creation; the block is now after signing. Continue all nine mobile/wall cases and exact-source full release gates. Do not publish provisional archives.

Add delayed/mixed/permanent hub-readback simulations, all-port restoration failures, safe recovery after a latched fault, no off before acknowledgment/phone/guard checks, explicit physical confirmation before automatic mode, and frontend failed-state button tests. Exercise the real signed primary remote with a fake root power controller in all themes, including checkbox → probe → independent restoration → confirmation → automatic. Test secondary refusal, disconnect cancellation, storage/update guard and failures; no real USB switching should occur in tests.

Then full software/build/CI gates, exact offline-signed install/rollback using published 0.3.8 and 0.3.11 installers, and production download equality before publishing a new v0.3.12 Beta. Preserve all saved settings/bonds, 70°C on / 60°C off, no discovery windows, standby power, pairing-list fixes and the root five-field wire contract. Do not weaken the physical-observation gate or claim a real Pi fan has been tested. Private key stays offline. Source edits are in the LumaSmartHub-0.2.4 repository, not the stale root SD Card folder.

## Exact final source checkpoint

Final safety source is `a74b92702d79956254293bc87ecc8d9d6d72c46e`, lab `/home/luma-build/luma-0312-qualified.xQZQvZ2D`. Focused suite: 68 passing. All nine themed cooling cases and all 24 shared-settings cases passed. The latter now waits for fonts and two layout frames, then measures once with the unchanged overflow assertion; no overflow-fit retry or relaxed threshold was added. The full remote fixture passed, including secondary denial, disconnect/revocation lockout and update progress. Remaining final gates: complete backend/packaging, 12 pairing-browser regressions, CI run 40182315428, exact signed candidate/legacy switches and forced rollbacks, publication and production equality. Earlier `P99LPFDw`/`3PqhHiRI` archives are provisional and must not be published. No test has operated the owner's fan.

## Published qualification — 2026-10-25

[v0.3.12 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.12) is published at the exact final safety source `a74b92702d79956254293bc87ecc8d9d6d72c46e`. [CI run 40182315428](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/40182315428) succeeded before publication. The final clean lab passed **2,364 backend tests** in 318.16 seconds, **222 frontend tests**, **43 packaging tests**, both production builds, all **nine cooling browser cases**, **24 shared-settings cases**, **12 pairing cases** and the complete private TLS remote fixture with zero browser exceptions. The new restart simulation proves an observed fault cannot revive old automatic qualification; ordinary standby still retains its selected preference.

The exact signed **2,154,131-byte / 92-file** archive has SHA-256 `584adc114533c06ab657144a43ab638b5f5d6770ad501433b43b512f7d2041de` and source fingerprint `61f99ba505985c0e7167991feff496f78c7f266910f0308b21a451d1a8165468`. The actual packaged wheel contains settling, duplicate-test rejection and durable disarming; compiled JavaScript contains the retry control. Candidate plus pinned published 0.3.8/0.3.11 installers each passed switching and forced health-failure rollback on the same bytes. Production `latest_release` from both installed versions verified the signature and byte-for-byte equality after publication. Release targets `main`, is neither draft nor prerelease, and has a Beta headline. No existing tag/asset was replaced. The signer stayed offline; dependencies, service units and storage schema are unchanged.

Final reports/logs, before/after comparison and six themed screenshots are retained under workspace `qa/0.3.12-fan-recovery`; no TLS private keys, browser profiles or owner data were copied. Earlier incomplete/provisional labs remain unpublished. Software work and publication are complete; the owner's actual physical fan stop/restart remains a required observation before automatic cooling. The historical triggering hardware condition remains unknown.

## Owner update steps

After publication, prefer Settings → Luma software → Check for updates → review **0.3.12 Beta** → Install. Keep Pi power connected through reboot. Confirm **0.3.12**, refresh the phone remote to load the new controls, reconnect the registered phone if needed and unlock primary Settings with the PIN. No reflash, account reset or bond deletion.

If the wall mouse is unpowered, the existing signed Pi Connect route is:

```sh
sudo -u luma /opt/luma/venv/bin/python - <<'PY'
import asyncio, base64, json
from importlib.metadata import version
from luma.github_updates import latest_release
from luma.update_broker import update_request
current = version('luma-smart-screen')
print('Downloading and verifying the signed update...', flush=True)
release = latest_release(current)
if release.get('state') != 'available' or release.get('version') != '0.3.12':
    raise SystemExit('Expected update unavailable; nothing installed. Current: ' + current)
result = asyncio.run(update_request({'action': 'install',
    'bundle': base64.b64encode(release['bundle']).decode()}))
print(json.dumps(result, indent=2))
PY
```

An accepted request is not success: wait through reboot and require version 0.3.12 from Settings or the normal health endpoint. Do not repeatedly retry a rollback; retain the updater/API logs.

Keep USB on until personally present. Remove USB storage, leave the fan's switch on and open Device → USB cooling → Verify physical fan switching. Acknowledge, choose Retry physical fan test (or Test five-second USB interruption if no current fault), observe the actual fan stop and restart, then check the new observation acknowledgment and Confirm. Only then select Automatic cooling. The minimum-on interval can keep power on for another minute after restoration; thresholds remain 70°C on / 60°C off. Do not confirm an unseen/failed switch. Persistent failure must remain unqualified and powered on best-effort. Report the retained fixed fault code/journal when available; this release does not prove the historical Pi cause or physical voltage/RPM.
