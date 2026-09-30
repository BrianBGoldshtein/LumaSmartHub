"""The FAT BOOT log must remain useful without leaking Luma user data."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


pytest.importorskip("fcntl")
SCRIPT = Path(__file__).resolve().parents[2] / "system/luma_boot_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("luma_boot_diagnostics", SCRIPT)
assert SPEC and SPEC.loader
diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostics)


def test_status_exports_only_fixed_codes_and_version(tmp_path):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({
        "state": "failed", "phase": "restoring", "target_version": "0.2.4",
        "message": "secret-calendar-title@example.com and a Google token",
    }), encoding="utf-8")
    result = diagnostics.read_update_status(status)
    assert result == {"state": "failed", "phase": "restoring", "target": "0.2.4"}
    assert "secret" not in json.dumps(result)


def test_status_rejects_malformed_or_linked_file(tmp_path):
    status = tmp_path / "status.json"
    status.write_text('{"state":"failed\nprivate","phase":"x","target_version":"x"}', encoding="utf-8")
    assert diagnostics.read_update_status(status)["state"] == "unavailable"
    target = tmp_path / "target.json"
    target.write_text('{}', encoding="utf-8")
    status.unlink()
    status.symlink_to(target)
    assert diagnostics.read_update_status(status)["state"] == "unavailable"


def test_boot_log_rotates_and_never_copies_free_form_message(tmp_path):
    log = tmp_path / "luma-diagnostics.log"
    previous = tmp_path / "luma-diagnostics.previous.log"
    lock = tmp_path / "luma.lock"
    log.write_bytes(b"x" * (diagnostics.MAX_LOG_BYTES - 100))
    state = {"active_version": "0.2.3", "update": {"state": "failed", "phase": "restoring", "target": "0.2.4"}}
    diagnostics.append_event("status_change", state, path=log, previous=previous, lock_path=lock)
    assert previous.stat().st_size == diagnostics.MAX_LOG_BYTES - 100
    row = json.loads(log.read_text(encoding="ascii"))
    assert row["event"] == "status_change"
    assert row["update"]["target"] == "0.2.4"
    assert log.stat().st_size < diagnostics.MAX_LOG_BYTES


def test_boot_log_refuses_link_destination(tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("must remain untouched", encoding="utf-8")
    log = tmp_path / "luma-diagnostics.log"
    log.symlink_to(elsewhere)
    with pytest.raises(OSError):
        diagnostics.append_event("boot", {}, path=log,
                                 previous=tmp_path / "previous.log", lock_path=tmp_path / "lock")
    assert elsewhere.read_text(encoding="utf-8") == "must remain untouched"


def test_active_version_is_only_semver(tmp_path):
    release = tmp_path / "0.2.5"
    release.mkdir()
    link = tmp_path / "luma"
    link.symlink_to(release, target_is_directory=True)
    assert diagnostics.active_version(link) == "0.2.5"
    link.unlink()
    other = tmp_path / "secret-token"
    other.mkdir()
    link.symlink_to(other, target_is_directory=True)
    assert diagnostics.active_version(link) == "unknown"
