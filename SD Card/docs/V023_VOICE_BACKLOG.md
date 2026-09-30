# Luma 0.2.3 offline voice implementation and remaining checks

Part of the broader [0.2.3 feature backlog](V023_FEATURE_BACKLOG.md), which
also plans the across-the-room typography and layout overhaul.

Owner request: expand **Hey Luma** into a useful, forgiving, fully offline
command interface. The code below is implemented on the 0.2.3 branch but is
**not a claim of physical microphone success**; the ReSpeaker must pass the
normal-speech meter and end-to-end spoken tests on the Pi before release.
Keep the existing privacy gate and explicit confirmation for actions that
change data or devices.

## Implemented in source

- 34 local spoken-question intents, including today/tomorrow weather,
  precipitation timing and probabilities, highs/lows, layer guidance,
  calendar today/tomorrow/next seven days, next-event location, current event,
  free time, today's/soon/overdue/completed tasks, timer, time/date, transit,
  phone/privacy/network/sync status, and help. Replies use the saved local
  snapshot and indicate stale or unavailable information. The detailed
  weather horizon is two days; later requests say so instead of pretending
  tomorrow is the requested date. Private calendar and tasks remain gated.
- Existing exact timer, scene, display, theme, brightness, volume, privacy and
  greeting commands remain. The matcher also recognizes 14 reversible local
  presentation intents (page navigation, controls and themes). It **cannot**
  choose a calendar write, room-device action, numeric setting or privacy
  unlock. Those still need explicit deterministic parsing and the existing
  owner/authorization checks.
- `source/backend/train_voice_model.py` trains a reproducible shallow neural
  bag-of-character-ngrams classifier using 466 authored/augmented public
  phrases. `luma/voice_intents.json` contains a ~368 KB quantized model. No
  user audio, calendar data or calibration sample is part of training. The
  inference runtime uses only Python's standard library and is included in
  the signed backend wheel; no model is downloaded by the Pi.
- Vosk's constrained recognizer remains the wake-word gate. After it accepts
  wake, a second, unrestricted recognizer replays at most nine seconds of
  buffered audio so natural phrasing can reach the classifier. This is local
  and bounded; audio is not sent to a cloud service or persisted.
- Exact phrases take precedence. Model decisions need both posterior and
  margin thresholds, and unsupported/uncertain speech leaves settings and
  devices untouched. A recognized but unavailable output gives a truthful
  explanation; unsupported speech gives a short command-library prompt.

Automated voice-query, paraphrase, safety and wheel-packaging checks pass in
the development environment. Pi 4 microphone level, wake distance, latency,
memory and offline spoken-input behavior remain **unverified on hardware**.

## Command coverage

- Weather: now, this afternoon/evening, tomorrow, rain timing/chance, highs
  and lows, and whether to bring a jacket/umbrella. Answers must use the
  configured local forecast and distinguish missing/stale data from a zero
  chance of rain. Open-Meteo already fetches two days of hourly data; expose
  the correct local-date slice and daily summary for tomorrow.
- Calendar: what is happening now; next event; today, tomorrow and the coming
  days; start/end time, free interval, location and leaving countdown. Respect
  selected calendars, timezone, overlaps and the hidden configured Sleep event.
- Tasks: what is due today/soon/overdue; list outstanding or completed tasks;
  complete/reopen a named task only after an unambiguous match and spoken or
  on-screen confirmation. Preserve the chosen Google Calendar completed color.
- Timers and hub controls: set/check/pause/resume/cancel timers; time/date;
  change theme, show a screen, brightness/volume controls, good night/morning,
  privacy status and temporary wake. Any voice-controlled purifier action must
  follow the existing authorization and safety rules. Do not add Woozoo code.
- Device status: Internet, last calendar/weather sync, phone authorization and
  why private standby is active. Speak only bounded, non-sensitive summaries
  while the phone is absent.

For each intent, define a small set of slots (day, time, duration, event/task
name, theme, quantity), a truthful answer template, and at least one graceful
clarification for ambiguity. Give the user an on-screen command library with
examples and a short "What can I ask?" response.

## Understanding varied wording

The implemented model is a tiny quantized neural softmax classifier written in
standard Python instead of fastText: this avoids introducing a new compiled
ARM dependency into the Pi image and update path. The intent model is not an
LLM and cannot answer arbitrary questions. Expand the held-out corpus with
consenting real-device ASR transcripts and compare exact/model/fuzzy behavior
before declaring the command surface complete. A larger runtime is a fallback
only if it materially improves Pi 4 accuracy inside measured memory and
latency budgets.

Exact high-confidence phrases may bypass the classifier; the classifier only
selects an intent. Parse dates, numbers, task/event names and safety-sensitive
arguments deterministically from the original transcript. Require a confidence
margin, not just a top label. If confidence is low, ask a concise clarifying
question or say what was heard; never guess an action, calendar write or device
command. Calibration phrases can tune capture gain/recognition and build a
local regression sample with consent, but must not silently retrain or upload
private speech. No cloud AI tokens, hosted inference or audio upload.

Acceptance: a physical ReSpeaker level meter that moves on normal speech;
reliable wake word at in-room distance; a held-out paraphrase/noisy-ASR test
set for every intent and rejection cases; command latency and memory measured
on the Pi 4; offline behavior with Wi-Fi disabled; privacy/authorization and
confirmation tests; graceful stale/missing-data speech; and no loss of timer
alarms or saved settings. Package any new model/runtime with the signed updater
or a separately signed asset route—never an unsigned background download.

Related follow-on: the [pleasant offline female voice](R14_VOICE_PLAN.md) is
still unimplemented and should be evaluated alongside this work, but speech
output and command understanding are independent gates.

Primary references: [fastText supervised classification and quantization](https://fasttext.cc/docs/en/supervised-tutorial.html),
[Vosk offline speech recognition](https://alphacephei.com/vosk/),
[Open-Meteo forecast variables](https://open-meteo.com/en/docs).
