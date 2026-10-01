# 0.2.6 beta backlog

Development branch: `codex/luma-026-development`. None of this is included in the signed 0.2.5 beta release. Do not publish a 0.2.6 release until the owner has reported hardware results and approved the final candidate.

## To-do deadline orbs

- Show a small but legible deadline-status orb next to **every** to-do entry, including entries already marked complete. Keep the check mark and completed-row dimming distinct from this orb.
- Determine urgency from the task's displayed due day (Google Calendar's exclusive all-day end minus one day) in Luma's configured local timezone, not UTC or the event start day.
- Due **today or tomorrow**: red. Due **more than seven days away**: green. For days two through seven, interpolate continuously in a perceptual color space through warm yellow around days three–four, avoiding a muddy RGB midpoint. Preserve a clear step at day seven to green or specify the endpoint during visual review.
- Match the orb's luminance and saturation to Glass, Hearth and Neon Grid theme palettes. Keep it visible against each theme's background and in privacy-safe previews; do not use color alone to distinguish urgency where a compact label or accessible name can convey the date.
- The current to-do ordering remains: outstanding tasks by nearest due date first, then completed tasks by nearest due date. Completed-only pages continue cycling faster. The orb must not change task completion, Google colors, or the five-minute sync cadence.
- Include day-boundary, daylight-saving, multi-day, overdue, and theme contrast tests. Decide the overdue color and exact completed-orb treatment during 0.2.6 design review; do not silently label overdue work as distant/green.

The first implementation uses a calendar-day delta (not elapsed hours), red for overdue/today/tomorrow, yellow near days three–four, and green by day seven. Completed rows keep their check and dimmed title while retaining a readable orb. Software tests and a frontend build pass; physical theme contrast and viewing-distance checks remain.

## Robotic or silent speech on the physical 0.2.5 Pi

The owner reports that replies still sound robotic. In the Voice panel, the separately started Kristin sample failed with “The local voice could not generate audio,” while the non-speech speaker tone failed its selected route. “Kristin installed” proves files exist, not that any sound came from that model. “Last command reply: Kristin” is a different, earlier result and cannot establish the sample or current listening experience. We must not call this fixed from software tests.

0.2.6 work in progress:

- Reuse the live voice service's warm Piper worker for **Hear a sample** whenever that service is active. This avoids loading a second model at the same time on the Pi 4. When voice is off/unavailable, the test uses a standalone worker as before.
- Prefer the owner's selected local ALSA speaker, then try the named Luma echo-cancel sink if it exists. The virtual sink's playback link may lag a change of physical output, so direct physical playback is the more dependable primary path. Never use a Bluetooth, phone or dummy output as fallback. Send bounded raw PCM through the explicit Pulse-compatible player. PipeWire's [echo-cancel module](https://pipewire.pages.freedesktop.org/pipewire/page_module_echo_cancel.html) has separate virtual sink/source and physical playback/capture streams; the image's present configuration does not explicitly pin the latter two, so physical routing still needs confirmation on the Pi.
- Report separate codes for missing audio session, missing safe route, playback failure, Piper startup, Piper generation, and invalid output. Display the route used by each successful tone/sample/reply. The fallback voice must not be labeled Kristin.
- Route the original eSpeak fallback through the **same explicit local PCM speaker path** as the tone and Piper, instead of letting it pick an implicit system device. Its streaming WAV header legitimately contains unknown/zero lengths; decode from the bounded returned bytes. If it too fails, report a **silent** result with both the fallback failure and the prior Piper failure, timestamped, rather than leaving a stale “Kristin” label.
- Keep tests for each failure stage and ensure an API-restart or timed-out sample leaves no pending job. A command reply and a sample should use the same model worker, but the owner must still confirm audible output.

Acceptance on the Pi: (1) hear the short tone, (2) hear the fixed Kristin sample, (3) ask “Hey Luma, what time is it?” twice and confirm the reported reply engine/route, (4) compare voice quality without relying on a status label. If Piper is audible but still unpleasant, audition properly licensed female voice alternatives and benchmark them on the Pi 4 before choosing a new signed asset. [The existing Kristin model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/kristin/medium/MODEL_CARD) identifies a medium-quality LibriVox-trained voice; a model switch is not presumed to fix a route failure.

