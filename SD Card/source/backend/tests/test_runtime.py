from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent, Command, CommandName, WeatherSnapshot
from luma.service import LumaService
from luma.storage import Storage
from luma.weather_runtime import WeatherRuntime


@pytest.fixture
def service(tmp_path):
    return LumaService(Storage(tmp_path / "luma.db"))


@pytest.mark.asyncio
async def test_weather_refresh_persists_and_failure_keeps_cache(service):
    service.update_settings({"latitude": 0.0, "longitude": 0.0})
    forecast = WeatherSnapshot(datetime.now(UTC), 70, 70, 75, 60, 0, "Clear")
    client = Mock()
    client.fetch.return_value = forecast
    runtime = WeatherRuntime(service, client)
    assert await runtime.refresh() == {"updated": True}
    assert LumaService(service.storage).weather.temperature == 70
    client.fetch.side_effect = OSError("offline")
    with pytest.raises(OSError):
        await runtime.refresh()
    assert service.snapshot()["weather"]["stale"]
    assert service.weather.temperature == 70
    assert runtime.status["error"]


@pytest.mark.asyncio
async def test_weather_requires_location_and_location_change_clears_cache(service):
    client = Mock()
    runtime = WeatherRuntime(service, client)
    with pytest.raises(ValueError, match="location"):
        await runtime.refresh()
    client.fetch.assert_not_called()
    service.replace_weather(WeatherSnapshot(datetime.now(UTC), 70, 70, 75, 60, 0, "Clear"))
    runtime.location_changed()
    assert service.weather is None
    assert LumaService(service.storage).weather is None


def test_sleep_begins_and_ends_without_new_calendar_fetch(service):
    now = datetime.now(UTC)
    service.update_settings({"sleep_calendar_ids": ["sleep"]})
    service.replace_events([CalendarEvent("sleep", "sleep", "Sleep", now + timedelta(minutes=1), now + timedelta(hours=8))], now)
    assert service.snapshot(now)["state"]["display_power"] == "on"
    service.tick(now + timedelta(minutes=2))
    assert service.state.display_power == "off"
    service.tick(now + timedelta(hours=9))
    assert service.state.display_power == "on"


def test_age_alone_marks_weather_stale(service):
    now = datetime.now(UTC)
    service.replace_weather(WeatherSnapshot(now - timedelta(hours=3), 70, 70, 75, 60, 0, "Clear"))
    assert service.snapshot(now)["weather"]["stale"]


def test_clock_tick_does_not_write_database_when_state_unchanged(service):
    service.storage.set_cache = Mock()
    service.tick()
    service.tick()
    service.storage.set_cache.assert_not_called()


def test_control_command_publishes_overlay_action(service):
    queue = service.subscribe()
    service.execute(Command(CommandName.SHOW_BRIGHTNESS))
    message = queue.get_nowait()
    assert message["action"]["overlay"] == "brightness"


@pytest.mark.parametrize("patch", [{"timezone": "Not/AZone"}, {"timezone": None}, {"latitude": 20}, {"volume": None}, {"visible_calendar_ids": None}])
def test_bad_settings_leave_previous_state_intact(tmp_path, patch):
    client = TestClient(create_app(data_dir=tmp_path))
    before = client.get("/api/v1/settings").json()
    assert client.patch("/api/v1/settings", json=patch).status_code == 422
    assert client.get("/api/v1/settings").json() == before


def test_location_can_be_cleared_atomically(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.patch("/api/v1/settings", json={"latitude": 0, "longitude": 0}).status_code == 200
    assert client.patch("/api/v1/settings", json={"latitude": None, "longitude": None}).status_code == 200
    assert client.post("/api/v1/weather/sync").status_code == 422
