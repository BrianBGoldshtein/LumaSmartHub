from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .models import CalendarEvent


def _friendly_time(value: datetime) -> str:
    """Format a clock time portably on Linux and Windows."""

    return value.strftime("%I:%M %p").lstrip("0")


def is_sleep_event(event: CalendarEvent, *, calendar_ids: set[str], title: str) -> bool:
    """The configured, timed event that controls sleep is not an agenda item."""
    return (event.calendar_id in calendar_ids
            and event.summary.strip().casefold() == title.strip().casefold()
            and event.status != "cancelled" and not event.self_declined
            and not event.all_day
            and event.end.astimezone(UTC) > event.start.astimezone(UTC))


def visible_events(
    events: list[CalendarEvent],
    *,
    now: datetime,
    calendar_ids: set[str],
    sleep_calendar_ids: set[str] | None = None,
    sleep_title: str = "Sleep",
) -> list[CalendarEvent]:
    return sorted(
        (
            event
            for event in events
            if event.calendar_id in calendar_ids
            and event.status != "cancelled"
            and event.end > now
            and not is_sleep_event(event, calendar_ids=sleep_calendar_ids or set(), title=sleep_title)
        ),
        key=lambda event: (event.start, event.end, event.summary.casefold()),
    )


def ongoing_events(events: list[CalendarEvent], now: datetime) -> list[CalendarEvent]:
    return sorted(
        (event for event in events if event.is_ongoing(now)),
        key=lambda event: (event.end, event.summary.casefold()),
    )


def todo_events(
    events: list[CalendarEvent],
    *,
    todo_calendar_id: str | None,
    now: datetime,
) -> list[CalendarEvent]:
    if not todo_calendar_id:
        return []
    return sorted(
        (
            event
            for event in events
            if event.calendar_id == todo_calendar_id
            and event.status != "cancelled"
            and event.all_day
            and event.start.date() <= now.astimezone(event.start.tzinfo).date() < event.end.date()
        ),
        key=lambda event: (event.end, event.summary.casefold(), event.id),
    )


def todo_view(event: CalendarEvent, completed_color_id: str | None) -> dict:
    """Task text is only the title; no location/description/account metadata."""
    return {"id": event.id, "calendar_id": event.calendar_id, "summary": event.summary,
            "start": event.start.isoformat(), "end": event.end.isoformat(), "all_day": True,
            "due_date": (event.end.date() - timedelta(days=1)).isoformat(),
            "completed": bool(completed_color_id and event.event_color_id == completed_color_id),
            "calendar_color": event.calendar_color, "event_color": event.event_color,
            "event_color_id": event.event_color_id, "etag": event.etag}


def active_sleep_end(
    events: list[CalendarEvent],
    *,
    calendar_ids: set[str],
    title: str,
    now: datetime,
) -> datetime | None:
    normalized_title = title.strip().casefold()
    # Merge the connected interval containing now, including future overlaps
    # and touching intervals. UTC comparisons avoid repeated-hour DST errors.
    intervals = sorted(
        (event.start.astimezone(UTC), event.end.astimezone(UTC))
        for event in events
        if is_sleep_event(event, calendar_ids=calendar_ids, title=normalized_title)
    )
    now = now.astimezone(UTC)
    merged_end = None
    for start, end in intervals:
        if merged_end is None:
            if start <= now < end:
                merged_end = end
            elif start > now:
                break
        elif start <= merged_end:
            merged_end = max(merged_end, end)
        else:
            break
    return merged_end


def format_briefing(
    *,
    now: datetime,
    timezone: str,
    weather_summary: str,
    events: list[CalendarEvent],
) -> str:
    local_now = now.astimezone(ZoneInfo(timezone))
    greeting = "Good morning" if local_now.hour < 12 else "Good afternoon"
    upcoming = [event for event in events if event.end > now and event.status != "cancelled"]
    upcoming.sort(key=lambda event: event.start)
    if not upcoming:
        agenda = "You have no remaining calendar events."
    else:
        event = upcoming[0]
        local_start = event.start.astimezone(ZoneInfo(timezone))
        if event.is_ongoing(now):
            agenda = f"{event.summary} is happening now."
        elif event.all_day:
            agenda = f"Your next item is {event.summary}, scheduled all day."
        else:
            agenda = f"Your next event is {event.summary} at {_friendly_time(local_start)}."
    return f"{greeting}. It is {_friendly_time(local_now)}. {weather_summary} {agenda}"
