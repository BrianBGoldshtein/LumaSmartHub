from __future__ import annotations

import json
import hashlib
import re
import secrets
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlsplit
from threading import RLock

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_httplib2 import AuthorizedHttp
import httplib2

from ..models import CalendarEvent
from ..storage import Storage


CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
TASK_WRITE_SCOPE = "https://www.googleapis.com/auth/calendar.events"
CLIENT_CONFIG_KEY = "google_client_config"
TOKEN_KEY = "google_credentials"
OAUTH_STATE_KEY = "google_oauth_state"


def calendar_failure_status(error: Exception) -> dict[str, Any]:
    """Classify structured SDK errors without exposing tokens/provider text."""
    rejected = isinstance(error, RefreshError) and any(
        isinstance(arg, dict) and arg.get("error") == "invalid_grant"
        for arg in error.args
    )
    unauthorized = isinstance(error, HttpError) and error.resp.status == 401
    if rejected or unauthorized:
        return {"error": "Google sign-in needs renewal. Use Reconnect Google; showing saved events.",
                "error_kind": "authorization", "reconnect_required": True}
    return {"error": "Calendar sync unavailable; showing saved events. Try again when the connection is available.",
            "error_kind": "unavailable", "reconnect_required": False}


class GoogleCalendarClient:
    def __init__(self, storage: Storage, *, redirect_uri: str = "http://127.0.0.1:8742/api/v1/google/callback"):
        self.storage = storage
        self.redirect_uri = redirect_uri
        self._oauth_lock = RLock()

    def configured(self) -> bool:
        return bool(self.storage.get_secret(CLIENT_CONFIG_KEY))

    def authorized(self) -> bool:
        return bool(self.storage.get_secret(TOKEN_KEY))

    def set_client_config(self, payload: dict[str, Any]) -> None:
        installed = payload.get("installed") or payload.get("web")
        if not installed or not installed.get("client_id") or not installed.get("client_secret"):
            raise ValueError("Google OAuth client JSON is missing its client ID or secret")
        with self._oauth_lock:
            self.storage.set_secret(CLIENT_CONFIG_KEY, json.dumps(payload, separators=(",", ":")))

    def task_write_authorized(self) -> bool:
        try:
            scopes = json.loads(self.storage.get_secret(TOKEN_KEY) or '{}').get('scopes', [])
            return isinstance(scopes, list) and TASK_WRITE_SCOPE in scopes
        except (ValueError, TypeError, AttributeError):
            return False

    def begin_authorization(self, *, task_updates: bool = False) -> str:
        with self._oauth_lock:
            config = self._client_config()
            state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(64)
            scopes = [CALENDAR_SCOPE] + ([TASK_WRITE_SCOPE] if task_updates or self.task_write_authorized() else [])
            flow = Flow.from_client_config(config, scopes=scopes, state=state,
                                          code_verifier=verifier, autogenerate_code_verifier=False)
            flow.redirect_uri = self.redirect_uri
            url, _ = flow.authorization_url(access_type="offline", prompt="consent", include_granted_scopes="true")
            # One atomic record survives a restart during the short setup window.
            # Do not depend on SDK defaults or retain the verifier only in a Flow.
            self.storage.set_secret(OAUTH_STATE_KEY, json.dumps({
                "state": state, "verifier": verifier, "issued_at": datetime.now(UTC).isoformat(),
                "config_sha256": self._config_digest(config),
                "scopes": scopes,
            }, separators=(",", ":")))
            return url

    def finish_authorization(self, authorization_response: str, state: str) -> None:
        with self._oauth_lock:
            self._finish_authorization(authorization_response, state)

    @staticmethod
    def _config_digest(config: dict) -> str:
        return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _finish_authorization(self, authorization_response: str, state: str) -> None:
        encoded = self.storage.get_secret(OAUTH_STATE_KEY)
        try:
            pending = json.loads(encoded or "null")
            if not isinstance(pending, dict) or not isinstance(state, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", state):
                raise ValueError("Invalid state")
            expected, verifier = pending["state"], pending["verifier"]
            if not isinstance(expected, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32}", expected) or not secrets.compare_digest(expected, state):
                raise ValueError("Wrong state")
            if not isinstance(verifier, str) or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier):
                raise ValueError("Missing verifier")
            age = (datetime.now(UTC) - datetime.fromisoformat(pending["issued_at"])).total_seconds()
            if not 0 <= age < 15 * 60:
                raise ValueError("Expired attempt")
            config = self._client_config()
            if pending["config_sha256"] != self._config_digest(config):
                raise ValueError("Client configuration changed")
            scopes = pending.get('scopes', [CALENDAR_SCOPE])
            if scopes not in ([CALENDAR_SCOPE], [CALENDAR_SCOPE, TASK_WRITE_SCOPE]):
                raise ValueError("Invalid requested permissions")
            response, target = urlsplit(authorization_response), urlsplit(self.redirect_uri)
            if len(authorization_response) > 8192 or response.fragment or (response.scheme, response.netloc, response.path) != (target.scheme, target.netloc, target.path):
                raise ValueError("Wrong callback")
            query = parse_qs(response.query, keep_blank_values=True, max_num_fields=32)
            codes = query.get("code", [])
            if query.get("state") != [state] or "error" in query or len(codes) != 1 or not 0 < len(codes[0]) <= 4096:
                raise ValueError("Invalid callback parameters")
        except (ValueError, TypeError, KeyError):
            raise ValueError("Google sign-in expired or did not match. Start sign-in again.") from None
        # Claim exactly this pending attempt once, even across separate clients.
        # Failed exchange requires a fresh consent attempt; existing tokens stay.
        if not self.storage.consume_secret(OAUTH_STATE_KEY, encoded):
            raise ValueError("Google sign-in was already handled. Start sign-in again.")
        flow = Flow.from_client_config(config, scopes=scopes, state=state,
                                      code_verifier=verifier, autogenerate_code_verifier=False)
        flow.redirect_uri = self.redirect_uri
        flow.oauth2session.trust_env = False
        # Permitted HTTP loopback redirect; the token exchange remains HTTPS.
        flow.fetch_token(code=codes[0], timeout=15)
        credentials = flow.credentials
        if not credentials.refresh_token:
            raise ValueError("Google did not grant offline access. Start sign-in again.")
        granted = credentials.granted_scopes if credentials.granted_scopes is not None else credentials.scopes
        if not set(scopes).issubset(set(granted or [])):
            raise ValueError("Google did not grant the requested permissions. Existing connection retained.")
        saved = json.loads(credentials.to_json())
        saved['scopes'] = list(granted or [])
        self.storage.set_secret(TOKEN_KEY, json.dumps(saved))

    def list_calendars(self) -> list[dict[str, Any]]:
        service = self._service()
        return self._list_calendars(service, service.colors().get().execute())

    def event_colors(self) -> list[dict[str, str]]:
        palette = self._service().colors().get().execute()
        return [{"id": key, "background": value["background"]} for key, value in palette.get('event', {}).items()
                if re.fullmatch(r'[1-9][0-9]{0,2}', key) and valid_color(value.get('background'))]

    @staticmethod
    def _list_calendars(service, palette: dict[str, Any]) -> list[dict[str, Any]]:
        calendars = []
        page_token = None
        while True:
            result = service.calendarList().list(pageToken=page_token).execute()
            for item in result.get("items", []):
                if item.get("deleted"):
                    continue
                background = valid_color(item.get("backgroundColor")) or valid_color(
                    palette.get("calendar", {}).get(item.get("colorId"), {}).get("background")
                )
                calendars.append({
                    "id": item["id"], "summary": item.get("summaryOverride") or item.get("summary", item["id"]),
                    "primary": item.get("primary", False), "background_color": background,
                    "selected": item.get("selected", False),
                    "access_role": item.get("accessRole", "reader"),
                })
            page_token = result.get("nextPageToken")
            if not page_token:
                return calendars

    def fetch_events(self, calendar_ids: list[str], start: datetime, end: datetime, timezone: str) -> list[CalendarEvent]:
        service = self._service()
        palette = service.colors().get().execute()
        calendars = self._list_calendars(service, palette)
        metadata = {item["id"]: item for item in calendars}
        primary = next((item for item in calendars if item["primary"]), {})
        events: list[CalendarEvent] = []
        for calendar_id in calendar_ids:
            calendar = primary if calendar_id == "primary" else metadata.get(calendar_id, {})
            page_token = None
            while True:
                result = service.events().list(
                    calendarId=calendar_id,
                    timeMin=start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    timeMax=end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    singleEvents=True,
                    orderBy="startTime",
                    pageToken=page_token,
                ).execute()
                for item in result.get("items", []):
                    if item.get("status") == "cancelled":
                        continue
                    event = parse_google_event(item, calendar_id, timezone)
                    event.calendar_name = calendar.get("summary")
                    event.calendar_color = calendar.get("background_color")
                    event.calendar_writable = calendar.get('access_role') in ('owner', 'writer')
                    event.event_color = valid_color(palette.get("event", {}).get(item.get("colorId"), {}).get("background"))
                    events.append(event)
                page_token = result.get("nextPageToken")
                if not page_token:
                    break
        return events

    @staticmethod
    def _countdown_colors(service, calendar_id):
        palette=service.colors().get().execute(num_retries=0)
        calendar=service.calendarList().get(calendarId=calendar_id).execute(num_retries=0)
        background=valid_color(calendar.get('backgroundColor')) or valid_color(palette.get('calendar',{}).get(calendar.get('colorId'),{}).get('background'))
        return palette,background

    def countdown_candidates(self,*,calendar_id,start,end,timezone,page_token=None):
        """One bounded, explicitly requested page; no automatic year-wide scan."""
        service=self._service()
        palette,background=self._countdown_colors(service,calendar_id)
        result=service.events().list(calendarId=calendar_id,timeMin=start.astimezone(UTC).isoformat(),
                    timeMax=end.astimezone(UTC).isoformat(),timeZone=timezone,singleEvents=True,
                    orderBy='startTime',showDeleted=False,maxResults=25,pageToken=page_token,
                    fields='nextPageToken,items(id,summary,start,end,status,colorId,attendees(self,responseStatus))').execute(num_retries=0)
        events=[]
        for raw in result.get('items',[]):
            if raw.get('status')=='cancelled': continue
            event=parse_google_event(raw,calendar_id,timezone)
            if event.self_declined: continue
            event.calendar_color=background
            event.event_color=valid_color(palette.get('event',{}).get(raw.get('colorId'),{}).get('background'))
            events.append(event)
        return {'events':events,'next_page':result.get('nextPageToken')}

    def countdown_event(self,*,calendar_id,event_id,timezone):
        service=self._service()
        try:
            raw=service.events().get(calendarId=calendar_id,eventId=event_id,
                    fields='id,summary,start,end,status,recurrence,colorId,attendees(self,responseStatus)').execute(num_retries=0)
        except HttpError as exc:
            if exc.resp.status in (404,410):
                return {'state':'deleted' if exc.resp.status==410 else 'unavailable','event':None}
            raise
        if raw.get('status')=='cancelled': return {'state':'deleted','event':None}
        if raw.get('recurrence'): raise ValueError('Pin one occurrence, not a recurring series.')
        event=parse_google_event(raw,calendar_id,timezone)
        if event.id!=event_id: raise ValueError('Google returned a different event.')
        if event.self_declined: return {'state':'unavailable','event':None}
        palette,background=self._countdown_colors(service,calendar_id)
        event.calendar_color=background
        event.event_color=valid_color(palette.get('event',{}).get(raw.get('colorId'),{}).get('background'))
        return {'state':'ready','event':event}

    def _client_config(self) -> dict[str, Any]:
        encoded = self.storage.get_secret(CLIENT_CONFIG_KEY)
        if not encoded:
            raise ValueError("Google OAuth client JSON has not been configured")
        return json.loads(encoded)

    def _credentials(self) -> Credentials:
        with self._oauth_lock:
            return self._load_credentials()

    def _load_credentials(self) -> Credentials:
        encoded = self.storage.get_secret(TOKEN_KEY)
        if not encoded:
            raise ValueError("Google Calendar has not been authorized")
        info = json.loads(encoded)
        credentials = Credentials.from_authorized_user_info(info, info.get('scopes') or [CALENDAR_SCOPE])
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self.storage.set_secret(TOKEN_KEY, credentials.to_json())
        return credentials

    def _service(self):
        return build("calendar", "v3", http=AuthorizedHttp(self._credentials(), http=httplib2.Http(timeout=15)), cache_discovery=False)

    def recolor_task(self, *, calendar_id: str, event_id: str, expected_etag: str,
                     color_id: str | None, timezone: str, now: datetime) -> CalendarEvent:
        if not self.task_write_authorized():
            raise PermissionError('Enable task updates in Google setup first.')
        service = self._service()
        raw = service.events().get(calendarId=calendar_id, eventId=event_id).execute(num_retries=0)
        event = parse_google_event(raw, calendar_id, timezone)
        from ..calendar_logic import todo_events
        if raw.get('recurrence') or not todo_events([event], todo_calendar_id=calendar_id, now=now):
            raise ValueError('This is no longer an active all-day task. Refresh your calendar.')
        if not event.etag or event.etag != expected_etag:
            raise TaskConflict('This task changed in Google. Refresh before updating it.')
        palette = service.colors().get().execute(num_retries=0)
        if color_id is not None and color_id not in palette.get('event', {}):
            raise ValueError('The completed color is unavailable. Choose it again in Google setup.')
        # Patch only color. Null clears the explicit override, restoring the
        # calendar default. An ETag prevents overwriting a concurrent edit.
        request = service.events().patch(calendarId=calendar_id, eventId=event_id,
                                         body={'colorId': color_id}, sendUpdates='none')
        request.headers['If-Match'] = expected_etag
        try:
            updated = request.execute(num_retries=0)
        except HttpError as exc:
            if exc.resp.status == 412:
                raise TaskConflict('This task changed in Google. Refresh before updating it.') from None
            raise
        result = parse_google_event(updated, calendar_id, timezone)
        if result.event_color_id != color_id:
            raise ValueError('Google did not confirm the requested color. Refresh your calendar.')
        result.event_color = valid_color(palette.get('event', {}).get(color_id, {}).get('background'))
        return result


