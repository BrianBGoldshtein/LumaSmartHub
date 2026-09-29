# Room devices — purifier, fans and scenes source status

Newest September 29 fan follow-up: the active Test view now shows a durable
unknown IR-send result immediately, instead of hiding it until Back, and a
failed/unknown send clears its acknowledgement so repeating requires a new
explicit decision. The real HTTP/WebSocket-capable temporary fixture with
fake IR passed three-theme narrow browser checks for unknown receipt, blocked
repeat, no secret/sentinel leak and no horizontal overflow. A held learn was
cancelled by a synthetic privacy lock; the private view disappeared and the
saved button revision did not change. Focused fan backend tests: 30 pass;
frontend 131 tests and production build pass. No actual USB IR/fans/touch or
owner account was used; hosted CI and next image remain outstanding.

Newest September 29 source follow-up: the purifier now displays a short,
disabled discovery countdown after successful login, matching the service's
five-second VeSync setup pacing rather than surfacing a predictable rate-limit
error during onboarding. `source/frontend/qa/room-interactions.mjs` passed
against temporary SQLite and the real local API with synthetic VeSync HTTP:
sample sign-in/selection, offline controls removed and fresh recovery in all
three themes at 390 px, privacy redaction during a dirty reconnect form, saved
selection survival, no provider token/password leak and zero unintended
purifier commands. The scene browser script additionally passed fan and
purifier dirty-draft, safe-focus, both-way Tab, Escape and discard checks in
all three themes at 390 px. 131 frontend tests and production build pass.
No physical touch, owner credentials, actual VeSync or USB IR were used;
the [hosted purifier CI run](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36646429234)
passed; the next image still needs this source.

Later September 29 source-only acceptance: a synthetic privacy transition
during a held scene action hid the private editor immediately; the durable
run was interrupted and did not replay on unlock. A shared keyboard handler
for scene, fan and purifier confirmations now focuses the safe choice, contains
Tab in both directions and lets Escape dismiss. Chrome checked all three
themes for the scene confirmation and sample fan/purifier dialogs at 390 px.
Physical touch, keyboard, Bluetooth timing and real device behavior are still
untested. The prior scene commit's hosted Linux CI run failed only in an
unclosed WebSocket test session (995 pass/1 teardown error); the test now
closes it explicitly and hosted Linux
[run 36645184679](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36645184679)
passed at `094d841`. These changes are newer than r11.

September 29 post-r11 scene correction: unsaved private iPhone scene
permissions can no longer be dropped by opening a scene or refreshing; an
explicit discard button is available. Stop scene appears only for a running
scene, uses an independent cancellation request, and the editor re-reads
durable local results rather than retrying the run. Backend cancellation and
mid-run authorization loss now leave a terminal **interrupted** journal, not a
misleading finished result. A three-theme 390 px Chrome fixture passed the
draft/discard flow; a held synthetic fan action was dispatched once, stopped,
and remained durably interrupted after reopening the store, with no replay.
The full Windows backend suite passed 963 tests/33 expected Linux-only skips;
131 frontend tests and production build passed. This source is **newer than
r11** and has not been built into a Pi image or tested on hardware. Fan dirty,
privacy transition, physical keyboard/touch, actual USB IR and appliance checks
remain open.

September 29 current addendum — source commit `9818b65` and
[hosted CI run 36635445931](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36635445931)
passed. A synthetic, real-rendered browser matrix now
covers Air purifier, Two fans and Room scenes entry/back navigation in Hearth,
Luma Glass and Neon Grid at390×844,1280×720 and1536×2048. All 27 combinations
fit their viewport without horizontal overflow; embedded Extras now resets
scroll to the selected page top. Against the local production HTTP API with a
fake VeSync transport, the purifier's long selected name, offline refresh and
successful fresh-state recovery passed in all three themes. An outage removes
the stale purifier controls immediately, while showing the saved reading and
fixed no-queue error; recovery restores controls only after a valid reported
read. No test logged in to a real account, contacted VeSync or switched an
appliance. This is source newer than the r10 image. Still open: scene/fan
interaction failures and recovery across themes, actual touch/keyboard and
owner hardware/provider checks. Older evidence paragraphs below are historical
and should not be read as denying this later viewport/recovery pass.

