"""On-demand, credential-free HTTPS checks from the Luma API process."""
import asyncio
import socket
import ssl

import httpx
import requests

from .integrations.open_meteo import FORECAST_URL, OpenMeteoClient

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def _failure(error: Exception) -> str:
    pending = [error]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, (ssl.SSLError, requests.exceptions.SSLError)):
            return "tls"
        if isinstance(current, socket.gaierror):
            return "dns"
        if isinstance(current, (TimeoutError, httpx.TimeoutException, requests.Timeout)):
            return "timeout"
        for cause in (current.__cause__, current.__context__, getattr(current, "reason", None), *current.args):
            if isinstance(cause, BaseException):
                pending.append(cause)
    return "connection"


def _google() -> str:
    try:
        with requests.Session() as session:
            session.trust_env = False  # Same direct HTTPS path as the Desktop OAuth exchange.
            with session.get(GOOGLE_TOKEN_URL, timeout=5, allow_redirects=False, stream=True) as reply:
                # The token endpoint expects POST with an authorization grant.
                return "reachable" if reply.status_code in (400, 404, 405) else "http"
    except (requests.RequestException, OSError) as error:
        return _failure(error)


def _weather(client: OpenMeteoClient) -> str:
    try:
        # The forecast endpoint rejects a request with no coordinates. That
        # response verifies routing and TLS without sending the owner's location.
        with client.client.stream("GET", FORECAST_URL, timeout=5, follow_redirects=False) as reply:
            return "reachable" if reply.status_code == 400 or 200 <= reply.status_code < 300 else "http"
    except (httpx.HTTPError, OSError) as error:
        return _failure(error)


async def check_providers(weather: OpenMeteoClient) -> dict[str, str]:
    async def probe(check, *args):
        try:
            return await asyncio.wait_for(asyncio.to_thread(check, *args), timeout=8)
        except TimeoutError:
            return "timeout"

    google, forecast = await asyncio.gather(probe(_google), probe(_weather, weather))
    return {"google": google, "weather": forecast}
