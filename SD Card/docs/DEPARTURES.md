# Leave-soon reminders

Implemented in source and included in the r9 development-image candidate. This is not a hardware-qualified image; real Google-account and physical-device tests remain unperformed.

## Setup

Open **Device setup → Extras → Leave soon** (also inside guided setup). Connect Google in Calendar setup first, or return to this extra after signing in. Choose calendars explicitly and enable reminders. Defaults are five minutes preparation and ten minutes travel; each accepts 0–240 whole minutes. The reminders use your estimates, not GPS, live directions or traffic. There is no extra Google permission or calendar write.

Calendar loading failure preserves saved selections. You can disable reminders without reconnecting Google. Settings save and provider sync have separate outcomes: a failed sync does not undo a successful preference save. The onboarding review reports enabled status and calendar count, not a live-connection or hardware-test pass. Unsaved edits and in-progress operations use the existing setup navigation guards, including touch-keyboard edits.

## On the wall

Leave time is event start minus preparation minus travel. From fifteen minutes before that time until event start, Luma displays one **Leave in … min** / **Time to leave** notice. The notice uses the event's Google color (calendar color when no override), existing theme fonts, and the shared feature island. It is private and silent. Private standby, a lost control connection, or screen-off hides it. Calendar data must have a successful sync within ten minutes and no subsequent sync failure; reboot cache alone is not sufficient.

The earliest qualifying departure wins when events overlap. Open Details to **Snooze 5 min**, **Dismiss this event**, or change the two time estimates for that occurrence. The settings and these actions survive restart. A changed start/end time is a new occurrence; title/color edits alone do not undo dismissal. Recurring instances have separate IDs. Cancellation, a declined invitation, or the event beginning removes eligibility. Dismissing one event may reveal another overlapping reminder.

Active controls take precedence over automatic notices. Timer completion takes precedence over departure notices, which take precedence over phone notifications; notices do not stack. Opening a reminder does not remount or reset the game underneath. A monotonic client clock advances the countdown from the server's timestamp; display text expires at event start even between snapshots.

## Event filtering and limitations

- Only explicitly selected calendars, timed future events, and non-cancelled/non-declined occurrences qualify. All-day events and the configured Sleep Time title do not.
- Online-only events are excluded by default. Recognized meeting-host URLs, a location exactly `online`/`virtual`, or conference metadata with no physical location qualify as online. Physical/hybrid locations remain eligible. Google Maps and unknown URLs are not blindly classified as virtual. Unrecognized online formats may still appear; setup has an explicit online-events opt-in and calendar selection.
- The integration retains only `self_declined` and `virtual_only` derived flags, not attendee lists or conferencing payloads. Google documents attendee response/self and conference fields in its [event resource](https://developers.google.com/workspace/calendar/api/v3/reference/events). The link-host rule is Luma's heuristic, not a Google classification guarantee.
- Existing five-minute calendar polling supplies data; disabled departure-only calendars are not added to the fetch. No new background worker, route API, per-tick SD writes or audio service is added.
- Occurrence actions are local-only, require an unlocked hub and a fresh currently displayed reminder key, and cannot change a Google event. Stale/rescheduled actions return a conflict. The bounded SQLite record stores a SHA-256 occurrence key, expiry, dismissal/snooze and numeric overrides, not another copy of the event title or location. At most 256 records remain; expired records are pruned on actions, and the newest action is always retained.

## Verification

`test_departures.py` covers eligibility, exact time windows, overlapping order, DST/midnight, privacy/freshness, restart, reschedule/title-color semantics, per-occurrence edits, invalid/corrupt/bounded state, minimal provider parsing, local API restrictions, absence of Google writes, strict settings, and enabled-only shared calendar fetching. Frontend tests cover countdown anchoring/expiry and preference validation.

Browser preview checked the notice, dialog and expanded setup in Glass, Hearth and Neon Grid at 2048×1536, 1536×2048 and 390×844 (27 layouts, no horizontal overflow). Per-event editing, preview snooze/dismiss, required calendar selection, unsaved-change guard, save/navigation and privacy suppression were exercised. Notice borders matched the actual sample event color in all themes. These are software checks, not real Google, touchscreen, audio, phone-presence or physical-Pi acceptance. The night-clock feature must also suppress these notices when its explicit mode is added.
