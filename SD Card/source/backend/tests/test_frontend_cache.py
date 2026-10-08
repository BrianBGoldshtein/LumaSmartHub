from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app


@pytest.fixture
def frontend_client(tmp_path: Path):
    frontend = tmp_path / "frontend"
    assets = frontend / "assets"
    assets.mkdir(parents=True)
    (frontend / "index.html").write_text('<script src="/assets/release-a.js"></script>')
    (frontend / "help.html").write_text("<h1>Help</h1>")
    (assets / "release-a.js").write_text("window.release='a';")
    app = create_app(data_dir=tmp_path / "data", frontend_dir=frontend)
    with TestClient(app) as client:
        yield client, frontend


@pytest.mark.parametrize("path", ["/", "/?setup=google", "/index.html", "/help.html", "/dashboard/settings"])
def test_html_entry_points_are_not_cached(frontend_client, path):
    client, _ = frontend_client
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("text/html")


def test_fresh_setup_url_loads_the_new_entry_point_without_resetting_settings(frontend_client):
    client, frontend = frontend_client
    before = client.get("/?setup=google&ui_refresh=1")
    client.patch("/api/v1/settings", json={"theme": "hearth", "volume": 42})
    (frontend / "index.html").write_text('<script src="/assets/release-b.js"></script>')
    after = client.get("/?setup=google&ui_release=0.2.11&ui_refresh=2", headers={"If-None-Match": before.headers["etag"]})
    assert after.status_code == 200
    assert "release-b.js" in after.text
    assert after.headers["cache-control"] == "no-store"
    settings = client.get("/api/v1/settings").json()
    assert settings["theme"] == "hearth"
    assert settings["volume"] == 42


def test_hashed_assets_and_api_routes_keep_their_existing_behavior(frontend_client):
    client, _ = frontend_client
    asset = client.get("/assets/release-a.js")
    assert asset.status_code == 200
    assert asset.text == "window.release='a';"
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
