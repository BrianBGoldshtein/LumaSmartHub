"""Restricted companion controller; loopback-only, not a generic HTTP proxy.

The opt-in gateway exposes only a fixed allowlist. A signed dispatch uses an in-process
ASGI operation table to reuse the existing validated local controllers/locks.
No caller-selected upstream URL, headers, credentials or API path is allowed.
"""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .companion_auth import CompanionAuth, CompanionDenied, MAX_BODY, _identity_digest, private_origin
from .serde import to_primitive
from .tailscale_setup import tailscale_request
from .pi_connect_setup import qr_data
from .companion_google import CompanionGoogle


SETTINGS_KEYS = frozenset({
    "theme", "orientation", "brightness", "volume", "timezone", "latitude", "longitude", "cycle",
    "weather_location_label", "visible_calendar_ids", "todo_calendar_id", "todo_completed_color_id",
    "sleep_calendar_ids", "sleep_event_title", "departure_calendar_ids", "departure_enabled",
    "departure_include_virtual", "departure_prep_minutes", "departure_travel_minutes", "voice_enabled",
    "night_clock_enabled", "night_brightness", "timer_focus_minutes", "timer_break_minutes",
    "notification_chime_enabled", "notification_chime_volume", "weather_nudges_enabled",
    "weather_rain_percent", "weather_gust_mph", "weather_hot_f", "weather_cold_f",
})
COMMANDS = frozenset({"set_brightness", "set_volume", "set_theme", "show_page", "next_page",
    "previous_page", "pause_cycle", "resume_cycle", "wake", "screen_off", "good_night",
    "good_morning", "privacy_now", "start_timer", "pause_timer", "resume_timer",
    "cancel_timer", "show_timer", "dismiss_timer"})
UPSTREAMS = {
    ("PATCH", "/remote/api/settings"): "/api/v1/settings",
    ("POST", "/remote/api/command"): "/api/v1/commands",
    ("GET", "/remote/api/google/status"): "/api/v1/google/status",
    ("GET", "/remote/api/google/calendars"): "/api/v1/google/calendars",
    ("GET", "/remote/api/google/colors"): "/api/v1/google/event-colors",
    ("POST", "/remote/api/google/sync"): "/api/v1/google/sync",
    ("POST", "/remote/api/todos/complete"): "/api/v1/todos/complete",
    ("GET", "/remote/api/updates/status"): "/api/v1/updates/status",
    ("POST", "/remote/api/updates/check"): "/api/v1/updates/check",
    ("POST", "/remote/api/updates/install"): "/api/v1/updates/install",
}
EVENT_KEYS = {"id", "calendar_id", "summary", "start", "end", "all_day", "location",
    "calendar_name", "calendar_color", "event_color", "event_color_id", "etag", "completed", "due_date"}


def remote_guard(request: Request):
    # ASGI scope only: never populate this callable from a request header/body.
    check = request.scope.get("luma_companion_check")
    if check is not None:
        check()


def settings_view(service):
    values = to_primitive(service.settings)
    return {key: values[key] for key in SETTINGS_KEYS}


def preview_view(service):
    view = service.snapshot()
    result = {key: view[key] for key in ("server_time", "privacy_redacted", "weather", "timer", "departure", "todo_controls")}
    result["settings"] = {key: view["settings"][key] for key in ("theme", "timezone", "weather_location_label")}
    result["state"] = {key: view["state"][key] for key in ("active_page", "display_power", "phone_connected")}
    for key in ("calendar", "ongoing", "todos"):
        result[key] = [{field: row[field] for field in EVENT_KEYS if field in row} for row in view[key]]
    return result  # Never notifications, phone address, game state or future settings.


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def parse_object(raw: bytes):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict): raise ValueError
        return value
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, "Remote request is invalid.") from None


async def _body(request: Request, limit=100000):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise HTTPException(413, "Remote request is too large.")
        raw.extend(chunk)
    return parse_object(bytes(raw))


def _shape(payload, required, optional=frozenset()):
    if not required <= payload.keys() or payload.keys() - required - optional:
        raise HTTPException(422, "Remote request is invalid.")


