# 0.2.10 working checkpoint — 2026-10-08

**Published and owner-installed; Google UI recovery unresolved:** [Luma 0.2.10 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.2.10). Owner confirms API/settings version 0.2.10; Pi Connect is available, but this laptop's computer/browser-use runtime fails before initialization. Owner confirms the one-time fresh pairing test **works** after the encrypted-link failure was isolated. This does not establish long-term reconnect reliability or hardware acceptance of the new application. Historical investigation notes below retain their original stage-specific claims; this publication record supersedes them.

## Published artifact and completion audit

### Post-publication Google UI discrepancy — October 8

Owner's photos show the pre-0.2.10 error-only Google setup (raw renewal error, Retry calendar settings, no reconnect button), both standalone and embedded. Settings reports 0.2.10. Owner's read-only HTTP probe confirms **API 0.2.10**, served script **/assets/index-C34MlrQ4.js**, and **Reconnect fix present: True**. The signed published archive independently has that same script and staged recovery markers. Thus the server serves the fix, but the visible browser view is inconsistent with that served code; old loaded/cached frontend is a supported hypothesis, not a proven disk-cache cause. Do not reinstall, replace OAuth JSON or erase settings. Next is an isolated luma-kiosk user-service restart, preserving the API, Pi Connect, credentials and phone bond, then recheck the actual reconnect view.

Source review also finds that the current updater keeps Chromium running and calls **location.reload()** on installed/complete, not an automatic full OS reboot. Prior owner-facing notes saying automatic reboot were too strong. Investigate cache-safe versioned navigation and explicit post-success reboot behavior in the next correction; do not claim an already implemented reboot from documentation alone.

Owner subsequently reports the reconnect action **still missing after the suggested kiosk restart**. Do not repeat an ordinary restart as the next experiment, claim a successful restart from absent command output, or label disk caching proven. Next isolated experiment: open the verified `/?setup=google` route with a unique `refresh` query using Chromium through the existing luma graphical user manager. This avoids reusing the old HTML URL without deleting a browser profile, changing saved configuration, or starting Google consent on the owner's behalf. Await the actual displayed page and any command failure before treating this as a recovery. Permanent HTML no-store/versioned update navigation remains unimplemented.

Owner then confirms the unique-URL Chromium launch **opened the previously inaccessible Google dashboard and Google is now updated**. The owner requests the durable fix in **0.2.11**. This is direct on-device recovery evidence, not a proven identification of the browser's precise stale-entry mechanism. Preserve the now-renewed Google connection and working phone bond. Follow-up source work and verification are tracked in `V0211_WORKING_NOTES.md`; 0.2.10 publication remains immutable.

- Accepted/tagged commit: **47385899fb704ea646fe152f5740a6a07de2e6ae**, exact [CI run 37749102730](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/37749102730) completed successfully, including Linux-only backend integration tests, full frontend/build and image/recovery packaging.
- Final publisher reran **1,533 backend tests** (26 dependency/intentional malformed-archive warnings, 55.21s), **170 frontend tests**, production build and **43 packaging tests** (0.56s). Existing >500kB chunk warning remains.
- Offline-signed asset: `luma-update-0.2.10.lup`, **1,301,437 bytes**, **31 payload files**, SHA-256 **6bfdddd75148e5195057c310a14dbd6e7b07ba92fc2cbc2a7f178cbf75352b30**. Local artifact/logs: `/home/luma-build/luma-0210-release-20261008/`. Signing key stayed outside checkout/CI/GitHub; only the public verifier key enters the appliance.
- Exact signed archive passed installed wheel version/command relocation/non-root readability, switch and forced-health-failure rollback from the **0.2.9 dependency/schema contract**, with durable-state marker untouched in both cases. This is disposable Linux qualification, not a physical Pi update/systemd test.
- Production `latest_release('0.2.9')` fetched GitHub metadata and asset using its normal HTTPS restrictions, verified size/checksum/signature/payload and returned **available 0.2.10**. Downloaded bytes exactly equal the locally qualified archive. GitHub release is not draft/prerelease, targets **main**, and title is **Luma 0.2.10 Beta**. Annotated tag peels to the accepted CI commit.
- Runtime dependency fingerprint remains **986f6f0a0f2eaa86c4bfd4b59ee98b564f6177920a70d79c7fa9808da50e83ba**, storage schema **1**. Keyword sidecar remains **v0.2.9**; speech/wake assets are not regenerated. App-only boundary still excludes OS units/config, credentials and user data.
- Requirements delivered: accessible Google reauthorization after failed catalog; no incomplete selections overwrite; structured renewal vs transient errors and real SDK regressions; Bluetooth terminal-rejection cleanup no longer cancels another request; own timeout/manual-link/bond/privacy regressions; physically reflected Pong contacts with pace/checkpoints/themes retained and sustained gameplay regressions; privacy-filtered probes and owner-confirmed scoped phone recovery documented.
- On-device follow-up remains separate: confirm 0.2.10/settings after install, new Google consent/sync and later automatic refresh, repeated phone return/reboot/range acceptance, and physical Pong viewing. The owner-reported fresh pairing recovery on 0.2.9 is real evidence, but source tests do not prove these further outcomes. Do not reflash or forget the working phone bond.

