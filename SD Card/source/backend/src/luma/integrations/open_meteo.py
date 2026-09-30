from __future__ import annotations

from datetime import UTC, datetime
import math
from zoneinfo import ZoneInfo

import httpx

from ..models import WeatherHour, WeatherSnapshot


DESCRIPTIONS = {
    0: "Clear skies.", 1: "Mostly clear.", 2: "Partly cloudy.", 3: "Overcast.",
    45: "Foggy.", 48: "Fog with frost.", 51: "Light drizzle.", 53: "Drizzle.",
    55: "Heavy drizzle.", 61: "Light rain.", 63: "Rain.", 65: "Heavy rain.",
    71: "Light snow.", 73: "Snow.", 75: "Heavy snow.", 80: "Light showers.",
    81: "Rain showers.", 82: "Heavy showers.", 95: "Thunderstorms nearby.",
}


class OpenMeteoClient:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=12.0)

    def fetch(self, *, latitude: float, longitude: float, timezone: str) -> WeatherSnapshot:
        response = self.client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone,
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "precipitation_unit": "mm",
                "timeformat": "unixtime",
                "current": "temperature_2m,apparent_temperature,weather_code",
                "hourly": "temperature_2m,precipitation_probability,weather_code,apparent_temperature,precipitation,wind_gusts_10m",
                "daily": "temperature_2m_max,temperature_2m_min",
                "forecast_days": 2,
            },
        )
        response.raise_for_status()
        return parse_forecast(response.json(), timezone)


def _moment(value, zone: ZoneInfo) -> datetime:
    # Unix timestamps preserve both occurrences of a repeated DST hour. ISO
    # support also keeps older fixtures/caches and explicit offsets readable.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC).astimezone(zone)
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(zone) if parsed.tzinfo else parsed.replace(tzinfo=zone)


def _number(value, low: float, high: float) -> float | None:
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        return None
    return float(value)


def _optional(hourly: dict, name: str, index: int, low: float, high: float) -> float | None:
    values = hourly.get(name)
    return _number(values[index], low, high) if isinstance(values, list) and index < len(values) else None


def parse_forecast(payload: dict, timezone: str) -> WeatherSnapshot:
    zone = ZoneInfo(timezone)
    current = payload["current"]
    daily = payload["daily"]
    hourly = payload["hourly"]
    observed = _moment(current["time"], zone)
    hours: list[WeatherHour] = []
    for index, (time, temperature, code) in enumerate(zip(
        hourly["time"],
        hourly["temperature_2m"],
        hourly["weather_code"],
        strict=True,
    )):
        moment = _moment(time, zone)
        if moment.timestamp() >= observed.timestamp():
            probability = _optional(hourly, "precipitation_probability", index, 0, 100)
            hours.append(WeatherHour(moment, float(temperature), round(probability) if probability is not None else None, int(code),
                                     _optional(hourly, "apparent_temperature", index, -150, 160),
                                     _optional(hourly, "wind_gusts_10m", index, 0, 300),
                                     _optional(hourly, "precipitation", index, 0, 1000)))
        # Keep the remainder of today and all of tomorrow for local spoken
        # questions. The dashboard still renders only its first few hours.
        if len(hours) == 48:
            break
    code = int(current["weather_code"])
    return WeatherSnapshot(
        observed_at=observed,
        temperature=float(current["temperature_2m"]),
        apparent_temperature=float(current["apparent_temperature"]),
        high=float(daily["temperature_2m_max"][0]),
        low=float(daily["temperature_2m_min"][0]),
        weather_code=code,
        summary=DESCRIPTIONS.get(code, "Current conditions are available."),
        hourly=hours,
    )
