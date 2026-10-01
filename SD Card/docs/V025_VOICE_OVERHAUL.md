# 0.2.5 voice overhaul — working design and acceptance gates

Status: the **unpublished supervised 0.2.5 hardware-test package is ready** in the owner's local `SD Card/updates/v025-supervised-20261001` folder; see [V025_SUPERVISED_TEST.md](V025_SUPERVISED_TEST.md). **Do not publish 0.2.5 or call voice fixed until the physical Pi passes the tests below.** Keep the separately signed 0.2.4 voice asset and all user settings during application updates. Main/release promotion still requires owner approval.

Release integration gate: this branch starts at the current `main` snapshot. The updater recovery work (including the installed-release permission fix) is now merged locally; BOOT-card logging remains a separate OS-image draft and cannot be installed through an app-only bundle. A feature-branch test candidate must use a supervised local/SD delivery path; the hub's stable updater only accepts a signed release targeting `main`. Qualify signed-bundle switching and rollback on a disposable Linux tree before offering the candidate for physical Pi testing, then perform the real-Pi acceptance and seek owner approval before stable `main` promotion.

First source slice on `codex/luma-voice-025`: the API and voice service explicitly select the same per-user Pulse socket and Luma sink; the latest reply engine/fixed playback failure code is visible locally; the sample reports a concrete route or synthesis error instead of a generic silent failure. This is not yet hardware-qualified.