## Historical development checkpoints

## Latest release checkpoint

Latest complete source check: **1,533 backend tests passed**, 26 dependency/intentional malformed-archive warnings, 52.13s (`/home/luma-build/luma-0210-bluetooth.3X6uAYyy/backend-final-0210.txt`). **170 frontend tests passed** and TypeScript/production build succeeded (`/home/luma-build/luma-0210-google.8P0jxBZv/frontend-final-0210.txt`, `frontend-build-final-0210.txt`). The existing bundle-size warning remains; no signed artifact or exact-commit CI result yet. These totals include the final Google renewal-state changes and controller-probe fixture, superseding earlier partial totals.

Owner reported **Works!** after the phone-only two-sided forget, fresh code-confirmed pairing, notification authorization and automatic-return instructions. Treat this as acceptance of that recovery test, not proof of every reboot/range scenario. No agent removed the bond; all other settings were preserved by the scoped workflow. Leave the new bond alone and do not add an automatic forget/re-pair behavior. The manual Experimental=true configuration remains an owner OS change, outside the signed application update.

Completed a further Google fix: only structured SDK invalid_grant or an HTTP 401 produces reconnect_required/authorization status with fixed renewal copy. Timeouts, 403, 429, 5xx and arbitrary provider text do not falsely claim a revoked grant. Failed sync/catalog retains credentials, settings and cached events; a later timeout cannot erase an already observed rejected-grant state. Successful consent or event sync clears that state. Setup displays renewal copy and retains the accessible consent action independently of catalog success. No credentials or provider descriptions are exposed. **39 targeted Google tests passed**, including actual SDK refresh rejection with synthetic HTTP transport and successful consent clearing. First fixture run used a Pydantic method on a dataclass and failed three tests; corrected to asdict and reran successfully, without changing production behavior to accommodate it. Full suite/build and signed release qualification still required.

## Google recovery

Owner read-only status shows last sync October 6 at 9:18 PM Pacific and a generic saved-calendar error. A bounded, no-persist refresh probe returned `invalid_grant`. The OAuth project is already In production; owner may not have reauthorized Luma since moving it out of Testing. The enabled client secret is not evidence that the saved refresh token is accepted. Production issuance and rejection cause need verification after fresh consent; do not ask for raw credentials or repeatedly create clients.

Confirmed front-end defect: setup waited for calendars and colors before rendering its reconnect action, making expired-token recovery unreachable. Implemented staged loading: local settings/status render first, protected catalog errors show fixed recovery copy, and the editor/save/task-permission controls remain unavailable until both calendars and colors load. Restored saved calendar IDs before fetching. Primary aliases normalize without silently dropping unavailable saved calendars. A cancelled page ignores late state updates. No auth, settings, schema, Bluetooth, wake-model or speech-runtime changes in this checkpoint.

