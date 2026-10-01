# 0.2.6 beta backlog

Planning only. None of this is included in the signed 0.2.5 beta release.

## To-do deadline orbs

- Show a small but legible deadline-status orb next to **every** to-do entry, including entries already marked complete. Keep the check mark and completed-row dimming distinct from this orb.
- Determine urgency from the task's displayed due day (Google Calendar's exclusive all-day end minus one day) in Luma's configured local timezone, not UTC or the event start day.
- Due **today or tomorrow**: red. Due **more than seven days away**: green. For days two through seven, interpolate continuously in a perceptual color space through warm yellow around days three–four, avoiding a muddy RGB midpoint. Preserve a clear step at day seven to green or specify the endpoint during visual review.
- Match the orb's luminance and saturation to Glass, Hearth and Neon Grid theme palettes. Keep it visible against each theme's background and in privacy-safe previews; do not use color alone to distinguish urgency where a compact label or accessible name can convey the date.
- The current to-do ordering remains: outstanding tasks by nearest due date first, then completed tasks by nearest due date. Completed-only pages continue cycling faster. The orb must not change task completion, Google colors, or the five-minute sync cadence.
- Include day-boundary, daylight-saving, multi-day, overdue, and theme contrast tests. Decide the overdue color and exact completed-orb treatment during 0.2.6 design review; do not silently label overdue work as distant/green.
