from datetime import UTC, datetime, timedelta
from dataclasses import asdict
from unittest.mock import MagicMock, patch
import pytest
import httplib2
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from fastapi.testclient import TestClient

from luma.api import create_app
from luma.integrations.google_calendar import GoogleCalendarClient, valid_color
from luma.models import CalendarEvent
from luma.service import LumaService
from luma.storage import Storage


NOW = datetime.now(UTC)
PALETTE = {"calendar": {"2": {"background": "#123456"}}, "event": {"5": {"background": "#fbd75b"}}}


def google_event(event_id="e1", **extra):
    return {"id": event_id, "summary": "Meeting", "start": {"dateTime": NOW.isoformat()},
            "end": {"dateTime": (NOW + timedelta(hours=1)).isoformat()}, **extra}


def client_and_service(tmp_path):
    client = GoogleCalendarClient(Storage(tmp_path / "luma.db"))
    service = MagicMock()
    client._service = lambda: service
    service.colors().get().execute.return_value = PALETTE
    return client, service


def test_custom_calendar_rgb_wins_and_event_override_is_retained(tmp_path):
    client, service = client_and_service(tmp_path)
    service.calendarList().list().execute.return_value = {"items": [
        {"id": "work", "summary": "Old", "summaryOverride": "Work", "colorId": "2", "backgroundColor": "#7986cb"}]}
    service.events().list().execute.return_value = {"items": [google_event(colorId="5"), google_event("e2")]}
    events = client.fetch_events(["work"], NOW, NOW + timedelta(days=1), "UTC")
    assert events[0].calendar_name == "Work"
    assert events[0].calendar_color == "#7986cb"
    assert events[0].event_color == "#fbd75b"
    assert events[1].event_color is None
    assert events[1].calendar_color == "#7986cb"


def test_calendar_and_event_pagination_primary_alias_and_deleted_events(tmp_path):
    client, service = client_and_service(tmp_path)
    service.calendarList().list().execute.side_effect = [
        {"items": [{"id": "deleted", "deleted": True}], "nextPageToken": "more-calendars"},
        {"items": [{"id": "owner@example.test", "primary": True, "summary": "Personal", "colorId": "2"}]},
    ]
    service.events().list().execute.side_effect = [
        {"items": [{"id": "deleted", "status": "cancelled"}], "nextPageToken": "more-events"},
        {"items": [google_event(colorId="unknown")]},
    ]
    events = client.fetch_events(["primary"], NOW, NOW + timedelta(days=1), "UTC")
    assert len(events) == 1
    assert events[0].calendar_name == "Personal"
    assert events[0].calendar_color == "#123456"
    assert events[0].event_color is None
    assert service.calendarList().list.call_args.kwargs["pageToken"] == "more-calendars"
    assert service.events().list.call_args.kwargs["pageToken"] == "more-events"


def test_colors_survive_restart_and_privacy_redacts_them(tmp_path):
    storage = Storage(tmp_path / "luma.db")
    service = LumaService(storage)
    service.update_settings({"visible_calendar_ids": ["work"]})
    event = CalendarEvent("e", "work", "Meeting", NOW, NOW + timedelta(hours=1), calendar_color="#123456", event_color="#fbd75b", calendar_name="Work")
    service.replace_events([event], NOW)
    restored = LumaService(storage)
    assert restored.events[0].event_color == "#fbd75b"
    assert restored.snapshot(NOW)["calendar"] == []
    restored.phone_seen(NOW)
    assert restored.snapshot(NOW)["calendar"][0]["calendar_color"] == "#123456"


def test_unsafe_colors_are_not_treated_as_css():
    assert valid_color("#abcdef") == "#abcdef"
    assert valid_color("red; background:url(https://example.test)") is None
    assert valid_color(None) is None