def install_companion_api(app, service, storage, bluetooth, local_only, google_connected=None):
    auth = CompanionAuth(storage, bluetooth.companion_presence)
    app.state.companion = auth
    app.state.bluetooth = bluetooth
    web_google=CompanionGoogle(auth,app.state.google)
    app.state.companion_google=web_google

    def denied(error):
        return HTTPException(403, str(error))

    @app.post("/api/v1/companion/local", dependencies=[Depends(local_only)])
    async def local(request: Request):
        payload = await _body(request, 1024)
        _shape(payload, {"action", "pin"}, {"device_id", "comparison_code"})
        try:
            action = payload["action"]
            if action == "issue":
                _shape(payload, {"action", "pin"})
                auth._pin(payload["pin"])  # Reject before privileged transport lookup.
                status = await tailscale_request({"action": "status"})
                url = status.get("command_url")
                if not isinstance(url, str) or not url.endswith("/command"):
                    raise HTTPException(409, "Enable Luma’s private Tailscale HTTPS connection first.")
                origin = private_origin(url.removesuffix("/command"))
                ticket = auth.issue_ticket(payload["pin"], origin)
                url=origin + "/remote/#enroll=" + ticket
                result = {"url":url, "qr":await qr_data(url), "expires_in_seconds":300}
            elif action == "pending":
                _shape(payload, {"action", "pin"})
                result = {"pending": auth.pending_status(payload["pin"])}
            elif action == "approve":
                _shape(payload, {"action", "pin", "device_id", "comparison_code"})
                auth.approve(payload["pin"], payload["device_id"], payload["comparison_code"])
                result = {"approved": True}
            elif action == "devices":
                _shape(payload, {"action", "pin"})
                result = {"devices": auth.devices(payload["pin"])}
            elif action == "revoke":
                _shape(payload, {"action", "pin", "device_id"})
                auth.revoke(payload["pin"], payload["device_id"])
                result = {"revoked": True}
            else:
                raise HTTPException(422, "Remote request is invalid.")
        except CompanionDenied as error:
            raise denied(error) from None
        except (ValueError, TypeError):
            raise HTTPException(503, "Private connection setup is unavailable.") from None
        return JSONResponse(result, headers={"Cache-Control":"no-store", "Referrer-Policy":"no-referrer"})

    @app.post("/api/v1/companion/protocol", dependencies=[Depends(local_only)])
    async def protocol(request: Request):
        payload = await _body(request, 4096)
        _shape(payload, {"action", "origin", "identity"},
               {"ticket", "public_key", "signature", "device_id", "method", "path", "body_digest"})
        try:
            origin, identity = private_origin(payload["origin"]), payload["identity"]
            digest = _identity_digest(identity)
            if payload["action"] == "bootstrap":
                _shape(payload, {"action", "origin", "identity"})
                result = {"origin": origin, "identityDigest": digest}
            elif payload["action"] == "claim":
                _shape(payload, {"action", "origin", "identity", "ticket", "public_key", "signature"})
                result = auth.claim(payload["ticket"], origin, identity, payload["public_key"], payload["signature"])
            elif payload["action"] == "challenge":
                _shape(payload, {"action", "origin", "identity", "device_id", "method", "path", "body_digest"})
                result = auth.challenge(payload["device_id"], origin, identity, payload["method"], payload["path"], payload["body_digest"])
            else:
                raise HTTPException(422, "Remote request is invalid.")
        except CompanionDenied as error:
            raise denied(error) from None
        except (ValueError, TypeError):
            raise HTTPException(422, "Remote request is invalid.") from None
        return JSONResponse(result, headers={"Cache-Control":"no-store"})

    @app.post('/api/v1/companion/google-callback',dependencies=[Depends(local_only)])
    async def google_callback(request: Request):
        payload=await _body(request,20000)
        _shape(payload,{'origin','identity','query'})
        try:
            await asyncio.to_thread(web_google.finish,payload['origin'],payload['identity'],payload['query'])
            if google_connected:google_connected()
            connected=True
        except Exception:
            # Fixed completion only, never log/reflect the code or SDK error.
            connected=False
        return JSONResponse({'connected':connected},headers={'Cache-Control':'no-store'})

    @app.post("/api/v1/companion/dispatch", dependencies=[Depends(local_only)])
    async def dispatch(request: Request):
        payload = await _body(request)
        _shape(payload, {"device_id", "nonce", "origin", "identity", "method", "path", "body", "signature"})
        try:
            if not isinstance(payload["body"], str) or len(payload["body"]) > 87384:
                raise HTTPException(413, "Remote request is too large.")
            body = base64.b64decode(payload["body"], validate=True)
            if len(body) > MAX_BODY: raise HTTPException(413, "Remote request is too large.")
            keys = (payload["device_id"], payload["nonce"], payload["origin"], payload["identity"],
                    payload["method"], payload["path"], body, payload["signature"])
            initial = auth.verify(*keys)
            def recheck():
                try:
                    auth.still_authorized(payload["device_id"], payload["origin"], payload["identity"], initial)
                except CompanionDenied as error:
                    raise denied(error) from None
            method, path = payload["method"], payload["path"]
            if (method, path) == ("GET", "/remote/api/preview"):
                result, status_code = preview_view(service), 200
            elif (method, path) == ("GET", "/remote/api/settings"):
                result, status_code = settings_view(service), 200
            elif path=='/remote/api/google/web-client':
                value=parse_object(body)
                try:
                    result=await asyncio.to_thread(web_google.set_client,value,payload['origin'],recheck)
                except CompanionDenied:
                    raise
                except ValueError:
                    raise HTTPException(422,'Upload a Google Web application client with this exact HTTPS redirect URI.') from None
                status_code=200
            elif path=='/remote/api/google/authorize':
                value=parse_object(body);_shape(value,{'task_updates'})
                try:
                    result=await asyncio.to_thread(web_google.begin,payload['device_id'],payload['origin'],payload['identity'],initial,task_updates=value['task_updates'])
                except CompanionDenied:
                    raise
                except ValueError:
                    raise HTTPException(422,'Configure Google Web consent, then request sign-in again.') from None
                status_code=200
            else:
                upstream = UPSTREAMS.get((method, path))
                if not upstream:
                    raise HTTPException(501, "This remote feature is still being prepared.")
                if method != "GET":
                    value = parse_object(body)
                    if path == "/remote/api/settings":
                        if not value or value.keys() - SETTINGS_KEYS:
                            raise HTTPException(422, "This setting is not available from the phone.")
                    elif path == "/remote/api/command":
                        _shape(value, {"name"}, {"value"})
                        if not isinstance(value["name"], str) or value["name"] not in COMMANDS:
                            raise HTTPException(422, "This command is not available from the phone.")
                        value["source"] = "phone_remote"
                        body = json.dumps(value, separators=(",", ":")).encode()
                    elif path in {"/remote/api/google/sync", "/remote/api/updates/check"} and value:
                        raise HTTPException(422, "Remote request is invalid.")
                # Scope callback is created here, never accepted from a client.
                async def guarded(scope, receive, send):
                    recheck()
                    await app({**scope, "luma_companion_check": recheck}, receive, send)
                async with asyncio.timeout(45):
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=guarded, client=("127.0.0.1", 0)),
                            base_url="http://127.0.0.1:8742", trust_env=False, follow_redirects=False) as client:
                        response = await client.request(method, upstream, content=body if method != "GET" else None,
                                                        headers={"Content-Type":"application/json"})
                recheck()
                if len(response.content) > 1024 * 1024:
                    raise HTTPException(503, "Remote response is too large.")
                if response.status_code >= 400:
                    # Never reflect validation inputs/provider text to a phone.
                    code = response.status_code if response.status_code in {403, 409, 410, 422, 503} else 503
                    raise HTTPException(code, "Hub operation unavailable. Refresh and review before trying again.")
                result, status_code = response.json(), response.status_code
                if path=='/remote/api/google/status':result={**result,**web_google.status(payload['origin'])}
                elif path == "/remote/api/settings": result = settings_view(service)
                elif path == "/remote/api/command": result = {"result":result["result"], "preview":preview_view(service)}
                elif path == "/remote/api/todos/complete": result = preview_view(service)
            recheck()
            return JSONResponse(result, status_code=status_code, headers={"Cache-Control":"no-store"})
        except CompanionDenied as error:
            raise denied(error) from None
        except HTTPException:
            raise
        except (ValueError, TypeError, KeyError, TimeoutError, httpx.HTTPError):
            raise HTTPException(503, "Hub operation unavailable. Refresh before trying again.") from None
