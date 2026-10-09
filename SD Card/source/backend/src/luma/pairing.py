"""Bounded, explicitly confirmed phone pairing. Never an unattended default agent."""
from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from time import monotonic
from uuid import uuid4

ADDRESS = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")


def device_choices(objects, adapter):
    devices = []
    for path, interfaces in objects.items():
        props = interfaces.get("org.bluez.Device1", {})
        if props.get("Adapter") != adapter or not path.startswith(adapter + "/dev_"):
            continue
        address = props.get("Address", "")
        if not ADDRESS.fullmatch(address):
            continue
        name = "".join(c for c in str(props.get("Alias") or props.get("Name") or "Bluetooth device") if c.isprintable())[:80]
        devices.append({"path": path, "name": name, "address": address,
                        "paired": props.get("Paired") is True and props.get("Bonded") is True,
                        "trusted": props.get("Trusted") is True})
    return sorted(devices, key=lambda item: (not item["paired"], item["name"].casefold(), item["address"]))[:40]


class PairingFlow:
    def __init__(self, save_phone, driver_factory=None, *, validate_phone=lambda address: None):
        self.save_phone = save_phone
        self.validate_phone = validate_phone
        self.driver_factory = driver_factory or BlueZPairing
        self.task = None
        self.session = None
        self.phase = "idle"
        self.devices = []
        self.selected = None
        self.challenge = None
        self.passkey = None
        self.message = ""
        self.choice = None
        self.confirmation = None

    def snapshot(self):
        return {"session": self.session, "phase": self.phase, "devices": self.devices,
                "selected": self.selected, "challenge": self.challenge,
                "passkey": self.passkey, "message": self.message}

    def start(self):
        if self.task and not self.task.done():
            raise ValueError("A pairing session is already open")
        self.session = str(uuid4())
        self.phase = "scanning"
        self.devices = []
        self.selected = None
        self.message = "Open Settings → Bluetooth on your iPhone and keep it nearby."
        self.choice = asyncio.get_running_loop().create_future()
        self.task = asyncio.create_task(self.run())
        return self.snapshot()

    def check_session(self, session):
        if session != self.session or not self.task or self.task.done():
            raise ValueError("That pairing session has ended; start again")

    def select(self, session, path):
        self.check_session(session)
        if self.phase != "scanning" or self.choice.done():
            raise ValueError("Select a phone from the current scan")
        selected = next((item for item in self.devices if item["path"] == path), None)
        if not selected:
            raise ValueError("Select a phone from the current scan")
        self.selected = selected
        self.phase = "pairing"
        self.choice.set_result(path)
        return self.snapshot()

    async def request_confirmation(self, path, passkey):
        if not self.selected or path != self.selected["path"] or self.confirmation is not None:
            return False
        if not isinstance(passkey, int) or not 0 <= passkey <= 999999:
            return False
        self.challenge = str(uuid4())
        self.passkey = f"{passkey:06d}"
        self.phase = "confirming"
        self.message = "Confirm only if these six digits match the code on your iPhone."
        self.confirmation = asyncio.get_running_loop().create_future()
        try:
            return await asyncio.wait_for(self.confirmation, 45)
        except TimeoutError:
            return False
        finally:
            self.challenge = None
            self.passkey = None
            self.confirmation = None
            self.phase = "pairing"

    def confirm(self, session, challenge, accepted):
        self.check_session(session)
        if challenge != self.challenge or self.phase != "confirming" or not self.confirmation or self.confirmation.done():
            raise ValueError("That confirmation has expired")
        self.confirmation.set_result(accepted)
        return {"accepted": True}

    async def cancel(self, session):
        self.check_session(session)
        if self.phase == "complete":
            await self.task
            return self.snapshot()
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        # Cancellation can occur before run() executes its first instruction.
        self.phase = "cancelled"
        self.message = "Pairing cancelled. Your previous phone selection is unchanged."
        self.challenge = None
        self.passkey = None
        self.confirmation = None
        return self.snapshot()

    async def close(self):
        if self.task and not self.task.done():
            await self.cancel(self.session)

    async def forget_phone(self, address):
        """Remove only the exact currently selected BlueZ phone bond."""
        if not isinstance(address, str) or not ADDRESS.fullmatch(address):
            raise ValueError("No valid selected phone")
        if self.task and not self.task.done():
            raise ValueError("Finish or cancel the current pairing session first")
        driver = self.driver_factory()
        try:
            await driver.open()
            objects = await driver.objects()
            path = next((path for path, interfaces in objects.items()
                         if path.startswith(driver.adapter + "/dev_")
                         and interfaces.get("org.bluez.Device1", {}).get("Address", "").casefold() == address.casefold()), None)
            if path is None:
                return False
            props = await driver.properties(path)
            if props.get("Address", "").casefold() != address.casefold():
                raise ValueError("The selected phone changed during removal")
            if props.get("Connected") is True:
                device = await driver.interface(path, "org.bluez.Device1")
                with suppress(Exception):
                    await asyncio.wait_for(device.call_disconnect(), 5)
            adapter = await driver.interface(driver.adapter, "org.bluez.Adapter1")
            await asyncio.wait_for(adapter.call_remove_device(path), 10)
            return True
        finally:
            with suppress(Exception):
                await asyncio.wait_for(driver.close(), 10)

    async def run(self):
        driver = self.driver_factory()
        path = None
        try:
            async with asyncio.timeout(180):
                await driver.open()
                await driver.start_scan()
                deadline = monotonic() + 45
                while not self.choice.done():
                    self.devices = device_choices(await driver.objects(), driver.adapter)
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError()
                    with suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(self.choice), min(2, remaining))
                path = self.choice.result()
                await driver.stop_scan()
                # Recheck the actual BlueZ object, not the stale browser list.
                props = await driver.properties(path)
                if props.get("Address", "").casefold() != self.selected["address"].casefold():
                    raise ValueError("Device changed")
                self.validate_phone(props['Address'])
                already_bonded = props.get("Paired") is True and props.get("Bonded") is True
                if already_bonded and props.get("Trusted") is not True:
                    self.phase = "error"
                    self.message = "This phone has an unfinished or untrusted bond. Forget Luma on the iPhone and remove that bond with the administrator guide before pairing again."
                    return
                if not already_bonded:
                    self.message = "Waiting for your iPhone’s pairing request…"
                    await asyncio.wait_for(driver.pair(path, self.request_confirmation), 90)
                props = await driver.properties(path)
                if (props.get('Address', '').casefold() != self.selected['address'].casefold()
                        or not (props.get("Paired") is True and props.get("Bonded") is True)):
                    raise ValueError("Pairing did not create a bond")
                self.validate_phone(props['Address'])
                await driver.trust(path)
                props = await driver.properties(path)
                if (props.get('Address', '').casefold() != self.selected['address'].casefold()
                        or not all(props.get(key) is True for key in ('Paired','Bonded','Trusted'))):
                    raise ValueError("Trust was not saved")
                self.validate_phone(props['Address'])
                self.save_phone(props["Address"])
                self.phase = "complete"
                self.message = "Phone selected. Enable Share System Notifications for Luma in iPhone Bluetooth settings if offered. Private content stays hidden until that access is authorized."
        except asyncio.CancelledError:
            self.phase = "cancelled"
            self.message = "Pairing cancelled. Your previous phone selection is unchanged."
            raise
        except TimeoutError:
            self.phase = "expired"
            self.message = "Pairing timed out. Keep iPhone Bluetooth settings open and try again."
        except Exception:
            self.phase = "error"
            self.message = "Could not pair. Check Bluetooth on both devices and try again. Your previous phone selection is unchanged."
        finally:
            if path and self.phase != "complete":
                with suppress(Exception):
                    await asyncio.wait_for(driver.cancel_pair(path), 5)
            with suppress(Exception):
                await asyncio.wait_for(driver.close(), 10)
            self.challenge = None
            self.passkey = None
            self.confirmation = None