def test_sync_endpoint_updates_cache_and_keeps_it_on_failure(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.luma.update_settings({"visible_calendar_ids": ["work"]})
    event = CalendarEvent("e", "work", "Meeting", NOW, NOW + timedelta(hours=1), calendar_color="#123456")
    with patch.object(app.state.google, "authorized", return_value=True), patch.object(app.state.google, "fetch_events", return_value=[event]) as fetch:
        client = TestClient(app)
        assert client.post("/api/v1/google/sync").json()["count"] == 1
        assert app.state.luma.events[0].calendar_color == "#123456"
        fetch.side_effect = OSError("offline")
        assert client.post("/api/v1/google/sync").status_code == 502
        assert app.state.luma.events == [event]
        assert "saved events" in client.get("/api/v1/google/status").json()["error"]


def test_google_routes_require_lan_auth_and_bad_oauth_state_is_rejected(tmp_path):
    app = create_app(data_dir=tmp_path)
    remote = TestClient(app, client=("192.0.2.20", 1000))
    assert remote.get("/api/v1/google/calendars").status_code == 401
    assert remote.post("/api/v1/google/config", json={}).status_code == 401
    assert remote.post("/api/v1/google/sync").status_code == 401
    local = TestClient(app)
    failed = local.get("/api/v1/google/callback?state=wrong&code=fake", follow_redirects=False)
    assert failed.status_code == 303
    assert failed.headers["location"] == "/?setup=google&google_error=1"
    assert local.get("/api/v1/google/status").json()["authorized"] is False


def test_sync_worker_runs_on_startup(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.luma.update_settings({"visible_calendar_ids": ["work"]})
    with patch.object(app.state.google, "authorized", return_value=True), patch.object(app.state.google, "fetch_events", return_value=[]) as fetch:
        with TestClient(app) as client:
            client.post("/api/v1/google/sync")
        assert fetch.call_count >= 2


@pytest.mark.parametrize("route,method", [("sync", "post"), ("calendars", "get"), ("event-colors", "get")])
def test_rejected_grant_exposes_reconnect_without_deleting_saved_state(tmp_path, route, method):
    from luma.integrations.google_calendar import TOKEN_KEY
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.update_settings({"visible_calendar_ids": ["work"], "sleep_calendar_ids": ["sleep"]})
    event = CalendarEvent("saved", "work", "Saved title", NOW, NOW + timedelta(hours=1))
    service.replace_events([event], NOW)
    app.state.google.storage.set_secret(TOKEN_KEY, "synthetic-saved-refresh-token")
    saved_settings = asdict(service.settings)
    rejected = RefreshError("private provider description", {"error": "invalid_grant", "error_description": "private detail"})
    target = {"sync": "fetch_events", "calendars": "list_calendars", "event-colors": "event_colors"}[route]
    client = TestClient(app)
    with patch.object(app.state.google, target, side_effect=rejected):
        response = getattr(client, method)(f"/api/v1/google/{route}")
    assert response.status_code == 502
    assert "Reconnect Google" in response.json()["detail"]
    assert "private" not in response.text
    status = client.get("/api/v1/google/status").json()
    assert status["authorized"] is True  # Stored grant retained, not proof of validity.
    assert status["reconnect_required"] is True
    assert status["error_kind"] == "authorization"
    assert service.events == [event]
    assert asdict(service.settings) == saved_settings
    assert app.state.google.storage.get_secret(TOKEN_KEY) == "synthetic-saved-refresh-token"
    with patch.object(app.state.google, "fetch_events", side_effect=OSError("private timeout")):
        assert client.post("/api/v1/google/sync").status_code == 502
    assert client.get("/api/v1/google/status").json()["reconnect_required"] is True
    with patch.object(app.state.google, "fetch_events", return_value=[event]):
        assert client.post("/api/v1/google/sync").status_code == 200
    recovered = client.get("/api/v1/google/status").json()
    assert recovered["error"] is None and recovered["error_kind"] is None
    assert recovered["reconnect_required"] is False


@pytest.mark.parametrize("error,renew", [
    (RefreshError("private", {"error": "invalid_grant"}), True),
    (HttpError(httplib2.Response({"status": "401"}), b'{"error":{"message":"private"}}'), True),
    (HttpError(httplib2.Response({"status": "403"}), b'{"error":{"message":"private"}}'), False),
    (HttpError(httplib2.Response({"status": "429"}), b'{"error":{"message":"private"}}'), False),
    (HttpError(httplib2.Response({"status": "503"}), b'{"error":{"message":"private"}}'), False),
    (RefreshError("invalid_grant private text without structured rejection"), False),
    (RefreshError("private", {"error": "temporarily_unavailable"}), False),
    (OSError("private invalid_grant string is not evidence"), False),
])
def test_google_failure_classifies_only_structured_authorization_evidence(error, renew):
    from luma.integrations.google_calendar import calendar_failure_status
    result = calendar_failure_status(error)
    assert result["reconnect_required"] is renew
    assert result["error_kind"] == ("authorization" if renew else "unavailable")
    assert "private" not in result["error"]
