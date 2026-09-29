from __future__ import annotations

import unittest
from datetime import UTC

from luma.integrations.google_calendar import parse_google_event
from luma.integrations.open_meteo import parse_forecast


class IntegrationParsingTests(unittest.TestCase):
    def test_open_meteo_forecast_parsing(self) -> None:
        payload = {
            "current": {"time": "2026-09-24T09:00", "temperature_2m": 68.2, "apparent_temperature": 67.1, "weather_code": 1},
            "daily": {"temperature_2m_max": [75.0], "temperature_2m_min": [57.0]},
            "hourly": {
                "time": ["2026-09-24T08:00", "2026-09-24T09:00", "2026-09-24T10:00"],
                "temperature_2m": [66, 68, 70], "precipitation_probability": [0, 5, 10], "weather_code": [0, 1, 2],
            },
        }

        result = parse_forecast(payload, "America/Los_Angeles")

        self.assertEqual(result.temperature, 68.2)
        self.assertEqual(result.summary, "Mostly clear.")
        self.assertEqual(len(result.hourly), 2)
        self.assertIsNotNone(result.observed_at.utcoffset())

    def test_google_timed_event_parsing(self) -> None:
        payload = {"id": "event-1", "summary": "Call", "status": "confirmed", "start": {"dateTime": "2026-09-24T16:00:00Z"}, "end": {"dateTime": "2026-09-24T17:00:00Z"}}

        result = parse_google_event(payload, "primary", "America/Los_Angeles")

        self.assertFalse(result.all_day)
        self.assertEqual(result.start.tzinfo, UTC)

    def test_google_all_day_end_remains_exclusive(self) -> None:
        payload = {"id": "event-2", "summary": "Holiday", "start": {"date": "2026-09-24"}, "end": {"date": "2026-09-25"}}

        result = parse_google_event(payload, "primary", "America/Los_Angeles")

        self.assertTrue(result.all_day)
        self.assertEqual((result.end - result.start).days, 1)


if __name__ == "__main__":
    unittest.main()
