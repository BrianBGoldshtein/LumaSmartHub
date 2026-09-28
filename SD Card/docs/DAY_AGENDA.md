# Complete day calendar

Owner requirement: packed days (normally 6–7+ events) across any selected agenda calendars must not be truncated. Home keeps its two upcoming events; the Calendar slide no longer uses a three-event slice.

## Data and schedule

`agenda.py` builds a separate privacy-gated snapshot field. Includes earlier-today, ongoing, future, all-day and multi-day events from all selected agenda calendars. Cancelled/declined/unselected events are excluded. Google fetch already follows every events page and expands recurring occurrences; no additional network worker or scope is needed.

When available, latest completed Sleep interval within24h gives wake, next Sleep start within24h gives bedtime. Touching/overlapping intervals merge. Missing boundaries use local midnight rather than invented sleep hours. The view expands for today's appointments outside those boundaries; overnight awake spans include the previous evening. Time arithmetic uses UTC instants and local day boundaries, including25-hour DST days. All-day end dates remain exclusive. Cached data is labeled Saved calendar; new process must sync before claiming freshness.

Privacy/night/off/waking/clock-trust rules apply to the entire agenda field. It is null when redacted, and explicitly cleared when the browser loses its control connection. No event contents are saved in browser storage.

## Display and interaction

Four-hour timeline sections with prominent hour labels, proportional event positions and Google color accents. Titles/times share a restrained scale and the existing theme fonts. Short events have a minimum45-minute visual footprint (labels always show actual times); column collision calculations use the same footprint, preventing text blocks overlapping. Near a section boundary, a minimum-height card may shift upward to stay visible; its printed time is authoritative. Multi-section appointments continue on each relevant section.

Up to two overlap columns, or one on narrow panels. Additional overlaps become more sections, never narrower and narrower cards. All-day events paginate three per section; every item remains reachable. All sections rotate every9seconds; only the next section index survives slide cycling, so the next Calendar visit continues rather than restarting at morning. Manual previous/next pauses rotation, with a Resume control. Interaction delays the global slide cycle for60seconds. Tap an appointment to read its full title, source calendar, time/date and location; Escape closes and restores focus. Private state unmounts the detail view.

No arbitrary event-count cutoff. There is a practical readable-display tradeoff: a busy day takes more sections and visits to review, rather than all events simultaneously shrinking to illegible text. Neon uses existing pixel type/spacing and snapped appointment geometry; Google semantic colors remain consistent across all themes.

## Software evidence

Seven backend tests:24 events from two calendars, earlier events, sleep bounds/outside appointments, overnight spans, interval merge, cancellation/decline/privacy, all-day exclusive dates and DST. Five frontend tests:40 simultaneous events across distinct calendars, short-event collision avoidance, all-day/long-event pagination, IDs/colors and empty/invalid ranges. Night integration additionally checks agenda redaction.

Browser:9 theme/viewport combinations (2048x1536,1536x2048,390x844), no horizontal overflow; event times fit. Details open/Escape/focus restoration checked. All21 sample events in a crowded day reached across11 sections, no loss. Preview fixtures `?demo=1&theme=neon-grid&page=agenda&hold=1&fixture=packed` (9events) and `fixture=crowded` (21events). No real account or assembled-device testing.