Further September29 source-only browser pass: the fan/scene detail views now
reset their scroll positions after each transition. Three themes at narrow
phone-width and Glass portrait showed the top heading, with no horizontal
overflow. The real local fan API on a disposable fake-IR transport returned
USB-unavailable during a one-shot test; the UI immediately reloaded saved
state, displayed a durable unknown outcome and fixed no-retry message, and
exposed no transport sentinel. A stale-but-currently-valid scene grant could
be deliberately reauthorized from the local UI; the fake scene dispatch count
did not increase. **131 frontend tests and production build pass.** This is
not in r10. Dirty/edit cancellation, privacy lock during operation, physical
touch, actual USB and appliance outcomes remain to be qualified.

USB IR transport, owner-local fan setup, scene paths and a separate default-off remote-scene allowlist are implemented in source. Read [IR_DEVICES.md](IR_DEVICES.md) and [SCENES.md](SCENES.md) before extending. Dedicated unprivileged Unix broker, bounded isolated child, strict USB/LIRC discovery, one-button capture/one-shot transmission and packaging have prior73Linux-test evidence. `fans.py`, `fan_runtime.py`, `fan_api.py`, `FanSetup.tsx` and `fanState.ts` add durable two-output configuration, bounded learn/test/cancel, same-state repeatability and both-direction observation checks, unknown-before-send receipts, one-hour overrides, private owner/same-origin gates and themed optional setup. `scene_devices.py`, `scene_runtime.py`, `scene_api.py`, `scene_executor.py` and `SceneSetup.tsx` connect absolute safe actions, strict local owner access, explicit calendar/presence triggers and durable no-replay accounting. Hey Luma supports fixed manual run/cancel phrases for already-enabled scenes through the same owner/device/clock guards. The local **Private iPhone actions** panel separately grants named remote scene bundles; the restricted Tailscale gateway verifies the exact ordered actions and device bindings, and any change/relink requires local re-review. Learning/pairing never grants scene or remote permission. Remaining: fan/purifier credential and error/reconnect paths across themes, custom long-name layouts, real touch/pointer acceptance and owner hardware/account checks. No physical qualification yet; hardware selection remains open in [HARDWARE_ADDITIONS.md](HARDWARE_ADDITIONS.md).

Fan UI evidence — September28 browser passes: an earlier sample-mode Hearth flow configured two outputs, enforced separate learner/test acknowledgements and two-fan observation, and kept the second observation requirement visible; no IR device was accessed. A later real-rendered `FanSetup` pass used the production local HTTP API with the disposable fake-IR fixture; its details follow below. Earlier overview-only checks include Neon at390×844,2048×1536,1536×2048 and Glass portrait with no horizontal overflow. `fan-setup-hearth-qa.png` is synthetic demo data, not hardware proof. The attempted broad rapid viewport matrix was invalid/stale and must not be counted. No physical touch qualification. All-theme/theme-specific game-style/keyboard/error/reconnect/pointer and real remote/fan paths still need coverage. Do not redo the fan store/API/UI because an older checkpoint says transport-only.

September28 setup-flow recheck — the interactive demo was rendered at2048×1536,1536×2048 and390×844 for Air purifier, Two fans and Room scenes in all3 themes (27 overview combinations). Every document/body width matched the viewport; no horizontal overflow. A sample two-output configuration kept learning disabled until both distinct fan outputs were selected, and retained the explicit IR identification/test/observe-both-fans guardrails. The scene editor presented only supported sample actions; an empty scene remained off, the scheduled Sleep trigger stayed disabled until explicit scene opt-in, and leaving a dirty draft required confirmation. The sample draft was discarded and all four scenes remained off; no settings, account, provider, hardware or appliance were changed. This closes the broad overview-size/theme matrix only—not narrow/portrait interaction error recovery, actual touch, or owner hardware acceptance.