Eight added regressions cover early reconnect metadata with a blocked catalog request, either Google catalog request failing, retained saved settings/IDs, no protected request before authorization, local-settings load failure, primary aliases, retry recovery and unsuccessful callback copy. Full frontend **165 passed**, TypeScript/production build successful in `/home/luma-build/luma-0210-google.8P0jxBZv` (`frontend-tests.txt`, `frontend-build.txt`). Existing >500 kB chunk warning remains. An initial test-copy attempt failed due to Windows/Bash quote transport before tests; rerun via stdin succeeded. No browser visual validation or owner hardware acceptance is claimed.

Package version is locally 0.2.10; publisher qualification starts from the owner's installed **0.2.9**, not the 0.2.0 full-image base. Existing keyword asset remains pinned to immutable **v0.2.9**; do not relabel or regenerate its sidecar for this UI correction. No commit, main push, exact-commit CI, signed app qualification or publication has yet occurred.

## Bluetooth evidence needed

BlueZ 5.82; currently authorized ANCS when owner connects manually. Recorded reconnect count 4,903 is cumulative, not a measured request rate; service-recovery count zero. Advertising stops normally for the connected selected phone. Need a sample while the iPhone automatically shows Connecting, before manual intervention: selected Device1 bond/trust/blocked/connection/services state, optional PreferredBearer availability/value, adapter roles and advertisement capacity, plus changing Luma reconnect counters/status. Never print phone addresses, names, notification contents, credentials or PINs. A read-only ObjectManager poll does not initiate radio connection, scan, forget, pair, alter settings or grant privacy.

BlueZ 5.82 marks PreferredBearer optional/experimental. Current code skips an absent property, then calls generic Device1.Connect; no proof yet that the affected request selects the wrong bearer. Preserve existing authorized-ANCS privacy gate. Await actual disconnected/connecting evidence rather than making speculative changes or hiding failure behind presence heuristics.

Owner failed-state samples now confirm selected Paired/Bonded/Trusted true, Blocked false, Connected/ServicesResolved false, PreferredBearer absent. Adapter supports central and peripheral roles with one active advertisement; Luma reports notification reconnect advertising throughout. Reconnect counts **4924 → 4925 → 4926** in two 15-second intervals, with zero service-recovery attempts. This is pre-link failure, not an ANCS-subscription/privacy bug or missing advertisement. Missing PreferredBearer can also indicate an LE-only device; do not label it proof of an incorrect bearer. Next read-only check: selected bond's allowlisted SupportedTechnologies/preference and presence (not values) of LE/classic bond keys. No OS experimental-interface enablement or bond-file edits are justified yet.

Concrete source correction implemented: after an explicit terminal BlueZ Connect rejection (including InProgress), Luma no longer sends Disconnect to a radio operation it did not acquire. It still explicitly cancels its own timed-out/cancelled wait, rechecks the selected trusted bond and leaves completed manual links intact. BlueZ 5.82's device.c returns InProgress when dev->connect/browse/pending or bonding is already active; prior indiscriminate cleanup could cancel another incoming/manual request. This source defect is established, but the owner's underlying error code has not been captured and causation for the observed failure remains unproven. No experimental API or privacy shortcut was added.

Four new terminal-error regressions and one real private-D-Bus busy-reply test verify the other pending request is not disconnected and the bond remains. **47 targeted Bluetooth/ANCS/advertising tests passed**, 11 existing dependency deprecation warnings, 2.91s, in `/home/luma-build/luma-0210-bluetooth.3X6uAYyy/tests.txt`. Full backend check is running from that same isolated copied tree. Neither source tests nor private D-Bus stand-ins prove the real Pi controller/iPhone reconnect outcome. No commit, main push, signature or release has occurred.

First full backend run: **1,508 passed / 3 failed**, 22 warnings, 85.72s. All three failures are FileNotFoundError for omitted sibling test inputs (`tools/build-keyword-asset.py`, `system/install.sh`, `system/luma-tailscaled.service`) because the initial isolated copy included only backend. Copied the unchanged source tools/system directories into the same isolated source root and started a full rerun, logging `backend-full-with-fixtures.txt`. Do not call the incomplete first run green or weaken those tests. Actual radio/Google reauthorization acceptance and release qualification remain pending.

