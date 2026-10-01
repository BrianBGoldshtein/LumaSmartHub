from __future__ import annotations

import os
import asyncio
import shutil
import sys
from importlib.metadata import version as package_version
from time import monotonic
from uuid import uuid4
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from typing import Annotated, Any, Literal

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .models import AssistantPhase, Command, CommandName, Orientation, Theme
from .voice import parse_local_command
from .briefing import morning_briefing
from .voice_library import LIBRARY, answer_query
from .voice_model import predict as predict_voice_intent
from .countdown_api import install_countdown_api
from .transit_api import install_transit_api
from .room_api import install_room_api
from .scene_api import install_scene_api
from .backup_api import install_backup_api
from .update_api import install_update_api
from .bluetooth_runtime import BluetoothRuntime
from .security import SecurityManager
from .service import LumaService
from .storage import Storage
from .integrations.google_calendar import GoogleCalendarClient, TaskConflict
from .integrations.open_meteo import OpenMeteoClient
from .weather_runtime import WeatherRuntime
from .voice_calibration import VoiceCalibration
from .voice_call_trial import VoiceCallTrial
from .voice_asset import (fetch_and_install as fetch_voice_asset,
                          ready as voice_asset_ready, recover_interrupted_repair,
                          voice_status)
from .voice_speech import (VoicePlaybackError, play_fallback_preview,
                           play_preview as play_voice_preview, play_test_tone,
                           speaker_route_warning)
from .voice_health import load_history as load_voice_health, record as record_voice_health
from .voice_signal import AudioProfile, read_profile
from .voice_wake import read_wake_mode
from .voice_adaptation import PhraseAdaptations
from . import mic_hardware
from .network import network_request, validate_request
from .network_runtime import NetworkRuntime
from .tailscale_setup import tailscale_request, validate_request as validate_tailscale_request
from .pi_connect_setup import pi_connect_request
from .pairing import PairingFlow
from .shortcut_protocol import command_token, read_command
from .focus_timer import TIMER_COMMANDS


class CommandRequest(BaseModel):
    name: CommandName
    value: Any = None
    source: str = Field(default="ui", max_length=32)


