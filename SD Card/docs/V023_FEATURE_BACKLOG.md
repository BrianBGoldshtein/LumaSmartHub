# Luma 0.2.3 feature backlog (planning only)

This document is deliberately separate from the published `0.2.2` bugfix.
Nothing here has been implemented or pushed to the Pi. Hardware feedback may
change the details before development begins.

## 1. In-room readability and visual harmony

Owner observation: the time is still too small in every theme, and the
information screens waste space. The goal is a cohesive wall display that can
be read from across the room, not simply today's layout with larger CSS font
values. Prioritize visibility, legible event titles/times and a composed
overall silhouette over decorative labels or empty margins.

Plan:

1. Audit screenshots of **every** cycling screen, privacy standby, temporary
   islands and all three themes at the actual screen resolution and portrait
   and landscape breakpoints. Photograph the physical display from normal
   viewing distances. Mark illegible text, clipped content, oversized chrome
   and unused regions. Separate the glanceable display from close-range setup
   screens; their typography should not share one scale.
2. Establish one display layout grid and a small set of typography/spacing
   tokens. Time, temperature, next-event time/title and countdown should be
   the largest elements according to page purpose; status text and navigation
   should be clearly subordinate. Use tabular numerals for clocks and event
   times. Keep each theme's own font and color character, but align equivalent
   information, weights and optical sizes across themes. For Neon Grid, snap
   text baselines, card edges and islands to the existing master pixel grid.
3. Recompose the **home clock** first. Give the time enough width/height to
   grow materially in 12-hour and 24-hour formats; move or compress adjacent
   weather/chrome instead of allowing time to shrink. Plan the same dominant
   clock treatment for privacy standby and small ambient clock overlays.
   Avoid a tiny AM/PM suffix or date that makes the clock feel misbalanced.
4. Review each information screen's content budget. Remove repeated labels,
   excessive padding and decorative containers. Fill newly available space
   with larger primary text—not more small-print detail. Dense calendar days
   must paginate or reveal detail on touch rather than reducing type until
   events become unreadable. Maintain the short-event title-first behavior.
5. Specify controlled text fitting: measure available width and use a small
   number of designed size steps/line breaks for variable event titles, long
   temperatures and countdowns. Never let arbitrary browser wrapping or
   clipping set the composition. Preserve contrast and touch targets.

Acceptance: side-by-side captures for all themes and screens; a consistent
hierarchy and baseline/spacing system; no accidental wrapping, overlapping or
dead space; clock visibly larger on each theme; long/short time strings and
packed-calendar fixtures pass; no regressions in portrait mode or the arcade
grid; and a real viewing-distance check on the mounted Pi before release.
Record before/after screenshots and ask the owner to approve visual direction
before changing the production cycle.

Current source hotspots for the later implementation: `styles.css` defines
the global clock, home grid, status bar and theme overrides; `agenda.css`,
`countdowns.css` and `features.css` contain additional page-specific type and
spacing rules. Consolidate the scattered `vmin` and pixel overrides only
after the visual audit; do not globally scale all text blindly.

## 2. Broader offline Hey Luma commands

See the detailed [voice-command plan](V023_VOICE_BACKLOG.md): tomorrow's
weather, calendar, tasks, timers, hub controls and status, with paraphrase
handling from a small offline intent classifier. Keep recognition, answers and
safety decisions local; reject uncertain or unauthorized actions. The
pleasant offline female speech output is a separate pending dependency and
hardware-audition task.
