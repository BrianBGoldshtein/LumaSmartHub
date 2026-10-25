"""Role-specific live phone authority, independent of PIN/grace privacy."""
from __future__ import annotations

import secrets
from time import monotonic

from .companion_auth import PhonePresence


class AuthorizedPhoneSession:
    def __init__(self, *, clock=monotonic, on_lost=lambda:None):
        self.clock = clock
        self.on_lost = on_lost
        self.clear()

    def clear(self):
        had_session = bool(getattr(self, 'generation', ''))
        self.address = self.generation = self.phone_path = self.source_path = ""
        self.last_checked = None
        if had_session:
            self.on_lost()

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
        ) or 'Blocked' in invalidated or ('Blocked' in changed and getattr(changed['Blocked'],'value',changed['Blocked']) is not False):
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


class BondedPhoneSession(AuthorizedPhoneSession):
    """Secondary-only authority from a selected live bonded BlueZ connection.

    No notification subscription, data characteristic or advertisement is a
    prerequisite. Primary phones must keep using AuthorizedPhoneSession.
    """
    @staticmethod
    def valid_link(address: str, properties: dict) -> bool:
        current = properties.get('Address')
        return (isinstance(current, str) and current.casefold() == address.casefold()
                and properties.get('Blocked', False) is False
                and all(properties.get(key) is True for key in
                        ('Paired', 'Bonded', 'Trusted', 'Connected', 'ServicesResolved')))

    def begin_bonded(self, address: str, phone_path: str, properties: dict):
        if not self.valid_link(address, properties):
            self.clear()
            raise ValueError('A selected live bonded phone is required.')
        super().begin(address, phone_path, '')

    def properties_changed(self, interface: str, changed: dict, invalidated: list):
        super().properties_changed(interface, changed, invalidated)
        if interface != 'org.bluez.Device1':
            return
        value = lambda key: getattr(changed[key], 'value', changed[key])
        if ({'ServicesResolved', 'Blocked', 'Address'}.intersection(invalidated)
                or ('ServicesResolved' in changed and value('ServicesResolved') is not True)
                or ('Blocked' in changed and value('Blocked') is not False)
                or ('Address' in changed and (not isinstance(value('Address'), str)
                    or value('Address').upper() != self.address))):
            self.clear()

    def source_properties_changed(self, interface: str, changed: dict, invalidated: list):
        # Secondary presence never depends on ANCS or its Notifying property.
        return None
