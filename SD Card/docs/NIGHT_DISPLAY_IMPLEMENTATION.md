# Night clock and gentle wake — implementation checkpoint

September 26, 2026. **Integrated in source: service, commands, local API, desktop bridge, themed UI and guided Extras.** Software verification is in progress; the old image is unchanged. No physical hardware calls were made during development. This is not panel/Pi qualification.

## Owner contract

- Night-clock: only large hours/minutes, black background, subdued theme text; no private calendar, cycling, notifications or seconds. Initial night brightness 5%, separate from day brightness.
- Effective Sleep Time uses the connected union of matching calendar intervals, including touching/future overlaps. Scheduled wake starts at its end, never earlier, and takes 300 seconds.
- Explicit Good morning may override sleep early and uses 20 seconds from the current level. Repeating it does not extend an existing explicit ramp. A morning command during a scheduled ramp replaces the remaining schedule with 20 seconds from the current level.
- Good night and explicit off cancel a ramp. Manual brightness wins over automatic ramp control. Scheduled waking is silent; explicit morning may produce a single privacy-safe briefing.
- Preserve darkness/private startup until boot-local time is trusted. Do not overwrite saved day brightness with ramp samples or write every second.

## Implemented components

`source/backend/src/luma/display_cycle.py` is a pure timing owner with SQLite persistence under cache `display/cycle`. It exposes day/night-clock/off/waking, current logical brightness, quiet state, awaiting-clock state, and a ramp sample (identity, kind, endpoints, elapsed/duration). The caller must supply effective sleep after command overrides, current day/night settings and explicit clock trust.

- Live ramps use injected monotonic time and a smoothstep curve. Late scheduled ticks are backdated to the actual sleep end; completed deadlines do not replay after reboot. Restored ramps use verified UTC only to establish a fresh monotonic anchor.
- Initial unknown clock is black/off. An explicit touch/voice wake can start from black before time sync, but remains marked awaiting-clock. A manual Good night before sync cannot later authorize an automatic wake from its guessed wall deadline.
- Invalid recovery state, backward recovery time or a ramp saved with untrusted UTC stays off until explicit touch/voice recovery. The full-screen wake target remains mounted even when black; the existing device touch reader handles actual powered-off outputs.
- Snoozing/scheduling has no relation to privacy unlock. `wake(..., morning=True)` returns briefing permission, with a 60-second repeated-command suppression record; callers must actually honor that return value. No speech occurs in the module.
- `night`, `off`, `wake`, `manual_brightness` and meaningful sync transitions persist. No tick/frame writes. Clock-disabled sleep can power off and still schedule waking; explicit `held_off` stays off until a wake command.

`source/backend/src/luma/display_handoff.py` coordinates the browser/bridge protocol without executing hardware itself. Only one immutable job is in flight. It uses a conservative physical reference of 100% whenever panel state is unknown. A pending increase raises the software reference before any hardware call; decreasing retains the old higher reference until confirmed. Re-targeting cannot drop the safety reference while a previous increase may still commit.

- Power-on/increase jobs require a matching fresh frame acknowledgement (10-second TTL). Claimed jobs have a 45-second lease, accommodating at most four existing 8-second driver operations. Timeout means unknown commit, never “unchanged”. Late reports and stale acknowledgements are rejected.
- Physical changes are serialized, at least four seconds apart; failure backoff is 60 seconds and cannot be bypassed by continuously changing brightness targets. Power-off is allowed promptly after brightness failure; failed power-off has its own bounded retry.
- A new bridge generation invalidates all physical knowledge. None of this volatile state is written to the SD card.
- `apply_display_job` invokes verified brightness before power-on, and power-off without a brightness call. Unsupported DDC can still power on only beneath a conservative software dimmer. These calls are mocked in tests.

