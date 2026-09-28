import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from dbus_next import DBusError
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.pairing import BlueZPairing, PairingFlow, device_choices
from luma.pairing_agent import PairingAgent

ADAPTER = "/org/bluez/hci0"
DEVICE = ADAPTER + "/dev_AA_BB_CC_DD_EE_FF"
ADDRESS = "AA:BB:CC:DD:EE:FF"


class FakeDriver:
    adapter = ADAPTER

    def __init__(self, paired=False, trusted=False):
        self.props = {"Address": ADDRESS, "Alias": "My iPhone", "Adapter": ADAPTER, "Paired": paired, "Bonded": paired, "Trusted": trusted}
        self.open = AsyncMock()
        self.start_scan = AsyncMock()
        self.stop_scan = AsyncMock()
        self.close = AsyncMock()
        self.cancel_pair = AsyncMock()
        self.pair_calls = 0
        self.trust_calls = 0

    async def objects(self):
        return {DEVICE: {"org.bluez.Device1": self.props}}

    async def properties(self, path):
        assert path == DEVICE
        return dict(self.props)

    async def pair(self, path, confirm):
        self.pair_calls += 1
        if not await confirm(path, 42817):
            raise ValueError("Rejected")
        self.props.update(Paired=True, Bonded=True)

    async def trust(self, path):
        self.trust_calls += 1
        assert self.props["Bonded"]
        self.props["Trusted"] = True


