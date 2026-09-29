from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.network import HOTSPOT_SSID, NetworkManager, ROOT, NM, connection_settings, hotspot_connection_settings, security_kind, validate_request

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


@pytest.mark.parametrize("payload", [None, {}, {"action": "shell"}, {"action": "scan", "command": "reboot"}, {**REQUEST, "device": "/etc/passwd"}, {**REQUEST, "access_point": ROOT + "/AccessPoint/1/../../"}, {**REQUEST, "password": "x\nsecret"}, {**REQUEST, "password": "x" * 65}, {"action": "hotspot-start", "password": "1234567"}, {"action": "hotspot-start", "password": "1234abcd"}, {"action": "hotspot-stop", "password": "leak"}])
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


def test_hotspot_profile_is_fixed_2_4ghz_wpa2_and_networkmanager_shared_nat():
    settings = hotspot_connection_settings("01234567", "wlan1")
    assert settings["802-11-wireless"]["ssid"].value == HOTSPOT_SSID.encode()
    assert settings["802-11-wireless"]["mode"].value == "ap"
    assert settings["802-11-wireless"]["band"].value == "bg"
    assert settings["802-11-wireless"]["channel"].value == 6
    assert settings["802-11-wireless-security"]["psk"].value == "01234567"
    assert settings["ipv4"]["method"].value == "shared"
    assert settings["ipv6"]["method"].value == "disabled"
    assert settings["connection"]["interface-name"].value == "wlan1"
    assert settings["connection"]["id"].value.endswith("[PIN]")
    separate = hotspot_connection_settings("a-stronger-passphrase", "wlx001122334455", same_as_pin=False)
    assert separate["connection"]["id"].value.endswith("[separate key]")
    assert separate["802-11-wireless-security"]["psk"].value == "a-stronger-passphrase"
    with pytest.raises(ValueError):
        hotspot_connection_settings("12345678", "wlan0;reboot")


def test_hotspot_broker_accepts_only_a_fixed_owner_selected_profile():
    payload = {"action": "hotspot-start", "password": "12345678", "same_as_pin": True}
    assert validate_request(payload) == payload
    custom = {"action": "hotspot-start", "password": "stronger-wifi-key", "same_as_pin": False}
    assert validate_request(custom) == custom
    for invalid in (
        {**payload, "same_as_pin": "true"},
        {**payload, "unexpected": "field"},
        {**payload, "password": "pässword"},
        {**payload, "password": "1234567"},
    ):
        with pytest.raises(ValueError):
            validate_request(invalid)


@pytest.mark.asyncio
async def test_hotspot_status_requires_an_independent_radio_and_active_wifi_uplink():
    manager = NetworkManager(None)
    manager.wifi_radios = AsyncMock(return_value=[
        {"path": DEVICE, "name": "wlan0", "phy": "phy0", "can_ap": True, "station": True},
    ])
    manager.hotspot_profile = AsyncMock(return_value=None)
    status = await manager.hotspot_status()
    assert status["upstream_connected"] is True
    assert status["can_enable"] is False
    assert "second" in status["reason"]

    manager.wifi_radios.return_value.append(
        {"path": ROOT + "/Devices/3", "name": "wlan1", "phy": "phy1", "can_ap": True, "station": False},
    )
    status = await manager.hotspot_status()
    assert status["can_enable"] is True
    assert status["ssid"] == HOTSPOT_SSID


@pytest.mark.asyncio
async def test_wifi_radio_capability_detection_requires_2_4ghz_when_reported(monkeypatch):
    from luma import network

    manager = NetworkManager(None)
    root = AsyncMock()
    root.call_get_devices.return_value = [DEVICE, ROOT + "/Devices/3"]
    manager.interface = AsyncMock(return_value=root)
    manager.properties = AsyncMock(side_effect=[
        {"DeviceType": 2, "Interface": "wlan0", "State": 100},
        {"WirelessCapabilities": 0x40 | 0x100 | 0x200, "Mode": 2, "ActiveAccessPoint": AP},
        {"DeviceType": 2, "Interface": "wlan1", "State": 30},
        {"WirelessCapabilities": 0x40 | 0x100 | 0x400, "Mode": 0, "ActiveAccessPoint": "/"},
    ])
    monkeypatch.setattr(network, "wifi_phy", lambda name: "phy0" if name == "wlan0" else "phy1")
    radios = await manager.wifi_radios()
    assert radios[0]["station"] is True
    assert radios[0]["can_ap"] is True
    assert radios[1]["can_ap"] is False