`DisplayController.set_brightness_confirmed` is used by the new bridge worker after commissioning. It reads the panel's VCP maximum, converts the percentage downward into that raw scale, leaves ddcutil's default set verification enabled, and independently reads back current/maximum. Ambiguous, unsupported, inconsistent or timed-out responses do not release the conservative fallback. See [ddcutil set verification](https://www.ddcutil.com/command_setvcp/) and [machine-readable continuous getvcp output](https://www.ddcutil.com/command_getvcp/). Percentages describe control values, not calibrated panel luminance; physical acceptance remains necessary.

## Live integration

Settings default to `night_clock_enabled=true`, `night_brightness=5` when absent, including existing configurations. Explicit saved false/brightness values win; day brightness, accounts, mute and game saves are untouched. Extras → Night & wake explains and saves these independently. Review shows the saved choice. Users preferring the original fully-off sleep can disable the clock.

`LumaService` supplies the effective sleep interval after forced, temporary and morning overrides. Completed installations use boot-local timesyncd trust; Windows preview and tests inject trust. Before commissioning is completed the legacy display path stays available so offline network setup remains possible. Night/off/waking snapshots redact private data regardless of presence. Internal explicit briefings still require real presence/PIN and trusted time. Voice and Shortcut endpoints honor repeated-morning suppression.

The one-second worker advances the cycle and publishes changed samples. Its comparison is against the prior broadcast sample, not the last HTTP read: frequent bridge polling must not consume the waking→day transition. The kiosk stays black before its first authoritative snapshot, interpolates locally, dims the document body over a black root, shows only the themed clock while waking, and acknowledges the matching revision after two animation frames. Frame acknowledgement retries do not grant readiness by timeout. A disconnected non-day view becomes black. Browser opacity does not cover native windows: the bridge closes its owned native keyboard and captive-portal process before claiming a night/wake hardware job, consuming old requests so wake does not replay them.

Local-only strict `/api/v1/display/frame` and `/api/v1/device/display-{register,claim,confirm}` implement the handoff. The desktop bridge runs slow DDC jobs serially on one worker thread so microphone/audio/touch polling continues. Legacy brightness/power calls are disabled when the new display state is present. Restart generations invalidate physical knowledge; driver exceptions report unknown, never success. Diagnostics retain fallback status. Timer chimes are silent in night/off and scheduled waking.

### Software output-off liveness evidence

`image-builder/display-frame-smoke.py` creates a private headless labwc/pixman output and fresh, sandboxed Chromium profile. It verifies only its `HEADLESS-*` output, then turns it off and on. An input-free page reports animation-frame counts; no accounts, browser automation, physical outputs or host desktop settings are involved. Debian Chromium154 on the WSL builder delivered240 frames per4-second interval before, during and after output-off; `document.hidden` remained false. The normal kiosk flags worked; production flags were not changed. This resolves the software compositor deadlock concern for this tested stack, **not physical Pi KMS/DPMS**. Actual panel off/on and retained-frame safety remain a required owner-triggered hardware check.

## Evidence at this checkpoint

57 component cases plus24 service/API/worker integration cases cover timing, recovery, strict local protocol, private startup, nonblocking DDC, driver failure, repeated briefings, timer silence, native helpers and polling/broadcast races. Full452 backend passed (one existing Starlette/httpx deprecation warning). Frontend85 tests and TypeScript/production build pass. Browser layout checks cover3 themes × landscape2048×1536, portrait1536×2048 and narrow390×844 for both night clock and setup (18 layouts total); an arcade narrow overflow, root-background conflict, checkbox alignment and setup-link theme mismatch were corrected. Unsaved-choice guard,101% rejection,7% preview save and navigation were verified.

`source/backend/tests/night_preview.py` is a bounded10-minute isolated real HTTP/WebSocket fixture with temporary SQLite, no provider workers, and simulated panel methods through the actual bridge worker. Browser touch wake completed into the permitted dashboard without reload; explicit off rendered empty black content before subsequent wake. This does not substitute for physical testing.

## Still required

- Keep night/reconnect/native-helper checks in the final integrated software review after the other features; retain honest source/image distinction.
- Include all new files in the exact-file image audit and build a new immutable image after the remaining selected features. Qualify real packaged WebSocket transport, not merely HTTP health.
- Hardware acceptance when requested: actual DDC scale/minimum, backlight glow, power-off/rAF liveness, no bright/private flash on boot/reconnect, physical touch wake, audio and microphone responsiveness during failed DDC.
