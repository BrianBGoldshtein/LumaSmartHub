from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from luma import update_api
from luma.api import create_app


def test_local_settings_flow_checks_reviews_and_installs_verified_release(monkeypatch, tmp_path):
    app = create_app(data_dir=tmp_path)
    archive = b"signed bundle bytes"
    monkeypatch.setattr(update_api, "latest_release", lambda current: {
        "state": "available", "current_version": current, "version": "0.3.0",
        "release_notes": "Keeps settings.\nFixes a bug.", "published_at": "2026-09-29T12:00:00Z",
        "release_url": "https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.0",
        "source_sha256": "a" * 64, "bundle": archive,
    })
    calls = []

    async def broker(request):
        calls.append(request)
        if request["action"] == "status":
            return {"state": "idle", "target_version": None, "message": ""}
        return {"accepted": True, "version": "0.3.0"}

    monkeypatch.setattr(update_api, "update_request", broker)
    with TestClient(app) as client:
        assert client.post('/api/v1/security/pin', json={'pin':'123456'}).status_code == 200
        status = client.get("/api/v1/updates/status")
        checked = client.post("/api/v1/updates/check")
        details = checked.json()
        installed = client.post("/api/v1/updates/install", json={"candidate_id": details["candidate_id"]})
        expired = client.post("/api/v1/updates/install", json={"candidate_id": details["candidate_id"]})

    assert status.status_code == 200 and status.json()["current_version"]
    assert checked.status_code == 200
    assert details["release_notes"] == "Keeps settings.\nFixes a bug."
    assert "bundle" not in details and details["version"] == "0.3.0"
    assert installed.status_code == 202
    assert calls[-1] == {"action": "install", "bundle": base64.b64encode(archive).decode()}
    assert expired.status_code == 410


def test_update_install_requires_a_reviewed_candidate_and_rejects_extra_fields(monkeypatch, tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app) as client:
        assert client.post('/api/v1/security/pin', json={'pin':'123456'}).status_code == 200
        missing = client.post("/api/v1/updates/install", json={"candidate_id": "a" * 40})
        extra = client.post("/api/v1/updates/install", json={"candidate_id": "a" * 40, "bundle": "x"})
    assert missing.status_code == 410
    assert extra.status_code == 422


def test_github_update_endpoints_are_local_only(tmp_path):
    app = create_app(data_dir=tmp_path)
    with TestClient(app, base_url="http://luma.local") as client:
        response = client.get("/api/v1/updates/status")
    assert response.status_code == 403