Purifier setup error/reconnect and long-name evidence — September 28 synthetic browser pass against `room_preview.py`: logged in and selected only a fake Core300S; tested a long custom device name, offline refresh, rate limiting, and a failed re-login using synthetic credentials. At1280×720 the name wrapped cleanly to two lines and page width stayed1280 in Hearth, Glass and Neon. An outage immediately reported “VeSync is unavailable. Nothing has been queued”; the later saved-state refresh correctly changed the header to “Saved reading · check needed,” relabeled values as the last reading, and removed controls until a fresh successful read. Rate limiting displayed its explicit wait message. Failed re-login displayed the fixed reconnect message, cleared the attempted password field, and retained the prior session/device selection; an API snapshot confirmed they remained saved and included none of the fake password/provider token/account sentinels. No actual account/device or provider was used. This does not cover narrow/portrait viewport, keyboard/touch, every error/recovery branch, or hardware.

Fan API integration evidence — September28 `fan_preview.py` + `fan_live_check.py`: real local HTTP and WebSocket over a temporary database, with the production `FanRuntime`, `Fans` store and API; only the transport is fake. Discovered one synthetic selectable USB IR endpoint, assigned separate emitter channels to two named slots, learned an absolute signal, required explicit test confirmation, recorded both same-state checks, and observed that scene eligibility became true only after the other fan also had an independent observation. An injected unavailable result after the durable claim produced a generic HTTP503 and preserved an `unknown` receipt; its private sentinel never appeared in HTTP or WebSocket. While a learn was deliberately blocked, another discovery returned429 (no queue), explicit cancel returned the in-flight request as409, and the late learned button was absent. The fresh hub WebSocket remained privacy-redacted. PASS; `tests/test_fans.py`:30 passed in Debian. Synthetic only—no USB, remote, appliance, Pi or SD. This does not qualify udev/socket activation, the installed broker under its systemd sandbox, actual IR output, touch or owner fan acceptance.

Rendered fan-setup follow-up — September28, Hearth at1280×720 against the temporary production-API/fake-IR fixture: configured both output labels (including a40-character label), and verified both persisted and rendered on the overview. The simulated USB-unavailable branch showed that no command would be retried. Entering button learning required explicit identification of the correct remote button; the one-shot test separately required acknowledgement and then asked the operator to observe both fans. I intentionally did not record a synthetic observation as a real outcome. A blocked learn exposed Cancel recording; cancelling it displayed the fixed no-retry/reload message. Reloading showed cancellation count1, fan1 retained only its earlier `Off` button at0/2 checks, fan2 retained no button, and the cancelled `On` button was not saved. An injected transport exception displayed a fixed “Fan operation could not finish. Check both fans before sending another command” message; setting the fake transport back to normal and reloading cleared the error while preserving saved setup, with no auto-retry or `On` button. The complete overview and Buttons & controls pages were also rendered in all three themes at1280×720; document dimensions stayed1280×720 with no overflow in Hearth, Luma Glass or Neon Grid. Interaction/error flows remain Hearth-only; narrow/portrait/tablet, real touch, full keyboard/pointer and actual remote/fan checks remain.