class PinRequest(BaseModel):
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class HotspotRequest(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal["enable", "disable"]
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")
    same_as_pin: bool = Field(default=True, strict=True)
    wifi_password: str | None = Field(default=None, max_length=63)
    stanford_permission_confirmed: bool = Field(default=False, strict=True)


class PairingSessionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    session: str = Field(min_length=36, max_length=36)


class PairingSelection(PairingSessionRequest):
    device: str = Field(max_length=160, pattern=r"^/org/bluez/hci[0-9]+/dev_(?:[0-9A-Fa-f]{2}_){5}[0-9A-Fa-f]{2}$")


class PairingConfirmation(PairingSessionRequest):
    challenge: str = Field(min_length=36, max_length=36)
    accepted: bool = Field(strict=True)


class ForgetPhoneRequest(BaseModel):
    model_config = {"extra": "forbid"}
    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class PiConnectRequest(BaseModel):
    model_config = {"extra": "forbid"}
    action: Literal["status", "diagnose", "signin", "shell_on", "shell_off"]


class DeviceReport(BaseModel):
    controls: dict[str, str]


class KeyboardRequest(BaseModel):
    model_config = {"extra": "forbid"}
    visible: bool = Field(strict=True)


class DisplayRevision(BaseModel):
    model_config = {'extra':'forbid'}
    revision: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class DisplayGeneration(BaseModel):
    model_config = {'extra':'forbid'}
    generation: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


class DisplayConfirmation(DisplayRevision, DisplayGeneration):
    brightness_ok: bool = Field(strict=True)
    power_ok: bool = Field(strict=True)


class VoiceCommand(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class VoicePhrasePreview(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=160)


class WakeConfirmationChoice(BaseModel):
    model_config = {'extra': 'forbid'}
    mode: Literal['standard', 'dual_decoder']


class PhraseCorrectionConfirm(BaseModel):
    model_config = {'extra': 'forbid'}
    session: str = Field(pattern=r'^[0-9a-f]{32}$')


class VoicePhase(BaseModel):
    phase: AssistantPhase


class VoiceDiagnostic(BaseModel):
    model_config = {"extra": "forbid"}
    code: Literal[
        "recognizer_unavailable", "model_unavailable",
        "audio_capture_tool_missing", "capture_source_invalid",
        "capture_source_unavailable", "capture_stream_stopped",
        "capture_stream_stalled",
    ]


class VoiceOutputReport(BaseModel):
    model_config = {"extra": "forbid"}
    engine: Literal["piper", "fallback", "silent"]
    route: Literal["luma_speaker", "system_speaker"] | None = None
    sink_warning: Literal["muted", "very_low"] | None = None
    error: Literal[
        "audio_session_unavailable", "speaker_route_unavailable",
        "speaker_playback_failed", "piper_start_failed", "piper_start_timeout",
        "piper_runtime_missing", "piper_model_load_failed", "piper_memory_pressure", "piper_synthesis_failed",
        "piper_audio_invalid", "synthesis_unavailable", "voice_asset_unavailable", "piper_retry_wait",
        "fallback_playback_failed",
    ] | None = None
    primary_error: Literal[
        "audio_session_unavailable", "speaker_route_unavailable", "speaker_playback_failed",
        "piper_start_failed", "piper_start_timeout", "piper_runtime_missing",
        "piper_model_load_failed", "piper_memory_pressure", "piper_synthesis_failed", "piper_audio_invalid",
        "synthesis_unavailable", "voice_asset_unavailable", "piper_retry_wait",
    ] | None = None


class VoicePreviewResult(BaseModel):
    model_config = {"extra": "forbid"}
    request_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    route: Literal["luma_speaker", "system_speaker"] | None = None
    sink_warning: Literal["muted", "very_low"] | None = None
    error: Literal[
        "audio_session_unavailable", "speaker_route_unavailable", "speaker_playback_failed",
        "piper_start_failed", "piper_start_timeout", "piper_runtime_missing",
        "piper_model_load_failed", "piper_memory_pressure", "piper_synthesis_failed", "piper_audio_invalid",
        "fallback_playback_failed",
    ] | None = None


class VoicePreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    variant: Literal["piper", "fallback"] = "piper"


class VoiceHeartbeat(BaseModel):
    model_config = {"extra": "forbid"}
    dropped_frames: int = Field(default=0, strict=True, ge=0, le=1_000_000)


class CalibrationSample(BaseModel):
    model_config = {"extra": "forbid"}
    session: str = Field(max_length=64)
    text: str = Field(max_length=1000)
    free_text: str = Field(default="", max_length=1000)
    raw_free_text: str = Field(default="", max_length=1000)
    raw_compared: bool = Field(default=False, strict=True)
    raw_constrained_wake: bool | None = Field(default=None, strict=True)
    selected_text: str | None = Field(default=None, max_length=1000)
    selection: Literal["", "constrained", "free", "agree", "free_query", "conflict", "negated", "unmatched", "learned"] = ""
    rms: float = Field(ge=0, le=1, allow_inf_nan=False)
    peak: float = Field(ge=0, le=1, allow_inf_nan=False)
    dc: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    clipped_fraction: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)


class CalibrationLevel(BaseModel):
    model_config = {"extra": "forbid"}
    session: str = Field(max_length=64)
    rms: float = Field(ge=0, le=1, allow_inf_nan=False)
    peak: float = Field(ge=0, le=1, allow_inf_nan=False)
    floor_rms: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    floor_low_frequency_fraction: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class CalibrationSaveAudio(BaseModel):
    model_config = {"extra": "forbid"}
    session: str = Field(pattern=r"^[0-9a-f]{32}$")


class CallTrialObservation(BaseModel):
    model_config = {"extra": "forbid"}
    session: str = Field(pattern=r"^[0-9a-f]{32}$")
    partial_wake: bool = Field(strict=True)
    constrained_wake: bool = Field(strict=True)
    constrained_near_start: bool = Field(strict=True)
    free_wake: bool = Field(strict=True)
    free_near_start: bool = Field(strict=True)


class MicGainRequest(BaseModel):
    model_config = {"extra": "forbid"}
    gain: int = Field(strict=True, ge=0, le=63)


class SettingsPatch(BaseModel):
    night_clock_enabled: bool | None = Field(default=None, strict=True)
    night_brightness: int | None = Field(default=None, strict=True, ge=0, le=100)
    departure_calendar_ids: list[str] | None = Field(default=None, max_length=50)
    departure_enabled: bool | None = Field(default=None, strict=True)
    departure_include_virtual: bool | None = Field(default=None, strict=True)
    departure_prep_minutes: int | None = Field(default=None, strict=True, ge=0, le=240)
    departure_travel_minutes: int | None = Field(default=None, strict=True, ge=0, le=240)
    todo_completed_color_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{0,2}$")
    weather_nudges_enabled: bool | None = Field(default=None, strict=True)
    weather_rain_percent: int | None = Field(default=None, ge=1, le=100, strict=True)
    weather_gust_mph: int | None = Field(default=None, ge=5, le=100, strict=True)
    weather_hot_f: int | None = Field(default=None, ge=-50, le=130, strict=True)
    weather_cold_f: int | None = Field(default=None, ge=-50, le=130, strict=True)
    timer_focus_minutes: int | None = Field(default=None, ge=1, le=240, strict=True)
    timer_break_minutes: int | None = Field(default=None, ge=1, le=240, strict=True)
    onboarding_completed: bool | None = None
    theme: Theme | None = None
    orientation: Orientation | None = None
    brightness: int | None = Field(default=None, ge=0, le=100)
    volume: int | None = Field(default=None, ge=0, le=100)
    timezone: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    weather_location_label: str | None = None
    visible_calendar_ids: list[str] | None = None
    todo_calendar_id: str | None = None
    sleep_calendar_ids: list[str] | None = None
    sleep_event_title: str | None = None
    notification_app_allowlist: list[str] | None = None
    audio_output: str | None = None
    voice_enabled: bool | None = None
    phone_address: str | None = None


class TaskCompletionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    calendar_id: str = Field(min_length=1, max_length=1024)
    event_id: str = Field(min_length=1, max_length=1024, pattern=r"^[A-Za-z0-9_]+$")
    etag: str = Field(min_length=1, max_length=256, pattern=r"^[^\r\n]+$")
    completed: bool = Field(strict=True)


class DepartureRequest(BaseModel):
    model_config = {'extra':'forbid'}
    key: str = Field(pattern=r'^[a-f0-9]{64}$')
    action: str = Field(pattern=r'^(snooze|dismiss|override)$')
    prep: int | None = Field(default=None, strict=True, ge=0, le=240)
    travel: int | None = Field(default=None, strict=True, ge=0, le=240)


def _loopback(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def create_app(
    *,
    data_dir: str | Path | None = None,
    frontend_dir: str | Path | None = None,
) -> FastAPI:
    data_root = Path(data_dir or os.environ.get("LUMA_DATA_DIR", "/var/lib/luma"))
    storage = Storage(data_root / "luma.db")
    service = LumaService(storage)
    security = SecurityManager(storage)
    security.get_or_create_lan_token()
    google = GoogleCalendarClient(storage)
    service.todo_write_authorized = google.task_write_authorized()
    weather_client = OpenMeteoClient()
    weather = WeatherRuntime(service, weather_client)
    bluetooth = BluetoothRuntime(service)
    calibration = VoiceCalibration()
    call_trial = VoiceCallTrial()
    phrase_adaptations = PhraseAdaptations(storage.get_cache('voice', 'phrase_adaptations'))
    voice_asset_root = data_root / "voice-assets"
    voice_asset_retry = asyncio.Event()
    voice_asset_repair_requested = False
    voice_preview_lock = asyncio.Lock()
    mic_gain_lock = asyncio.Lock()
    voice_preview_job: dict[str, Any] = {}
    voice_tone_job: dict[str, Any] = {}
    voice_agent_status: dict[str, Any] = {"last_seen": 0.0, "phase": "idle", "diagnostic": None,
                                          "dropped_frames": 0}
    voice_output_status: dict[str, Any] = {"last_reply_engine": None, "last_reply_error": None,
                                          "last_reply_primary_error": None, "last_reply_at": None,
                                          "last_reply_route": None, "last_reply_sink_warning": None,
                                          "last_preview_error": None, "last_preview_route": None,
                                          "last_preview_sink_warning": None,
                                          "last_fallback_error": None, "last_fallback_route": None,
                                          "last_fallback_sink_warning": None,
                                          "last_tone_error": None, "last_tone_route": None,
                                          "last_tone_sink_warning": None}
    voice_health_history = load_voice_health(storage)
    for event in voice_health_history:
        if event['kind'] == 'reply':
            voice_output_status.update(last_reply_engine=event['engine'],
                                       last_reply_error=event['error'],
                                       last_reply_primary_error=event['primary_error'],
                                       last_reply_at=event['at'], last_reply_route=event['route'])
        elif event['kind'] == 'sample':
            if event['engine'] == 'fallback':
                voice_output_status.update(last_fallback_error=event['error'],
                                           last_fallback_route=event['route'])
            else:
                voice_output_status.update(last_preview_error=event['error'],
                                           last_preview_route=event['route'])
        elif event['kind'] == 'tone':
            voice_output_status.update(last_tone_error=event['error'],
                                       last_tone_route=event['route'])
    google_sync_lock = asyncio.Lock()
    google_status: dict[str, Any] = {"last_synced": None, "error": None}
    device_status: dict[str, Any] = {"last_seen": None, "controls": {}}
    portal_request: dict[str, Any] = {"id": None, "expires": 0}
    keyboard_request: dict[str, Any] = {"id": None, "expires": 0, "visible": False}
    network = NetworkRuntime()

    def save_paired_phone(address):
        service.update_settings({"phone_address": address})
        service.phone_disconnected()
        service.state.phone_last_seen_at = None
        service.tick()

    pairing = PairingFlow(save_paired_phone)

    async def sync_google() -> dict[str, Any]:
        async with google_sync_lock:
            if not google.authorized():
                raise ValueError("Connect Google Calendar first")
            settings = service.settings
            departure_ids = settings.departure_calendar_ids if settings.departure_enabled else []
            ids = list(dict.fromkeys(settings.visible_calendar_ids + settings.sleep_calendar_ids + departure_ids + ([settings.todo_calendar_id] if settings.todo_calendar_id else [])))
            if not ids:
                service.replace_events([])
                return {"count": 0}
            now = datetime.now(UTC)
            try:
                fetched = await asyncio.to_thread(google.fetch_events, ids, now - timedelta(days=7), now + timedelta(days=7), settings.timezone)
            except Exception:
                google_status["error"] = "Calendar sync unavailable; showing saved events."
                service.calendar_sync_error = True
                service.publish('calendar.stale')
                raise
            service.calendar_synced_at = now
            service.calendar_sync_error = False
            service.replace_events(fetched)
            google_status.update(last_synced=now.isoformat(), error=None)
            return {"count": len(fetched)}

    async def calendar_worker() -> None:
        while True:
            if google.authorized():
                with suppress(Exception):
                    await sync_google()
            await asyncio.sleep(300)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async def voice_asset_worker():
            nonlocal voice_asset_repair_requested
            # The system image sets LUMA_DATA_DIR. Tests and desktop previews
            # never fetch a 130+ MB runtime or touch the host's data partition.
            await asyncio.sleep(20)
            while True:
                # A power cut during a repair must restore the previous voice
                # before another download or any new voice can be advertised.
                with suppress(Exception):
                    await asyncio.to_thread(recover_interrupted_repair, voice_asset_root)
                repair_now = voice_asset_repair_requested
                voice_asset_repair_requested = False
                if repair_now or not voice_asset_ready(voice_asset_root):
                    try:
                        await asyncio.to_thread(fetch_voice_asset, root=voice_asset_root,
                                                replace_existing=repair_now)
                    except Exception:
                        pass  # Fixed, non-secret status is persisted for the UI.
                try:
                    await asyncio.wait_for(voice_asset_retry.wait(), 900)
                except asyncio.TimeoutError:
                    pass
                voice_asset_retry.clear()

        async def clock_worker():
            while True:
                service.tick()
                await asyncio.sleep(15)

        async def backup_worker():
            while True:
                with suppress(Exception):
                    # Seven bounded slots, atomic replacement, private filesystem permissions.
                    slot = datetime.now(UTC).weekday()
                    await asyncio.to_thread(storage.backup, data_root / "backups" / f"luma-{slot}.db")
                await asyncio.sleep(86400)

        async def timer_worker():
            # /run is boot-local; timesyncd touches this only after a successful sync.
            synchronized = Path('/run/systemd/timesync/synchronized')
            while True:
                try:
                    trusted = synchronized.is_file()
                except OSError:
                    trusted = False
                service.timer_tick(trusted=trusted)
                await asyncio.sleep(1)

        workers = [asyncio.create_task(calendar_worker()), asyncio.create_task(weather.run()), asyncio.create_task(clock_worker()), asyncio.create_task(backup_worker()), asyncio.create_task(bluetooth.run()), asyncio.create_task(bluetooth.scene_presence_worker()), asyncio.create_task(network.run()), asyncio.create_task(timer_worker()), asyncio.create_task(app.state.countdown_runtime.run()), asyncio.create_task(app.state.transit_runtime.run()), asyncio.create_task(app.state.room_runtime.run()), asyncio.create_task(app.state.scene_runtime.run())]
        if (sys.platform == "linux" and os.environ.get("LUMA_DATA_DIR") == "/var/lib/luma"):
            workers.append(asyncio.create_task(voice_asset_worker()))
        try:
            yield
        finally:
            await pairing.close()
            await app.state.scene_runtime.close()
            for worker in workers:
                worker.cancel()
            for worker in workers:
                with suppress(asyncio.CancelledError):
                    await worker
            weather_client.client.close()
            app.state.transit_runtime.close()
            await app.state.room_runtime.close()

    app = FastAPI(title="Luma Smart Screen", version=package_version("luma-smart-screen"), lifespan=lifespan)
    app.state.luma = service
    app.state.security = security
    app.state.google = google
    app.state.weather = weather
    app.state.network = network
    app.state.pairing = pairing

    def authorize(
        request: Request,
        x_luma_token: Annotated[str | None, Header()] = None,
    ) -> None:
        host = request.client.host if request.client else None
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            raise HTTPException(403, "Cross-origin requests are not allowed")
        if _loopback(host) and request.url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            raise HTTPException(403, "Use the local address for local access")
        if not _loopback(host) and not security.verify_lan_token(x_luma_token):
            raise HTTPException(status_code=401, detail="A valid Luma token is required")

    secured = Depends(authorize)

    def local_only(request: Request) -> None:
        if not _loopback(request.client.host if request.client else None):
            raise HTTPException(403, "This operation is only available on Luma")
        authorize(request)

    install_countdown_api(app,service,google,google_sync_lock,local_only)
    install_transit_api(app,service,local_only)
    install_room_api(app,service,local_only)
    install_scene_api(app,service,local_only,bluetooth)
    install_backup_api(app,service,storage,local_only)
    install_update_api(app,local_only)

    @app.get("/api/v1/onboarding", dependencies=[Depends(local_only)])
    def onboarding_status():
        from .onboarding import load_progress
        return JSONResponse({**load_progress(storage), "completed": service.settings.onboarding_completed,
                             "summary": {"weather": service.settings.latitude is not None,
                                         "pin": security.pin_is_configured(),
                                         "google": google.authorized(),
                                         "phone_selected": bool(service.settings.phone_address),
                                         "weather_nudges_enabled": service.settings.weather_nudges_enabled,
                                         "departure_enabled": service.settings.departure_enabled,
                                         "departure_calendars": len(service.settings.departure_calendar_ids),
                                         "night_clock_enabled": service.settings.night_clock_enabled,
                                         "night_brightness": service.settings.night_brightness,
                                         "countdowns": len(service.countdowns.items),
                                         "public_countdowns": sum(item['public'] for item in service.countdowns.items),
                                         "transit_stops": len(service.transit.items),
                                         "public_transit_stops": sum(item['public'] for item in service.transit.items),
                                         "transit_token": bool(service.transit.token()),
                                         "purifier_session": service.room.session is not None,
                                         "purifier_selected": service.room.selected is not None,
                                         "room_recovery": service.room.recovery_error,
                                         "scenes_enabled": sum(row['enabled'] for row in service.scenes.definitions.values()),
                                         "scenes_automatic": sum(row['automatic'] for row in service.scenes.definitions.values()),
                                         "scenes_recovery": service.scenes.recovery_error,
                                         "timer_focus_minutes": service.settings.timer_focus_minutes,
                                         "timer_break_minutes": service.settings.timer_break_minutes,
                                         "voice_enabled": service.settings.voice_enabled}},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/onboarding", dependencies=[Depends(local_only)])
    async def onboarding_update(request: Request):
        import json
        from .onboarding import load_progress, transition
        raw = bytearray()
        try:
            async with asyncio.timeout(3):
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > 1024:
                        raise HTTPException(413, "Setup request too large")
                    raw.extend(chunk)
            payload = json.loads(raw)
            progress = transition(load_progress(storage), payload)
        except (ValueError, TypeError, TimeoutError):
            raise HTTPException(422, "Invalid setup step; refresh and try again") from None
        storage.set_cache("onboarding", "progress", progress)
        if payload["action"] == "finish":
            service.update_settings({"onboarding_completed": True})
        return onboarding_status()

    @app.get("/api/v1/bluetooth/pairing", dependencies=[Depends(local_only)])
    def pairing_status() -> dict:
        return {**pairing.snapshot(), "phone_address": service.settings.phone_address,
                "connection_status": bluetooth.status,
                "last_reconnect_at": bluetooth.last_reconnect_at,
                "reconnect_attempts": bluetooth.reconnect_attempts,
                "last_service_recovery_at": bluetooth.last_service_recovery_at,
                "service_recovery_attempts": bluetooth.service_recovery_attempts}

    @app.post("/api/v1/bluetooth/pairing/start", dependencies=[Depends(local_only)])
    async def pairing_start() -> dict:
        try:
            return pairing.start()
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/bluetooth/pairing/select", dependencies=[Depends(local_only)])
    async def pairing_select(payload: PairingSelection) -> dict:
        try:
            return pairing.select(payload.session, payload.device)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/bluetooth/pairing/confirm", dependencies=[Depends(local_only)])
    async def pairing_confirm(payload: PairingConfirmation) -> dict:
        try:
            return pairing.confirm(payload.session, payload.challenge, payload.accepted)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/bluetooth/pairing/cancel", dependencies=[Depends(local_only)])
    async def pairing_cancel(payload: PairingSessionRequest) -> dict:
        try:
            return await pairing.cancel(payload.session)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.post("/api/v1/bluetooth/forget", dependencies=[Depends(local_only)])
    async def bluetooth_forget(payload: ForgetPhoneRequest) -> dict[str, bool]:
        address = service.settings.phone_address
        if not address:
            raise HTTPException(409, "No iPhone is selected.")
        if not security.pin_is_configured():
            raise HTTPException(409, "Set a Luma PIN before forgetting the paired iPhone.")
        if not security.verify_pin(payload.pin):
            raise HTTPException(401, "Incorrect PIN, or too many attempts. After five failures, wait one minute.")
        try:
            bond_removed = await pairing.forget_phone(address)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(503, "Luma could not remove the iPhone pairing. No settings were cleared.") from None
        service.update_settings({"phone_address": None})
        service.phone_disconnected()
        bluetooth.scene_authorized = None
        bluetooth.status = "Not configured"
        return {"forgotten": True, "bond_removed": bond_removed}

    @app.get("/api/v1/network/status", dependencies=[Depends(local_only)])
    def network_status() -> dict:
        return network.snapshot()

    @app.post("/api/v1/tailscale", dependencies=[Depends(local_only)])
    async def private_connection(request: Request):
        import json
        from fastapi.responses import JSONResponse
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 256:
                raise HTTPException(413, "Private connection request too large")
        try:
            payload = validate_tailscale_request(json.loads(raw))
        except Exception:
            raise HTTPException(422, "Invalid private connection request") from None
        try:
            result = await tailscale_request(payload)
        except ValueError as error:
            raise HTTPException(503, str(error)) from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/pi-connect", dependencies=[Depends(local_only)])
    async def pi_connect_setup(payload: PiConnectRequest):
        try:
            result = await pi_connect_request({"action": payload.action})
        except ValueError as error:
            raise HTTPException(503, str(error)) from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/network", dependencies=[Depends(local_only)])
    async def network_setup(request: Request) -> dict:
        # Parse explicitly so validation never returns the submitted password.
        import json
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                raise HTTPException(413, "Wi-Fi request is too large")
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and str(parsed.get("action", "")).startswith("hotspot-"):
                raise ValueError("Use the PIN-protected hotspot controls")
            payload = validate_request(parsed)
        except Exception:
            raise HTTPException(422, "Invalid Wi-Fi setup request") from None
        try:
            return await network_request(payload)
        except ValueError as error:
            raise HTTPException(503, str(error)) from None

    @app.get("/api/v1/network/hotspot", dependencies=[Depends(local_only)])
    async def hotspot_status():
        from fastapi.responses import JSONResponse
        try:
            result = await network_request({"action": "hotspot-status"})
        except ValueError as error:
            raise HTTPException(503, str(error)) from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/network/hotspot", dependencies=[Depends(local_only)])
    async def hotspot_change(request: Request):
        from fastapi.responses import JSONResponse
        import json
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 2048:
                raise HTTPException(413, "Hotspot request is too large")
        try:
            payload = HotspotRequest.model_validate(json.loads(raw))
        except Exception:
            # Pydantic's default error detail includes the submitted `input`,
            # which could be the Wi-Fi passphrase. Keep secrets out of errors.
            raise HTTPException(422, "Invalid hotspot request; input is not echoed") from None
        if payload.action == "enable" and not payload.stanford_permission_confirmed:
            raise HTTPException(422, "Confirm that Stanford or the local network administrator allows this access point before enabling sharing.")
        if not security.pin_is_configured():
            raise HTTPException(409, "Set a Luma PIN before enabling the Wi-Fi hotspot.")
        if not security.verify_pin(payload.pin):
            raise HTTPException(401, "Incorrect PIN, or too many attempts. After five failures, wait one minute.")
        if payload.action == "enable":
            if payload.same_as_pin:
                if payload.wifi_password is not None:
                    raise HTTPException(422, "Choose either the Luma PIN or a separate Wi-Fi key, not both.")
                if len(payload.pin) != 8:
                    raise HTTPException(422, "WPA2 needs at least eight characters. To use the exact Luma PIN as the Wi-Fi key, set an eight-digit PIN first.")
                wifi_password = payload.pin
            else:
                wifi_password = payload.wifi_password
                if not isinstance(wifi_password, str) or not 16 <= len(wifi_password) <= 63 or not wifi_password.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in wifi_password):
                    raise HTTPException(422, "Use a separate Wi-Fi passphrase of 16–63 ASCII characters, or choose the eight-digit Luma PIN option.")
            request = {"action": "hotspot-start", "password": wifi_password, "same_as_pin": payload.same_as_pin}
        else:
            if payload.wifi_password is not None:
                raise HTTPException(422, "A Wi-Fi passphrase is not accepted when disabling the hotspot.")
            request = {"action": "hotspot-stop"}
        try:
            result = await network_request(request)
        except ValueError as error:
            raise HTTPException(503, str(error)) from None
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/network/portal", dependencies=[Depends(local_only)])
    def open_network_portal() -> dict:
        seen = device_status["last_seen"]
        if not seen or datetime.now(UTC) - datetime.fromisoformat(seen) > timedelta(seconds=15):
            raise HTTPException(503, "The desktop bridge is unavailable; try again when Luma is running on the Pi")
        portal_request.update(id=str(uuid4()), expires=monotonic() + 30)
        return {"requested": True}

    @app.get("/api/v1/network/portal-request", dependencies=[Depends(local_only)])
    def pending_network_portal() -> dict:
        return {"id": portal_request["id"] if monotonic() < portal_request["expires"] else None}

    @app.post("/api/v1/device/report", dependencies=[Depends(local_only)])
    async def device_report(payload: DeviceReport) -> dict[str, bool]:
        allowed = {"power", "brightness", "orientation", "volume", "audio_output", "voice", "keyboard", "timer_chime"}
        if not payload.controls.keys() <= allowed or any(value not in ({'played','silent','unavailable; not replayed'} if key=='timer_chime' else {"ok", "unavailable; retrying"}) for key,value in payload.controls.items()):
            raise HTTPException(422, "Invalid device report")
        device_status.update(last_seen=datetime.now(UTC).isoformat(), controls=payload.controls)
        return {"accepted": True}

    @app.post('/api/v1/display/frame', dependencies=[Depends(local_only)])
    def display_frame(payload: DisplayRevision):
        service.snapshot()
        accepted = service.display_handoff.frame_ready(payload.revision)
        if accepted: service.publish('display.frame')
        return {'accepted': accepted}

    @app.post('/api/v1/device/display-register', dependencies=[Depends(local_only)])
    def display_register(payload: DisplayGeneration):
        if service.display_bridge_generation != payload.generation:
            service.display_bridge_generation = payload.generation
            service.display_handoff.invalidate_bridge()
            service.publish('display.bridge')
        return {'accepted':True}

    @app.post('/api/v1/device/display-claim', dependencies=[Depends(local_only)])
    def display_claim(payload: DisplayGeneration):
        if service.display_bridge_generation != payload.generation:
            raise HTTPException(409,'Register this bridge generation first.')
        service.snapshot()
        return {'job': service.display_handoff.claim() if service.display_state else None}

    @app.post('/api/v1/device/display-confirm', dependencies=[Depends(local_only)])
    def display_confirm(payload: DisplayConfirmation):
        if service.display_bridge_generation != payload.generation:
            raise HTTPException(409,'Bridge generation changed.')
        accepted = service.display_handoff.report(payload.revision,brightness_ok=payload.brightness_ok,power_ok=payload.power_ok)
        if accepted: service.publish('display.confirmed')
        return {'accepted':accepted}

    @app.post("/api/v1/device/keyboard", dependencies=[Depends(local_only)])
    def request_keyboard(payload: KeyboardRequest) -> dict:
        seen = device_status["last_seen"]
        if not seen or datetime.now(UTC) - datetime.fromisoformat(seen) > timedelta(seconds=15):
            raise HTTPException(503, "The desktop keyboard is available only on the running Pi")
        if payload.visible and service.snapshot()["state"]["display_power"] != "on":
            raise HTTPException(409, "Wake the screen before opening the keyboard")
        keyboard_request.update(id=str(uuid4()), expires=monotonic() + 30, visible=payload.visible)
        return {"requested": True}

    @app.get("/api/v1/device/keyboard-request", dependencies=[Depends(local_only)])
    def pending_keyboard() -> dict:
        return {"id": keyboard_request["id"] if monotonic() < keyboard_request["expires"] else None,
                "visible": keyboard_request["visible"]}

    @app.post("/api/v1/voice/phase", dependencies=[Depends(local_only)])
    async def voice_phase(payload: VoicePhase) -> dict[str, bool]:
        if not service.settings.voice_enabled:
            return {"accepted": False}
        voice_agent_status["last_seen"] = monotonic()
        voice_agent_status["phase"] = payload.phase.value
        if payload.phase != AssistantPhase.ERROR:
            voice_agent_status["diagnostic"] = None
        changed = service.state.assistant_phase != payload.phase
        service.state.assistant_phase = payload.phase
        if changed:
            service.publish("voice.phase")
        return {"accepted": True}

    @app.post("/api/v1/voice/diagnostic", dependencies=[Depends(local_only)])
    async def voice_diagnostic(payload: VoiceDiagnostic) -> dict[str, bool]:
        if not service.settings.voice_enabled:
            return {"accepted": False}
        voice_agent_status.update(last_seen=monotonic(), phase="error", diagnostic=payload.code)
        changed = service.state.assistant_phase != AssistantPhase.ERROR
        service.state.assistant_phase = AssistantPhase.ERROR
        if changed:
            service.publish("voice.phase")
        return {"accepted": True}

    @app.post("/api/v1/voice/heartbeat", dependencies=[Depends(local_only)])
    async def voice_heartbeat(payload: VoiceHeartbeat | None = None) -> dict[str, bool]:
        if not service.settings.voice_enabled:
            return {"accepted": False}
        voice_agent_status["last_seen"] = monotonic()
        if payload is not None:
            voice_agent_status["dropped_frames"] = payload.dropped_frames
        return {"accepted": True}

    @app.post("/api/v1/voice/output-report", dependencies=[Depends(local_only)])
    async def voice_output_report(payload: VoiceOutputReport) -> dict[str, bool]:
        if not service.settings.voice_enabled:
            return {"accepted": False}
        event = record_voice_health(voice_health_history, storage, kind='reply',
                                    engine=payload.engine, route=payload.route,
                                    error=payload.error, primary_error=payload.primary_error)
        voice_output_status.update(last_reply_engine=payload.engine,
                                   last_reply_error=payload.error,
                                   last_reply_primary_error=payload.primary_error,
                                   last_reply_at=event['at'],
                                   last_reply_route=payload.route,
                                   last_reply_sink_warning=payload.sink_warning)
        return {"accepted": True}

    def calibration_payload() -> dict[str, Any]:
        result = calibration.status()
        seen = voice_agent_status["last_seen"]
        diagnostic = voice_agent_status["diagnostic"]
        available = (service.settings.voice_enabled and seen > 0
                     and monotonic() - seen <= 15 and diagnostic is None)
        saved_profile = read_profile(storage.get_cache("voice", "audio_profile"))
        # A new check must measure untouched capture first. Reusing an old
        # saved profile during its baseline would taint the A/B comparison;
        # the saved everyday profile is restored when this check ends.
        active_profile = (read_profile(result.get('audio_candidate'))
                          if result['active'] else saved_profile)
        wake_mode = read_wake_mode(storage.get_cache('voice', 'wake_confirmation'))
        return {**result, "audio_profile": active_profile.public(),
                "call_trial": call_trial.status(),
                "wake_confirmation": {'version': 1, 'mode': wake_mode},
                "phrase_adaptations": phrase_adaptations.public(),
                "learned_phrase_count": len(phrase_adaptations.entries),
                "agent_available": available,
                "agent_phase": voice_agent_status["phase"] if available else "unavailable",
                "agent_error": diagnostic,
                "dropped_frames": voice_agent_status["dropped_frames"]}

    @app.get("/api/v1/voice/calibration", dependencies=[Depends(local_only)])
    async def calibration_status() -> dict:
        return calibration_payload()

    @app.post('/api/v1/voice/call-trial/start', dependencies=[Depends(local_only)])
    async def start_voice_call_trial() -> dict:
        if not service.settings.voice_enabled:
            raise HTTPException(409, 'Enable local voice first.')
        if calibration.status()['active']:
            raise HTTPException(409, 'Finish or cancel the guided voice check first.')
        if (voice_agent_status['last_seen'] <= 0 or
                monotonic() - voice_agent_status['last_seen'] > 15 or
                voice_agent_status['diagnostic'] is not None):
            raise HTTPException(409, 'The local voice service must be live before a call test.')
        try:
            return call_trial.start()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get('/api/v1/voice/call-trial', dependencies=[Depends(local_only)])
    async def voice_call_trial_status() -> dict:
        return call_trial.status()

    @app.post('/api/v1/voice/call-trial/stop', dependencies=[Depends(local_only)])
    async def stop_voice_call_trial() -> dict:
        return call_trial.stop()

    @app.post('/api/v1/voice/call-trial/observation', dependencies=[Depends(local_only)])
    async def voice_call_trial_observation(payload: CallTrialObservation) -> dict:
        try:
            return call_trial.record(
                payload.session, partial_wake=payload.partial_wake,
                constrained_wake=payload.constrained_wake,
                constrained_near_start=payload.constrained_near_start,
                free_wake=payload.free_wake,
                free_near_start=payload.free_near_start)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post('/api/v1/voice/wake-confirmation', dependencies=[Depends(local_only)])
    async def set_wake_confirmation(payload: WakeConfirmationChoice) -> dict:
        """Owner-local false-wake filter; never described as voice identity."""
        if payload.mode == 'dual_decoder' and not calibration.status()['strict_wake_ready']:
            raise HTTPException(409, 'Run the local voice check first: Luma needs four independently heard wakes and one no-wake sample before enabling this filter.')
        value = {'version': 1, 'mode': payload.mode}
        storage.set_cache('voice', 'wake_confirmation', value)
        return {'wake_confirmation': value}

    @app.post('/api/v1/voice/calibration/confirm-correction', dependencies=[Depends(local_only)])
    async def confirm_phrase_correction(payload: PhraseCorrectionConfirm) -> dict:
        """A prompt-specific owner confirmation, never an automatic audio guess."""
        try:
            heard_variants, canonical, confirmations = calibration.confirm_correction(payload.session)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        saved = False
        if confirmations >= 2:
            if not phrase_adaptations.add_many(heard_variants, canonical):
                calibration.message = 'That correction conflicts with a supported command or the personal phrase limit; nothing was saved.'
                raise HTTPException(409, calibration.message)
            storage.set_cache('voice', 'phrase_adaptations', phrase_adaptations.public())
            saved = True
        return {**calibration_payload(), 'correction_saved': saved}

    @app.post('/api/v1/voice/adaptations/reset', dependencies=[Depends(local_only)])
    async def reset_phrase_adaptations() -> dict:
        nonlocal phrase_adaptations
        phrase_adaptations = PhraseAdaptations()
        storage.set_cache('voice', 'phrase_adaptations', phrase_adaptations.public())
        return {'learned_phrase_count': 0}

    @app.get("/api/v1/voice/hardware", dependencies=[Depends(local_only)])
    async def mic_hardware_status() -> dict:
        return await asyncio.to_thread(mic_hardware.status)

    @app.post("/api/v1/voice/hardware/gain", dependencies=[Depends(local_only)])
    async def mic_hardware_gain(payload: MicGainRequest) -> dict:
        async with mic_gain_lock:
            try:
                before = await asyncio.to_thread(mic_hardware.status)
                after = await asyncio.to_thread(mic_hardware.save_and_apply, payload.gain)
            except mic_hardware.MicHardwareError as exc:
                raise HTTPException(409, str(exc)) from exc
            if (calibration.status()['active'] and before.get('available') and after.get('available')
                    and before.get('gain') != after.get('gain')):
                calibration.record_gain(int(after['gain']))
            return after

    @app.post("/api/v1/voice/calibration/start", dependencies=[Depends(local_only)])
    async def calibration_start() -> dict:
        if not service.settings.voice_enabled:
            raise HTTPException(409, "Enable local voice first")
        if call_trial.status()['active']:
            raise HTTPException(409, "Finish or stop the call false-wake test first.")
        calibration.start(ambient_seconds=4)
        return calibration_payload()

    @app.post('/api/v1/voice/audio-profile/reset', dependencies=[Depends(local_only)])
    async def reset_voice_audio_profile() -> dict:
        """Owner-local escape hatch if a room or microphone change degrades recognition."""
        profile = AudioProfile().public()
        storage.set_cache('voice', 'audio_profile', profile)
        return {'audio_profile': profile}

    @app.post('/api/v1/voice/calibration/save-audio', dependencies=[Depends(local_only)])
    async def save_calibrated_audio(payload: CalibrationSaveAudio) -> dict:
        """Save clean acoustic tuning even when no phrase passed the word test."""
        result = calibration.status()
        candidate = result.get('audio_candidate')
        if not result['active'] or result['session'] != payload.session or not candidate:
            raise HTTPException(409, 'No active room-audio measurement is ready to save.')
        profile = read_profile(candidate)
        if (profile.quality not in {'quiet', 'clear'}
                or (profile.gain == 1 and not profile.high_pass)):
            raise HTTPException(409, 'The measured audio does not need safe processing.')
        storage.set_cache('voice', 'audio_profile', profile.public())
        calibration.cancel()
        return calibration_payload()

    @app.post("/api/v1/voice/calibration/cancel", dependencies=[Depends(local_only)])
    async def calibration_cancel() -> dict:
        calibration.cancel()
        return calibration_payload()

    @app.post("/api/v1/voice/calibration/level", dependencies=[Depends(local_only)])
    async def calibration_level(payload: CalibrationLevel) -> dict:
        try:
            calibration.report_level(payload.session, payload.rms, payload.peak,
                                     floor_rms=payload.floor_rms,
                                     floor_low_frequency_fraction=payload.floor_low_frequency_fraction)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return calibration_payload()

    @app.post("/api/v1/voice/calibration/sample", dependencies=[Depends(local_only)])
    async def calibration_sample(payload: CalibrationSample) -> dict:
        async with mic_gain_lock:
            try:
                result = calibration.submit(payload.session, payload.text, payload.rms, payload.peak,
                                            free_text=payload.free_text,
                                            raw_free_text=payload.raw_free_text,
                                            raw_compared=payload.raw_compared,
                                            raw_constrained_wake=payload.raw_constrained_wake,
                                            selected_text=payload.selected_text,
                                            selection=payload.selection, dc=payload.dc,
                                            clipped_fraction=payload.clipped_fraction)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            step = (calibration.gain_step(payload.rms, payload.peak, payload.clipped_fraction)
                    if result["active"] and not result["ambient_remaining"]
                    and result["attempts"] > 0 else 0)
            if step:
                hardware = await asyncio.to_thread(mic_hardware.status)
                if (hardware["available"] and payload.session == calibration.session
                        and calibration.status()["active"]):
                    current = int(hardware["gain"])
                    adjusted = min(63, max(0, current + step))
                    if adjusted != current:
                        try:
                            await asyncio.to_thread(mic_hardware.save_and_apply, adjusted)
                        except mic_hardware.MicHardwareError:
                            pass  # A failed mixer change never fakes a passed phrase.
                        else:
                            calibration.record_gain(adjusted)
            if result["passed"]:
                storage.set_cache("voice", "calibration", {"checked_at": datetime.now(UTC).isoformat(), "results": result["results"]})
                storage.set_cache("voice", "audio_profile", result["audio_profile"] or AudioProfile().public())
            return calibration_payload()

    @app.get('/api/v1/voice/library', dependencies=[Depends(local_only)])
    async def voice_library():
        return {'wake_phrase': 'Hey Luma', 'groups': LIBRARY, 'local_only': True,
                'phrase_model': 'offline-neural-v1'}

    @app.get('/api/v1/voice/asset', dependencies=[Depends(local_only)])
    async def offline_voice_asset() -> dict:
        return {**voice_status(voice_asset_root), **voice_output_status,
                'health_history': list(voice_health_history)}

    @app.post('/api/v1/voice/asset/retry', dependencies=[Depends(local_only)])
    async def retry_offline_voice_asset() -> dict:
        if sys.platform != 'linux' or os.environ.get('LUMA_DATA_DIR') != '/var/lib/luma':
            raise HTTPException(409, 'Offline voice installation runs on the Raspberry Pi only.')
        voice_asset_retry.set()
        return voice_status(voice_asset_root)

    @app.post('/api/v1/voice/asset/repair', dependencies=[Depends(local_only)])
    async def repair_offline_voice_asset() -> dict:
        nonlocal voice_asset_repair_requested
        if sys.platform != 'linux' or os.environ.get('LUMA_DATA_DIR') != '/var/lib/luma':
            raise HTTPException(409, 'Offline voice repair runs on the Raspberry Pi only.')
        if not voice_asset_ready(voice_asset_root):
            raise HTTPException(409, 'The offline voice is not installed; use the signed download instead.')
        if voice_asset_repair_requested or voice_status(voice_asset_root)['phase'] in {
                'checking', 'downloading', 'verifying', 'installing'}:
            raise HTTPException(409, 'An offline voice installation is already in progress.')
        voice_asset_repair_requested = True
        voice_asset_retry.set()
        return {'started': True, 'message': 'Signed offline voice repair queued. The previous voice stays available until verification.'}

    @app.post('/api/v1/voice/asset/preview', dependencies=[Depends(local_only)])
    async def preview_offline_voice_asset(payload: VoicePreviewRequest | None = None) -> dict:
        variant = payload.variant if payload else 'piper'
        if variant == 'piper' and not voice_asset_ready(voice_asset_root):
            raise HTTPException(409, 'Install the offline voice before previewing it.')
        if voice_preview_lock.locked():
            raise HTTPException(409, 'Voice preview is already playing.')
        async with voice_preview_lock:
            try:
                # Reuse the live voice agent's warm Piper model when present.
                # A second simultaneous model on a Pi 4 can exhaust memory;
                # direct synthesis is reserved for when the agent is inactive.
                agent_active = (service.settings.voice_enabled and voice_agent_status['last_seen'] > 0 and
                                monotonic() - voice_agent_status['last_seen'] <= 15 and
                                voice_agent_status['diagnostic'] is None)
                if agent_active:
                    job = voice_preview_job
                    job.update(id=uuid4().hex, event=asyncio.Event(), result=None,
                               variant=variant)
                    try:
                        await asyncio.wait_for(job['event'].wait(), timeout=120)
                        result = job['result']
                        if not isinstance(result, VoicePreviewResult) or result.error:
                            raise VoicePlaybackError(result.error if result else
                                                     ('fallback_playback_failed' if variant == 'fallback' else 'piper_synthesis_failed'))
                        route = result.route
                        if route is None:
                            raise VoicePlaybackError('speaker_playback_failed')
                        sink_warning = result.sink_warning
                    except asyncio.TimeoutError as exc:
                        raise VoicePlaybackError('fallback_playback_failed' if variant == 'fallback'
                                                 else 'piper_synthesis_failed') from exc
                    finally:
                        voice_preview_job.clear()
                else:
                    preview = play_fallback_preview if variant == 'fallback' else play_voice_preview
                    route = await asyncio.to_thread(preview, voice_asset_root)
                    sink_warning = await asyncio.to_thread(speaker_route_warning, route)
            except VoicePlaybackError as exc:
                status_prefix = 'last_fallback' if variant == 'fallback' else 'last_preview'
                voice_output_status[f'{status_prefix}_error'] = exc.code
                voice_output_status[f'{status_prefix}_route'] = None
                voice_output_status[f'{status_prefix}_sink_warning'] = None
                record_voice_health(voice_health_history, storage, kind='sample', engine=variant,
                                    error=exc.code)
                messages = {
                    "audio_session_unavailable": "The Pi audio session is not ready. Try again after the desktop finishes starting.",
                    "speaker_route_unavailable": "No safe local speaker was found. Select HDMI or HAT in Device setup.",
                    "speaker_playback_failed": "The selected speaker rejected the sample. Check its output and volume.",
                    "piper_start_failed": "The offline voice worker could not start.",
                    "piper_start_timeout": "The offline voice took too long to start. Try again after the Pi settles.",
                    "piper_runtime_missing": "The installed neural voice runtime is incomplete. Try Repair installed voice.",
                    "piper_model_load_failed": "The installed neural voice model could not load. Try Repair installed voice.",
                    "piper_memory_pressure": "The neural voice stopped under possible memory pressure. Close other apps and retry.",
                    "piper_synthesis_failed": "The offline voice worker could not synthesize the sample.",
                    "piper_audio_invalid": "The offline voice produced an invalid audio format.",
                    "synthesis_unavailable": "The local voice could not synthesize the sample.",
                    "fallback_playback_failed": "The original local voice could not reach the selected speaker.",
                }
                raise HTTPException(409, messages.get(exc.code, 'Offline voice preview could not play.')) from exc
            except Exception as exc:
                code = 'fallback_playback_failed' if variant == 'fallback' else 'synthesis_unavailable'
                status_prefix = 'last_fallback' if variant == 'fallback' else 'last_preview'
                voice_output_status[f'{status_prefix}_error'] = code
                voice_output_status[f'{status_prefix}_route'] = None
                voice_output_status[f'{status_prefix}_sink_warning'] = None
                record_voice_health(voice_health_history, storage, kind='sample', engine=variant,
                                    error=code)
                raise HTTPException(409, 'The local voice could not play the sample.') from exc
            status_prefix = 'last_fallback' if variant == 'fallback' else 'last_preview'
            voice_output_status[f'{status_prefix}_error'] = None
            voice_output_status[f'{status_prefix}_route'] = route
            voice_output_status[f'{status_prefix}_sink_warning'] = sink_warning
            record_voice_health(voice_health_history, storage, kind='sample', engine=variant,
                                route=route)
        return {'played': True, 'route': route}

    @app.get('/api/v1/voice/asset/preview/pending', dependencies=[Depends(local_only)])
    async def pending_voice_preview() -> dict[str, str | None]:
        # The agent only receives a nonce; the sample text is fixed locally.
        return {'request_id': voice_preview_job.get('id'),
                'variant': voice_preview_job.get('variant')}

    @app.post('/api/v1/voice/asset/preview/result', dependencies=[Depends(local_only)])
    async def complete_voice_preview(payload: VoicePreviewResult) -> dict[str, bool]:
        job = voice_preview_job
        if job.get('id') != payload.request_id or job.get('result') is not None:
            return {'accepted': False}
        job['result'] = payload
        job['event'].set()
        return {'accepted': True}

    @app.post('/api/v1/voice/asset/tone', dependencies=[Depends(local_only)])
    async def test_voice_speaker_route() -> dict:
        """Test the same live audio path used by spoken replies, without Piper."""
        if voice_preview_lock.locked():
            raise HTTPException(409, 'Another speaker test is already running.')
        async with voice_preview_lock:
            try:
                agent_active = (service.settings.voice_enabled and voice_agent_status['last_seen'] > 0 and
                                monotonic() - voice_agent_status['last_seen'] <= 15 and
                                voice_agent_status['diagnostic'] is None)
                if agent_active:
                    job = voice_tone_job
                    job.update(id=uuid4().hex, event=asyncio.Event(), result=None)
                    try:
                        await asyncio.wait_for(job['event'].wait(), timeout=30)
                        result = job['result']
                        if not isinstance(result, VoicePreviewResult) or result.error:
                            raise VoicePlaybackError(result.error if result else 'speaker_playback_failed')
                        if result.route is None:
                            raise VoicePlaybackError('speaker_playback_failed')
                        route = result.route
                        sink_warning = result.sink_warning
                    except asyncio.TimeoutError as exc:
                        raise VoicePlaybackError('speaker_playback_failed') from exc
                    finally:
                        voice_tone_job.clear()
                else:
                    route = await asyncio.to_thread(play_test_tone)
                    sink_warning = await asyncio.to_thread(speaker_route_warning, route)
            except VoicePlaybackError as exc:
                voice_output_status["last_tone_error"] = exc.code
                voice_output_status["last_tone_route"] = None
                voice_output_status["last_tone_sink_warning"] = None
                record_voice_health(voice_health_history, storage, kind='tone', error=exc.code)
                message = ('The Pi audio session is not ready.' if exc.code == 'audio_session_unavailable'
                           else 'No safe local speaker was found; select HDMI or HAT in Device setup.'
                           if exc.code == 'speaker_route_unavailable'
                           else 'The selected speaker could not play the test tone.')
                raise HTTPException(409, message) from exc
            except Exception as exc:
                voice_output_status["last_tone_error"] = "speaker_route_unavailable"
                voice_output_status["last_tone_route"] = None
                voice_output_status["last_tone_sink_warning"] = None
                record_voice_health(voice_health_history, storage, kind='tone',
                                    error='speaker_route_unavailable')
                raise HTTPException(409, 'The Luma speaker test could not run.') from exc
            voice_output_status["last_tone_error"] = None
            voice_output_status["last_tone_route"] = route
            voice_output_status["last_tone_sink_warning"] = sink_warning
            record_voice_health(voice_health_history, storage, kind='tone', route=route)
        return {'sent': True, 'route': route}

    @app.get('/api/v1/voice/asset/tone/pending', dependencies=[Depends(local_only)])
    async def pending_voice_tone() -> dict[str, str | None]:
        return {'request_id': voice_tone_job.get('id')}

    @app.post('/api/v1/voice/asset/tone/result', dependencies=[Depends(local_only)])
    async def complete_voice_tone(payload: VoicePreviewResult) -> dict[str, bool]:
        job = voice_tone_job
        if job.get('id') != payload.request_id or job.get('result') is not None:
            return {'accepted': False}
        job['result'] = payload
        job['event'].set()
        return {'accepted': True}

    @app.post('/api/v1/voice/phrase-preview', dependencies=[Depends(local_only)])
    async def voice_phrase_preview(payload: VoicePhrasePreview) -> dict[str, Any]:
        """Explain local intent matching without running a command or reading private data."""
        learned = phrase_adaptations.resolve(payload.text)
        parsed = parse_local_command(learned or payload.text)
        model = predict_voice_intent(payload.text)
        return {
            'understood': parsed is not None,
            'command': parsed.name.value if parsed else None,
            'intent': str(parsed.value) if parsed and parsed.name == CommandName.LOCAL_QUERY else None,
            'personal_correction': learned is not None,
            'model_suggestion': model[0] if model else None,
            'model_confidence': round(model[1], 2) if model else None,
            'executed': False,
        }

    @app.post("/api/v1/voice/command", dependencies=[Depends(local_only)])
    async def voice_command(payload: VoiceCommand) -> dict[str, Any]:
        if not service.settings.voice_enabled:
            return {"accepted": False, "message": "Local voice is turned off."}
        if calibration.status()["active"]:
            return {"accepted": False, "message": "Voice check in progress; no commands were applied."}
        if call_trial.status()['active']:
            return {"accepted": False, "message": "Call false-wake test in progress; no commands were applied."}
        parsed = parse_local_command(payload.text)
        if parsed is None:
            return {"accepted": False, "message": "That phrase is not in my local library. Say, Hey Luma, what can I say?"}
        if parsed.name in (CommandName.RUN_SCENE, CommandName.CANCEL_SCENE):
            runtime = app.state.scene_runtime
            # Scenes are private device actions: voice never bypasses the same
            # nearby-phone/PIN owner gate used by the local touch controls.
            if not runtime.owner_allowed():
                return {"accepted": False, "message": "Unlock Luma with your PIN or connect your paired phone before controlling room devices."}
            if parsed.name == CommandName.CANCEL_SCENE:
                if runtime.executor.task is None and (runtime.job is None or runtime.job.done()):
                    return {"accepted": False, "message": "No room scene is running."}
                await runtime.cancel()
                return {"accepted": True, "message": "I stopped the scene. Check Room devices to see which actions were already sent."}
            key = parsed.value
            definition = runtime.store.definitions[key]
            if not definition['enabled'] or not definition['actions']:
                return {"accepted": False, "message": f"The {key} scene is not set up yet. Configure and enable it in Room devices first."}
            if not runtime.trusted():
                return {"accepted": False, "message": "My clock is still syncing. I cannot safely run a room scene yet."}
            current = runtime.configuration()['definitions'][key]
            if current['needs_review']:
                return {"accepted": False, "message": f"The {key} scene needs review in Room devices before it can run."}
            if runtime.executor.task is not None or runtime.job is not None and not runtime.job.done():
                return {"accepted": False, "message": "A room scene is already running. Nothing was queued."}
            task = asyncio.create_task(runtime.manual(key, runtime.store.revision))
            runtime.job = task
            task.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)
            return {"accepted": True, "message": f"I started the {key} scene. Check Room devices for each action’s result; uncertain actions are never retried."}
        if parsed.name == CommandName.LOCAL_QUERY:
            voice_view = service.voice_snapshot(authorized=google.authorized())
            voice_view['voice_status'] = {'network': network.snapshot(), 'bluetooth': bluetooth.status}
            return {'accepted': True, 'message': answer_query(parsed.value, voice_view)}
        result = service.execute(parsed)
        reply = morning_briefing(service.snapshot(briefing=True)) if parsed.name == CommandName.GOOD_MORNING and result.data.get('briefing') else result.message
        return {"accepted": result.accepted, "message": reply}

    @app.get("/api/v1/diagnostics", dependencies=[secured])
    async def diagnostics() -> dict[str, Any]:
        return {
            "database": "ok" if storage.integrity_check() else "error",
            "free_storage_mb": shutil.disk_usage(data_root).free // (1024 * 1024),
            "calendar": {"authorized": google.authorized(), **google_status},
            "weather": {"configured": service.settings.latitude is not None, **weather.status},
            "privacy": service.snapshot()["state"]["privacy"],
            "phone_connected": service.state.phone_connected,
            "bluetooth": bluetooth.status,
            "hardware": {**device_status, "qualified": False},
        }

    @app.get("/api/v1/weather/status", dependencies=[secured])
    async def weather_status() -> dict[str, Any]:
        return {"configured": service.settings.latitude is not None, **weather.status}

    @app.post("/api/v1/weather/sync", dependencies=[secured])
    async def weather_sync() -> dict[str, Any]:
        try:
            return await weather.refresh()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, "Weather unavailable. Saved forecast retained.") from exc

    @app.get("/api/v1/google/status", dependencies=[secured])
    def calendar_status() -> dict[str, Any]:
        return {"configured": google.configured(), "authorized": google.authorized(), "task_updates": google.task_write_authorized(), **google_status}

    @app.post("/api/v1/google/authorize-tasks", dependencies=[Depends(local_only)])
    def calendar_authorize_tasks() -> dict[str, str]:
        try:
            return {"url": google.begin_authorization(task_updates=True)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/google/event-colors", dependencies=[Depends(local_only)])
    def calendar_event_colors():
        try:
            return google.event_colors()
        except Exception:
            raise HTTPException(502, "Could not load Google event colors. Your saved choice is unchanged.") from None

    @app.post("/api/v1/google/config", dependencies=[secured])
    def calendar_config(payload: dict[str, Any]) -> dict[str, bool]:
        try:
            google.set_client_config(payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"configured": True}

    @app.post("/api/v1/google/authorize", dependencies=[secured])
    def calendar_authorize() -> dict[str, str]:
        try:
            return {"url": google.begin_authorization()}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/google/callback", dependencies=[Depends(local_only)])
    def calendar_callback(request: Request, state: str = "") -> RedirectResponse:
        try:
            google.finish_authorization(str(request.url), state)
            service.todo_write_authorized = google.task_write_authorized()
        except Exception:
            # A kiosk has no browser Back button. Return to the themed setup
            # instead of stranding a cancelled/expired sign-in on raw JSON.
            return RedirectResponse("/?setup=google&google_error=1", status_code=303,
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        return RedirectResponse("/?setup=google", status_code=303,
                                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})

    @app.get("/api/v1/google/calendars", dependencies=[secured])
    def calendars() -> list[dict[str, Any]]:
        try:
            return google.list_calendars()
        except Exception as exc:
            raise HTTPException(502, "Could not load Google calendars. Check the connection and sign-in.") from exc

    @app.post("/api/v1/google/sync", dependencies=[secured])
    async def calendar_sync() -> dict[str, Any]:
        try:
            return await sync_google()
        except Exception as exc:
            raise HTTPException(502, "Could not sync Google Calendar. Saved events are retained.") from exc

    @app.post('/api/v1/todos/complete', dependencies=[Depends(local_only)])
    async def complete_task(payload: TaskCompletionRequest):
        async with google_sync_lock:
            from .calendar_logic import todo_events
            now = datetime.now(UTC)
            if service.snapshot(now)['privacy_redacted']:
                raise HTTPException(403, 'Unlock private information before changing a task.')
            settings = service.settings
            if payload.calendar_id != settings.todo_calendar_id or not settings.todo_completed_color_id:
                raise HTTPException(422, 'Choose your to-do calendar and completed color in Google setup first.')
            current = next((event for event in todo_events(service.events, todo_calendar_id=settings.todo_calendar_id, now=now)
                            if event.id == payload.event_id), None)
            if current is None or current.etag != payload.etag:
                raise HTTPException(409, 'This task changed. Refresh your calendar before trying again.')
            desired = settings.todo_completed_color_id if payload.completed else None
            try:
                updated = await asyncio.to_thread(google.recolor_task, calendar_id=settings.todo_calendar_id,
                                                  event_id=current.id, expected_etag=payload.etag, color_id=desired,
                                                  timezone=settings.timezone, now=now)
            except PermissionError:
                raise HTTPException(403, 'Enable task updates in Google setup, and check calendar write access.') from None
            except TaskConflict as exc:
                raise HTTPException(409, str(exc)) from None
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            except Exception:
                # A timeout might happen AFTER Google committed. Do not queue or
                # blindly replay it, and never show a local-only completion.
                raise HTTPException(502, 'Update not confirmed. Refresh Google Calendar before retrying.') from None
            updated.calendar_name, updated.calendar_color = current.calendar_name, current.calendar_color
            updated.calendar_writable = current.calendar_writable
            service.replace_events([updated if event.calendar_id == updated.calendar_id and event.id == updated.id else event
                                    for event in service.events])
            return service.snapshot()

    @app.post('/api/v1/departures/action', dependencies=[Depends(local_only)])
    async def departure_action(payload: DepartureRequest):
        async with google_sync_lock:
            now=datetime.now(UTC)
            current = service.snapshot(now)
            if current['privacy_redacted']:
                raise HTTPException(403,'Unlock private information before changing a reminder.')
            if not current['departure'] or current['departure']['key'] != payload.key:
                raise HTTPException(409,'This reminder changed or needs a fresh calendar sync.')
            try:
                service.departures.act(**payload.model_dump(),events=service.events,settings=service.settings,now=now)
            except ValueError as exc:
                raise HTTPException(409,str(exc)) from None
            service.publish('departure.updated')
            return service.snapshot()

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "database": "ok" if storage.integrity_check() else "error",
            "version": app.version,
        }

    @app.get("/api/v1/state", dependencies=[secured])
    async def state() -> dict[str, Any]:
        return service.snapshot()

    @app.get("/api/v1/settings", dependencies=[secured])
    async def get_settings() -> dict[str, Any]:
        return service.snapshot()["settings"]

    @app.patch("/api/v1/settings", dependencies=[secured])
    async def patch_settings(patch: SettingsPatch, request: Request) -> dict[str, Any]:
        updates = patch.model_dump(exclude_unset=True)
        if {"phone_address", "voice_enabled", "timer_focus_minutes", "timer_break_minutes",
            "weather_nudges_enabled", "weather_rain_percent", "weather_gust_mph", "weather_hot_f", "weather_cold_f", "night_clock_enabled", "night_brightness",
            "todo_calendar_id", "todo_completed_color_id", "sleep_calendar_ids", "sleep_event_title", "departure_calendar_ids", "departure_enabled",
            "departure_include_virtual", "departure_prep_minutes", "departure_travel_minutes"} & updates.keys():
            local_only(request)
        if any(value is None for key, value in updates.items() if key not in {"latitude", "longitude", "todo_calendar_id", "todo_completed_color_id", "phone_address"}):
            raise HTTPException(422, "This setting cannot be null")
        old_location = weather.location()
        old_phone = service.settings.phone_address
        try:
            if {'todo_calendar_id', 'todo_completed_color_id', 'timezone', 'visible_calendar_ids', 'sleep_calendar_ids', 'sleep_event_title',
                'departure_calendar_ids','departure_enabled','departure_include_virtual','departure_prep_minutes','departure_travel_minutes'} & updates.keys():
                async with google_sync_lock:
                    service.update_settings(updates)
            else:
                service.update_settings(updates)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, str(exc)) from exc
        if updates.get("voice_enabled") is False:
            calibration.cancel()
            voice_agent_status.update(last_seen=0.0, phase="idle", diagnostic=None,
                                      dropped_frames=0)
            service.state.assistant_phase = AssistantPhase.IDLE
            service.publish("voice.disabled")
        if weather.location() != old_location:
            weather.location_changed()
        if service.settings.phone_address != old_phone:
            service.phone_disconnected()
            service.state.phone_last_seen_at = None
            service.tick()
        return service.snapshot()["settings"]

    @app.post("/api/v1/shortcut-command", dependencies=[Depends(local_only)])
    async def shortcut_command(request: Request):
        # A proxy arrives locally, but is NEVER a local-user authentication.
        if not security.verify_lan_token(command_token(request)):
            raise HTTPException(401, "Command authentication required.")
        parsed = await read_command(request)
        if parsed.name == CommandName.RUN_REMOTE_SCENE:
            runtime = app.state.scene_runtime
            key = parsed.value
            definition = runtime.store.definitions[key]
            if not runtime.trusted() or not runtime.remote_policy.effective(key, definition):
                return {"accepted": False, "message": "That exact room scene is not allowlisted for remote control."}
            current = runtime.configuration()['definitions'][key]
            if current['needs_review']:
                return {"accepted": False, "message": "Room devices need local review before this scene can run remotely."}
            if runtime.executor.task is not None or runtime.job is not None and not runtime.job.done():
                return {"accepted": False, "message": "A room scene is already running. Nothing was queued."}
            task = asyncio.create_task(runtime.remote(key))
            runtime.job = task
            task.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)
            return JSONResponse({"accepted": True, "message": "The allowlisted room scene started. Check Luma for each action’s result."},
                                headers={"Cache-Control": "no-store"})
        service.tick()  # Expire old presence/PIN leases before any briefing.
        result = service.execute(parsed)
        message = morning_briefing(service.snapshot(briefing=True)) if parsed.name == CommandName.GOOD_MORNING and result.data.get('briefing') else result.message
        return JSONResponse({"accepted": result.accepted, "message": message[:1600]},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/commands", dependencies=[secured])
    async def command(payload: CommandRequest, request: Request) -> dict[str, Any]:
        if payload.name.value in TIMER_COMMANDS:
            local_only(request)  # Remote timers use the smaller Shortcut protocol.
        try:
            result = service.execute(Command(payload.name, payload.value, payload.source))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "result": {
                "accepted": result.accepted,
                "message": result.message,
                "state_changed": result.state_changed,
                "data": result.data,
            },
            "snapshot": service.snapshot(),
        }

    @app.post('/api/v1/device/timer-chime', dependencies=[Depends(local_only)])
    async def timer_chime():
        service.timer_tick()
        return JSONResponse({'play': service.timer.claim_chime(muted=service.timer_muted())},
                            headers={'Cache-Control':'no-store'})

    @app.get("/api/v1/security/status", dependencies=[secured])
    def security_status() -> dict[str, bool]:
        return {"pin_configured": security.pin_is_configured()}

    @app.get("/api/v1/security/lan-token", dependencies=[Depends(local_only)])
    def lan_token(request: Request):
        from fastapi.responses import JSONResponse
        host = request.client.host if request.client else None
        if not _loopback(host):
            raise HTTPException(status_code=403, detail="The LAN token is only shown on Luma")
        return JSONResponse({"token": security.get_or_create_lan_token()}, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/security/lan-token/rotate", dependencies=[Depends(local_only)])
    def rotate_lan_token():
        from fastapi.responses import JSONResponse
        return JSONResponse({"token": security.rotate_lan_token()}, headers={"Cache-Control": "no-store"})

    @app.post("/api/v1/security/pin", dependencies=[Depends(local_only)])
    def set_pin(payload: PinRequest) -> dict[str, bool]:
        security.set_pin(payload.pin)
        return {"configured": True}

    @app.post("/api/v1/security/unlock", dependencies=[Depends(local_only)])
    async def unlock(payload: PinRequest) -> dict[str, Any]:
        if not security.verify_pin(payload.pin):
            raise HTTPException(status_code=401, detail="Incorrect PIN, or too many attempts. After five failures, wait one minute.")
        service.unlock_with_pin()
        return service.snapshot()

    @app.websocket("/api/v1/events")
    async def events(websocket: WebSocket) -> None:
        host = websocket.client.host if websocket.client else None
        token = websocket.query_params.get("token")
        origin = websocket.headers.get("origin")
        if origin and urlsplit(origin).netloc != websocket.headers.get("host"):
            await websocket.close(code=4403)
            return
        if _loopback(host) and websocket.url.hostname not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            await websocket.close(code=4403)
            return
        if not _loopback(host) and not security.verify_lan_token(token):
            await websocket.close(code=4401)
            return
        await websocket.accept()
        queue = service.subscribe()
        receive = asyncio.create_task(websocket.receive())
        next_message = asyncio.create_task(queue.get())
        try:
            await websocket.send_json({"type": "snapshot", "data": service.snapshot()})
            while True:
                ready, _ = await asyncio.wait({receive, next_message}, return_when=asyncio.FIRST_COMPLETED)
                if receive in ready:
                    incoming = receive.result()
                    if incoming['type'] != 'websocket.disconnect':
                        # This is a receive-only event stream, never a command API.
                        await websocket.close(code=1008)
                    break
                await websocket.send_json({**next_message.result(), "data": service.snapshot()})
                next_message = asyncio.create_task(queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            service.unsubscribe(queue)
            receive.cancel()
            next_message.cancel()
            await asyncio.gather(receive, next_message, return_exceptions=True)

    frontend_value = frontend_dir or os.environ.get("LUMA_FRONTEND_DIR")
    frontend_root = Path(frontend_value).resolve() if frontend_value else None
    if frontend_root and frontend_root.is_dir():
        assets = frontend_root / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str) -> FileResponse:
            candidate = frontend_root / path
            if candidate.is_file() and frontend_root in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(frontend_root / "index.html")

    return app


def main() -> None:
    frontend = os.environ.get("LUMA_FRONTEND_DIR")
    # Campus/guest Wi-Fi is not a trusted LAN. Remote access needs a separately
    # configured encrypted path; the kiosk and device bridge use loopback.
    # Callback URLs contain short-lived OAuth codes/state. Do not log request
    # URLs or trust proxy-supplied client addresses on this local control plane.
    uvicorn.run(create_app(frontend_dir=frontend), host=os.environ.get("LUMA_LISTEN_HOST", "127.0.0.1"),
                port=8742, access_log=False, proxy_headers=False)