Full backend rerun with the required sibling fixtures completed successfully: **1,511 passed**, 22 dependency deprecation warnings, 85.44s (`backend-full-with-fixtures.txt`). This supersedes the earlier running/incomplete check, not the outstanding hardware and signed-release gates.

Owner's latest allowlisted bond inspection confirms **one selected bond**, both **BR/EDR and LE**, and stored LE long-term, classic link and identity-resolution keys. No key values, addresses or notifications were printed. The LE-only explanation for an absent PreferredBearer no longer fits this record; the optional experimental D-Bus interface is the next dependency to inspect. Do not forget/re-pair or edit bond files. Read General.Experimental and the Bluetooth service's ExecStart before offering a reversible daemon-configuration experiment. No daemon setting has been changed, and wrong-bearer selection remains a hypothesis, not an observed radio trace.

Verified against BlueZ 5.82's own `main.conf` and Device API: General.Experimental exposes D-Bus experimental interfaces; KernelExperimental and Testing are separate switches and are not required or proposed. PreferredBearer is optional/experimental for dual-mode devices. Any experiment must preserve the existing config with an exact backup, retain secure pairing and ANCS authorization, and briefly restart Bluetooth only (not Wi-Fi/Connect). The signed application updater intentionally excludes OS config; do not claim an app-only 0.2.10 update can silently enable this OS dependency. Actual controller/iPhone testing must precede calling it a fix.

## October 8: passive capture and Pong scope addition

Owner's daemon-wide capture:

```text
1791445050.227903 Disconnect
1791445050.228523 Failed
1791445060.260780 InvalidArguments
1791445066.817863 Connect
1791445078.187481 Connect
```

Disconnect→Failed gap is ~0.00062s; two later Connect calls are ~11.37s apart. This fallback excludes successful replies, identifiers and unknown error text, so it cannot associate the Failed with a particular call, distinguish callers, or establish the cause of InvalidArguments. Do not claim InvalidArguments proves an invalid LE bearer/filter or that the two Connect calls belong to the same phone/session. BlueZ 5.82 can report `br-connection-canceled` when cancelling a pending Connect even on an LE request; the earlier LE-only reason allowlist omitted that code. This code alone must not be treated as proof of classic transport.

The correlated Python probe now includes successful replies, numbered anonymous caller/request labels, exact allowlisted LE/BR reason codes, selected-phone Connected/ServicesResolved boolean signals and no-reply durations. It ignores other phone paths and never treats a successful Connect as ANCS privacy authorization. **Nine targeted checks passed** including success/error/cross-device isolation, real dbus-monitor filtering and cancellation-code privacy, 4 dependency warnings, 0.72s. Full backend rerun with these probes has started (`backend-full-with-probes.txt`); do not claim that rerun complete yet. No owner-run correlated result or live application modification exists.

Full backend rerun subsequently completed: **1,520 passed**, 26 dependency/fixture warnings, 49.51s in `backend-full-with-probes.txt`. This supersedes the earlier running status. Owner still needs to run the exact correlated source probe through the installed venv; the local Codex file-open request was queued, not a verified Pi remote-shell action. No live input, signed artifact, commit/push or publication was performed.

Owner adds the recurring incorrect Pong reflection to 0.2.10 explicitly. Found a concrete cause: paddle collisions replaced the incident angle with hit-offset/spin steering and then applied an anti-retrace angle nudge. Implemented flat-face specular reflection (flip vx, preserve vy direction), preserving existing 2.5% per-hit gain, maximum speed, paddle tuning, random serves, scores, checkpoints and theme rendering. Mirror substep penetration at paddle/wall planes instead of clipping position to the contact plane. No Tetris pacing, theme layout or saved-data changes.