class BlueZPairing:
    def __init__(self):
        self.bus = None
        self.adapter = None
        self.discovering = False
        self.agent = None
        self.registered = False
        self.agent_path = "/org/luma/PairingAgent"

    async def interface(self, path, name):
        intro = await asyncio.wait_for(self.bus.introspect("org.bluez", path), 5)
        return self.bus.get_proxy_object("org.bluez", path, intro).get_interface(name)

    async def open(self):
        import sys
        if sys.platform != "linux":
            raise ValueError("Pairing requires the Pi")
        from dbus_next import BusType
        from dbus_next.aio import MessageBus
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        objects = await self.objects()
        self.adapter = next((path for path, obj in sorted(objects.items()) if "org.bluez.Adapter1" in obj), None)
        if not self.adapter:
            raise ValueError("No Bluetooth adapter")

    async def objects(self):
        manager = await self.interface("/", "org.freedesktop.DBus.ObjectManager")
        objects = await asyncio.wait_for(manager.call_get_managed_objects(), 5)
        return {path: {name: {key: value.value for key, value in props.items()} for name, props in interfaces.items()} for path, interfaces in objects.items()}

    async def properties(self, path):
        proxy = await self.interface(path, "org.freedesktop.DBus.Properties")
        return {key: value.value for key, value in (await asyncio.wait_for(proxy.call_get_all("org.bluez.Device1"), 5)).items()}

    async def start_scan(self):
        from dbus_next import Variant
        props = await self.interface(self.adapter, "org.freedesktop.DBus.Properties")
        await asyncio.wait_for(props.call_set("org.bluez.Adapter1", "Powered", Variant("b", True)), 5)
        adapter = await self.interface(self.adapter, "org.bluez.Adapter1")
        await asyncio.wait_for(adapter.call_set_discovery_filter({"Transport": Variant("s", "auto"), "DuplicateData": Variant("b", False)}), 5)
        await asyncio.wait_for(adapter.call_start_discovery(), 5)
        self.discovering = True

    async def stop_scan(self):
        if self.discovering:
            adapter = await self.interface(self.adapter, "org.bluez.Adapter1")
            await asyncio.wait_for(adapter.call_stop_discovery(), 5)
            self.discovering = False

    async def pair(self, path, confirm):
        from .pairing_agent import PairingAgent
        self.agent = PairingAgent(path, confirm)
        self.bus.export(self.agent_path, self.agent)
        manager = await self.interface("/org/bluez", "org.bluez.AgentManager1")
        await asyncio.wait_for(manager.call_register_agent(self.agent_path, "DisplayYesNo"), 5)
        self.registered = True
        device = await self.interface(path, "org.bluez.Device1")
        await device.call_pair()
        # Refuse silent/Just Works pairing even if a backend reports success.
        if not self.agent.confirmed:
            raise ValueError("Pairing code was not confirmed")

    async def trust(self, path):
        from dbus_next import Variant
        props = await self.interface(path, "org.freedesktop.DBus.Properties")
        await asyncio.wait_for(props.call_set("org.bluez.Device1", "Trusted", Variant("b", True)), 5)

    async def cancel_pair(self, path):
        device = await self.interface(path, "org.bluez.Device1")
        await asyncio.wait_for(device.call_cancel_pairing(), 3)

    async def close(self):
        try:
            with suppress(Exception):
                await self.stop_scan()
            if self.registered:
                manager = await self.interface("/org/bluez", "org.bluez.AgentManager1")
                await asyncio.wait_for(manager.call_unregister_agent(self.agent_path), 3)
        finally:
            if self.bus:
                self.bus.unexport(self.agent_path)
                self.bus.disconnect()