@pytest.mark.asyncio
async def test_hotspot_status_detects_only_our_active_networkmanager_profile():
    manager = NetworkManager(None)
    manager.wifi_radios = AsyncMock(return_value=[
        {"path": DEVICE, "name": "wlan0", "phy": "phy0", "can_ap": True, "station": True},
        {"path": ROOT + "/Devices/3", "name": "wlan1", "phy": "phy1", "can_ap": True, "station": False},
    ])
    manager.hotspot_profile = AsyncMock(return_value=ROOT + "/Settings/3")
    manager.hotspot_uses_pin = AsyncMock(return_value=False)
    manager.properties = AsyncMock(side_effect=[
        {"ActiveConnections": [ROOT + "/ActiveConnection/3"]},
        {"Connection": ROOT + "/Settings/3", "State": 2},
    ])
    status = await manager.hotspot_status()
    assert status["configured"] is True
    assert status["active"] is True
    assert status["same_as_pin"] is False


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
    for data in [{**REQUEST, "password": secret * 3}, {"action": "scan", "password": secret},
                 {"action": "hotspot-start", "password": "12345678", "same_as_pin": True}]:
        response = client.post("/api/v1/network", json=data)
        assert response.status_code == 422
        assert secret not in response.text
    response = client.post("/api/v1/network", content=b"x" * 2049)
    assert response.status_code == 413
    broker.assert_not_called()


def test_hotspot_api_requires_local_owner_pin_and_exact_wpa2_length(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    broker = AsyncMock(return_value={"ssid": HOTSPOT_SSID, "configured": True, "active": True,
                                     "upstream_connected": True, "can_enable": True, "reason": "Ready."})
    monkeypatch.setattr("luma.api.network_request", broker)

    assert client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "12345678"}).status_code == 422
    assert client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "12345678",
                                                        "stanford_permission_confirmed": True}).status_code == 409
    app.state.security.set_pin("1234")
    assert client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "9999",
                                                        "stanford_permission_confirmed": True}).status_code == 401
    short_pin = client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "1234",
                                                             "stanford_permission_confirmed": True})
    assert short_pin.status_code == 422
    assert "eight-digit" in short_pin.json()["detail"]
    app.state.security.set_pin("01234567")
    response = client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "01234567",
                                                            "stanford_permission_confirmed": True})
    assert response.status_code == 200
    assert "password" not in response.text
    broker.assert_awaited_once_with({"action": "hotspot-start", "password": "01234567", "same_as_pin": True})

    broker.reset_mock()
    custom_key = "unique-passphrase-2026"
    response = client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "01234567",
                                                              "same_as_pin": False, "wifi_password": custom_key,
                                                              "stanford_permission_confirmed": True})
    assert response.status_code == 200
    assert custom_key not in response.text
    broker.assert_awaited_once_with({"action": "hotspot-start", "password": custom_key, "same_as_pin": False})

    response = client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "01234567",
                                                              "same_as_pin": False, "wifi_password": "too-short",
                                                              "stanford_permission_confirmed": True})
    assert response.status_code == 422
    assert custom_key not in response.text

    oversized_key = "sensitive-" + "x" * 70
    response = client.post("/api/v1/network/hotspot", json={"action": "enable", "pin": "01234567",
                                                              "same_as_pin": False, "wifi_password": oversized_key,
                                                              "stanford_permission_confirmed": True})
    assert response.status_code == 422
    assert oversized_key not in response.text

    remote = TestClient(app, client=("192.0.2.20", 4000))
    token = app.state.security.get_or_create_lan_token()
    assert remote.post("/api/v1/network/hotspot", json={"action": "disable", "pin": "01234567"},
                       headers={"X-Luma-Token": token}).status_code == 403
    assert broker.await_count == 1


def test_hotspot_can_use_a_strong_separate_key_with_a_shorter_luma_pin(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    app.state.security.set_pin("1234")
    client = TestClient(app)
    broker = AsyncMock(return_value={"ssid": HOTSPOT_SSID, "configured": True, "active": True,
                                     "same_as_pin": False, "upstream_connected": True,
                                     "can_enable": True, "reason": "Ready."})
    monkeypatch.setattr("luma.api.network_request", broker)
    key = "separate-strong-wifi-key"
    response = client.post("/api/v1/network/hotspot", json={
        "action": "enable", "pin": "1234", "same_as_pin": False, "wifi_password": key,
        "stanford_permission_confirmed": True,
    })
    assert response.status_code == 200
    assert key not in response.text
    broker.assert_awaited_once_with({"action": "hotspot-start", "password": key, "same_as_pin": False})


def test_hotspot_status_is_local_only_and_never_cacheable(tmp_path, monkeypatch):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    broker = AsyncMock(return_value={"ssid": HOTSPOT_SSID, "configured": False, "active": False,
                                     "same_as_pin": None, "upstream_connected": False,
                                     "can_enable": False, "reason": "Connect first."})
    monkeypatch.setattr("luma.api.network_request", broker)
    response = client.get("/api/v1/network/hotspot")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    remote = TestClient(app, client=("192.0.2.20", 4000))
    token = app.state.security.get_or_create_lan_token()
    assert remote.get("/api/v1/network/hotspot", headers={"X-Luma-Token": token}).status_code == 403
    broker.assert_awaited_once_with({"action": "hotspot-status"})
