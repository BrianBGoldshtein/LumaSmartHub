# Focus timer — source implementation

September 26, 2026. Available in current source and preview; not yet packaged in the delivered Tailscale image. Physical audio checks remain deferred.

## Use

Open dashboard controls → **Focus timer**. Focus defaults to 25 minutes and Break to five. Customize their defaults in guided setup → **Choose your extras → Daily rhythm**, or Device setup → **New: daily rhythm & extras**. Each accepts whole minutes from 1 to 240 and does not change a timer already running.

The timer panel provides pause/resume/cancel and an optional custom duration/label. Starting another active timer requires explicit replacement confirmation tied to that exact timer ID. If another command changed the timer while the confirmation was open, it will not overwrite the new run. Custom labels are redacted from private snapshots and the private display.

Information pages show a compact remaining-time control. Ordinary page cycling continues. Ambient games remain unobstructed until completion; the completion notice and timer panel leave the game component mounted. A single shared overlay choice prevents timer controls, timer completion and phone notifications from stacking.

Local voice phrases:

- “Hey Luma, start focus timer” / “start break timer.”
- “Hey Luma, start a five minute timer,” with supported durations 5, 10, 15, 20, 25, 30, 45 or 60 minutes.
- “Hey Luma, pause timer,” “resume timer,” “cancel timer,” “show timer,” or “dismiss timer.”

The existing private Siri Shortcut endpoint additionally accepts `start_timer` with an integer from 1–240 or `"focus"`/`"break"`, and the no-value actions above. Remote commands cannot provide a custom label or confirm replacement; they do not unlock privacy. Configure the transport as described in `TAILSCALE.md`. No account sign-in is needed for local timers.

## Time and durability

The backend owns the countdown. While alive it uses a monotonic deadline, so wall-clock/NTP changes do not shorten or lengthen the run. Browser rendering extrapolates a server sample using `performance.now()`; browser time is not authoritative. SQLite stores only meaningful transitions and corrected recovery anchors, never every displayed second.

On restart a running timer waits for verified system time before using its saved UTC deadline. The Pi uses the boot-local timesyncd synchronization marker. A timer that began before time verification remains paused after restart until reviewed/resumed; it never guesses elapsed outage time. Pause recovery and Resume can explicitly continue the saved remaining duration if offline, accepting that the outage duration is not known. A timer already expired on restart completes silently, without replaying an old chime.

Upstream basis: [systemd-timesyncd synchronization marker](https://github.com/systemd/systemd/blob/main/man/systemd-timesyncd.service.xml). The marker is boot-local, unlike the persistent approximate clock file. The image must retain its timesyncd service; a different NTP implementation needs its own qualified trust adapter.

## Completion and audio

A backend transition creates a ten-second, memory-only opportunity to play a clear, 2.08-second rising multi-tone alarm, ending with a sustained note. The desktop bridge claims it once before playback. Claim failure, playback failure, process restart and bridge retries do not replay it. Scheduled Sleep, display-off and night-clock quiet modes do **not** suppress a timer the owner explicitly started; setting hub volume to zero does. A timer already expired on reboot remains silent and is never replayed.

The alarm is synthesized in memory and sent to the already-installed `paplay` utility on the selected system sink. No audio file, browser autoplay exception or external sound asset is required. See [Debian paplay reference](https://manpages.debian.org/bookworm/pulseaudio-utils/paplay.1.en.html). Software verifies the playback request and at-most-once behavior; actual speaker audibility, output routing and volume still require the owner's physical qualification.

## Implementation and checks

- Backend: `focus_timer.py`; additive timer preset settings; service snapshot/command integration; one-second completion worker; local-only sound claim; bounded Shortcut language; local speech grammar; `timer_chime.py` desktop bridge.
- Frontend: `FocusTimer.tsx`, `timerState.ts`, `features.css`, `ExtrasSetup.tsx`; shared root overlay selection and optional onboarding step. Tetris/other game engines unchanged.
- Automated timer tests cover pause/resume, monotonic vs wall time, reboot trust/expiration, reanchoring, no periodic writes, stale replacement IDs, bounds, corrupt cache, label privacy, quiet/expired sound claims, API restrictions, voice/Shortcut grammar, failed playback deduplication and demo arithmetic.
- Timer checkpoint: 297 backend tests (including real TCP transport) and 75 frontend tests pass. TypeScript and production build pass. End-to-end local browser checks used isolated `runtime/timer-ui-qa` storage, no owner accounts and no hardware bridge/audio process; pushed completion without reload verified after the dependency fix. Both isolated API sessions were stopped. Later feature increments increase the suite counts in `CURRENT_STATUS.md`.

Remaining delivery gates: integrate the other planned features (including night-clock silence), test complete cross-feature priorities, build and software-qualify a new immutable Pi image, then await the owner before physical testing.

### Real transport regression discovered during UI testing

The existing minimal `uvicorn` dependency did not install a WebSocket transport. The in-process TestClient suite could pass while a real browser failed to receive updates. Added explicit `websockets>=15,<17` (Windows QA resolved 16.1.1), plus `test_live_transport.py`, which starts the real Uvicorn TCP server, subscribes to the live event stream, starts a timer over HTTP and verifies pushed completion and one-shot sound claiming. It does not use Starlette's in-process WebSocket stand-in.

Also fixed server-side disconnect handling: the event route now waits for connection closure as well as queued state, cancels its tasks and unsubscribes promptly. The real transport test checks bounded server shutdown. This dependency is required for all live dashboard updates, not only timers. [Uvicorn documents WebSocket transport as optional in a minimal install](https://uvicorn.dev/installation/).

**Do not treat the old image's HTTP/QEMU smoke pass as proof of live WebSocket delivery.** New image acceptance must explicitly verify the real event stream from its packaged environment. The old image is retained as a historical candidate, not the final expansion deliverable.
