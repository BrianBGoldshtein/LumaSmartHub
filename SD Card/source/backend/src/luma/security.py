from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .storage import Storage


PIN_SECRET_KEY = "pin_hash"
LAN_TOKEN_KEY = "lan_token"


def _validate_pin_shape(pin: str) -> None:
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ValueError("PIN must contain 4 to 8 digits")


@dataclass(slots=True)
class SecurityManager:
    storage: Storage

    def pin_is_configured(self) -> bool:
        return self.storage.get_secret(PIN_SECRET_KEY) is not None

    def set_pin(self, pin: str) -> None:
        _validate_pin_shape(pin)
        salt = secrets.token_bytes(16)
        digest = hashlib.scrypt(
            pin.encode("utf-8"),
            salt=salt,
            n=2**14,
            r=8,
            p=1,
            dklen=32,
        )
        self.storage.set_secret(PIN_SECRET_KEY, f"scrypt$16384$8$1${salt.hex()}${digest.hex()}")
        self.storage.set_cache("security", "pin_attempts", {"failures": 0, "locked_until": None})

    def verify_pin(self, pin: str) -> bool:
        now = datetime.now(UTC)
        attempts = self.storage.get_cache("security", "pin_attempts") or {"failures": 0, "locked_until": None}
        if attempts["locked_until"] and datetime.fromisoformat(attempts["locked_until"]) > now:
            return False
        if attempts["locked_until"]:
            attempts = {"failures": 0, "locked_until": None}
        encoded = self.storage.get_secret(PIN_SECRET_KEY)
        if not encoded:
            return False
        try:
            algorithm, n, r, p, salt_hex, expected_hex = encoded.split("$")
            if algorithm != "scrypt":
                return False
            actual = hashlib.scrypt(
                pin.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=int(n),
                r=int(r),
                p=int(p),
                dklen=len(bytes.fromhex(expected_hex)),
            )
        except (ValueError, TypeError):
            return False
        valid = hmac.compare_digest(actual, bytes.fromhex(expected_hex))
        failures = 0 if valid else attempts["failures"] + 1
        self.storage.set_cache("security", "pin_attempts", {"failures": failures, "locked_until": (now + timedelta(seconds=60)).isoformat() if failures >= 5 else None})
        return valid

    def get_or_create_lan_token(self) -> str:
        token = self.storage.get_secret(LAN_TOKEN_KEY)
        if token:
            return token
        token = secrets.token_urlsafe(32)
        self.storage.set_secret(LAN_TOKEN_KEY, token)
        return token

    def verify_lan_token(self, candidate: str | None) -> bool:
        if not candidate:
            return False
        expected = self.storage.get_secret(LAN_TOKEN_KEY)
        return bool(expected and hmac.compare_digest(expected, candidate))

    def rotate_lan_token(self) -> str:
        token = secrets.token_urlsafe(32)
        self.storage.set_secret(LAN_TOKEN_KEY, token)
        return token
