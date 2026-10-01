"""Small, transcript-free voice health history for owner-local troubleshooting."""
from __future__ import annotations

from datetime import UTC, datetime
import sqlite3
from typing import Any


MAX_EVENTS = 12
KINDS = {"reply", "sample", "tone"}
ENGINES = {"piper", "fallback", "silent"}
ROUTES = {"luma_speaker", "system_speaker"}
ERRORS = {
    "audio_session_unavailable", "speaker_route_unavailable", "speaker_playback_failed",
    "piper_start_failed", "piper_start_timeout", "piper_runtime_missing",
    "piper_model_load_failed", "piper_memory_pressure", "piper_synthesis_failed",
    "piper_audio_invalid", "synthesis_unavailable", "voice_asset_unavailable",
    "piper_retry_wait", "fallback_playback_failed",
}


def _valid(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != {
            "kind", "at", "engine", "route", "error", "primary_error"}:
        return False
    if any(value is not None and not isinstance(value, str)
           for value in (row["kind"], row["engine"], row["route"],
                         row["error"], row["primary_error"])):
        return False
    if (row["kind"] not in KINDS or row["engine"] not in ENGINES | {None}
            or row["route"] not in ROUTES | {None}
            or row["error"] not in ERRORS | {None}
            or row["primary_error"] not in ERRORS | {None}):
        return False
    at = row["at"]
    if not isinstance(at, str) or len(at) > 40:
        return False
    try:
        return datetime.fromisoformat(at).tzinfo is not None
    except ValueError:
        return False


def load_history(storage) -> list[dict[str, Any]]:
    try:
        saved = storage.get_cache("voice", "health_history")
    except (OSError, ValueError, sqlite3.Error):
        return []
    if not isinstance(saved, list):
        return []
    return [row for row in saved[-MAX_EVENTS:] if _valid(row)]


def record(history: list[dict[str, Any]], storage, *, kind: str,
           engine: str | None = None, route: str | None = None,
           error: str | None = None, primary_error: str | None = None) -> dict[str, Any]:
    row = {"kind": kind, "at": datetime.now(UTC).isoformat(), "engine": engine,
           "route": route, "error": error, "primary_error": primary_error}
    if not _valid(row):
        raise ValueError("Invalid voice health event")
    history.append(row)
    del history[:-MAX_EVENTS]
    try:
        storage.set_cache("voice", "health_history", history)
    except (OSError, ValueError, sqlite3.Error):
        # A full/read-only data partition must not suppress a spoken reply or
        # obscure its immediate in-memory diagnostic.
        pass
    return row
