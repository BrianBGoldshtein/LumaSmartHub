"""Full temporary Linux UDS broker → real backup API/media integration.

This uses a temporary directory as synthetic USB media. It does not mount,
discover, eject, or write any actual removable disk.
"""
import asyncio
from datetime import UTC, datetime
import os
import socket
import subprocess
import sys

try:
    import pwd
except ImportError:  # Windows collects the test but skips its POSIX body.
    pwd = None

import httpx
import pytest

import luma.backup_broker as backup_broker
from luma.api import create_app
from luma.backup_media import BackupMedia, RemovableVolume
from luma.models import Theme


VOLUME_ID = "a" * 32
PASSWORD = "integration test passphrase"


def test_broker_cold_import_does_not_load_room_integrations():
    """The root socket worker must stay independent of cloud/device SDK imports."""
    result = subprocess.run(
        [sys.executable, "-c", (
            "import sys; import luma.backup_broker; "
            "assert not any(name == 'luma.scenes' or name.startswith('luma.scenes.') "
            "or name == 'luma.purifier_adapter' or name.startswith('pyvesync') "
            "for name in sys.modules)"
        )],
        capture_output=True, text=True, timeout=15,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")),
            os.environ.get("PYTHONPATH", ""),
        )))},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "linux", reason="Unix socket and peer credentials require Linux")
async def test_packaged_socket_protocol_media_and_owner_api_round_trip(tmp_path, monkeypatch):
    """Exercise real UDS framing, SO_PEERCRED, encrypted media, API preview/apply/eject."""
    socket_path = tmp_path / "luma-backup.sock"
    media_root = tmp_path / "synthetic-usb"
    media_root.mkdir()
    stat = media_root.stat()
    volume = RemovableVolume(
        id=VOLUME_ID,
        label="Synthetic USB",
        mount_root=media_root,
        device_node="/dev/synthetic-usb",
        filesystem_device=(os.major(stat.st_dev), os.minor(stat.st_dev)),
        require_mountpoint=False,
    )

    class Inventory:
        def __init__(self):
            self.scans = 0

        def scan(self, *, mount):
            assert mount is True
            self.scans += 1
            return [volume]

        def current_volumes(self):
            return [volume]

    inventory = Inventory()
    powered_off = []
    media = BackupMedia(lambda: inventory.current_volumes(), power_off=powered_off.append,
                        now=lambda: datetime(2026, 9, 28, 18, 0, 0, tzinfo=UTC))
    broker = backup_broker.BackupBroker(inventory=inventory, media=media)

    # The Linux qualification host does not provision the appliance's `luma`
    # account. Preserve the real SO_PEERCRED UID read while mapping the expected
    # service name to this isolated test process only.
    real_getpwnam = pwd.getpwnam
    current_user = pwd.getpwuid(os.geteuid())
    monkeypatch.setattr(pwd, "getpwnam", lambda name: current_user if name == "luma" else real_getpwnam(name))

    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    listener.listen(8)
    monkeypatch.setattr(backup_broker, "SOCKET", str(socket_path))

    app = create_app(data_dir=tmp_path / "luma-data")
    app.state.luma.settings.theme = Theme.HEARTH
    app.state.luma.settings.voice_enabled = False
    app.state.luma.settings.visible_calendar_ids = ["private-calendar"]
    app.state.luma.settings.phone_address = "AA:BB:CC:DD:EE:FF"
    app.state.luma.storage.save_settings(app.state.luma.settings)
    app.state.luma.storage.set_secret("google.refresh", "sentinel-secret")

    broker_task = asyncio.create_task(backup_broker._serve_listener(listener, broker))
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
                scanned = await client.post("/api/v1/backups/scan")
                assert scanned.status_code == 200
                assert scanned.json()["volumes"] == [{"id": VOLUME_ID, "label": "Synthetic USB", "backups": []}]
                assert inventory.scans == 1

                games = {"snake": {"body": [1, 0], "food": 3, "head": 1, "score": 120,
                                    "best": 120, "pause": 0, "won": False}}
                exported = await client.post("/api/v1/backups/export", json={
                    "volume_id": VOLUME_ID, "passphrase": PASSWORD,
                    "confirm_passphrase": PASSWORD, "games": games,
                })
                assert exported.status_code == 200 and exported.json()["verified"] is True
                assert len(list((media_root / "Luma Backups").iterdir())) == 1

                listed = await client.get("/api/v1/backups/media")
                entry = listed.json()["volumes"][0]["backups"][0]
                assert entry["id"] and entry["created_at"]
                preview = await client.post("/api/v1/backups/preview", json={
                    "volume_id": VOLUME_ID, "backup_id": entry["id"], "passphrase": PASSWORD,
                })
                assert preview.status_code == 200
                assert preview.json()["counts"]["game_checkpoints"] == 1
                assert "Google account and calendar links" in preview.json()["preserved_here"]
                applied = await client.post("/api/v1/backups/apply", json={
                    "preview_id": preview.json()["preview_id"], "confirmed": True,
                })
                assert applied.status_code == 200 and applied.json()["games"] == games

                service = app.state.luma
                assert service.settings.theme is Theme.HEARTH
                assert service.settings.voice_enabled is False
                assert service.settings.visible_calendar_ids == ["private-calendar"]
                assert service.settings.phone_address == "AA:BB:CC:DD:EE:FF"
                assert service.storage.get_secret("google.refresh") == "sentinel-secret"
                ejected = await client.post("/api/v1/backups/eject", json={"volume_id": VOLUME_ID})
                assert ejected.status_code == 200 and ejected.json() == {"ejected": True}
                assert powered_off == ["/dev/synthetic-usb"]
    finally:
        broker_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await broker_task