class TaskConflict(ValueError):
    pass


def valid_color(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else None


def parse_google_event(payload: dict[str, Any], calendar_id: str, timezone: str) -> CalendarEvent:
    zone = ZoneInfo(timezone)
    all_day = "date" in payload["start"]
    if all_day:
        start = datetime.combine(date.fromisoformat(payload["start"]["date"]), time.min, zone)
        end = datetime.combine(date.fromisoformat(payload["end"]["date"]), time.min, zone)
    else:
        start = datetime.fromisoformat(payload["start"]["dateTime"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(payload["end"]["dateTime"].replace("Z", "+00:00"))
    return CalendarEvent(
        id=payload["id"], calendar_id=calendar_id, summary=payload.get("summary", "Untitled event"),
        start=start, end=end, all_day=all_day, location=payload.get("location"),
        description=payload.get("description"), status=payload.get("status", "confirmed"),
        event_color_id=str(payload['colorId']) if payload.get('colorId') not in (None, '', '0', 0) else None,
        etag=payload.get('etag'),
        self_declined=any(item.get('self') is True and item.get('responseStatus') == 'declined'
                          for item in payload.get('attendees', []) if isinstance(item, dict)),
        virtual_only=_virtual_only(payload),
    )


def _virtual_only(payload: dict[str, Any]) -> bool:
    location = str(payload.get('location') or '').strip()
    # Do not mistake a map/address URL for a virtual meeting. Unknown URLs
    # remain eligible; owners can choose which calendars to include.
    try:
        host = (urlsplit(location).hostname or '').lower()
    except ValueError:
        host = ''
    meeting_hosts = ('meet.google.com','zoom.us','teams.microsoft.com','teams.live.com','webex.com')
    virtual_location = location.casefold() in {'online', 'virtual'} or any(host == domain or host.endswith('.'+domain) for domain in meeting_hosts)
    return virtual_location or bool((payload.get('hangoutLink') or payload.get('conferenceData')) and not location)
