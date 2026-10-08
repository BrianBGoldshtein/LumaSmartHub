"""Dormant browser-key authorization; no routes or network listener installed.

Local callers alone may issue/approve/revoke. The future gateway must enforce
its fixed private HTTPS origin and trustworthy Serve identity independently.
Browser keys prove possession, not physical iPhone or Secure Enclave identity.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
import secrets
from threading import RLock
from time import monotonic
from typing import Callable
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

from .security import SecurityManager
from .storage import Storage


GRANTS_KEY = "companion_browser_grants_v1"
MAX_GRANTS = 8
MAX_CHALLENGES = 128
MAX_BODY = 65536
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
PHONE = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")
HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z0-9-]{1,63}\.ts\.net\Z")
# A request proof can never authorize an arbitrary local API path.
OPERATIONS = frozenset({
    ("GET", "/remote/api/preview"), ("GET", "/remote/api/settings"),
    ("PATCH", "/remote/api/settings"), ("POST", "/remote/api/command"),
    ("GET", "/remote/api/google/status"), ("GET", "/remote/api/google/calendars"),
    ("GET", "/remote/api/google/colors"), ("POST", "/remote/api/google/sync"),
    ("POST", "/remote/api/google/web-client"), ("POST", "/remote/api/google/authorize"),
    ("POST", "/remote/api/todos/complete"), ("GET", "/remote/api/updates/status"),
    ("POST", "/remote/api/updates/check"), ("POST", "/remote/api/updates/install"),
})


class CompanionDenied(ValueError):
    """Fixed public failure; never include identity, key, body or provider data."""


@dataclass(frozen=True, slots=True)
class PhonePresence:
    address: str
    authorized: bool
    generation: str


def _decode(value: str, size: int) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise CompanionDenied("Remote proof is invalid.")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError:
        raise CompanionDenied("Remote proof is invalid.") from None
    if len(raw) != size or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
        raise CompanionDenied("Remote proof is invalid.")
    return raw


def _public_key(value: str):
    point = _decode(value, 65)
    if point[0] != 4:
        raise CompanionDenied("Remote proof is invalid.")
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except ValueError:
        raise CompanionDenied("Remote proof is invalid.") from None


def _verify(key: str, signature: str, message: bytes) -> None:
    raw = _decode(signature, 64)  # WebCrypto's P-256 r || s, not DER on the wire.
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    try:
        _public_key(key).verify(der, message, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise CompanionDenied("Remote proof is invalid.") from None


def _identity_digest(identity: str) -> str:
    if (not isinstance(identity, str) or not 1 <= len(identity) <= 256
            or any(ord(c) < 32 or ord(c) == 127 for c in identity)):
        raise CompanionDenied("Private connection identity required.")
    return hashlib.sha256(identity.encode()).hexdigest()


def private_origin(origin: str) -> str:
    if not isinstance(origin, str) or len(origin) > 200:
        raise CompanionDenied("Private HTTPS origin required.")
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise CompanionDenied("Private HTTPS origin required.") from None
    if (parsed.scheme != "https" or not HOST.fullmatch(parsed.netloc)
            or parsed.path or parsed.query or parsed.fragment):
        raise CompanionDenied("Private HTTPS origin required.")
    return origin


def enrollment_message(ticket: str, origin: str, identity: str, public_key: str) -> bytes:
    if not isinstance(ticket, str) or not TOKEN.fullmatch(ticket):
        raise CompanionDenied("Enrollment expired. Request a new QR on Luma.")
    point = _decode(public_key, 65)
    return "\n".join(("LUMA_ENROLL_V1", ticket, private_origin(origin),
                     _identity_digest(identity), hashlib.sha256(point).hexdigest())).encode()


def request_message(device_id: str, nonce: str, origin: str, identity: str,
                    method: str, path: str, body: bytes) -> bytes:
    if (not isinstance(device_id, str) or not TOKEN.fullmatch(device_id)
            or not isinstance(nonce, str) or not TOKEN.fullmatch(nonce)
            or (method, path) not in OPERATIONS or type(body) is not bytes
            or len(body) > MAX_BODY or (method == "GET" and body)):
        raise CompanionDenied("Remote request is invalid.")
    return "\n".join(("LUMA_REMOTE_V1", private_origin(origin), _identity_digest(identity),
                     device_id, nonce, method, path, hashlib.sha256(body).hexdigest())).encode()


class CompanionAuth:
    def __init__(self, storage: Storage, presence: Callable[[], PhonePresence],
                 *, clock: Callable[[], float] = monotonic):
        self.storage, self.security = storage, SecurityManager(storage)
        self.presence, self.clock = presence, clock
        self.lock = RLock()
        self.ticket = None
        self.pending = None
        self.challenges: dict[str, dict] = {}

    def _phone(self) -> PhonePresence:
        try:
            phone = self.presence()
        except Exception:
            self.challenges.clear()
            self.ticket = self.pending = None
            raise CompanionDenied("Connect the selected iPhone to Luma first.") from None
        if (not isinstance(phone, PhonePresence) or not phone.authorized
                or not isinstance(phone.address, str) or not PHONE.fullmatch(phone.address)
                or not isinstance(phone.generation, str) or not phone.generation
                or len(phone.generation) > 100):
            # Disconnect fails closed, even if a PIN grace lease is still full.
            self.challenges.clear()
            self.ticket = self.pending = None
            raise CompanionDenied("Connect the selected iPhone to Luma first.")
        return phone

    def _pin(self, pin: str):
        if not isinstance(pin, str) or not self.security.verify_pin(pin):
            raise CompanionDenied("A valid hub PIN is required.")

    def _grants(self) -> dict:
        try:
            rows = json.loads(self.storage.get_secret(GRANTS_KEY) or "{}")
            if not isinstance(rows, dict) or len(rows) > MAX_GRANTS:
                raise ValueError
            for key, row in rows.items():
                if (not TOKEN.fullmatch(key) or not isinstance(row, dict)
                        or set(row) != {"public_key", "phone", "origin", "identity", "label"}
                        or not PHONE.fullmatch(row["phone"])
                        or not re.fullmatch(r"[0-9a-f]{64}", row["identity"])
                        or not isinstance(row["label"], str) or len(row["label"]) > 64):
                    raise ValueError
                private_origin(row["origin"])
                _public_key(row["public_key"])
            return rows
        except (ValueError, TypeError, KeyError):
            raise CompanionDenied("Remote enrollment needs local recovery.") from None

    def issue_ticket(self, pin: str, origin: str) -> str:
        with self.lock:
            self._pin(pin)
            phone = self._phone()
            origin = private_origin(origin)
            ticket = secrets.token_urlsafe(32)
            self.ticket = {"digest": hashlib.sha256(ticket.encode()).hexdigest(),
                           "origin": origin, "phone": phone.address,
                           "generation": phone.generation, "expires": self.clock() + 300}
            self.pending = None
            return ticket  # RAM-only caller renders fragment QR; no secret/audit write.

    def claim(self, ticket: str, origin: str, identity: str,
              public_key: str, signature: str) -> dict:
        with self.lock:
            phone = self._phone()
            message = enrollment_message(ticket, origin, identity, public_key)
            row = self.ticket
            if (not row or self.clock() >= row["expires"] or row["origin"] != origin
                    or row["phone"] != phone.address or row["generation"] != phone.generation
                    or not secrets.compare_digest(row["digest"], hashlib.sha256(ticket.encode()).hexdigest())):
                raise CompanionDenied("Enrollment expired. Request a new QR on Luma.")
            _verify(public_key, signature, message)
            device_id = secrets.token_urlsafe(32)
            code = f"{secrets.randbelow(1000000):06d}"
            self.pending = {"device_id": device_id, "code": code, "public_key": public_key,
                            "origin": origin, "identity": _identity_digest(identity),
                            "phone": phone.address, "generation": phone.generation,
                            "expires": self.clock() + 300}
            self.ticket = None
            return {"device_id": device_id, "comparison_code": code}

    def pending_status(self, pin: str) -> dict | None:
        with self.lock:
            self._pin(pin)
            phone = self._phone()
            row = self.pending
            if (not row or self.clock() >= row["expires"] or row["phone"] != phone.address
                    or row["generation"] != phone.generation):
                self.pending = None
                return None
            return {"device_id": row["device_id"], "comparison_code": row["code"]}

    def approve(self, pin: str, device_id: str, comparison_code: str) -> None:
        with self.lock:
            status = self.pending_status(pin)
            if (not status or not isinstance(comparison_code, str) or status["device_id"] != device_id
                    or not secrets.compare_digest(status["comparison_code"], comparison_code)):
                raise CompanionDenied("Enrollment does not match the phone screen.")
            rows = self._grants()
            if len(rows) >= MAX_GRANTS:
                raise CompanionDenied("Revoke an old browser before enrolling another.")
            row = self.pending
            rows[device_id] = {k: row[k] for k in ("public_key", "phone", "origin", "identity")}
            rows[device_id]["label"] = "iPhone browser"
            self.storage.set_secret(GRANTS_KEY, json.dumps(rows, separators=(",", ":")))
            self.pending = None

    def devices(self, pin: str) -> list[dict]:
        with self.lock:
            self._pin(pin)
            return [{"device_id": key, "label": row["label"]} for key, row in self._grants().items()]

    def revoke(self, pin: str, device_id: str) -> None:
        with self.lock:
            self._pin(pin)
            if not isinstance(device_id, str) or not TOKEN.fullmatch(device_id):
                raise CompanionDenied("Remote enrollment is invalid.")
            rows = self._grants()
            rows.pop(device_id, None)
            self.storage.set_secret(GRANTS_KEY, json.dumps(rows, separators=(",", ":")))
            self.challenges = {n: r for n, r in self.challenges.items() if r["device_id"] != device_id}

    def _grant(self, device_id: str, origin: str, identity: str):
        phone = self._phone()
        if not isinstance(device_id, str) or not TOKEN.fullmatch(device_id):
            raise CompanionDenied("Remote enrollment is invalid.")
        row = self._grants().get(device_id)
        if (not row or row["phone"] != phone.address or row["origin"] != private_origin(origin)
                or row["identity"] != _identity_digest(identity)):
            raise CompanionDenied("This browser is not enrolled for the connected phone.")
        return row, phone

    def challenge(self, device_id: str, origin: str, identity: str,
                  method: str, path: str, body_digest: str) -> dict:
        with self.lock:
            row, phone = self._grant(device_id, origin, identity)
            if ((method, path) not in OPERATIONS or not isinstance(body_digest, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", body_digest)
                    or (method == "GET" and body_digest != hashlib.sha256(b"").hexdigest())):
                raise CompanionDenied("Remote request is invalid.")
            now = self.clock()
            self.challenges = {n: r for n, r in self.challenges.items() if r["expires"] > now}
            if len(self.challenges) >= MAX_CHALLENGES:
                raise CompanionDenied("Remote is busy. Try again shortly.")
            nonce = secrets.token_urlsafe(32)
            self.challenges[nonce] = {"device_id": device_id, "generation": phone.generation,
                                      "origin": origin, "identity": row["identity"],
                                      "method": method, "path": path, "digest": body_digest,
                                      "expires": now + 30}
            return {"nonce": nonce, "expires_in_seconds": 30}

    def verify(self, device_id: str, nonce: str, origin: str, identity: str,
               method: str, path: str, body: bytes, signature: str) -> PhonePresence:
        with self.lock:
            # Single consumption before crypto; even a bad proof cannot be replayed.
            if not isinstance(nonce, str) or not TOKEN.fullmatch(nonce):
                raise CompanionDenied("Remote proof is invalid.")
            challenge = self.challenges.pop(nonce, None)
            row, phone = self._grant(device_id, origin, identity)
            message = request_message(device_id, nonce, origin, identity, method, path, body)
            if (not challenge or self.clock() >= challenge["expires"]
                    or challenge["device_id"] != device_id
                    or challenge["generation"] != phone.generation
                    or challenge["origin"] != origin or challenge["identity"] != row["identity"]
                    or challenge["method"] != method or challenge["path"] != path
                    or challenge["digest"] != hashlib.sha256(body).hexdigest()):
                raise CompanionDenied("Remote request expired. Try again while connected.")
            _verify(row["public_key"], signature, message)
            return phone  # Slow operations must recheck this generation before response/commit.

    def still_authorized(self, device_id: str, origin: str, identity: str,
                         initial: PhonePresence) -> None:
        with self.lock:
            _, current = self._grant(device_id, origin, identity)
            if current != initial:
                raise CompanionDenied("Phone connection changed. Try again while connected.")
