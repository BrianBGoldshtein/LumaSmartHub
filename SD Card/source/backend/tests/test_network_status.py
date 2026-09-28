from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.network import NetworkManager, network_request, validate_request
from luma.network_runtime import NetworkRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize("value,expected", [(0, "unknown"), (1, "offline"), (2, "portal"), (3, "limited"), (4, "online"), (999, "unknown")])
async def test_status_is_bounded_and_never_scans_or_modifies_connections(value, expected):
    manager = NetworkManager(None)
    manager.properties = AsyncMock(return_value={"Connectivity": value, "ConnectivityCheckAvailable": True, "ConnectivityCheckEnabled": True, "State": 70})
    manager.interface = AsyncMock()
    result = await manager.execute({"action": "status"})
    assert result == {"state": expected, "checking_enabled": True}
    manager.interface.assert_not_called()
    assert len(result) == 2  # No SSIDs, IPs or account information in the status.


@pytest.mark.asyncio
async def test_disabled_probe_cannot_claim_internet_even_when_nm_reports_full():
    manager = NetworkManager(None)
    manager.properties = AsyncMock(return_value={"Connectivity": 4, "State": 70})
    assert (await manager.status())["state"] == "unknown"
    manager.properties.return_value["State"] = 20
    assert (await manager.status())["state"] == "offline"


@pytest.mark.asyncio
async def test_explicit_recheck_uses_nm_check_not_wifi_scan():
    manager = NetworkManager(None)
    proxy = AsyncMock()
    manager.interface = AsyncMock(return_value=proxy)
    manager.properties = AsyncMock(return_value={"Connectivity": 2, "ConnectivityCheckAvailable": True, "ConnectivityCheckEnabled": True})
    assert (await manager.execute({"action": "check"}))["state"] == "portal"
    proxy.call_check_connectivity.assert_awaited_once()
    proxy.call_get_devices.assert_not_called()
    with pytest.raises(ValueError):
        validate_request({"action": "check", "uri": "http://attacker.example"})


@pytest.mark.asyncio
async def test_runtime_debounces_outages_and_clears_on_recovery(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("luma.network_runtime.monotonic", lambda: clock[0])
    request = AsyncMock(return_value={"state": "online", "checking_enabled": True})
    runtime = NetworkRuntime(request)
    assert runtime.snapshot()["stale"]
    await runtime.poll()
    assert runtime.snapshot()["state"] == "online"
    request.return_value["state"] = "portal"
    await runtime.poll()
    assert runtime.snapshot()["state"] == "online"
    await runtime.poll()
    assert runtime.snapshot()["state"] == "portal"
    request.return_value["state"] = "online"
    await runtime.poll()
    assert runtime.snapshot()["state"] == "online"
    clock[0] += 101
    assert runtime.snapshot()["state"] == "unknown"
    assert runtime.snapshot()["stale"]
    assert all(call.args == ({"action": "status"},) for call in request.call_args_list)


@pytest.mark.asyncio
async def test_runtime_service_failure_does_not_claim_portal_or_keep_online():
    request = AsyncMock(return_value={"state": "online", "checking_enabled": True})
    runtime = NetworkRuntime(request)
    await runtime.poll()
    request.side_effect = ValueError("private third-party detail")
    await runtime.poll()
    assert runtime.snapshot()["state"] == "unavailable"
    assert "private" not in str(runtime.snapshot())


def test_status_api_remains_local_and_does_not_expose_settings(tmp_path):
    app = create_app(data_dir=tmp_path)
    local = TestClient(app)
    status = local.get("/api/v1/network/status").json()
    assert status["state"] == "unknown"
    assert set(status) == {"state", "checked_at", "stale", "checking_enabled"}
    remote = TestClient(app, client=("192.168.1.8", 4200))
    token = app.state.security.get_or_create_lan_token()
    assert remote.get("/api/v1/network/status", headers={"X-Luma-Token": token}).status_code == 403
    assert local.get("/api/v1/network/status", headers={"Origin": "https://attacker.example"}).status_code == 403


@pytest.mark.asyncio
async def test_non_linux_preview_degrades_without_crashing_background_workers(monkeypatch):
    monkeypatch.delattr("asyncio.open_unix_connection", raising=False)
    with pytest.raises(ValueError, match="Linux appliance"):
        await network_request({"action": "status"})