Room-scene UI evidence — September28 preview-only browser pass: scene list and action editor fit 2048×1536,1536×2048 and390×844 in Glass, Hearth and Neon with no horizontal overflow. Sample actions remained explicitly labeled as preview-only; all four automatic scene defaults stayed off after discarding the test draft. Pointer selection/add/review and local-enable controls worked in Neon; keyboard Space toggled the Sleep trigger after the explicit scene enable, then was reverted. The unsaved-edit dialog appeared and safely discarded the draft. QA found muted status text below1.5:1 contrast; scene-card statuses are now bold22.4px and inherit the card's dark text, measuring12.01:1 Glass,9.83:1 Hearth and13.18:1 Neon over the nine theme/viewport combinations. This is sample UI behavior, not an owner-configured live scene, full touch acceptance, provider failure/reconnect test, or hardware proof. Current frontend tests:112 passed; TypeScript and production build passed (`index-DgQv9Dlb.js`, `index-CjCfDND2.css`).

The former scene-foundation-only description is historical: production dispatcher, runtime worker, API and themed UI are now connected, and native local voice run/cancel commands were added September28. See SCENES.md for current gates. Purifier manual override persists independently of selection/last receipt and survives edits/reconnect; scene claims do not extend it.

Feature9 is not complete. The Core300S adapter, durable store, service worker, owner-local API, themed setup/control panel and onboarding summary are implemented. Synthetic HTTP, real local HTTP/WebSocket and keyboard-driven browser checks have passed as described below. Native local voice scene commands now run/cancel saved manual scenes under existing gates. A separate default-off remote-scene allowlist now exists: it is locally owner-managed, bound to exact ordered scene actions/device bindings, and becomes ineffective after a scene edit or device relink until re-reviewed. No real account enrollment, appliance command or physical test has occurred. Fan hardware acceptance and further UI qualification remain. This document supplements the exact owner requirements in EXPANSION_PLAN section9; it does not narrow them.

## Store, runtime and UI integration

`room.py` atomically persists the selected device and private session, using separate configuration revisions and process/session generations. Candidate login failure preserves the previous account; successful replacement/disconnect clears selection and receipts. Corrupt saved data stays untouched and disables commands. Readings remain memory-only, avoiding per-poll SD writes. A durable unconfirmed command receipt is written BEFORE transmission, including a one-hour manual-override deadline. Restart never replays it; failed final storage leaves the durable unknown outcome intact. `scene_devices.py` and `scene_executor.py` recheck this persisted per-device override before every scene dispatch; a manual command suppresses that device for one hour, and scene dispatch does not extend the deadline.

`room_runtime.py` starts no provider I/O until both a saved session and selected device exist. It polls about every120seconds, backs off failures up to30minutes, waits an hour on provider rate limits, and stops automatic authentication attempts after expiry. Owner operations are serialized without queuing; discovery/sign-in and commands have separate short pacing gates. Every awaited operation checks configuration/session revisions; commands additionally recheck privacy after their preflight read and before transmission. Disconnect invalidates the session before waiting for in-flight I/O. Old failures cannot mark a new selection offline. Service shutdown cancels/awaits workers before adapter close.

Owner-local endpoints: GET `/api/v1/room`; POST `/api/v1/room/vesync/login`, `/vesync/disconnect`, `/purifier/discover`, `/purifier/select`, `/purifier/refresh`, `/purifier/command` (all relative to `/api/v1/room`). Configuration changes/actions require current revision; selection requires a current discovered device and successful read. Login alone manually streams at most4096bytes in3seconds, rejects duplicate fields and never returns validation echoes of credentials. Post-commissioning phone/PIN privacy, loopback and same-origin gates apply; there is no remote API bypass. The service snapshot `room` is null outside full private access, including night; the browser clears it on lost WebSocket connection.

Extras → Room devices → Air purifier reuses existing themed setup tokens/TouchField. Flow: vendor/network prerequisites and cloud disclosure → masked local sign-in → discovery → explicit selection/name review → fresh capability-gated controls. Setting speed/mode clearly warns it can power on the purifier. Reports power/mode/speed/filter/optional particle/display fields; missing metrics are absent, not zero. Displays stale readings and unconfirmed outcomes explicitly; controls expire client-side after5minutes without fresh data. Local configuration refresh every15seconds does not call VeSync. UI requests have30second deadlines and never auto-retry uncertain commands. Draft/discard, busy, separate removal confirmation and post-commission privacy-unmount paths are present. Demo uses only in-memory synthetic state, no real writes. Onboarding includes only session/selection/recovery booleans, never device/account names or secrets.

