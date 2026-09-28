from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch

from luma.api import create_app
from luma.models import CalendarEvent


def test_sleep_setup_uses_selected_hidden_calendar_and_custom_title(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    now = datetime.now(UTC)
    response = client.patch("/api/v1/settings", json={"visible_calendar_ids": ["work"], "sleep_calendar_ids": ["rest"], "sleep_event_title": "Bed Time"})
    assert response.status_code == 200
    service = app.state.luma
    service.replace_events([CalendarEvent("work", "work", "Bed Time", now - timedelta(hours=1), now + timedelta(hours=1))], now)
    assert service.snapshot(now)["state"]["display_power"] == "on"
    service.replace_events([CalendarEvent("rest", "rest", "Bed Time", now - timedelta(hours=1), now + timedelta(hours=1))], now)
    assert service.snapshot(now)["state"]["display_power"] == "off"
    service.phone_seen(now)
    assert service.snapshot(now)["calendar"] == []  # Sleep-only calendar stays off the agenda.
    restarted = create_app(data_dir=tmp_path)
    assert restarted.state.luma.settings.sleep_calendar_ids == ["rest"]
    assert restarted.state.luma.settings.sleep_event_title == "Bed Time"


def test_empty_sleep_calendar_selection_disables_automatic_sleep(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    now = datetime.now(UTC)
    assert client.patch("/api/v1/settings", json={"visible_calendar_ids": ["work"], "sleep_calendar_ids": []}).status_code == 200
    app.state.luma.replace_events([CalendarEvent("night", "work", "Sleep", now - timedelta(hours=1), now + timedelta(hours=1))], now)
    assert app.state.luma.snapshot(now)["state"]["display_power"] == "on"


def test_daily_sleep_default_uses_independent_calendar_and_survives_restart(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    now = datetime(2026, 9, 27, 6, tzinfo=UTC)  # 23:00 local; crosses midnight.
    service.update_settings({'visible_calendar_ids': ['work', 'personal'], 'sleep_calendar_ids': ['rest']})
    assert service.settings.sleep_event_title == 'Sleep'
    events = [CalendarEvent(f'night-{day}', 'rest', ' Sleep ', now + timedelta(days=day),
                            now + timedelta(days=day, hours=8)) for day in range(2)]
    service.replace_events(events, now - timedelta(seconds=1))
    assert service.state.scheduled_sleep_end is None
    for day in range(2):
        start = now + timedelta(days=day)
        service.tick(start)
        assert service.state.scheduled_sleep_end == start + timedelta(hours=8)
        service.tick(start + timedelta(hours=8))
        assert service.state.scheduled_sleep_end is None
    restarted = create_app(data_dir=tmp_path).state.luma
    restarted.tick(now + timedelta(hours=1))
    assert restarted.state.scheduled_sleep_end == now + timedelta(hours=8)
    assert restarted.settings.visible_calendar_ids == ['work', 'personal']
    assert restarted.settings.sleep_calendar_ids == ['rest']


@pytest.mark.parametrize('changes', [dict(calendar_id='work'), dict(summary='Sleep Time'),
                                    dict(all_day=True), dict(status='cancelled'), dict(self_declined=True)])
def test_sleep_ignores_wrong_calendar_title_and_ineligible_events(tmp_path, changes):
    service = create_app(data_dir=tmp_path).state.luma
    service.update_settings({'visible_calendar_ids': ['work'], 'sleep_calendar_ids': ['rest']})
    now = datetime.now(UTC)
    values = dict(id='night', calendar_id='rest', summary='Sleep', start=now-timedelta(hours=1), end=now+timedelta(hours=1))
    service.replace_events([CalendarEvent(**(values | changes))], now)
    assert service.state.scheduled_sleep_end is None


def test_google_sync_fetches_sleep_calendar_separately_from_all_agenda_calendars(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.luma.update_settings({'visible_calendar_ids': ['work', 'personal'], 'sleep_calendar_ids': ['rest']})
    with patch.object(app.state.google, 'authorized', return_value=True), patch.object(app.state.google, 'fetch_events', return_value=[]) as fetch:
        assert TestClient(app).post('/api/v1/google/sync').status_code == 200
        assert fetch.call_args.args[0] == ['work', 'personal', 'rest']


@pytest.mark.parametrize('values', [{'sleep_event_title': ''}, {'sleep_event_title': ' '},
                                  {'sleep_event_title': 'x'*101}, {'sleep_event_title': 'Sleep\n'},
                                  {'sleep_calendar_ids': ['']}, {'sleep_calendar_ids': ['c']*51}])
def test_sleep_settings_validation(tmp_path, values):
    assert TestClient(create_app(data_dir=tmp_path)).patch('/api/v1/settings', json=values).status_code == 422
