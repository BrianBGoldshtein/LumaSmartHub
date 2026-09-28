"""Small, explicit command language for a future private HTTPS transport."""
from __future__ import annotations

import asyncio
import json
import re

from fastapi import HTTPException, Request
from starlette.requests import ClientDisconnect

from .models import Command, CommandName, Page, Theme

MAX_BODY = 1024
NO_VALUE = frozenset({
    "show_brightness", "show_volume", "good_night", "good_morning", "wake", "screen_off",
    "next_page", "previous_page", "pause_cycle", "resume_cycle", "privacy_now",
    "show_timer", "pause_timer", "resume_timer", "cancel_timer", "dismiss_timer",
})


def command_token(request: Request) -> str:
    # Shortcuts is not a browser API. No query credentials, cookies, CORS, or
    # Origin-based exceptions, even when an HTTPS proxy arrives on loopback.
    if request.url.query or "origin" in request.headers:
        raise HTTPException(403, "This endpoint accepts native command requests only.")
    tokens = request.headers.getlist("x-luma-token")
    if len(tokens) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{43}", tokens[0]):
        raise HTTPException(401, "Command authentication required.")
    return tokens[0]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite number")


def parse_command(raw: bytes) -> Command:
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
        if not isinstance(payload, dict) or not set(payload) <= {"name", "value"}:
            raise ValueError("Unexpected fields")
        name, value = payload.get("name"), payload.get("value")
        if not isinstance(name, str):
            raise ValueError("Missing name")
        if name in NO_VALUE:
            valid = value is None
        elif name in {"set_brightness", "set_volume"}:
            valid = type(value) is int and 0 <= value <= 100
        elif name == "set_theme":
            valid = isinstance(value, str) and value in {item.value for item in Theme}
        elif name == "show_page":
            valid = isinstance(value, str) and value in {item.value for item in Page}
        elif name == "start_timer":
            valid = (type(value) is int and 1 <= value <= 240) or (isinstance(value, str) and value in {'focus', 'break'})
        elif name == "run_remote_scene":
            valid = isinstance(value, str) and value in {'morning', 'night', 'arrive', 'away'}
        else:
            valid = False
        if not valid:
            raise ValueError("Unsupported command or value")
        return Command(CommandName(name), value, "siri")
    except (ValueError, TypeError, RecursionError):
        # Never echo inputs, tokens, or parser diagnostics into the response.
        raise HTTPException(422, "Unsupported command or value.") from None


async def read_command(request: Request) -> Command:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "JSON required.")
    if "content-encoding" in request.headers:
        raise HTTPException(415, "Compressed requests are not supported.")
    lengths = request.headers.getlist("content-length")
    if lengths and (len(lengths) != 1 or not lengths[0].isascii() or
                    not lengths[0].isdigit() or len(lengths[0]) > 6):
        raise HTTPException(400, "Invalid request length.")
    if lengths and int(lengths[0]) > MAX_BODY:
        raise HTTPException(413, "Command is too large.")
    body = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_BODY:
                    raise HTTPException(413, "Command is too large.")
                body.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "Command timed out.") from None
    except ClientDisconnect:
        raise HTTPException(400, "Incomplete command.") from None
    return parse_command(bytes(body))