## Verified library and compatibility

Public [PyPI metadata](https://pypi.org/project/pyvesync/3.4.2/) reports3.4.2, Python>=3.11. Installed that exact release in the project virtualenv and pinned it in backend pyproject.toml. Wheel SHA256: `8f0a75433ce51f7ba8a539880ab654d3c5291a3a87de00cd496a5b8630a402f0`. The installed MIT notice is also retained under source/assets/licenses/PYVESYNC-LICENSE.txt. Transitive dependencies still need final-image inventory/ARM validation, like the existing Python dependencies.

[Upstream documentation](https://github.com/webdjoe/pyvesync) describes the asynchronous V3 interface and session credential import/export. Exact installed3.4.2 source was inspected: vesync.py, auth.py, device_map.py, devices/vesyncpurifier.py, base_devices/purifier_base.py, utils/device_mixins.py/helpers.py/errors.py/logs.py and relevant response models. This is an unofficial cloud API integration, not a local-LAN protocol or vendor-supported Luma integration.

Supported API model IDs are the library's Core300S family: Core300S, LAP-C301S-WJP, LAP-C302S-WUSB, LAP-C301S-WAAA and LAP-C302S-WGC. A printed300S-P label alone is not evidence of its returned API ID; discovery must match. Core400S and unrelated devices are intentionally not exposed by this owner-scoped adapter. Three speeds and manual/sleep/auto modes come from the discovered library feature map. Display control appears only after a valid device response reports its display fields. Missing particle/air-quality metrics remain unknown, never zero.

## Implemented adapter boundary

`purifier_adapter.py` owns no storage, worker, presence, scene or authorization. It has no I/O until called. Runtime must authorize owner access and select one discovered device before invoking it.

- Version mismatch fails closed. `PurifierAdapter(saved_credentials?, timezone, transport?)` supports injected httpx transport for tests. `login(username,password,country)` returns internal session fields only; never send this return value to a browser. Username/password exist only in the short-lived candidate login and are cleared from the pinned library auth object on success or failure. A failed candidate preserves the prior session. This is best-effort Python reference clearing, not guaranteed RAM zeroization.
- Persist only token/account_id/country_code/current_region in the existing private secrets store. No plaintext password persistence, implicit token-file discovery, account-file writes or provider automatic password retry. Token expiry requires owner reconnection.
- Library request/response models and device methods are reused. The HTTP boundary is replaced: fixed HTTPS US/EU hosts; four exact API paths; five named Core300S methods; TLS validation; no redirects or environment proxies;10-second I/O timeout/5-second connect;20-second whole-operation deadline;2MiB decoded response limit. Cross-region login is capped at four authentication requests. Device discovery rejects unsupported larger/paginated accounts rather than silently presenting a partial list as complete.
- Third-party payload/device-name logs are suppressed; exceptions translated to fixed messages. No provider payload or credential is copied to UI/audit errors. httpx request lines contain fixed endpoints, not query credentials.
- `discover()` lists only compatible models and returns opaque stable IDs (hash of provider CID), bounded names and capabilities. It does not poll every account device. `read(id)` performs one status request; only actual valid read responses become reported state. A failed/malformed response cannot reuse optimistic state or a previous sample as fresh.
- `command(id,action,value)` permits absolute power/display booleans, speeds1–3 and discovered modes. No arbitrary method, raw payload, filter reset, timer, firmware change or blind toggle. Speed/mode actions can turn on the purifier (the library's semantics); explain this next to those controls. Preflight status must succeed. Busy calls are rejected immediately, not queued. Exactly one requested command is sent; no automatic replay.
- Return `confirmed` only after a separate valid readback matches the requested state (including on/manual for speed). An accepted but unmatched/unreadable response is `unconfirmed`. A timeout after dispatch is unknown, never a falsely failed command inviting automatic replay. Runtime must preserve this distinction. External cancellation may interrupt an operation; runtime must record outcome unknown, not retry on restart.
- `close()` waits for serialized operations; runtime cancels/awaits its worker first. No aiohttp session is opened by the library because every API call uses the bounded transport.

## Evidence

34 adapter tests use real pinned pyvesync classes with httpx.MockTransport. Covers discovery/filtering; no unrelated polling; real command serialization; fresh readback vs optimistic state; missing fields; strict actions; authentication/429/redirect/server errors; busy rejection; secret-free logs/session returns; old-session retention and password clearing; malformed/oversized responses; deadline after dispatch; token expiry/no reauthentication; endpoint/method allowlist; larger-account rejection.

22 room store/runtime/API tests add restart persistence/no replay, atomic disconnect, corruption preservation, failed claims/final disk writes, reading expiry, no-network idle, real adapter selection/command/cadence, backoff/auth stop, owner expiry during login/preflight, disconnect mid-read, cancellation after dispatch, immediate busy rejection, stale-failure suppression and local/owner/secret-body gates. Four frontend pure tests cover empty defaults, client-side expiry, strict fresh capabilities and distinct outcomes. Full685backend and103frontend passed; TypeScript/production build passed (details in CURRENT_STATUS).

Disposable `tests/room_preview.py` serves real app/SQLite/HTTP/WS against synthetic VeSync on8750 for20minutes; no unrelated radio/audio/provider workers. Browser saved a named device after masked login, discovered only the supported model, enforced dirty navigation, reloaded selection, issued one confirmed and one accepted-but-unmatched sample command, removed private controls/names on WS lock, discarded reconnect credentials, and confirmed disconnect. `tests/room_live_check.py` independently verifies that browser-saved record, secret-free config/review, real WS redaction, locked API/command403 and no unintended mutation. Temporary fixture data is not an owner account.

Control layout: all3themes ×2048×1536,1536×2048,390×844 with six reported fields; no horizontal overflow/clipped buttons. Rapid viewport requests occasionally returned the prior dimensions; actual missing dimensions were rechecked separately. Pointer automation did not reliably activate controls despite visible unobstructed elements; keyboard activation succeeded. Do not claim touch/pointer acceptance from this run. Remaining UI checks: pointer behavior in a responsive browser session/physical device, all-theme credential-keyboard/review/long-name layouts, browser provider-error recovery and disconnect while a form/command is in progress. Backend covers these races, but it is not a substitute for UI evidence. Screenshot `room-setup-hearth-qa.png` shows synthetic data only.

## Next integration sequence

1. Complete remaining purifier/fan/scene UI qualification above, including the remote-permission consent/review and stale-grant recovery paths. Native local voice scene run/cancel is implemented; do not weaken owner-local credentials, privacy, learning or presence requirements.
2. Preserve the USB/LIRC and two-fan learning gates. Do not use ReSpeaker GPIO. Exact USB adapter/emitter and fan models remain owner/hardware setup inputs. Independent reception checks in both directions are mandatory before autonomous action; learned toggles remain manual-only; report IR results as unconfirmed.
3. Keep Morning/Night/Arrive/Away empty and disabled by default. Authenticated nearby-phone evidence only (not PIN/Tailscale/boot),30-second arrival/3-minute departure,5-minute cooldown,1-hour per-device override. Never replay missed runs; persist claims before I/O and show partial/uncertain outcomes. Pairing and local setup never grant remote permission.
4. Finish real temporary HTTP/WS/browser checks, long names, touch/keyboard, errors and all-theme layouts, then exact-image/Linux/ARM/packaged-WebSocket checks. Only the owner can qualify actual VeSync, IR, campus and physical behavior. No appliance/network enrollment on the owner's behalf.