async def until(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("Pairing did not reach expected state")


async def select_phone(flow):
    flow.start()
    await until(lambda: bool(flow.devices))
    flow.select(flow.session, DEVICE)


def test_choices_only_include_real_devices_from_the_selected_adapter():
    props = FakeDriver().props
    objects = {DEVICE: {"org.bluez.Device1": {**props, "Alias": "iPhone\n\x00"}},
               ADAPTER + "/dev_bad": {"org.bluez.Device1": {**props, "Address": "bad"}},
               "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF": {"org.bluez.Device1": {**props, "Adapter": "/org/bluez/hci1"}}}
    choices = device_choices(objects, ADAPTER)
    assert len(choices) == 1 and choices[0]["name"] == "iPhone"
    assert choices[0]["path"] == DEVICE


@pytest.mark.asyncio
async def test_new_phone_is_only_trusted_and_saved_after_matching_code():
    driver, save = FakeDriver(), Mock()
    flow = PairingFlow(save, lambda: driver)
    await select_phone(flow)
    await until(lambda: flow.phase == "confirming")
    assert flow.snapshot()["passkey"] == "042817"
    assert driver.trust_calls == 0
    save.assert_not_called()
    flow.confirm(flow.session, flow.challenge, True)
    await flow.task
    assert flow.phase == "complete" and flow.passkey is None
    assert driver.trust_calls == 1
    save.assert_called_once_with(ADDRESS)
    driver.stop_scan.assert_awaited_once()
    driver.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_rejection_never_changes_phone_or_trust():
    driver, save = FakeDriver(), Mock()
    flow = PairingFlow(save, lambda: driver)
    await select_phone(flow)
    await until(lambda: flow.phase == "confirming")
    flow.confirm(flow.session, flow.challenge, False)
    await flow.task
    assert flow.phase == "error" and flow.passkey is None
    save.assert_not_called()
    assert driver.trust_calls == 0
    driver.cancel_pair.assert_awaited_once_with(DEVICE)


@pytest.mark.asyncio
async def test_cancel_clears_code_and_closes_owned_discovery_and_agent():
    driver, save = FakeDriver(), Mock()
    flow = PairingFlow(save, lambda: driver)
    await select_phone(flow)
    await until(lambda: flow.phase == "confirming")
    await flow.cancel(flow.session)
    assert flow.phase == "cancelled" and flow.passkey is None
    assert driver.trust_calls == 0
    save.assert_not_called()
    driver.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_immediate_cancel_before_worker_starts_does_not_leave_scanning_ui():
    driver = FakeDriver()
    flow = PairingFlow(Mock(), lambda: driver)
    flow.start()
    await flow.cancel(flow.session)
    assert flow.phase == "cancelled" and flow.task.done()
    driver.open.assert_not_called()
    flow.start()
    await flow.close()


@pytest.mark.asyncio
async def test_trusted_existing_bond_can_be_selected_without_repairing():
    driver, save = FakeDriver(paired=True, trusted=True), Mock()
    flow = PairingFlow(save, lambda: driver)
    await select_phone(flow)
    await flow.task
    assert flow.phase == "complete" and driver.pair_calls == 0
    save.assert_called_once_with(ADDRESS)


@pytest.mark.asyncio
async def test_untrusted_partial_bond_cannot_bypass_code_confirmation_on_retry():
    driver, save = FakeDriver(paired=True), Mock()
    flow = PairingFlow(save, lambda: driver)
    await select_phone(flow)
    await flow.task
    assert flow.phase == "error" and "unfinished" in flow.message
    assert driver.trust_calls == 0 and driver.pair_calls == 0
    save.assert_not_called()


@pytest.mark.asyncio
async def test_sessions_and_challenges_reject_stale_or_unsolicited_approvals():
    driver = FakeDriver()
    flow = PairingFlow(Mock(), lambda: driver)
    flow.start()
    await until(lambda: bool(flow.devices))
    with pytest.raises(ValueError):
        flow.start()
    with pytest.raises(ValueError):
        flow.select("wrong-session", DEVICE)
    with pytest.raises(ValueError):
        flow.select(flow.session, ADAPTER + "/dev_00_11_22_33_44_55")
    flow.select(flow.session, DEVICE)
    await until(lambda: flow.phase == "confirming")
    with pytest.raises(ValueError):
        flow.confirm(flow.session, "old-code", True)
    assert not await flow.request_confirmation("other-device", 123456)
    await flow.close()
    with pytest.raises(ValueError):
        flow.confirm(flow.session, "old-code", True)


@pytest.mark.asyncio
async def test_scan_expires_and_closes_without_a_selection(monkeypatch):
    times = iter([0, 46])
    monkeypatch.setattr("luma.pairing.monotonic", lambda: next(times))
    driver, save = FakeDriver(), Mock()
    flow = PairingFlow(save, lambda: driver)
    flow.start()
    await flow.task
    assert flow.phase == "expired"
    driver.close.assert_awaited_once()
    save.assert_not_called()


@pytest.mark.asyncio
async def test_agent_rejects_just_works_other_devices_and_unrelated_services():
    confirm = AsyncMock(return_value=True)
    agent = PairingAgent(DEVICE, confirm)
    with pytest.raises(DBusError):
        agent.RequestAuthorization(DEVICE)
    with pytest.raises(DBusError):
        agent.AuthorizeService(DEVICE, "audio-uuid")
    with pytest.raises(DBusError):
        await agent.RequestConfirmation.__wrapped__(agent, "other-device", 123456)
    confirm.assert_not_called()
    await agent.RequestConfirmation.__wrapped__(agent, DEVICE, 42817)
    assert agent.confirmed
    assert agent.introspect().name == "org.bluez.Agent1"
    agent.Cancel()
    with pytest.raises(DBusError):
        await agent.RequestConfirmation.__wrapped__(agent, DEVICE, 42817)


@pytest.mark.asyncio
async def test_bluez_pair_never_requests_default_agent_or_trusts_silently():
    driver = BlueZPairing()
    driver.bus = Mock()
    proxy = AsyncMock()
    driver.interface = AsyncMock(return_value=proxy)
    with pytest.raises(ValueError, match="not confirmed"):
        await driver.pair(DEVICE, AsyncMock(return_value=True))
    proxy.call_register_agent.assert_awaited_once_with(driver.agent_path, "DisplayYesNo")
    proxy.call_request_default_agent.assert_not_called()
    proxy.call_set.assert_not_called()
    await driver.close()
    proxy.call_unregister_agent.assert_awaited_once()
    driver.bus.disconnect.assert_called_once()


@pytest.mark.parametrize("path,body", [("", None), ("/start", {}), ("/select", {"session": "x" * 36, "device": DEVICE}), ("/confirm", {"session": "x" * 36, "challenge": "x" * 36, "accepted": True}), ("/cancel", {"session": "x" * 36})])
def test_pairing_routes_reject_lan_and_cross_origin(tmp_path, path, body):
    app = create_app(data_dir=tmp_path)
    remote = TestClient(app, client=("192.168.1.2", 4200))
    local = TestClient(app)
    method = "GET" if not path else "POST"
    url = "/api/v1/bluetooth/pairing" + path
    token = app.state.security.get_or_create_lan_token()
    assert remote.request(method, url, json=body, headers={"X-Luma-Token": token}).status_code == 403
    assert local.request(method, url, json=body, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert app.state.pairing.session is None


def test_successful_pairing_selection_does_not_itself_unlock_private_data(tmp_path):
    app = create_app(data_dir=tmp_path)
    app.state.pairing.save_phone(ADDRESS)
    assert app.state.luma.settings.phone_address == ADDRESS
    snapshot = app.state.luma.snapshot()
    assert snapshot["privacy_redacted"]
    assert not snapshot["state"]["phone_connected"]


def test_pairing_api_drives_confirmation_and_persists_selection(tmp_path):
    app = create_app(data_dir=tmp_path)
    driver = FakeDriver()
    app.state.pairing.driver_factory = lambda: driver
    with TestClient(app) as client:
        started = client.post("/api/v1/bluetooth/pairing/start").json()
        for _ in range(100):
            current = client.get("/api/v1/bluetooth/pairing").json()
            if current["devices"]:
                break
        assert current["devices"][0]["address"] == ADDRESS
        session = started["session"]
        assert client.post("/api/v1/bluetooth/pairing/select", json={"session": session, "device": DEVICE}).status_code == 200
        for _ in range(100):
            current = client.get("/api/v1/bluetooth/pairing").json()
            if current["phase"] == "confirming":
                break
        assert current["passkey"] == "042817"
        response = client.post("/api/v1/bluetooth/pairing/confirm", json={"session": session, "challenge": current["challenge"], "accepted": True})
        assert response.status_code == 200
        for _ in range(100):
            current = client.get("/api/v1/bluetooth/pairing").json()
            if current["phase"] == "complete":
                break
        assert current["phase"] == "complete"
        assert current["phone_address"] == ADDRESS
        assert client.get("/api/v1/state").json()["privacy_redacted"]
    # App restart preserves the selected identity but not presence/unlock.
    restarted = create_app(data_dir=tmp_path)
    assert restarted.state.luma.settings.phone_address == ADDRESS
    assert restarted.state.luma.snapshot()["privacy_redacted"]
