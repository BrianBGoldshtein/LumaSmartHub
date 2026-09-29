from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.network import NetworkManager, ROOT, NM, connection_settings, security_kind, validate_request

DEVICE = ROOT + "/Devices/2"
AP = ROOT + "/AccessPoint/1"
REQUEST = {"action": "connect", "device": DEVICE, "access_point": AP, "password": "testing123"}
PROPS = {"Ssid": b"Home: Wi-Fi", "Mode": 2, "Flags": 1, "RsnFlags": 0x100}


@pytest.mark.asyncio
async def test_scan_waits_until_networkmanager_reports_scan_complete():
    manager = NetworkManager(None)
    root = AsyncMock()
    root.call_get_devices.return_value = [DEVICE]
    wifi = AsyncMock()
    wifi.call_request_scan.return_value = None
    wifi.call_get_access_points.return_value = [AP]
    manager.interface = AsyncMock(side_effect=lambda path, name: root if path == ROOT else wifi)
    manager.properties = AsyncMock(side_effect=[
        {"WirelessEnabled": True, "WirelessHardwareEnabled": True, "Connectivity": 1},
        {"DeviceType": 2},
        {"LastScan": 100},
        {"LastScan": 100},  # NetworkManager has not finished yet.
        {"LastScan": 101},  # LastScan advances only after scan completion.
        {"LastScan": 101, "ActiveAccessPoint": "/"},
        {**PROPS, "Strength": 83},
    ])

    result = await manager.scan()

    assert wifi.call_request_scan.await_count == 1
    assert result["scan_complete"] is True
    assert result["wifi_device_count"] == 1
    assert result["networks"][0]["ssid"] == "Home: Wi-Fi"


@pytest.mark.asyncio
async def test_scan_reports_timeout_instead_of_claiming_it_saw_no_networks(monkeypatch):
    from luma import network

    monkeypatch.setattr(network, "SCAN_TIMEOUT_SECONDS", 0)
    manager = NetworkManager(None)
    root = AsyncMock()
    root.call_get_devices.return_value = [DEVICE]
    wifi = AsyncMock()
    wifi.call_get_access_points.return_value = []
    manager.interface = AsyncMock(side_effect=lambda path, name: root if path == ROOT else wifi)
    manager.properties = AsyncMock(side_effect=[
        {"WirelessEnabled": True, "WirelessHardwareEnabled": True, "Connectivity": 1},
        {"DeviceType": 2},
        {"LastScan": -1},
        {"LastScan": -1},
        {"LastScan": -1, "ActiveAccessPoint": "/"},
    ])

    result = await manager.scan()

    assert result["scan_complete"] is False
    assert result["wifi_device_count"] == 1
    assert result["networks"] == []


@pytest.mark.parametrize("payload", [None, {}, {"action": "shell"}, {"action": "scan", "command": "reboot"}, {**REQUEST, "device": "/etc/passwd"}, {**REQUEST, "access_point": ROOT + "/AccessPoint/1/../../"}, {**REQUEST, "password": "x\nsecret"}, {**REQUEST, "password": "x" * 65}])
def test_wifi_rejects_unbounded_or_arbitrary_operations(payload):
    with pytest.raises(ValueError):
        validate_request(payload)


def test_profiles_preserve_exact_ssid_bytes_and_only_supported_settings():
    settings = connection_settings(PROPS, "testing123")
    assert settings["802-11-wireless"]["ssid"].value == b"Home: Wi-Fi"
    assert settings["802-11-wireless-security"]["psk"].value == "testing123"
    assert settings["802-11-wireless-security"]["key-mgmt"].value == "wpa-psk"
    assert settings["ipv4"]["method"].value == "auto"
    assert "proxy" not in settings
    assert security_kind({**PROPS, "RsnFlags": 0x500}) == "sae"
    assert security_kind({**PROPS, "RsnFlags": 0x200}) == "unsupported"
    assert security_kind({**PROPS, "RsnFlags": 0, "WpaFlags": 0x100}) == "unsupported"


@pytest.mark.parametrize("password", ["short", "x" * 64, "é" * 8])
def test_wpa2_rejects_invalid_credentials(password):
    with pytest.raises(ValueError):
        connection_settings(PROPS, password)


def test_wpa2_hex_and_open_networks():
    connection_settings(PROPS, "a" * 64)
    open_ap = {**PROPS, "RsnFlags": 0, "Flags": 0}
    assert "802-11-wireless-security" not in connection_settings(open_ap, "")
    with pytest.raises(ValueError):
        connection_settings(open_ap, "password")


def fake_manager(state=2):
    manager = NetworkManager(None)
    connection = AsyncMock()
    connection.call_add_and_activate_connection2.return_value = (ROOT + "/Settings/1", ROOT + "/ActiveConnection/1", {})
    manager.interface = AsyncMock(return_value=connection)
    manager.scan = AsyncMock(return_value={"networks": [{"device": DEVICE, "access_point": AP, "connected": False}]})
    manager.properties = AsyncMock(side_effect=[PROPS, {"State": state}])
    return manager, connection


@pytest.mark.asyncio
async def test_success_waits_for_activation_before_saving_credentials():
    manager, connection = fake_manager()
    assert (await manager.connect(REQUEST))["connected"]
    args = connection.call_add_and_activate_connection2.call_args.args
    assert args[3]["persist"].value == "memory"
    assert args[1:3] == (DEVICE, AP)
    connection.call_save.assert_awaited_once()
    connection.call_delete.assert_not_called()


@pytest.mark.asyncio
async def test_failed_activation_removes_only_the_new_unsaved_profile():
    manager, connection = fake_manager(state=4)
    with pytest.raises(ValueError):
        await manager.connect(REQUEST)
    connection.call_delete.assert_awaited_once()
    connection.call_save.assert_not_called()
    assert manager.interface.call_args.args == (ROOT + "/Settings/1", NM + ".Settings.Connection")


@pytest.mark.asyncio
async def test_disappeared_access_point_cannot_trigger_connection_changes():
    manager, connection = fake_manager()
    manager.scan.return_value = {"networks": []}
    with pytest.raises(ValueError):
        await manager.connect(REQUEST)
    connection.call_add_and_activate_connection2.assert_not_called()


def test_network_api_local_only_even_with_valid_lan_token(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    broker = AsyncMock(return_value={"networks": []})
    monkeypatch.setattr("luma.api.network_request", broker)
    local = TestClient(app)
    token = local.get("/api/v1/security/lan-token").json()["token"]
    remote = TestClient(app, client=("192.168.1.2", 4321))
    assert remote.post("/api/v1/network", json={"action": "scan"}, headers={"X-Luma-Token": token}).status_code == 403
    assert local.post("/api/v1/network", json={"action": "scan"}, headers={"Origin": "https://attacker.example"}).status_code == 403
    broker.assert_not_called()
    assert local.post("/api/v1/network", json={"action": "scan"}).status_code == 200
    broker.assert_awaited_once()


def test_invalid_api_requests_never_echo_passwords(tmp_path, monkeypatch):
    client = TestClient(create_app(data_dir=tmp_path))
    broker = AsyncMock()
    monkeypatch.setattr("luma.api.network_request", broker)
    secret = "secret-that-must-not-be-returned"
    for data in [{**REQUEST, "password": secret * 3}, {"action": "scan", "password": secret}]:
        response = client.post("/api/v1/network", json=data)
        assert response.status_code == 422
        assert secret not in response.text
    response = client.post("/api/v1/network", content=b"x" * 2049)
    assert response.status_code == 413
    broker.assert_not_called()
