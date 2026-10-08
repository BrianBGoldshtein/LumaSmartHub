from __future__ import annotations

import json
import sqlite3
import os
import tempfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Settings
from .serde import settings_from_dict, to_primitive


SCHEMA_VERSION = 1


class Storage:
    """Durable SQLite state with atomic settings and cache writes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    PRIMARY KEY(namespace, key)
                );
                CREATE TABLE IF NOT EXISTS secrets (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            count = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
            if count == 0:
                now = datetime.now(UTC).isoformat()
                connection.execute(
                    "INSERT INTO settings(id, payload, updated_at) VALUES(1, ?, ?)",
                    (json.dumps(to_primitive(Settings()), sort_keys=True), now),
                )

    def load_settings(self) -> Settings:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT payload FROM settings WHERE id = 1").fetchone()
        if row is None:
            return Settings()
        return settings_from_dict(json.loads(row["payload"]))

    def save_settings(self, settings: Settings) -> None:
        settings.validate()
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(to_primitive(settings), separators=(",", ":"), sort_keys=True)
        with self.transaction() as connection:
            old = connection.execute("SELECT payload FROM settings WHERE id=1").fetchone()
            if old and json.loads(old["payload"]).get("phone_address") != settings.phone_address:
                # Selecting/forgetting another bond must not resurrect grants
                # when the previous phone is later selected again.
                connection.execute("DELETE FROM secrets WHERE key IN (?, ?)",
                                   ("companion_browser_grants_v1", "companion_google_oauth_state_v1"))
            connection.execute(
                "UPDATE settings SET payload = ?, updated_at = ? WHERE id = 1",
                (payload, now),
            )
            connection.execute(
                "INSERT INTO audit_log(kind, payload, created_at) VALUES(?, ?, ?)",
                ("settings.changed", payload, now),
            )

    def set_cache(
        self,
        namespace: str,
        key: str,
        payload: Any,
        *,
        expires_at: datetime | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        encoded = json.dumps(to_primitive(payload), separators=(",", ":"), sort_keys=True)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO cache(namespace, key, payload, updated_at, expires_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at,
                    expires_at = excluded.expires_at
                """,
                (namespace, key, encoded, now, expires_at.isoformat() if expires_at else None),
            )

    def get_cache(self, namespace: str, key: str, *, allow_expired: bool = True) -> Any | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT payload, expires_at FROM cache WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
        if row is None:
            return None
        if row["expires_at"] and not allow_expired:
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at <= datetime.now(UTC):
                return None
        return json.loads(row["payload"])

    def set_secret(self, key: str, payload: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO secrets(key, payload, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (key, payload, now),
            )

    def get_secret(self, key: str) -> str | None:
        with closing(self.connect()) as connection:
            row = connection.execute("SELECT payload FROM secrets WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["payload"])

    def backup(self, destination: str | Path) -> Path:
        destination_path = Path(destination)
        if destination_path.resolve() == self.path.resolve():
            raise ValueError("backup destination must differ from the live database")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".luma-backup-", suffix=".db", dir=destination_path.parent)
        os.close(handle)
        try:
            with closing(self.connect()) as source, closing(sqlite3.connect(temporary)) as target:
                source.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("backup integrity check failed")
            os.chmod(temporary, 0o600)
            os.replace(temporary, destination_path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination_path

    def integrity_check(self) -> bool:
        with closing(self.connect()) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return result == "ok"

    def restore(self, source: str | Path) -> None:
        """Restore offline only; callers must stop the API and all writers first."""
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if source_path.resolve() == self.path.resolve():
            raise ValueError("cannot restore the live database onto itself")
        test = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)
        try:
            if test.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("backup database failed integrity check")
            objects = test.execute("SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
            expected = {"metadata", "settings", "cache", "secrets", "audit_log"}
            if {name for name, kind in objects if kind == "table"} != expected or any(kind != "table" for _, kind in objects):
                raise ValueError("not a supported Luma backup")
            if test.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone() != (str(SCHEMA_VERSION),):
                raise ValueError("unsupported backup schema")
            settings_from_dict(json.loads(test.execute("SELECT payload FROM settings WHERE id=1").fetchone()[0]))
            # Prepare/scrub before the atomic destination backup. A historical
            # backup must never resurrect a revoked phone-browser grant, even
            # if power fails during restore. Normal app updates do not restore
            # this database, so their enrolled browsers are retained.
            handle, prepared_path = tempfile.mkstemp(prefix=".luma-restore-", suffix=".db", dir=self.path.parent)
            os.close(handle)
            try:
                with closing(sqlite3.connect(prepared_path)) as prepared:
                    test.backup(prepared)
                    prepared.execute("DELETE FROM secrets WHERE key IN (?, ?)",
                                     ("companion_browser_grants_v1", "companion_google_oauth_state_v1"))
                    prepared.commit()
                    # SQLite backup handles the live destination WAL.
                    with closing(self.connect()) as destination:
                        prepared.backup(destination)
            finally:
                Path(prepared_path).unlink(missing_ok=True)
        finally:
            test.close()
