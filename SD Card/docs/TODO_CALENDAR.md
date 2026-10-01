# Calendar-backed to-dos

September 26, 2026 owner clarification, implemented in source and included in the r9 development-image candidate. No real Google account or physical device has been tested.

## Your calendar is the task database

- Select one Google calendar in Calendar setup. Use **all-day events only**; the event title is the task. Luma does not derive tasks from descriptions or locations.
- Every non-cancelled all-day event occupying today is included, including tasks that began weeks ago. Future tasks do not appear before their start date. Timed events are ignored by this slide.
- The **last day visibly occupied in Google Calendar is the due day**. Google returns an exclusive API end date, so an event visible September 24–27 has API end September 28; Luma displays “Due Sep 27” and includes it through the 27th. This also avoids a one-day error over daylight-saving changes. [Google event date semantics](https://developers.google.com/workspace/calendar/api/v3/reference/events).
- Only outstanding tasks appear on the rotating to-do slide, sorted by due date/title. Completed tasks remain in Google and the local sync cache, but consume no slide space or page. Lists larger than three are paginated rather than truncated or shrunk. Pages advance every eight seconds, have touch arrows, pause during a write, and resume at the next page across slide cycles.

## Completion color — owner-confirmed rule

Choose one color from Google's **event** palette (not its separate calendar palette). Events inheriting the calendar's default color are outstanding. **Only the chosen event color ID means complete**. Other manually chosen colors remain outstanding. IDs, not approximate RGB comparisons, determine completion.

A completed task is hidden from the to-do slide in every Luma theme. Manually applying that same color in Google hides it on the next successful sync (normally within five minutes); Refresh tasks requests a sync immediately. Reverting the event to default—or any other color—in Google makes it outstanding again. Changing the selected completed color reinterprets existing colors; it never mass-recolors past tasks.

Tapping an outstanding task's checkbox on Luma patches its Google event color and removes it from the slide after confirmation. To reopen it, restore the event's default color in Google Calendar. No title, description, dates, recurrence rule, attendees or other event fields are changed. Recurring task occurrences are targeted by their instance ID, never the entire series. [Google's patch behavior](https://developers.google.com/workspace/calendar/api/v3/reference/events/patch).

## Setup and permissions

1. Connect Google as usual, initially read-only.
2. Select the To-do calendar and a Completed color; save calendars.
3. To allow touchscreen completion, choose **Enable task updates with Google** and approve Google's additional event-edit permission on the Pi.

The permission requested is `calendar.events`, alongside existing `calendar.readonly`. Google grants event editing across calendars the account can edit; it cannot restrict this scope to one selected calendar. **Luma's task endpoint is restricted to the selected to-do calendar, currently displayed all-day tasks, and color-only writes.** Setup discloses that distinction before consent. Read-only connections can still display manually colored completion without upgrading. A calendar itself must also grant writer/owner access.

The explicit upgrade is local-only, uses the existing restart-safe PKCE/state flow, and never unlocks the display. Requested scopes are stored in the pending attempt; only a successful grant with offline refresh support replaces credentials. Existing read-only tokens are not silently treated as write-enabled. Reconnect preserves an already granted write scope. Failed/cancelled upgrades retain the old connection. Google's consent is left to the owner; no account permissions have been granted during development.

## Safety, offline behavior and privacy

- Only the unlocked local hub can change tasks. Remote Shortcut/network tokens cannot use the task endpoint or change the to-do calendar/completed-color settings.
- The backend rechecks the selected calendar and active all-day event, then fetches the current Google event and compares its ETag. The color-only PATCH carries `If-Match`, so a concurrent Google edit produces a refresh/conflict message rather than an overwrite. [Conditional Google updates](https://developers.google.com/workspace/calendar/api/guides/version-resources).
- Provider requests have a 15-second HTTP timeout. Writes have **no automatic retries or offline queue**. A timeout may follow a successful provider commit: the UI therefore says unconfirmed and asks for refresh instead of claiming success or replaying the change.
- The checkbox changes only after the provider confirms the result. A failed request keeps the last confirmed cache. Calendar-sync failure marks the tasks saved/awaiting sync.
- Successful results persist in the existing SQLite calendar cache and survive restart. Sync and task mutations share a lock, including relevant calendar-setting changes, so an in-flight sync cannot replace a newer confirmed color with an older response.
- Private standby removes all task records. Task snapshots contain title, dates, color, ETag and completion only, not event descriptions/locations. No credentials or task copies are stored in browser storage; only a transient pagination index is retained while the application runs.

## Software verification

Tests cover active-day boundaries, one-day/multi-day/DST events, title-only projection, exactly one completed color, default RGB vs explicit color ID, more than three tasks, manual recolor reversal, cache restoration, permission/role gates, strict input/local/privacy restrictions, ETag races, no retries, failure preservation, color-only patch and clearing the override. Actual OAuth SDK tests use synthetic HTTP exchanges to verify successful and denied permission upgrades.

Previous browser preview covered the former complete/reopen styling, save-before-consent, unsaved color-choice warning, and task-slide/color-picker layout across Glass/Hearth/Neon Grid at 2048×1536, 1536×2048 and 390×844. The newer outstanding-only slide has a focused pagination test; its visual layout still needs rechecking before release. Google/provider behavior is mocked in automated tests, not claimed as live account acceptance. Final image packaging and owner-authorized real-account/hardware checks remain outstanding.
