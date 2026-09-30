"""Real OAuth SDK behavior with only the HTTP transport replaced; no accounts."""
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch

import requests
import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.integrations.google_calendar import GoogleCalendarClient, TOKEN_KEY, OAUTH_STATE_KEY
from luma.storage import Storage

CONFIG = {"installed": {"client_id": "synthetic.apps.googleusercontent.com", "client_secret": "synthetic-secret",
          "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
          "redirect_uris": ["http://localhost"]}}


def test_real_sdk_pkce_survives_recreated_client_and_saves_refresh_token(tmp_path):
    db = tmp_path / "luma.db"
    initial = GoogleCalendarClient(Storage(db))
    initial.set_client_config(CONFIG)
    query = parse_qs(urlsplit(initial.begin_authorization()).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    restored = GoogleCalendarClient(Storage(db))

    def token_exchange(session, request, **kwargs):
        assert request.url == CONFIG["installed"]["token_uri"]
        form = parse_qs(request.body)
        assert "code_verifier" in form, "PKCE verifier was lost between authorization and callback"
        verifier = form["code_verifier"][0]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        assert query["code_challenge"] == [challenge]
        assert kwargs["timeout"] == 15
        assert session.trust_env is False
        response = requests.Response()
        response.request = request
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps({"access_token": "synthetic-access", "refresh_token": "synthetic-refresh",
                                       "token_type": "Bearer", "expires_in": 3600}).encode()
        return response

    callback = restored.redirect_uri + "?" + urlencode({"state": query["state"][0], "code": "synthetic-code"})
    with patch.object(requests.Session, "send", token_exchange):
        restored.finish_authorization(callback, query["state"][0])
    assert json.loads(Storage(db).get_secret(TOKEN_KEY))["refresh_token"] == "synthetic-refresh"
    assert Storage(db).get_secret(OAUTH_STATE_KEY) is None


def pending_client(tmp_path):
    client = GoogleCalendarClient(Storage(tmp_path / "luma.db"))
    client.set_client_config(CONFIG)
    state = parse_qs(urlsplit(client.begin_authorization()).query)["state"][0]
    callback = client.redirect_uri + "?" + urlencode({"state": state, "code": "synthetic-code"})
    return client, state, callback


@pytest.mark.parametrize("change", ["expired", "future", "missing_verifier", "old_format", "bad_state", "new_client"])
def test_invalid_pending_attempts_never_exchange_or_replace_existing_tokens(tmp_path, change):
    client, state, callback = pending_client(tmp_path)
    client.storage.set_secret(TOKEN_KEY, "existing-synthetic-credentials")
    pending = json.loads(client.storage.get_secret(OAUTH_STATE_KEY))
    if change == "expired":
        pending["issued_at"] = (datetime.now(UTC) - timedelta(minutes=16)).isoformat()
    elif change == "future":
        pending["issued_at"] = (datetime.now(UTC) + timedelta(minutes=1)).isoformat()
    elif change == "missing_verifier":
        pending.pop("verifier")
    elif change == "old_format":
        pending = state
    elif change == "bad_state":
        state = "not-the-original-state"
    elif change == "new_client":
        client.set_client_config({"installed": {**CONFIG["installed"], "client_id": "different-client"}})
    client.storage.set_secret(OAUTH_STATE_KEY, json.dumps(pending))
    with patch.object(requests.Session, "send") as exchange, pytest.raises(ValueError):
        client.finish_authorization(callback, state)
    exchange.assert_not_called()
    assert client.storage.get_secret(TOKEN_KEY) == "existing-synthetic-credentials"


@pytest.mark.parametrize("change", ["duplicate_state", "duplicate_code", "wrong_host", "wrong_path", "denied", "no_code"])
def test_callback_shape_is_checked_before_any_exchange(tmp_path, change):
    client, state, callback = pending_client(tmp_path)
    if change == "duplicate_state":
        callback += "&state=" + state
    elif change == "duplicate_code":
        callback += "&code=second"
    elif change == "wrong_host":
        callback = callback.replace("127.0.0.1", "example.test")
    elif change == "wrong_path":
        callback = callback.replace("/callback", "/wrong")
    elif change == "denied":
        callback += "&error=access_denied"
    elif change == "no_code":
        callback = client.redirect_uri + "?state=" + state
    with patch.object(requests.Session, "send") as exchange, pytest.raises(ValueError):
        client.finish_authorization(callback, state)
    exchange.assert_not_called()


def test_failed_exchange_is_single_use_and_retains_previous_account(tmp_path):
    client, state, callback = pending_client(tmp_path)
    client.storage.set_secret(TOKEN_KEY, "existing-synthetic-credentials")
    with patch.object(requests.Session, "send", side_effect=requests.Timeout("synthetic timeout")) as exchange:
        with pytest.raises(requests.Timeout):
            client.finish_authorization(callback, state)
        with pytest.raises(ValueError):
            client.finish_authorization(callback, state)
    assert exchange.call_count == 1
    assert client.storage.get_secret(OAUTH_STATE_KEY) is None
    assert client.storage.get_secret(TOKEN_KEY) == "existing-synthetic-credentials"


def test_repeated_and_concurrent_callbacks_cannot_exchange_twice(tmp_path):
    initial, state, callback = pending_client(tmp_path)
    def complete():
        client = GoogleCalendarClient(Storage(tmp_path / "luma.db"))
        try:
            client.finish_authorization(callback, state)
        except (ValueError, requests.Timeout):
            pass
    with patch.object(requests.Session, "send", side_effect=requests.Timeout("synthetic timeout")) as exchange:
        with ThreadPoolExecutor(max_workers=2) as workers:
            list(workers.map(lambda _: complete(), range(2)))
    assert exchange.call_count == 1
    assert initial.storage.get_secret(OAUTH_STATE_KEY) is None


def test_incomplete_offline_grant_does_not_replace_saved_refresh_token(tmp_path):
    client, state, callback = pending_client(tmp_path)
    client.storage.set_secret(TOKEN_KEY, "existing-synthetic-credentials")
    def access_only(session, request, **kwargs):
        response = requests.Response()
        response.request = request
        response.status_code = 200
        response._content = b'{"access_token":"synthetic-only","token_type":"Bearer","expires_in":3600}'
        return response
    with patch.object(requests.Session, "send", access_only), pytest.raises(ValueError, match="offline access"):
        client.finish_authorization(callback, state)
    assert client.storage.get_secret(TOKEN_KEY) == "existing-synthetic-credentials"


def test_network_callback_cannot_use_local_oauth_state(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.google.set_client_config(CONFIG)
    state = parse_qs(urlsplit(app.state.google.begin_authorization()).query)["state"][0]
    remote = TestClient(app, client=("192.0.2.20", 1000), base_url="http://127.0.0.1:8742")
    headers = {"X-Luma-Token": app.state.security.get_or_create_lan_token()}
    with patch.object(requests.Session, "send") as exchange:
        response = remote.get("/api/v1/google/callback", params={"state": state, "code": "synthetic"}, headers=headers)
    assert response.status_code == 403
    exchange.assert_not_called()


def test_local_browser_callback_completes_and_returns_to_setup(tmp_path):
    app = create_app(data_dir=tmp_path)
    browser = TestClient(app, base_url="http://127.0.0.1:8742")
    assert browser.post("/api/v1/google/config", json=CONFIG).status_code == 200
    authorization = browser.post("/api/v1/google/authorize").json()
    assert set(authorization) == {"url"}
    query = parse_qs(urlsplit(authorization["url"]).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/calendar.readonly"]
    assert "code_verifier" not in query
    def exchange(session, request, **kwargs):
        form = parse_qs(request.body)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"][0].encode()).digest()).decode().rstrip("=")
        assert query["code_challenge"] == [challenge]
        response = requests.Response()
        response.request = request
        response.status_code = 200
        response._content = b'{"access_token":"synthetic-access","refresh_token":"synthetic-refresh","token_type":"Bearer","expires_in":3600}'
        return response
    with patch.object(requests.Session, "send", exchange):
        response = browser.get("/api/v1/google/callback", params={"state": query["state"][0], "code": "synthetic-code"}, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/?setup=google"
    assert browser.get("/api/v1/google/status").json()["authorized"] is True
    assert browser.get("/api/v1/state").json()["privacy_redacted"] is True


def test_api_launcher_does_not_log_oauth_callback_urls_or_trust_proxy_headers():
    from luma.api import main
    with patch("luma.api.create_app"), patch("luma.api.uvicorn.run") as run:
        main()
    assert run.call_args.kwargs["access_log"] is False
    assert run.call_args.kwargs["proxy_headers"] is False


def test_cancelled_sign_in_returns_to_touch_setup_without_echoing_provider_details(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.google.set_client_config(CONFIG)
    state = parse_qs(urlsplit(app.state.google.begin_authorization()).query)["state"][0]
    browser = TestClient(app, base_url="http://127.0.0.1:8742")
    with patch.object(requests.Session, "send") as exchange:
        response = browser.get("/api/v1/google/callback", params={"state": state, "error": "access_denied", "error_description": "synthetic-private-detail"}, follow_redirects=False)
    exchange.assert_not_called()
    assert response.status_code == 303
    assert response.headers["location"] == "/?setup=google&google_error=1"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "synthetic-private-detail" not in response.text
    assert not app.state.google.authorized()
