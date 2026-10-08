"""ANCS authorization lifetime for the remote; independent of PIN/grace privacy."""
from __future__ import annotations

import secrets
from time import monotonic

from .companion_auth import PhonePresence


class AuthorizedPhoneSession:
    def __init__(self, *, clock=monotonic):
        self.clock = clock
        self.clear()

    def clear(self):
        self.address = self.generation = self.phone_path = self.source_path = ""
        self.last_checked = None

    def begin(self, address: str, phone_path: str, source_path: str):
        # Call ONLY after Notification Source StartNotify succeeds. Link,
        # advertisement, Connect and PIN actions must never call this.
        self.address, self.phone_path, self.source_path = address.upper(), phone_path, source_path
        self.generation = secrets.token_urlsafe(24)
        self.last_checked = None  # First live trusted-link/service check required.

    def heartbeat(self, address: str):
        if self.generation and self.address == address.upper():
            if self.last_checked is not None and not 0 <= self.clock() - self.last_checked <= 15:
                self.clear()
                return
            self.last_checked = self.clock()

    def properties_changed(self, interface: str, changed: dict, invalidated: list):
        if interface != "org.bluez.Device1":
            return
        needed = {"Paired", "Bonded", "Trusted", "Connected"}
        if needed.intersection(invalidated) or any(
            key in changed and getattr(changed[key], "value", changed[key]) is not True for key in needed
        ):
            self.clear()

    def interfaces_removed(self, path: str, interfaces: list):
        if ((path == self.phone_path and "org.bluez.Device1" in interfaces)
                or (path == self.source_path and "org.bluez.GattCharacteristic1" in interfaces)):
            self.clear()

    def source_properties_changed(self, interface: str, changed: dict, invalidated: list):
        if interface == "org.bluez.GattCharacteristic1" and (
            "Notifying" in invalidated or ("Notifying" in changed
                and getattr(changed["Notifying"], "value", changed["Notifying"]) is not True)
        ):
            self.clear()

    def snapshot(self, selected: str | None, *, phone_connected: bool) -> PhonePresence:
        address = (selected or "").upper()
        age = self.clock() - self.last_checked if self.last_checked is not None else None
        fresh = age is not None and 0 <= age <= 15
        authorized = bool(self.generation and self.address == address and phone_connected and fresh)
        return PhonePresence(address, authorized, self.generation if authorized else "")
