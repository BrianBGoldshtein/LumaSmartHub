from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import math
import re


class Theme(StrEnum):
    LUMA_GLASS = "luma-glass"
    HEARTH = "hearth"
    NEON_GRID = "neon-grid"


class Orientation(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT_CLOCKWISE = "portrait-clockwise"
    PORTRAIT_COUNTERCLOCKWISE = "portrait-counterclockwise"


class Page(StrEnum):
    HOME = "home"
    AGENDA = "agenda"
    WEATHER = "weather"
    TODOS = "todos"
    AMBIENT = "ambient"
    COUNTDOWNS = "countdowns"
    TRANSIT = "transit"


class PrivacyLevel(StrEnum):
    PRIVATE = "private"
    FULL = "full"


class DisplayPower(StrEnum):
    ON = "on"
    OFF = "off"


class AssistantPhase(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class CommandName(StrEnum):
    SHOW_BRIGHTNESS = "show_brightness"
    SET_BRIGHTNESS = "set_brightness"
    SHOW_VOLUME = "show_volume"
    SET_VOLUME = "set_volume"
    GOOD_NIGHT = "good_night"
    GOOD_MORNING = "good_morning"
    SCREEN_OFF = "screen_off"
    SET_THEME = "set_theme"
    SET_ORIENTATION = "set_orientation"
    SHOW_PAGE = "show_page"
    NEXT_PAGE = "next_page"
    PREVIOUS_PAGE = "previous_page"
    PAUSE_CYCLE = "pause_cycle"
    RESUME_CYCLE = "resume_cycle"
    PRIVACY_NOW = "privacy_now"
    WAKE = "wake"
    ASK = "ask"
    LOCAL_QUERY = "local_query"
    START_TIMER = "start_timer"
    PAUSE_TIMER = "pause_timer"
    RESUME_TIMER = "resume_timer"
    CANCEL_TIMER = "cancel_timer"
    SHOW_TIMER = "show_timer"
    DISMISS_TIMER = "dismiss_timer"
    RUN_SCENE = "run_scene"
    CANCEL_SCENE = "cancel_scene"
    RUN_REMOTE_SCENE = "run_remote_scene"


@dataclass(slots=True)
class CycleTiming:
    page: Page
    seconds: int


DEFAULT_CYCLE: tuple[CycleTiming, ...] = (
    CycleTiming(Page.HOME, 45),
    CycleTiming(Page.AGENDA, 30),
    CycleTiming(Page.WEATHER, 25),
    CycleTiming(Page.TODOS, 25),
    CycleTiming(Page.AMBIENT, 14),
)


@dataclass(slots=True)
class Settings:
    schema_version: int = 1
    onboarding_completed: bool = False
    device_name: str = "Luma"
    theme: Theme = Theme.LUMA_GLASS
    orientation: Orientation = Orientation.LANDSCAPE
    brightness: int = 70
    night_clock_enabled: bool = True
    night_brightness: int = 5
    volume: int = 55
    timezone: str = "America/Los_Angeles"
    latitude: float | None = None
    longitude: float | None = None
    weather_location_label: str = ""
    visible_calendar_ids: list[str] = field(default_factory=list)
    todo_calendar_id: str | None = None
    todo_completed_color_id: str | None = None
    departure_calendar_ids: list[str] = field(default_factory=list)
    departure_enabled: bool = False
    departure_prep_minutes: int = 5
    departure_travel_minutes: int = 10
    departure_include_virtual: bool = False
    sleep_calendar_ids: list[str] = field(default_factory=list)
    sleep_event_title: str = "Sleep"
    notification_app_allowlist: list[str] = field(
        default_factory=lambda: [
            "com.apple.mobilephone",
            "net.whatsapp.WhatsApp",
            "com.hammerandchisel.discord",
        ]
    )
    audio_output: str = "auto"
    voice_enabled: bool = True
    timer_focus_minutes: int = 25
    timer_break_minutes: int = 5
    weather_nudges_enabled: bool = False
    weather_rain_percent: int = 50
    weather_gust_mph: int = 25
    weather_hot_f: int = 90
    weather_cold_f: int = 45
    phone_address: str | None = None
    phone_disconnect_grace_seconds: int = 45
    pin_unlock_minutes: int = 15
    temporary_night_wake_minutes: int = 5
    cloud_provider: str = "disabled"
    cloud_share_private_context: bool = False
    cycle: list[dict[str, Any]] = field(
        default_factory=lambda: [asdict(item) for item in DEFAULT_CYCLE]
    )

    def validate(self) -> None:
        if (not isinstance(self.sleep_calendar_ids, list) or len(self.sleep_calendar_ids) > 50
                or any(not isinstance(value, str) or not 1 <= len(value) <= 1024 for value in self.sleep_calendar_ids)):
            raise ValueError("Choose at most 50 sleep calendars")
        if (not isinstance(self.sleep_event_title, str) or not 1 <= len(self.sleep_event_title.strip()) <= 100
                or any(ord(char) < 32 for char in self.sleep_event_title)):
            raise ValueError("Sleep event title must contain 1 to 100 printable characters")
        if type(self.night_clock_enabled) is not bool or type(self.night_brightness) is not int or not 0 <= self.night_brightness <= 100:
            raise ValueError('Night brightness must be a whole percentage and night clock a boolean')
        if type(self.departure_enabled) is not bool or type(self.departure_include_virtual) is not bool:
            raise ValueError("Departure preferences must be enabled or disabled")
        if (not isinstance(self.departure_calendar_ids, list) or len(self.departure_calendar_ids) > 50
                or any(not isinstance(value, str) or not 1 <= len(value) <= 1024 for value in self.departure_calendar_ids)):
            raise ValueError("Choose at most 50 departure calendars")
        for value in (self.departure_prep_minutes, self.departure_travel_minutes):
            if type(value) is not int or not 0 <= value <= 240:
                raise ValueError("Preparation and travel must be whole minutes from 0 to 240")
        if self.todo_completed_color_id is not None and (not isinstance(self.todo_completed_color_id, str) or not re.fullmatch(r"[1-9][0-9]{0,2}", self.todo_completed_color_id)):
            raise ValueError("Choose a Google event color for completed tasks")
        if type(self.weather_nudges_enabled) is not bool:
            raise ValueError("Weather hints must be enabled or disabled")
        for name, low, high in (("weather_rain_percent", 1, 100), ("weather_gust_mph", 5, 100),
                                ("weather_hot_f", -50, 130), ("weather_cold_f", -50, 130)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be a whole number from {low} to {high}")
        if self.weather_cold_f >= self.weather_hot_f:
            raise ValueError("The cool-weather threshold must be below the hot-weather threshold")
        for value in (self.timer_focus_minutes, self.timer_break_minutes):
            if type(value) is not int or not 1 <= value <= 240:
                raise ValueError("Timer presets must be whole minutes from 1 to 240")
        if self.audio_output not in {"auto", "hdmi", "hat"}:
            raise ValueError("audio_output must be auto, hdmi, or hat")
        if self.phone_address is not None and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", self.phone_address):
            raise ValueError("phone_address must be a paired Bluetooth MAC address")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be set or cleared together")
        for name, value, limit in (("latitude", self.latitude, 90), ("longitude", self.longitude, 180)):
            if value is not None and (not math.isfinite(value) or not -limit <= value <= limit):
                raise ValueError(f"{name} is outside its valid range")
        if not self.cycle or any(item.get("page") not in set(Page) or not isinstance(item.get("seconds"), int) or not 5 <= item["seconds"] <= 600 for item in self.cycle):
            raise ValueError("cycle must contain valid pages lasting 5 to 600 seconds")
        if not 0 <= self.brightness <= 100:
            raise ValueError("brightness must be between 0 and 100")
        if not 0 <= self.volume <= 100:
            raise ValueError("volume must be between 0 and 100")
        if self.phone_disconnect_grace_seconds < 0:
            raise ValueError("phone disconnect grace must not be negative")
        if self.pin_unlock_minutes <= 0:
            raise ValueError("PIN unlock duration must be positive")
        if self.temporary_night_wake_minutes <= 0:
            raise ValueError("temporary wake duration must be positive")


@dataclass(slots=True)
class CalendarEvent:
    id: str
    calendar_id: str
    summary: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str | None = None
    description: str | None = None
    status: str = "confirmed"
    calendar_name: str | None = None
    calendar_color: str | None = None
    event_color: str | None = None
    event_color_id: str | None = None
    etag: str | None = None
    calendar_writable: bool = False
    self_declined: bool = False
    virtual_only: bool = False

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())

    def is_ongoing(self, now: datetime) -> bool:
        return self.status != "cancelled" and self.start <= now < self.end


@dataclass(slots=True)
class RuntimeState:
    privacy: PrivacyLevel = PrivacyLevel.PRIVATE
    display_power: DisplayPower = DisplayPower.ON
    assistant_phase: AssistantPhase = AssistantPhase.IDLE
    active_page: Page = Page.HOME
    cycle_paused_until: datetime | None = None
    phone_connected: bool = False
    phone_last_seen_at: datetime | None = None
    pin_unlocked_until: datetime | None = None
    forced_private: bool = False
    scheduled_sleep_end: datetime | None = None
    forced_sleep_until: datetime | None = None
    temporary_wake_until: datetime | None = None
    morning_override_until: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Command:
    name: CommandName
    value: Any = None
    source: str = "local"


@dataclass(slots=True)
class CommandResult:
    accepted: bool
    message: str
    state_changed: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class WeatherHour:
    time: datetime
    temperature: float
    precipitation_probability: int | None
    weather_code: int
    apparent_temperature: float | None = None
    wind_gust_mph: float | None = None
    precipitation_mm: float | None = None


@dataclass(slots=True)
class WeatherSnapshot:
    observed_at: datetime
    temperature: float
    apparent_temperature: float
    high: float
    low: float
    weather_code: int
    summary: str
    attribution: str = "Weather data by Open-Meteo.com"
    hourly: list[WeatherHour] = field(default_factory=list)
    stale: bool = False


@dataclass(slots=True)
class PhoneNotification:
    id: str
    app_id: str
    app_name: str
    title: str
    body: str
    received_at: datetime
    category: str = "other"
    incoming: bool = True
