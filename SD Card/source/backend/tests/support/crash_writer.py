"""Fault-injection subprocess, used only with temporary test databases.

Parent kills this process at a deterministic commit/replace boundary. No network,
real credentials, appliance paths, or production processes are involved.
"""
from pathlib import Path
import os
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from luma.models import Theme
from luma.storage import Storage

database, operation, boundary = sys.argv[1:4]
armed = operation == "bootstrap"


def ready():
    print("ready", flush=True)
    # An open pipe is a barrier, not a time-based race. The parent never writes
    # to it: SIGKILL / TerminateProcess must prevent Python cleanup from running.
    sys.stdin.buffer.read(1)
    raise RuntimeError("Crash test barrier was unexpectedly released")


class CrashConnection(sqlite3.Connection):
    def commit(self):
        if armed and boundary == "before":
            ready()
        super().commit()
        if armed and boundary == "after":
            ready()


original_connect = sqlite3.connect


def crash_connect(*args, **kwargs):
    connection = original_connect(*args, **kwargs, factory=CrashConnection)
    # Force the large-cache case to spill uncommitted frames into its WAL.
    connection.execute("PRAGMA cache_size=8")
    return connection


if operation != "backup":
    sqlite3.connect = crash_connect
storage = Storage(database)
armed = True
if operation == "settings":
    settings = storage.load_settings()
    settings.theme = Theme.NEON_GRID
    settings.brightness = 31
    storage.save_settings(settings)
elif operation == "secret":
    storage.set_secret("google_credentials", '{"refresh_token":"fake-updated-token"}')
elif operation == "cache":
    storage.set_cache("crash-test", "payload", {"revision": 2, "padding": "x" * (2 * 1024 * 1024)})
elif operation == "backup":
    original_replace = os.replace

    def crash_replace(source, target):
        if boundary == "before":
            ready()
        original_replace(source, target)
        if boundary == "after":
            ready()

    os.replace = crash_replace
    storage.backup(Path(database).with_name("backup.db"))
else:
    raise ValueError("Unknown test operation")
raise RuntimeError("Operation unexpectedly passed the crash boundary")
