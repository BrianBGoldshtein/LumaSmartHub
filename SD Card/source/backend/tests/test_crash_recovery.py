"""Abrupt process-death tests, not claims about physical SD power-loss safety."""
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading

import pytest

from luma.models import CalendarEvent, Theme, WeatherSnapshot
from luma.service import LumaService
from luma.storage import Storage

WRITER = Path(__file__).with_name("support") / "crash_writer.py"
ORIGINAL_TOKEN = '{"refresh_token":"fake-original-token"}'
UPDATED_TOKEN = '{"refresh_token":"fake-updated-token"}'


def kill_at_boundary(path: Path, operation: str, boundary: str):
    process = subprocess.Popen([sys.executable, str(WRITER), str(path), operation, boundary],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    messages = queue.Queue()
    reader = threading.Thread(target=lambda: messages.put(process.stdout.readline()), daemon=True)
    reader.start()
    try:
        assert messages.get(timeout=15) == "ready\n", "Writer did not reach the requested boundary"
        assert process.poll() is None
        if operation == "cache":
            # Prove the case actually exercises on-disk WAL frames, not just
            # uncommitted bytes that never left a Python/SQLite memory buffer.
            assert path.with_name(path.name + "-wal").stat().st_size > 1024 * 1024
        process.kill()
        process.wait(timeout=5)
        assert process.returncode != 0
        if sys.platform == "linux":
            assert process.returncode == -signal.SIGKILL
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        reader.join(timeout=2)


def seed(path: Path):
    storage = Storage(path)
    settings = storage.load_settings()
    settings.theme = Theme.HEARTH
    settings.visible_calendar_ids = ["primary"]
    settings.phone_address = "AA:BB:CC:DD:EE:FF"
    storage.save_settings(settings)
    storage.set_secret("google_credentials", ORIGINAL_TOKEN)
    storage.set_cache("crash-test", "payload", {"revision": 1})
    service = LumaService(storage)
    now = datetime.now(UTC)
    service.replace_events([CalendarEvent("fixture", "primary", "Private fixture event", now, now + timedelta(hours=1))], now)
    service.replace_weather(WeatherSnapshot(now, 71, 70, 75, 60, 0, "Clear"))
    service.phone_seen(now)
    assert not service.snapshot(now)["privacy_redacted"]
    return storage


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_first_database_creation_recovers_after_abrupt_interruption(tmp_path, boundary):
    path = tmp_path / "first-boot.db"
    kill_at_boundary(path, "bootstrap", boundary)
    recovered = Storage(path)
    assert recovered.integrity_check()
    assert recovered.load_settings().device_name == "Luma"
    assert recovered.get_secret("google_credentials") is None
    assert LumaService(recovered).snapshot()["privacy_redacted"]


@pytest.mark.parametrize("operation", ["settings", "secret", "cache"])
@pytest.mark.parametrize("boundary", ["before", "after"])
def test_crashed_write_recovers_atomic_data_without_restoring_phone_presence(tmp_path, operation, boundary):
    path = tmp_path / "luma.db"
    storage = seed(path)
    with closing(storage.connect()) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        audits_before = connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    kill_at_boundary(path, operation, boundary)
    recovered = Storage(path)
    assert recovered.integrity_check()
    committed = boundary == "after"
    changed_settings = operation == "settings" and committed
    assert recovered.load_settings().theme == (Theme.NEON_GRID if changed_settings else Theme.HEARTH)
    assert recovered.load_settings().brightness == (31 if changed_settings else 70)
    assert recovered.get_secret("google_credentials") == (UPDATED_TOKEN if operation == "secret" and committed else ORIGINAL_TOKEN)
    cache = recovered.get_cache("crash-test", "payload")
    assert cache["revision"] == (2 if operation == "cache" and committed else 1)
    if cache["revision"] == 2:
        assert cache["padding"] == "x" * (2 * 1024 * 1024)
    with closing(recovered.connect()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == audits_before + int(changed_settings)
    restarted = LumaService(recovered)
    snapshot = restarted.snapshot()
    assert snapshot["privacy_redacted"] and not restarted.state.phone_connected
    assert restarted.state.phone_last_seen_at is None
    assert snapshot["calendar"] == [] and snapshot["notifications"] == []
    assert restarted.events[0].summary == "Private fixture event"  # retained, not exposed
    assert snapshot["weather"]["temperature"] == 71


@pytest.mark.parametrize("boundary", ["before", "after"])
def test_interrupted_backup_keeps_an_intact_previous_or_replacement_snapshot(tmp_path, boundary):
    path = tmp_path / "luma.db"
    storage = seed(path)
    backup_path = storage.backup(tmp_path / "backup.db")
    settings = storage.load_settings()
    settings.brightness = 31
    storage.save_settings(settings)
    kill_at_boundary(path, "backup", boundary)
    backup = Storage(backup_path)
    assert backup.integrity_check() and storage.integrity_check()
    assert backup.load_settings().brightness == (31 if boundary == "after" else 70)
    assert backup.get_secret("google_credentials") == ORIGINAL_TOKEN
    storage.restore(backup_path.resolve())
    assert storage.load_settings().brightness == backup.load_settings().brightness
