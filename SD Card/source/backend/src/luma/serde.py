from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, TypeVar, get_type_hints

from .models import (
    AssistantPhase,
    CalendarEvent,
    DisplayPower,
    Orientation,
    Page,
    PhoneNotification,
    PrivacyLevel,
    RuntimeState,
    Settings,
    Theme,
    WeatherHour,
    WeatherSnapshot,
)

T = TypeVar("T")


def to_primitive(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_primitive(item) for item in value]
    return value


def settings_from_dict(payload: dict[str, Any]) -> Settings:
    allowed = get_type_hints(Settings)
    clean = {key: value for key, value in payload.items() if key in allowed}
    # Fresh installs use Settings(); older saved configurations must not silently
    # activate a microphone when upgrading from a version without this field.
    clean.setdefault("voice_enabled", False)
    if "theme" in clean:
        clean["theme"] = Theme(clean["theme"])
    if "orientation" in clean:
        clean["orientation"] = Orientation(clean["orientation"])
    settings = Settings(**clean)
    settings.validate()
    return settings


def runtime_state_from_dict(payload: dict[str, Any]) -> RuntimeState:
    date_fields = {
        "cycle_paused_until",
        "phone_last_seen_at",
        "pin_unlocked_until",
        "scheduled_sleep_end",
        "forced_sleep_until",
        "temporary_wake_until",
        "morning_override_until",
        "updated_at",
    }
    clean = {key: value for key, value in payload.items() if key in get_type_hints(RuntimeState)}
    for key in date_fields:
        if clean.get(key):
            clean[key] = datetime.fromisoformat(clean[key])
    if "privacy" in clean:
        clean["privacy"] = PrivacyLevel(clean["privacy"])
    if "display_power" in clean:
        clean["display_power"] = DisplayPower(clean["display_power"])
    if "assistant_phase" in clean:
        clean["assistant_phase"] = AssistantPhase(clean["assistant_phase"])
    if "active_page" in clean:
        clean["active_page"] = Page(clean["active_page"])
    # A Bluetooth link never survives a process restart. The monitor must prove it again;
    # retaining the old grace timestamp could briefly reveal private data after a reboot.
    clean["phone_connected"] = False
    clean["phone_last_seen_at"] = None
    return RuntimeState(**clean)


def calendar_event_from_dict(payload: dict[str, Any]) -> CalendarEvent:
    clean = dict(payload)
    clean["start"] = datetime.fromisoformat(clean["start"])
    clean["end"] = datetime.fromisoformat(clean["end"])
    return CalendarEvent(**clean)


def weather_from_dict(payload: dict[str, Any]) -> WeatherSnapshot:
    clean = dict(payload)
    clean["observed_at"] = datetime.fromisoformat(clean["observed_at"])
    clean["hourly"] = [
        WeatherHour(time=datetime.fromisoformat(item["time"]), **{k: v for k, v in item.items() if k != "time"})
        for item in clean.get("hourly", [])
    ]
    return WeatherSnapshot(**clean)


def notification_from_dict(payload: dict[str, Any]) -> PhoneNotification:
    clean = dict(payload)
    clean["received_at"] = datetime.fromisoformat(clean["received_at"])
    return PhoneNotification(**clean)
