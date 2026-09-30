# Hey Luma — free local question library

Implemented in source; native scene commands were added September28,2026 and must be included in the next image. No LLM, AI API, token usage, new paid service, or uploaded microphone audio. Vosk recognition, deterministic Python answers and espeak-ng speech run on the Pi. Microphone capture explicitly selects PipeWire/Pulse source `luma_mic`; it does not trust an implicit PortAudio default. This is a supported phrase library, not open-ended conversational AI or Siri.

Start with **Hey Luma**, then one of these questions. You can say the wake phrase and question together, or ask within the existing seven-second wake window.

| Topic | Examples |
| --- | --- |
| Time/date | “What time is it?” · “What day is it?” · “What is the date today?” |
| Weather | “What's the weather today?” · “What is the temperature?” · “Will it rain today?” · “Do I need an umbrella?” |
| Calendar | “When is my next event?” · “What's on my calendar today?” · “What's on my calendar tomorrow?” · “What is happening now?” |
| Tasks | “What are my tasks today?” · “What tasks are due today?” · “Read my tasks” |
| Timer | “How much time is left on my timer?” |
| Room scenes | “Run Morning/Night/Arrival/Away scene” · “Cancel scene” (requires an enabled, reviewed scene and current owner access) |
| Help | “What can I say?” · “What can you do?” |

Existing timer, page, theme, brightness, volume, privacy and night/wake commands remain. “Good morning” continues to give the daily briefing; only the distinct “run morning scene” phrase runs appliances. Scene voice commands use the same owner unlock, enabled saved definition, current device binding and trusted-clock checks as local touch. They cannot configure scenes or turn on automatic or remote permissions. “Cancel scene” never undoes an action already sent; each result remains visible in Room devices. **Show calendar/weather** navigates; a question speaks a read-only answer. Questions do not unlock private content, change a page, wake the display, alter a task/event or start network synchronization. “Ask …” and unknown question forms never fall through to the optional cloud adapter or keyword-based mutations.

## Data and privacy contract

- Recognition, interpretation and speech are offline. Weather and Google Calendar still need the existing internet sync for fresh information; these questions add no provider requests or permissions. Saved data is used if available, with an explicit stale warning. Freshness follows the existing two-hour weather and ten-minute calendar policies; a forecast from a different local day is also described as old.
- Time/date follow the configured IANA timezone. A configured hub with untrusted boot time asks the user to wait for clock sync. No invented time/date answer.
- Weather reports Fahrenheit, current/saved temperature, feels-like or daily high/low. Rain reports the maximum hourly probability over remaining **available** hours today, not an invented all-day probability. Missing probabilities are unknown, not zero.
- Calendar/tasks pass through the same phone/PIN and night/recovery redaction as the screen. No title is exposed in private mode. Voice recognition is not identity proof. Authorizations are checked when the question is answered. Existing microphone-off and calibration suppression apply unchanged.
- Today includes earlier-today, ongoing, all-day and remaining events from selected visible calendars. Tomorrow uses local calendar-day overlap and exclusive end boundaries. Cancelled/declined/unselected events are omitted. Next event means the next future start in the saved calendar window; ongoing timed events have their own question.
- Tasks use the chosen task calendar and its established all-day date/color rules. Only the chosen completed color removes a task from outstanding answers. Due today means the last occupied Google day, not its exclusive API end date.
- Read at most three titles, each limited to64characters, then count the remainder. Titles are inert text sent to espeak via stdin, not shell flags/instructions. Questions do not log transcripts or save audio.

## Implementation and verification

`voice_library.py` owns the intent/alias library and deterministic answer formatting. `voice.py` adds every alias to the offline recognizer grammar and resolves questions before navigation keywords. `LumaService.voice_snapshot` creates privacy-filtered, freshness-aware context including earlier-today events. The local-only voice API serves both answers and `/api/v1/voice/library`. Voice setup has a collapsed, themed “Things you can ask” reference; no extra always-visible kiosk island.

64 new tests cover every alias, every presented example, wake gate, unknown questions, no cloud/provider calls, local endpoint access, mute, privacy/night/clock trust, selected calendars, earlier events, cancellation/declines, timezone/day boundaries, task colors/due dates, stale/missing weather, rain gaps, bounded titles, time/date and timer status. Browser checks cover9 expanded-library layouts (three themes × native landscape, portrait and narrow390px). Real far-field recognition, pronunciation and speaker output remain part of deferred hardware acceptance.
