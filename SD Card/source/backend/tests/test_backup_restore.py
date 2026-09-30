import sqlite3

import pytest

from luma.storage import Storage


def test_restore_uses_backup_api_with_live_wal(tmp_path):
    storage = Storage(tmp_path / "luma.db")
    settings = storage.load_settings()
    settings.brightness = 30
    storage.save_settings(settings)
    backup = storage.backup(tmp_path / "snapshot.db")
    settings.brightness = 90
    storage.save_settings(settings)
    keeper = storage.connect()
    try:
        storage.restore(backup)
        assert storage.load_settings().brightness == 30
        assert storage.integrity_check()
    finally:
        keeper.close()


def test_restore_rejects_non_luma_database_without_mutating_live_settings(tmp_path):
    storage = Storage(tmp_path / "luma.db")
    source = tmp_path / "unrelated.db"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE other (id INTEGER)")
    with pytest.raises(ValueError, match="supported Luma"):
        storage.restore(source)
    assert storage.load_settings().brightness == 70


def test_backup_cannot_overwrite_live_database(tmp_path):
    storage = Storage(tmp_path / "luma.db")
    with pytest.raises(ValueError):
        storage.backup(storage.path)