Further output-path work: both Piper playback and a new short, non-speech diagnostic tone now verify that PipeWire lists the named `luma_speaker` sink and explicitly target it. Settings → Voice shows separate tone and speech-sample results, so an absent sink is not mistaken for a bad voice model. A successful process exit still cannot prove the tone was audible; the owner must confirm that on the Pi. The two paths still run in the API service rather than the voice service, so matching user/session routing is source-checked but not yet a physical acceptance result. The named-sink check and explicit-device playback use the documented PulseAudio-compatible [`pactl`](https://manpages.debian.org/testing/pulseaudio-utils/pactl.1.en.html) and [`paplay`](https://dyn.manpages.debian.org/testing/pulseaudio-utils/pacat.1) interfaces.

Second source slice: the guided check now covers ten phrases: eight wake+command examples, including the owner's failed "what time is it"/"good morning" and a distinct "what's the time" variant, followed by two ordinary speech controls that must **not** activate Hey Luma. It runs the same constrained and unrestricted transcription passes and arbitration as live commands. The temporary on-device Voice page now shows the actual raw results separately from the selected intent; it no longer fabricates a combined "heard" phrase. Conflicting decoders cannot pass calibration. The flow distinguishes a missed wake, false wake, wrong command, unsupported command, quiet signal and clipping, and can persist up to three bounded four-step ReSpeaker capture-gain changes for clear level faults. It does not tune Vosk's acoustic weights, wake detector or intent network, and does not claim that automatic gain fixes recognition errors with an adequate signal.

Third source slice: live commands now compare constrained and unrestricted decoding instead of always replacing a valid constrained command with garbled free dictation. Disagreement on a consequential action or numeric value does not execute either command; safe query disagreements favor unrestricted wording. An incomplete utterance caused by a full audio queue is discarded and counted. Non-command API calls have a short timeout so they cannot stall the four-second capture queue. A held-out authored paraphrase set revealed a missing "what's the time now" variant; common time, calendar and weather wordings were added and the local intent weights regenerated. A partial wake hypothesis now lights the listening orb while speech is ongoing, but only the finalized exact wake can execute a command; false partials return to idle. This is still not a physical speech-accuracy benchmark.

Desktop qualification as of October 1: the full backend suite passes (1,098 tests), the image-builder suite passes (43 tests), the frontend unit suite passes (133 tests), and an isolated Windows frontend TypeScript/production build passes. The former updater symlink-layout test failed only because this Ubuntu 3.14 test host generated an extra non-ASCII `𝜋thon` alias; the test fixture now removes that host-only alias while the updater keeps rejecting unexpected links. The updater-test fixture also now handles a CRLF source `pyproject.toml` while preserving the installed dependency-contract check. The final copied signed package is 1,197,599 bytes, SHA-256 `193b44eec29f07f00bb7c96af6abbfcfd1ae8d4cea4a5e00e62c5fbca7d3a96f`, matches source commit `586e1fdb44d33aa9ec4b1bc9057aee4076110877`, and passed disposable Debian 0.2.4→0.2.5 switch and failed-health rollback checks. The Windows BOOT armer passed a simulated-card test; its Pi first run is pending. Earlier draft archives in `.build-tools` are stale and **must not be used**. These checks do **not** prove that the Pi's microphone capture, speech playback, latency, thermals, updater or rollback work in place.

The owner's latest to-do preference is also implemented on this branch: completed Google Calendar tasks no longer appear or consume pages on the rotating to-do slide. The Google color/sync state is retained; [TODO_CALENDAR.md](TODO_CALENDAR.md) explains how to reopen a task in Google.

The Calendar slide's automatic rotation now looks forward 14 hours, including ongoing appointments and tomorrow morning when late-night viewing crosses midnight; past/empty windows are skipped. Manual **Full day** still exposes the entire local day. This change has backend/frontend unit coverage and a clean TypeScript build, but visual/device acceptance remains open; see [DAY_AGENDA.md](DAY_AGENDA.md).

## What 0.2.4 actually does

1. ReSpeaker capture is read from the PipeWire `luma_mic` source at 16 kHz. A fixed Vosk grammar listens for `hey luma`; the whole utterance is then retranscribed with an unrestricted Vosk recognizer. The wake indicator is only shown after Vosk ends the utterance. The small neural intent classifier sees *text after transcription*, so it cannot recover a missed wake word or badly transcribed speech.
2. The three-phrase "calibration" only reports level and exact phrase matches. It saves no learned sensitivity, timing or gain profile and does not train an acoustic model. Rename it or make it genuinely adaptive.
3. The optional Kristin Piper model is marked "ready" when its files and runtime exist. That is not a speaker-path test. A normal voice reply silently falls back to `espeak-ng` for 120 seconds after any Piper startup, synthesis or playback failure. The UI does not show which engine spoke or why it fell back.
4. "Hear a sample" runs in the system `luma-api.service`; ordinary voice replies run in the user's `luma-voice.service`. Only the latter has the user audio-session context. The two tests therefore do not exercise the same path. The system service does not explicitly set `XDG_RUNTIME_DIR`/Pulse socket access. This is a concrete candidate for the owner's silent preview, not yet a proven physical-Pi root cause.

The owner reports a working speaker, silent sample, robotic command replies and unreliable commands. These are not evidence of a bad speaker. The video recording is not yet machine-auditioned; do not assert its precise timbre from the file name alone.

## 0.2.5 implementation order

### A. Make output truthful and audible

- Use one explicit local PipeWire/Pulse playback route for both preview and replies. Resolve the running user audio socket without assuming a fixed UID. Verify the target sink is present; if it is absent, report that rather than claim a sample played. Do not use a cloud TTS service.
- Separate model-installed, synthesis-passed, sink-connected and audible-owner-confirmed states. Surface a short error code and the **actual last-used engine** (`Piper` or fallback) in Settings → Voice. Keep speech text and raw audio out of logs.
- Never silently disguise the original voice as Kristin. If the fallback runs, show why and when the next retry will occur. Provide a retry/test button. Preserve timer alarm behavior during Sleep.
- Test sample speech and a short diagnostic tone via the same service/session/sink as command replies. Ask the owner to confirm audibility; software cannot infer acoustic loudness from a successful `paplay` exit alone.
- Audition several locally runnable, properly licensed voice models with the owner. Tune pace, phrase splitting, pronunciation and Piper's supported synthesis controls conservatively; benchmark native Pi latency, memory and thermals before replacing the shipped voice. Do not mistake a different model's label for an improvement in sound.

The maintained [Piper voice catalog](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md) lists alternate local voices and explicitly warns that each model's own card controls licensing. Do not swap the shipped voice based only on its name or a desktop sample; first establish whether the Pi is actually playing Kristin or the robotic fallback.

### B. Make input measurable before tuning

- Add a private on-device Voice Lab showing: mic RMS/peak/noise floor, capture gain, wake detected/not detected, final transcript, interpreted command, response latency and drop/overflow count. Transcripts are ephemeral unless the owner explicitly exports them; no audio upload or persistent raw recording.
- Run a guided setup from normal wall distance with wake-only phrases, wake+command phrases, calendar/weather questions, short/long utterances and a few deliberate non-wake phrases. Keep several held-out phrases for **validation**, not optimization.
- Tune bounded hardware capture gain and software wake/speech thresholds from the measured signal/noise ratio and recognition success. Save only a numeric profile, versioned with the recognizer, and allow reset. Calibration must never execute commands or inadvertently unlock private content.
- Do not claim that a handful of phrases trains a new acoustic neural network. User samples can tune thresholds and help choose among tested decoding configurations; full personalized acoustic training is a separate and far larger task.

### C. Improve recognition architecture

- Separate wake detection from free-form command transcription; start the listening visual as soon as wake is confidently detected, not after the command ends. Benchmark a dedicated offline `Hey Luma` detector against the current constrained Vosk grammar on Pi 4 before selecting it. Include false-wake tests with room speech and media playback.
- Keep audio frames contiguous during normal processing; expose queue overflow instead of silently dropping chunks. Do not perform blocking network/API calls in the hot capture path.
- Re-evaluate endpointing and post-wake timeouts so short follow-up commands and conversational pauses work. Avoid treating every utterance as a valid *mutation*: ambiguous or negated actions must ask for clarification or do nothing. Safe queries may use a ranked local intent matcher with paraphrase tests.
- Use a reproducible phrase/intent test corpus, including "what time is it" and "what's the time", today/tomorrow weather, next event, calendar today, timers, display, themes and privacy. Record intent accuracy separately from speech recognition accuracy.

## Required physical acceptance tests

1. Cold boot; run sample and test tone. Confirm both are audible and the Voice page reports the true engine and route. Try three replies after a deliberately failed Piper attempt; no hidden two-minute mystery fallback.
2. Run the guided eight wake+command and two no-wake phrases at ordinary room distance and speaking level; report raw constrained/unrestricted transcripts, selected intents, missed or false wakes and end-to-end response times. Repeat after reboot; calibrated numeric settings must persist. Then try at least two more natural command variations not shown during setup. Compare to 0.2.4 under the same conditions.
3. Ten additional non-wake phrases and background media to check false activation; several negated/ambiguous commands to check that no unsafe action runs.
4. Verify that Sleep/night display, privacy standby, Bluetooth reconnection, timer alarms, signed updater rollback and all existing settings survive. Re-run backend and frontend tests, plus native Pi CPU/memory and audio-path checks.

## References

- Vosk distinguishes vocabulary/language-model adaptation from acoustic recognition; its runtime model constraints matter on Pi: https://alphacephei.com/vosk/adaptation and https://alphacephei.com/vosk/models
- PipeWire's Pulse server uses the user runtime directory for its native socket: https://docs.pipewire.org/page_man_pipewire-pulse_1.html
- Piper exposes synthesis pace/variation controls, but they cannot turn an unsuitable model into an inherently natural voice: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