Added 210 side/angle/offset reflection cases, moving-paddle direction consistency, genuine misses/scoring and wall overshoot checks. Existing saved-match/tempo tests pass without a schema or tempo-version change. Sustained-game test retains original-window point/hit cadence and adds an equal second window for fresh-serve angle variety, instead of requiring random angle steering on a physically flat face. Three seeded runs show 8–9 genuine points and 12–16 distinct contact angles over ~384 seconds of simulated play; no later endless loop. First targeted run caught the old eight-angle threshold at ~192s for seed 7 (six angles/four points); this was not a bounce failure and was not reported green. **Complete frontend 169 passed**, TypeScript/production build successful (`frontend-tests-with-pong.txt`, `frontend-build-with-pong.txt`); existing >500kB bundle warning remains. No live-browser visual/Pi viewing acceptance, signed artifact or publication is claimed.

## Remaining before release (current)

October 8 controller result now supplied by owner:

```text
LE link event
Status: (0x00)
Pi role: Central
Encryption event
Status: (0x06)
Disconnect event
Status: (0x00)
Reason: (0x16)
```

BlueZ 5.82 monitor/packet.c maps 0x06 to PIN or Key Missing and 0x16 to Connection Terminated By Local Host. An observed Pi-central LE link succeeds but encryption fails before the local-host disconnect. This supports a key-acceptance problem on the automatic path, not merely a slow link or rejected ANCS subscription. The filter is controller-wide and omits peer/handle identifiers for privacy, so it does not independently prove the peer or which side has a missing/stale key. Combine with the selected-phone request capture, do not infer key contents. Manual iPhone-initiated authorization working does not establish that both LE roles have usable saved keys.

Verified existing phone-only recovery: Settings → Your iPhone → Forget this iPhone requires the local PIN; PairingFlow removes only the exact selected Device1 bond, and the API clears only phone_address plus transient phone authorization/presence. It does not clear Google credentials, Wi-Fi, PIN, themes, calendar choices or saved games. Next owner-directed test is a one-time two-sided Bluetooth forget and fresh, explicitly code-confirmed pairing, then Share System Notifications and an off/on automatic-return check. No bond has been removed by the agent. No automatic key deletion/re-pairing, privacy-gate bypass, or claim that the terminal-error cleanup source fix repairs encryption is justified. If fresh pairing still produces 0x06, retain that result and investigate role/key negotiation rather than loop through resets or increase timeouts.

Owner ran the exact correlated probe, without manually connecting:

```text
Connect #1 caller 1 observed
Disconnect #2 caller 1 observed
Connect #1 caller 1 after 15.0s: error: Failed: br-connection-canceled
Disconnect #2 caller 1 after 0.0s: returned successfully (not ANCS authorization)
Connect #3 caller 2 observed
Connected: True
Connect #3 caller 2 after 0.6s: returned successfully (not ANCS authorization)
Connected: False
```

This establishes explicit cancellation of the first pending selected-phone request at the installed app's 15s budget. Anonymous caller numbers identify D-Bus connections, not processes; Luma itself creates a new bus each retry, so caller 2 is not evidence of a second competing program. The next selected-phone request establishes a link in 0.6s, followed by an observed link drop with no further Device1.Disconnect call captured. No ServicesResolved=true was observed in this window and no ANCS authorization is shown. Do not label the drop a local app Disconnect, rejected notification permission, invalid LE key, or proof of wrong transport without further controller evidence. In particular, br-connection-canceled is BlueZ's common explicit-cancellation label and does not establish a BR/EDR connection.

Next discriminator is controller disconnect reason/encryption outcome/role, rather than another bond snapshot or arbitrary timeout increase. Prepared passive `tools/probe-bluetooth-link.sh` with output limited to fixed event/role labels and hexadecimal status/reason bytes. No raw btmon capture is stored or printed; controller-wide observations still require correlation before assigning a device. No new OS/app mutation, owner radio result, or published release is claimed.

Controller-output privacy fixture and the prior private-D-Bus checks pass together: **10 targeted probe tests**, 4 dependency warnings, 0.75s. The full 1,520-backend result above predates this single new fixture; no new full-suite total is claimed. Owner-facing command uses the same tested awk filter directly because the helper itself has not been installed/published to the Pi.

