import base64

from fastapi.testclient import TestClient

import luma.backup_api as backup_api
from luma.api import create_app
from luma.models import Theme
from luma.portable_backup import encrypt, snapshot


PASSWORD = "correct horse battery staple"
VOLUME = "a" * 32
BACKUP = "b" * 32


def _app(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    service.settings.voice_enabled = False
    service.settings.visible_calendar_ids = ["keep-calendar"]
    service.settings.phone_address = "AA:BB:CC:DD:EE:FF"
    service.storage.save_settings(service.settings)
    app.state.security.set_pin("1234")
    service.storage.set_secret("google.refresh", "KEEP_SECRET")
    archive = encrypt(snapshot(service.storage), PASSWORD)
    state = {"archive": archive, "writes": 0}

    async def broker(request):
        action = request["action"]
        if action == "scan":
            return {"volumes": [{"id": VOLUME, "label": "LUMA", "backups": []}]}
        if action == "list":
            return {"volumes": []}
        if action == "write":
            state["archive"] = base64.b64decode(request["archive"])
            state["writes"] += 1
            return {"verified": True, "created_at": "2026-09-28T12:00:00+00:00"}
        if action == "read":
            return {"archive": base64.b64encode(state["archive"]).decode()}
        if action == "eject":
            return {"ejected": True}
        raise AssertionError(action)

    monkeypatch.setattr(backup_api, "backup_request", broker)
    return app, state


def test_backup_routes_are_local_owner_gated_and_do_not_export_on_passphrase_mismatch(tmp_path, monkeypatch):
    app, state = _app(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post("/api/v1/backups/scan").status_code == 200
        mismatch = client.post("/api/v1/backups/export", json={
            "volume_id": VOLUME, "passphrase": PASSWORD, "confirm_passphrase": "wrong passphrase"})
        assert mismatch.status_code == 422 and state["writes"] == 0
        remote = TestClient(app, client=("192.0.2.1", 5000))
        remote.headers["X-Luma-Token"] = app.state.security.get_or_create_lan_token()
        assert remote.post("/api/v1/backups/scan").status_code == 403


def test_backup_export_preview_expiry_and_transactional_apply_preserve_pi_identity(tmp_path, monkeypatch):
    app, state = _app(tmp_path, monkeypatch)
    app.state.luma.settings.theme = Theme.HEARTH
    app.state.luma.settings.voice_enabled = False
    app.state.luma.storage.save_settings(app.state.luma.settings)
    with TestClient(app) as client:
        exported = client.post("/api/v1/backups/export", json={
            "volume_id": VOLUME, "passphrase": PASSWORD, "confirm_passphrase": PASSWORD,
            "games": {"snake": {"body": [1, 0], "food": 3, "head": 1, "score": 120,
                                 "best": 120, "pause": 0, "won": False}}})
        assert exported.status_code == 200 and exported.json()["verified"] is True
        assert state["writes"] == 1

        preview = client.post("/api/v1/backups/preview", json={
            "volume_id": VOLUME, "backup_id": BACKUP, "passphrase": PASSWORD})
        assert preview.status_code == 200
        preview_data = preview.json()
        assert preview_data["counts"]["game_checkpoints"] == 1
        assert "Google account and calendar links" in preview_data["preserved_here"]
        preview_id = preview_data["preview_id"]

        not_confirmed = client.post("/api/v1/backups/apply", json={"preview_id": preview_id, "confirmed": False})
        assert not_confirmed.status_code == 422
        applied = client.post("/api/v1/backups/apply", json={"preview_id": preview_id, "confirmed": True})
        assert applied.status_code == 200 and applied.json()["applied"] is True
        assert app.state.luma.settings.theme.value == "hearth"
        assert app.state.luma.settings.voice_enabled is False
        assert app.state.luma.settings.visible_calendar_ids == ["keep-calendar"]
        assert app.state.luma.settings.phone_address == "AA:BB:CC:DD:EE:FF"
        assert app.state.luma.storage.get_secret("google.refresh") == "KEEP_SECRET"
        assert applied.json()["games"]["snake"]["score"] == 120


def test_restore_preview_expires_and_wrong_passphrase_never_creates_session(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    clock = [10.0]
    monkeypatch.setattr(backup_api, "monotonic", lambda: clock[0])
    with TestClient(app) as client:
        wrong = client.post("/api/v1/backups/preview", json={
            "volume_id": VOLUME, "backup_id": BACKUP, "passphrase": "wrong horse battery staple"})
        assert wrong.status_code == 422
        opened = client.post("/api/v1/backups/preview", json={
            "volume_id": VOLUME, "backup_id": BACKUP, "passphrase": PASSWORD})
        assert opened.status_code == 200
        clock[0] = 311.0
        expired = client.post("/api/v1/backups/apply", json={
            "preview_id": opened.json()["preview_id"], "confirmed": True})
        assert expired.status_code == 410


def test_restore_endpoints_require_owner_unlock_after_initial_setup(tmp_path, monkeypatch):
    app, _ = _app(tmp_path, monkeypatch)
    app.state.luma.settings.onboarding_completed = True
    app.state.luma.display_clock_trusted = lambda: True
    with TestClient(app) as client:
        response = client.post("/api/v1/backups/scan")
        assert response.status_code == 403
        assert client.post("/api/v1/security/unlock", json={"pin": "1234"}).status_code == 200
        assert client.post("/api/v1/backups/scan").status_code == 200
