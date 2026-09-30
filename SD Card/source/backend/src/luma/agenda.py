"""Complete, privacy-gated day view; separate from the upcoming home cards."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .serde import to_primitive
from .calendar_logic import is_sleep_event


def day_agenda(events, settings, now, *, fresh):
    local = now.astimezone(ZoneInfo(settings.timezone))
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    now_utc = now.astimezone(UTC)
    # UTC ordering keeps repeated DST hours distinct. Overnight sleep is normal.
    sleeps = sorted((e.start.astimezone(UTC), e.end.astimezone(UTC)) for e in events
                    if is_sleep_event(e, calendar_ids=set(settings.sleep_calendar_ids), title=settings.sleep_event_title))
    merged = []
    for start, end in sleeps:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    wake = max((end for _, end in merged if now_utc-timedelta(days=1) <= end <= now_utc), default=None)
    bedtime = min((start for start, _ in merged if now_utc < start <= now_utc+timedelta(days=1)), default=None)
    start, end = wake or day_start.astimezone(UTC), bedtime or day_end.astimezone(UTC)
    # Include ALL today's events, even appointments outside the sleep window.
    # Also include the awake span when the owner's day crosses midnight.
    lower, upper = min(start, day_start.astimezone(UTC)), max(end, day_end.astimezone(UTC))
    selected = sorted((e for e in events if e.calendar_id in settings.visible_calendar_ids
                       and e.status != 'cancelled' and not e.self_declined
                       and not is_sleep_event(e, calendar_ids=set(settings.sleep_calendar_ids), title=settings.sleep_event_title)
                       and e.start.astimezone(UTC) < upper and e.end.astimezone(UTC) > lower),
                      key=lambda e: (e.start.astimezone(UTC), e.end.astimezone(UTC), e.calendar_id, e.id))
    timed = [e for e in selected if not e.all_day]
    if timed:
        start = min(start, max(lower, min(e.start.astimezone(UTC) for e in timed)))
        end = max(end, min(upper, max(e.end.astimezone(UTC) for e in timed)))
    return {'date': day_start.date().isoformat(), 'start': start.isoformat(), 'end': end.isoformat(),
            'wake': wake.isoformat() if wake else None, 'sleep': bedtime.isoformat() if bedtime else None,
            'stale': not fresh, 'events': to_primitive(selected)}
