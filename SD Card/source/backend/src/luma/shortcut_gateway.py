"""Dormant command-only gateway. Never proxy the local UI/API to a network.

No service is enabled by the installer. A chosen, qualified private HTTPS
transport is still required; this loopback listener alone is not phone setup.
"""
from __future__ import annotations

import asyncio
import json
from collections import deque
from time import monotonic

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request

from .shortcut_protocol import command_token, read_command

UPSTREAM = "http://127.0.0.1:8742/api/v1/shortcut-command"


def create_gateway(*, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    # Transport injection is for offline tests only, never a request parameter.
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    requests: deque[float] = deque()

    @app.middleware("http")
    async def no_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.post("/command")
    async def command(request: Request):
        token = command_token(request)
        # Shared single-process budget; never trust a caller's forwarded IP.
        now = monotonic()
        while requests and now - requests[0] >= 60:
            requests.popleft()
        if len(requests) >= 30 or sum(now - instant < 1 for instant in requests) >= 6:
            raise HTTPException(429, "Too many commands.", headers={"Retry-After": "60"})
        requests.append(now)
        parsed = await read_command(request)
        try:
            async with asyncio.timeout(5):
                async with httpx.AsyncClient(transport=transport, trust_env=False,
                                            follow_redirects=False, timeout=3) as client:
                    async with client.stream("POST", UPSTREAM,
                            headers={"X-Luma-Token": token, "Accept-Encoding": "identity"},
                            json={"name": parsed.name.value, "value": parsed.value}) as response:
                        if response.status_code == 401:
                            raise HTTPException(401, "Command authentication required.")
                        if response.status_code != 200 or response.headers.get("content-encoding"):
                            raise HTTPException(503, "Hub command unavailable.")
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 8192:
                                raise HTTPException(503, "Hub command unavailable.")
                            raw.extend(chunk)
            result = json.loads(raw)
            if (not isinstance(result, dict) or set(result) != {"accepted", "message"}
                    or type(result["accepted"]) is not bool
                    or not isinstance(result["message"], str) or len(result["message"]) > 1600):
                raise ValueError("Invalid upstream response")
            return result
        except (httpx.HTTPError, TimeoutError, ValueError, RecursionError):
            raise HTTPException(503, "Hub command unavailable.") from None

    return app


def main() -> None:
    # No bind-host env override, proxy-header trust, request logs, or multiworker
    # mode (the small rate budget above is deliberately process-local).
    uvicorn.run(create_gateway(), host="127.0.0.1", port=8743, proxy_headers=False,
                access_log=False, limit_concurrency=16, timeout_keep_alive=3,
                h11_max_incomplete_event_size=8192)
