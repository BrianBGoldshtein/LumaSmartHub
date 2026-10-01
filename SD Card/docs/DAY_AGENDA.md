# Complete day calendar

Owner requirement: packed days (normally 6–7+ events) across any selected agenda calendars must not be truncated. Home keeps its two upcoming events; the Calendar slide no longer uses a three-event slice. Latest preference: automatic Calendar rotation shows only events in progress or starting within the next 14 hours, never earlier appointments from today. A touch-accessible **Full day** control retains the complete day for manual review; **Upcoming** resumes forward-looking rotation.

## Data and schedule

`agenda.py` builds a separate privacy-gated snapshot field. Includes earlier-today, ongoing, future, all-day and multi-day events from all selected agenda calendars. It now also supplies near-term next-day events when the next 14 hours cross midnight. The manual day bounds remain anchored to the present local day. Cancelled/declined/unselected events are excluded. Google fetch already follows every events page and expands recurring occurrences; no additional network worker or scope is needed.

When available, latest completed Sleep interval within24h gives wake, next Sleep start within24h gives bedtime. Touching/overlapping intervals merge. Missing boundaries use local midnight rather than invented sleep hours. The view expands for today's appointments outside those boundaries; overnight awake spans include the previous evening. Time arithmetic uses UTC instants and local day boundaries, including25-hour DST days. All-day end dates remain exclusive. Cached data is labeled Saved calendar; new process must sync before claiming freshness.

Privacy/night/off/waking/clock-trust rules apply to the entire agenda field. It is null when redacted, and explicitly cleared when the browser loses its control connection. No event contents are saved in browser storage.

## Display and interaction

Four-hour timeline sections have prominent hour labels, proportional event positions and Google color accents. Titles and times use a shared, larger scale within each theme. Short events have an 80-minute minimum *visual* footprint (labels always show actual times); column collision calculations use the same footprint, preventing text blocks from overlapping. Near a section boundary, a minimum-height card may shift upward to stay visible; its printed time is authoritative. Multi-section appointments continue on each relevant section. The title takes priority over secondary details, and tapping a card reveals its full text.

Up to two overlap columns, or one on narrow panels. Additional overlaps become more sections, never narrower and narrower cards. All-day events paginate three per section; every item remains reachable in the appropriate view. In automatic mode, only populated upcoming sections rotate every 9 seconds; a past event is not replayed at night, and an empty time window is not a slide. The next section index survives slide cycling. Manual previous/next pauses rotation; **Full day** reveals earlier events, and **Upcoming** returns to the forward-looking view. Interaction delays the global slide cycle for 60 seconds. Tap an appointment to read its full title, source calendar, time/date and location; Escape closes and restores focus. Private state unmounts the detail view.

No arbitrary event-count cutoff. There is a practical readable-display tradeoff: a busy day takes more sections and visits to review, rather than all events simultaneously shrinking to illegible text. Neon uses existing pixel type/spacing and snapped appointment geometry; Google semantic colors remain consistent across all themes.

## Software evidence

Backend tests cover 24 events from two calendars, earlier events, sleep bounds/outside appointments, overnight spans, interval merge, cancellation/decline/privacy, all-day exclusive dates, DST, and a late-evening 14-hour lookahead into tomorrow. Frontend tests cover 40 simultaneous events across distinct calendars, short-event collision avoidance, all-day/long-event pagination, IDs/colors, empty/invalid ranges, and 11 PM filtering of past and distant events. Night integration additionally checks agenda redaction.

Earlier browser checks covered 9 theme/viewport combinations (2048x1536, 1536x2048, 390x844), details/Escape/focus restoration, and all 21 crowded-day sample events in the former full-day rotation. The new automatic lookahead/Full day toggle still needs visual rechecking. Preview fixtures `?demo=1&theme=neon-grid&page=agenda&hold=1&fixture=packed` and `fixture=crowded` remain available. No real-account acceptance of this change has occurred.