Latest owner config evidence (October 8): General.Experimental unset (default false), KernelExperimental unset, service ExecStart `/usr/libexec/bluetooth/bluetoothd` without flags. The missing experimental-interface dependency is confirmed. Prepared [an explicit reversible owner-run test](BLUEZ_LE_TEST.md) with exclusive backup and an isolated Experimental=true insertion. No live change or successful reconnection is claimed yet. App-only update boundaries remain unchanged.

Validated the exact owner-facing configuration script under WSL Linux against **six temporary fixture checks**: isolated setting insertion with unchanged remainder and original-byte backup; active setting refusal; missing General refusal; duplicate General refusal; existing-backup protection; symlink refusal. Successful rerun also refuses a second edit. No tests touch `/etc/bluetooth` or a live Pi. Await owner-run configuration experiment and actual automatic reconnect results before deciding whether this dependency resolves the stalled link.

Owner executed the configuration experiment successfully: exact backup at `/etc/bluetooth/main.conf.luma-before-le-20261008`, General.Experimental enabled, then `systemctl restart bluetooth.service`; `systemctl is-active` returned **active**. This is an owner-performed live OS configuration change, not an app update or agent screen takeover. Automatic iPhone link/PreferredBearer/authorized ANCS outcome is still unreported. Do not rerun the enable script, delete the backup, or label Bluetooth solved from daemon startup alone. Next acceptance check: nearby iPhone with Bluetooth on, no manual Connect, allow about a minute and report standby/link outcome; if successful, repeat Settings Bluetooth off/on twice without manual connection.

Owner subsequently reports no visible reconnect progress and asks for Connect takeover. Re-read computer-use skill/guidance/confirmations/API. Two fresh `cua.getState` attempts exited/reset the trusted Node kernel; supported Windows sky initialization failed with `windows sandbox failed: helper_unknown_error: setup refresh had errors`. No browser/session/remote shell was accessed or manipulated by the agent. The daemon test has not yet solved the observed behavior. Request a short read-only selected-phone Device1 snapshot (PreferredBearer, bond/trust/blocked/link/services only) plus fixed Luma connection status; do not print names/addresses/keys or initiate another competing Connect request.

Owner's next snapshot: **PreferredBearer=le**, Paired/Bonded/Trusted true, Blocked false, Connected/ServicesResolved false; Luma says Reconnecting to paired iPhone and Advertising iPhone notification reconnect, reconnect_attempts=12. Owner also fully power-cycled Luma. The counter is per-process, so 12 is not comparable to the earlier 4,926 as a failure-rate measure. Enabling the LE preference alone has not demonstrated a fix; a stale pre-restart session is not the sole explanation. Preserve the existing bond and do not ask for another reboot.

Prepared two passive probes under source/tools: `probe-bluetooth-reconnect.py` correlates only the selected phone's observed Connect/Disconnect request serials with BlueZ errors, emitting fixed allowlisted error/reason labels and elapsed seconds. It invokes no Device1 methods, ignores raw error text, stores no monitor capture, and handles observed method calls without replying. `probe-bluetooth-reconnect-errors.sh` is the shorter daemon-wide dbus-monitor fallback with an output-only allowlist; it cannot conclusively attribute other devices' errors to the selected iPhone. **Seven probe checks passed**, including an actual private-D-Bus monitor/error exchange and real dbus-monitor output filtering, 2 dependency warnings, 0.39s. No actual radio capture or owner-run probe result yet. The prior 1,511 full backend result predates these seven checks; do not claim a new complete suite run from the targeted result.

- Radio failure isolated; owner confirms fresh pairing recovery works. Terminal-error cleanup correction has race/timeout/bond/privacy regressions; do not claim that application change regenerates encryption keys.
- Verify actual expired-token UI rendering and signed app upgrade/rollback from 0.2.9, preserving local state.
- Full backend and packaging tests, clean accepted main commit and exact-commit CI.
- Offline-sign the new application asset, qualify the exact bytes and publish Beta on the stable GitHub channel. Do not modify older immutable assets.
- Owner installs once through Settings, reconnects Google, checks successful sync/refresh and tests actual automatic iPhone return. Source tests alone cannot prove Pi radio behavior.
