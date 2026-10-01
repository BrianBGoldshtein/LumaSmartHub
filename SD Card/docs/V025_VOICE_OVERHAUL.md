# 0.2.5 voice overhaul — working design and acceptance gates

Status: design and diagnosis in progress. **Do not publish 0.2.5 or call voice fixed until the physical Pi passes the tests below.** Keep the 0.2.4 voice asset and all user settings during application updates. Main/release promotion still requires owner approval.

Release integration gate: this branch starts at the current `main` snapshot. Before constructing a signed update, reconcile the still-separate updater recovery work (including the installed-release permission fix) and BOOT-card logging work, then run update/rollback qualification. Do not assume a feature-branch commit is deployable by the hub's stable updater.

First source slice on `codex/luma-voice-025`: the API and voice service explicitly select the same per-user Pulse socket and Luma sink; the latest reply engine/fixed playback failure code is visible locally; the sample reports a concrete route or synthesis error instead of a generic silent failure. This is not yet hardware-qualified.

Second source slice: the guided check now covers six phrases, including the two commands the owner reported failing ("what time is it" and "good morning"). It reuses the **same unrestricted second transcription pass** as live commands, briefly shows the effective words heard on the local setup screen, and can persist up to three bounded four-step ReSpeaker gain changes for clearly quiet or clipped attempts. It does not tune Vosk's acoustic weights, wake detector or intent network, and does not claim that automatic gain fixes recognition errors with an adequate signal.

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
2. Ten wake+command phrases at ordinary room distance and speaking level; report wakes, transcripts, matched intents and end-to-end response times. Repeat after reboot; calibrated numeric settings must persist. Compare to 0.2.4 under the same conditions.
3. Ten non-wake phrases and background media to check false activation; several negated/ambiguous commands to check that no unsafe action runs.
4. Verify that Sleep/night display, privacy standby, Bluetooth reconnection, timer alarms, signed updater rollback and all existing settings survive. Re-run backend and frontend tests, plus native Pi CPU/memory and audio-path checks.

## References

- Vosk distinguishes vocabulary/language-model adaptation from acoustic recognition; its runtime model constraints matter on Pi: https://alphacephei.com/vosk/adaptation and https://alphacephei.com/vosk/models
- PipeWire's Pulse server uses the user runtime directory for its native socket: https://docs.pipewire.org/page_man_pipewire-pulse_1.html
- Piper exposes synthesis pace/variation controls, but they cannot turn an unsuitable model into an inherently natural voice: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md
