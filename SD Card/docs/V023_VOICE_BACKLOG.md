# Luma 0.2.3 voice backlog (planning, not in 0.2.2)

Owner request: expand **Hey Luma** into a useful, forgiving, fully offline
command interface. These are candidate requirements for the next feature
release, not a claim that the microphone or voice pipeline has passed physical
testing. Keep the existing privacy gate and explicit confirmation for actions
that change data or devices.

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

Keep the existing offline wake-word and Vosk transcription path, then add a
small **on-device intent classifier** rather than enumerating every sentence.
Evaluate a quantized fastText supervised classifier first: it is a shallow
neural text model intended for fast local classification and has an official
quantization path. Train it off-device on authored paraphrases plus realistic
speech-recognition mistakes; ship only the tested model and labels. Compare it
against the current deterministic matcher and a compact fuzzy baseline on a
held-out set. A larger ONNX model is a fallback only if it materially improves
accuracy on the Pi 4 within measured RAM, startup and response-time budgets.

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
