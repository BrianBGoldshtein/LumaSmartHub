"""Serialized weather refresh with stale-cache fallback and location race protection."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from .integrations.open_meteo import OpenMeteoClient
from .service import LumaService


class WeatherRuntime:
    def __init__(self, service: LumaService, client: OpenMeteoClient):
        self.service = service
        self.client = client
        self.lock = asyncio.Lock()
        self.status: dict[str, Any] = {"last_synced": None, "error": None}
        self.changed = asyncio.Event()

    def location(self) -> tuple:
        settings = self.service.settings
        return settings.latitude, settings.longitude, settings.timezone

    async def refresh(self) -> dict[str, Any]:
        async with self.lock:
            location = self.location()
            if location[0] is None or location[1] is None:
                raise ValueError("Set a weather location first")
            try:
                forecast = await asyncio.to_thread(self.client.fetch, latitude=location[0], longitude=location[1], timezone=location[2])
            except Exception:
                self.status["error"] = "Weather unavailable; retaining the last forecast."
                if self.service.weather:
                    self.service.weather.stale = True
                    self.service.publish("weather.stale")
                raise
            # Do not label an old in-flight result with a newly configured location.
            if self.location() != location:
                self.changed.set()
                return {"updated": False}
            self.service.replace_weather(forecast)
            self.status.update(last_synced=datetime.now(UTC).isoformat(), error=None)
            return {"updated": True}

    def location_changed(self) -> None:
        self.service.weather = None
        self.service.storage.set_cache("weather", "forecast", None)
        self.status.update(last_synced=None, error=None)
        self.changed.set()

    async def run(self) -> None:
        while True:
            self.changed.clear()
            if self.location()[0] is not None:
                try:
                    await self.refresh()
                except Exception:
                    pass  # Diagnostics retain a safe message, never provider secrets.
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=900)
            except asyncio.TimeoutError:
                pass
