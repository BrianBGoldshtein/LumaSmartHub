from __future__ import annotations

import unittest
from zoneinfo import ZoneInfo
from datetime import UTC, datetime, timedelta

from luma.calendar_logic import (
    active_sleep_end,
    format_briefing,
    ongoing_events,
    todo_events,
    visible_events,
)
from luma.models import CalendarEvent


NOW = datetime(2026, 9, 24, 16, 30, tzinfo=UTC)


def event(
    event_id: str,
    calendar_id: str,
    summary: str,
    start: datetime,
    end: datetime,
    **kwargs: object,
) -> CalendarEvent:
    return CalendarEvent(event_id, calendar_id, summary, start, end, **kwargs)


class CalendarLogicTests(unittest.TestCase):
    def test_sleep_merges_future_overlaps_and_adjacency_but_not_gaps(self):
        def sleep(key,start,end,**kwargs):
            return event(key,'primary','Sleep Time',NOW+timedelta(hours=start),NOW+timedelta(hours=end),**kwargs)
        events=[sleep('a',-1,1),sleep('b',.5,2),sleep('c',2,3),sleep('later',4,5),sleep('cancelled',2,8,status='cancelled')]
        self.assertEqual(active_sleep_end(list(reversed(events)),calendar_ids={'primary'},title='Sleep Time',now=NOW),NOW+timedelta(hours=3))
        self.assertIsNone(active_sleep_end(events,calendar_ids={'primary'},title='Sleep Time',now=NOW+timedelta(hours=3)))
        self.assertIsNone(active_sleep_end(events,calendar_ids={'different'},title='Sleep Time',now=NOW))
        self.assertIsNone(active_sleep_end(events[1:],calendar_ids={'primary'},title='Sleep Time',now=NOW))

    def test_sleep_repeated_dst_hour_is_ordered_by_instant(self):
        zone=ZoneInfo('America/Los_Angeles')
        start=datetime(2026,11,1,1,40,tzinfo=zone,fold=0)
        end=datetime(2026,11,1,1,20,tzinfo=zone,fold=1)
        events=[event('dst','primary','Sleep Time',start,end)]
        self.assertEqual(active_sleep_end(events,calendar_ids={'primary'},title='Sleep Time',now=datetime(2026,11,1,9,tzinfo=UTC)),end.astimezone(UTC))
        self.assertIsNone(active_sleep_end(events,calendar_ids={'primary'},title='Sleep Time',now=end))

    def test_visible_events_hide_cancelled_unselected_and_finished(self) -> None:
        events = [
            event("future", "primary", "Dentist", NOW + timedelta(hours=2), NOW + timedelta(hours=3)),
            event("past", "primary", "Old", NOW - timedelta(hours=2), NOW - timedelta(hours=1)),
            event("other", "private", "Secret", NOW + timedelta(hours=1), NOW + timedelta(hours=2)),
            event(
                "cancelled",
                "primary",
                "Cancelled",
                NOW + timedelta(hours=1),
                NOW + timedelta(hours=2),
                status="cancelled",
            ),
        ]

        result = visible_events(events, now=NOW, calendar_ids={"primary"})

        self.assertEqual([item.id for item in result], ["future"])

    def test_ongoing_and_todo_filters(self) -> None:
        current = event("current", "work", "Standup", NOW - timedelta(minutes=10), NOW + timedelta(minutes=20))
        task = event(
            "task",
            "todos",
            "Buy filters",
            NOW + timedelta(minutes=5),
            NOW + timedelta(hours=1),
        )

        self.assertEqual(ongoing_events([task, current], NOW), [current])
        self.assertEqual(todo_events([current, task], todo_calendar_id="todos", now=NOW), [])  # Timed events are not tasks.

    def test_sleep_title_matching_is_case_and_whitespace_insensitive(self) -> None:
        sleep_end = NOW + timedelta(hours=7)
        events = [event("sleep", "primary", "  sleep TIME ", NOW - timedelta(hours=1), sleep_end)]

        self.assertEqual(
            active_sleep_end(events, calendar_ids={"primary"}, title="Sleep Time", now=NOW),
            sleep_end,
        )

    def test_briefing_formats_time_portably_and_reports_ongoing_event(self) -> None:
        current = event("current", "primary", "Focus block", NOW - timedelta(minutes=10), NOW + timedelta(minutes=20))

        result = format_briefing(
            now=NOW,
            timezone="America/Los_Angeles",
            weather_summary="It will be clear and 72 degrees.",
            events=[current],
        )

        self.assertIn("It is 9:30 AM", result)
        self.assertIn("Focus block is happening now", result)


if __name__ == "__main__":
    unittest.main()
