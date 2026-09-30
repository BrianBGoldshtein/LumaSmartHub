"""Pure, conservative forecast hints. No I/O, timers, writes or extra polling."""
from datetime import UTC, datetime, timedelta
from math import isfinite

from .models import Settings, WeatherSnapshot


def _valid(value, low, high):
    return type(value) in (int, float) and isfinite(value) and low <= value <= high


def weather_nudge(weather: WeatherSnapshot | None, settings: Settings, now: datetime) -> dict | None:
    if not settings.weather_nudges_enabled or weather is None or weather.stale:
        return None
    now = now.astimezone(UTC)
    age = now - weather.observed_at.astimezone(UTC)
    if age < timedelta(0) or age > timedelta(hours=2):
        return None
    # Probability/precipitation/gust timestamps describe the preceding hour.
    # Only upcoming interval ends are used, not the already-completed hour.
    hours = [h for h in weather.hourly if now < h.time.astimezone(UTC) <= now + timedelta(hours=6)]

    def hint(kind, title, detail):
        return {"kind": kind, "title": title, "detail": detail, "window": "Next 6h"}

    wet = [h for h in hours if _valid(h.precipitation_probability, 0, 100)
           and h.precipitation_probability >= settings.weather_rain_percent]
    if wet:
        codes = {h.weather_code for h in wet}
        # Probability covers rain AND snow; never call snowy/freezing hours rain.
        if codes <= {71, 73, 75, 77, 85, 86}:
            title = "Snow possible"
        elif codes & {56, 57, 66, 67, 71, 73, 75, 77, 85, 86}:
            title = "Wintry weather"
        elif codes <= {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}:
            title = "Rain possible"
        else:
            title = "Wet weather possible"
        return hint("precipitation", title, f"Up to {max(h.precipitation_probability for h in wet)}% chance")
    gusts = [h.wind_gust_mph for h in hours if _valid(h.wind_gust_mph, 0, 300)]
    if gusts and max(gusts) >= settings.weather_gust_mph:
        return hint("wind", "Gusty ahead", f"Gusts to {round(max(gusts))} mph")
    feels = [h.apparent_temperature for h in hours if _valid(h.apparent_temperature, -150, 160)]
    if feels and max(feels) >= settings.weather_hot_f:
        return hint("heat", "Hotter ahead", f"Feels up to {round(max(feels))}°")
    if feels and min(feels) <= settings.weather_cold_f:
        return hint("cold", "Cooler ahead", f"Feels down to {round(min(feels))}°")
    return None