## Audio-stage calibration before words and intent

The 0.2.5 phrase check changes only the ReSpeaker hardware mixer on obvious quiet/clipped samples. It does not tune the PCM sent to Vosk. 0.2.6 adds a numeric, conservative **pre-recognizer** profile:

1. At the start of a local check, show a four-second quiet-room interval. Its clock begins on the first actual microphone level report, not the UI tap, so a delayed voice service cannot skip it.
2. Retain only bounded numeric room-floor samples and phrase RMS, peak, DC bias, and clipped fraction. No audio or transcript is written to storage. The existing ten positive/negative phrase checks still verify the wake/word path and cannot execute actions.
   A separate acoustic phrase boundary during the check uses raw sound level, a short pre-roll, 750 ms of quiet to end a phrase, and a seven-second limit. It still submits a sample when Vosk emits no words or no endpoint. Outside calibration, this boundary cannot trigger commands.
3. After three acoustic speech segments, compare median raw speech level with the quiet-room floor **even if Vosk recognized no words**. A clean but weak signal can receive a temporary trial of at most 2× digital gain, limited per frame so sudden loud sounds do not clip. A persistent DC bias can enable a light 75 Hz high-pass filter. If SNR is poor, the source clips, or measurement is insufficient, trial untouched audio and explain the physical fix. Do **not** gate quiet consonants or blindly amplify a noisy room.
4. Apply this trial to 16 kHz mono PCM **before** wake recognition and the unrestricted replay decoder. Continue measuring the untouched capture in parallel; decoded phrases and intent results do not determine the signal profile. Any profile change resets partial recognition state. An owner-local button may save clean, measured signal tuning after three acoustic segments even when the recognizer failed every phrase; doing so closes the phrase check, does not declare it passed, and still requires a real-world before/after test. A fully passed check also saves the numeric profile automatically. Provide a local “Use untouched mic audio” escape hatch that leaves saved HAT gain unchanged.

Software tests use synthetic PCM, corrupt profile inputs, noisy/quiet/clipped examples, a delayed capture handshake, profile persistence and reset, and private-route authorization. They cannot prove recognition gain in the owner's room. On-Pi acceptance must compare the **same phrases** before and after calibration at the normal wall distance, with the microphone meter, dropped-frame count, SNR/quality assessment, and last-heard text visible. If the new profile makes recognition worse, reset it immediately; retain the raw behavior until a measured improvement is confirmed.

### Remaining audio hypotheses to discriminate on hardware

| Stage | Possible cause | Evidence needed |
| --- | --- | --- |
| ReSpeaker / PipeWire input | Missing virtual source, wrong capture route, too-low level, HAT gain at limit, clipping, room noise, or dropped frames under CPU load | Mic hardware state, raw meter, room floor, phrase peak, dropped-frame counter |
| Wake / words | Constrained Vosk grammar mishears wake, unrestricted decoder disagrees, echo from the speaker, or PCM conditioning harms words | Display both temporary transcripts during calibration; compare raw vs conditioned utterances before any intent change |
| Piper model | Installed files pass smoke test but worker fails later, second model exhausts Pi RAM, or the model itself has undesirable timbre | Separate sample worker/start/synthesis error and real audible sample through the same warmed service |
| Output | User audio socket unavailable, virtual sink absent, selected physical sink changes, playback command fails, or eSpeak silently chooses another route | Tone and speech route/error plus the actual sound heard by the owner |

None of these are declared physically resolved by desktop tests. The [eSpeak NG manual](https://manpages.debian.org/testing/espeak-ng/espeak-ng.1.en.html) documents its stdin/stdout speech options; its [source](https://github.com/espeak-ng/espeak-ng/blob/master/src/espeak-ng.c) shows that stdout WAV cannot have finalized lengths.

If the selected speaker and Piper engine both test successfully yet the voice remains unpleasant, timbre—not a software fallback—is the leading hypothesis. A possible future audition is the US female [LJ Speech Piper model](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/high/MODEL_CARD), whose card lists public-domain training data. It has not been auditioned or performance-tested on the Pi 4, so 0.2.6 does not silently replace Kristin or download an unsigned model.
