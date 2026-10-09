"""Signed browser grants bound to a registered user's live ANCS session.

Local PIN-approved callers alone may issue/approve/revoke. The gateway enforces
its fixed private HTTPS origin and trustworthy Serve identity independently.
Browser keys prove possession, not physical iPhone or Secure Enclave identity.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, replace
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
from .profiles import PRIMARY_ID, ProfileError, GRANTS_KEY as PROFILE_GRANTS_KEY, phone_address


GRANTS_KEY = "companion_browser_grants_v1"
MIGRATION_KEY = "companion_browser_grants_migrated_v2"
MAX_GRANTS = 8
MAX_CHALLENGES = 128
MAX_BODY = 65536
TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
PHONE = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")
HOST = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.[a-z0-9-]{1,63}\.ts\.net\Z")
# A request proof can never authorize an arbitrary local API path.
OPERATIONS = frozenset({
    ('POST', '/remote/api/hub-settings'),
    ('GET', '/remote/api/device/fan'), ('POST', '/remote/api/device/fan'),
    ("GET", "/remote/api/admin/status"), ("POST", "/remote/api/admin/unlock"), ("POST", "/remote/api/admin/lock"),
    ("GET", "/remote/api/personal-settings"), ("PATCH", "/remote/api/personal-settings"),
    ("GET", "/remote/api/setup"), ("POST", "/remote/api/setup"),
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
    profile_id: str = PRIMARY_ID
    role: str = "primary"


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
    def __init__(self, storage: Storage, presence: Callable[..., PhonePresence],
                 *, clock: Callable[[], float] = monotonic, profiles=None):
        self.storage, self.security = storage, SecurityManager(storage)
        self.presence, self.clock = presence, clock
        self.profiles = profiles
        self.grants_key = PROFILE_GRANTS_KEY if profiles else GRANTS_KEY
        self.lock = RLock()
        self.ticket = None
        self.pending = None
        self.challenges: dict[str, dict] = {}
        self.migration_checked = False

    def _clear_profile(self, uid):
        self.challenges = {n: row for n, row in self.challenges.items()
                           if row.get("profile_id", PRIMARY_ID) != uid}
        if self.ticket and self.ticket.get("profile_id", PRIMARY_ID) == uid:
            self.ticket = None
        if self.pending and self.pending.get("profile_id", PRIMARY_ID) == uid:
            self.pending = None

    def clear_ephemeral(self):
        """Call after policy/binding changes; persistent grants are revoked separately."""
        with self.lock:
            self.ticket = self.pending = None
            self.challenges.clear()

    def _profile(self, uid):
        if not self.profiles:
            if uid != PRIMARY_ID:
                raise CompanionDenied("This user’s private remote is not enabled.")
            return None
        try:
            user = self.profiles.get(uid)
            if not self.profiles.remote_allowed(uid):
                raise ProfileError("Remote disabled")
            return user
        except ProfileError:
            self._clear_profile(uid)
            raise CompanionDenied("This user’s private remote is not enabled.") from None

    def _phone(self, uid=PRIMARY_ID) -> PhonePresence:
        try:
            user = self._profile(uid)
            phone = self.presence(uid) if self.profiles else self.presence()
        except CompanionDenied:
            raise
        except Exception:
            self._clear_profile(uid)
            raise CompanionDenied("Connect the selected iPhone to Luma first.") from None
        if (not isinstance(phone, PhonePresence) or not phone.authorized
                or not isinstance(phone.address, str) or not PHONE.fullmatch(phone.address)
                or not isinstance(phone.generation, str) or not phone.generation
                or len(phone.generation) > 100
                or (user is not None and user.phone_address != phone.address)):
            # Disconnect fails closed, even if a PIN grace lease is still full.
            self._clear_profile(uid)
            raise CompanionDenied("Connect the selected iPhone to Luma first.")
        # Role and user come from the registry, never Bluetooth/client fields.
        return replace(phone, profile_id=uid, role=user.role if user else "primary")

    def _pin(self, pin: str):
        if not isinstance(pin, str) or not self.security.verify_pin(pin):
            raise CompanionDenied("A valid hub PIN is required.")

    @staticmethod
    def _validate_grants(encoded, *, multi=False):
        try:
            rows = json.loads(encoded or "{}")
            if not isinstance(rows, dict) or len(rows) > MAX_GRANTS:
                raise ValueError
            for key, row in rows.items():
                if (not TOKEN.fullmatch(key) or not isinstance(row, dict)
                        or set(row) != {"public_key", "phone", "origin", "identity", "label"} | ({"profile_id"} if multi else set())
                        or not PHONE.fullmatch(row["phone"])
                        or not re.fullmatch(r"[0-9a-f]{64}", row["identity"])
                        or not isinstance(row["label"], str) or len(row["label"]) > 64):
                    raise ValueError
                private_origin(row["origin"])
                _public_key(row["public_key"])
                if multi:
                    from .profiles import profile_id
                    profile_id(row["profile_id"])
            return rows
        except (ValueError, TypeError, KeyError):
            raise CompanionDenied("Remote enrollment needs local recovery.") from None

    def _migrate_primary(self):
        # One-time, atomic adoption. Preserve V1 for 0.3.0 rollback, but never
        # resurrect it after a V2 revoke/backup restore. No owner token changes.
        with self.storage.transaction() as db:
            marker = db.execute("SELECT value FROM metadata WHERE key=?", (MIGRATION_KEY,)).fetchone()
            current = db.execute("SELECT payload FROM secrets WHERE key=?", (PROFILE_GRANTS_KEY,)).fetchone()
            if marker or current:
                if current:
                    self._validate_grants(current[0], multi=True)
            else:
                legacy = db.execute("SELECT payload FROM secrets WHERE key=?", (GRANTS_KEY,)).fetchone()
                rows = self._validate_grants(legacy[0] if legacy else None)
                phone = phone_address(self.profiles._legacy(db).phone_address)
                adopted = {key: {**row, "profile_id": PRIMARY_ID} for key, row in rows.items()
                           if row["phone"] == phone}
                db.execute("INSERT INTO secrets(key,payload,updated_at) VALUES(?,?,datetime('now'))",
                           (PROFILE_GRANTS_KEY, json.dumps(adopted, separators=(",", ":"))))
            db.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO NOTHING", (MIGRATION_KEY, "1"))
        self.migration_checked = True

    def _grants(self) -> dict:
        if self.profiles and not self.migration_checked:
            self._migrate_primary()
        return self._validate_grants(self.storage.get_secret(self.grants_key), multi=bool(self.profiles))

    def _save_grants(self, db, rows):
        encoded = json.dumps(rows, separators=(",", ":"))
        db.execute("INSERT INTO secrets(key,payload,updated_at) VALUES(?,?,datetime('now')) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                   (self.grants_key, encoded))
        if self.profiles:
            primary = {key: {k: v for k, v in row.items() if k != "profile_id"}
                       for key, row in rows.items() if row["profile_id"] == PRIMARY_ID}
            db.execute("INSERT INTO secrets(key,payload,updated_at) VALUES(?,?,datetime('now')) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                       (GRANTS_KEY, json.dumps(primary, separators=(",", ":"))))

    def _commit_profile(self, db, uid, phone):
        if not self.profiles:
            return
        try:
            user = self.profiles._find(self.profiles._read(db), uid)
            allowed = user["remote_enabled"] and (uid == PRIMARY_ID or self.profiles._remote_policy(db) == "all_profiles")
            binding = phone_address(self.profiles._legacy(db).phone_address) if uid == PRIMARY_ID else user["phone_address"]
            if not allowed or binding != phone.address:
                raise ProfileError("Remote changed")
        except ProfileError:
            raise CompanionDenied("This user’s private remote is not enabled.") from None

    def issue_ticket(self, pin: str, origin: str, *, profile_id=PRIMARY_ID) -> str:
        with self.lock:
            self._pin(pin)
            return self._issue_ticket(origin, profile_id)

    def issue_for_setup(self, origin, profile_id, recheck):
        """Trusted local own-account setup only; not a wire-supplied PIN bypass."""
        with self.lock:
            recheck()
            for row in (self.ticket, self.pending):
                if row and self.clock() < row['expires'] and row.get('profile_id', PRIMARY_ID) != profile_id:
                    raise CompanionDenied('Finish the other user’s remote enrollment first.')
            return self._issue_ticket(origin, profile_id)

    def _issue_ticket(self, origin, profile_id):
        phone = self._phone(profile_id)
        origin = private_origin(origin)
        ticket = secrets.token_urlsafe(32)
        self.ticket = {"digest": hashlib.sha256(ticket.encode()).hexdigest(),
                       "origin": origin, "phone": phone.address,
                       "profile_id": profile_id,
                       "generation": phone.generation, "expires": self.clock() + 300}
        self.pending = None
        return ticket  # RAM-only caller renders fragment QR; no secret/audit write.

    def claim(self, ticket: str, origin: str, identity: str,
              public_key: str, signature: str) -> dict:
        with self.lock:
            row = self.ticket
            phone = self._phone(row.get("profile_id", PRIMARY_ID) if row else PRIMARY_ID)
            message = enrollment_message(ticket, origin, identity, public_key)
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
                            "profile_id": phone.profile_id,
                            "expires": self.clock() + 300}
            self.ticket = None
            return {"device_id": device_id, "comparison_code": code}

    def pending_status(self, pin: str) -> dict | None:
        with self.lock:
            self._pin(pin)
            return self._pending_status()

    def pending_for_setup(self, profile_id, recheck):
        with self.lock:
            recheck()
            if self.pending and self.pending.get('profile_id', PRIMARY_ID) != profile_id:
                return None  # Never reveal another user's comparison code.
            return self._pending_status(profile_id)

    def _pending_status(self, profile_id=PRIMARY_ID):
        row = self.pending
        phone = self._phone(row.get("profile_id", profile_id) if row else profile_id)
        if (not row or self.clock() >= row["expires"] or row["phone"] != phone.address
                or row["generation"] != phone.generation):
            self.pending = None
            return None
        return {"device_id": row["device_id"], "comparison_code": row["code"]}

    def approve(self, pin: str, device_id: str, comparison_code: str) -> None:
        with self.lock:
            status = self.pending_status(pin)
            self._approve(status, device_id, comparison_code)

    def approve_for_setup(self, profile_id, device_id, comparison_code, recheck):
        with self.lock:
            status = self.pending_for_setup(profile_id, recheck)
            recheck()
            self._approve(status, device_id, comparison_code)

    def _approve(self, status, device_id, comparison_code):
        if (not status or not isinstance(comparison_code, str) or status["device_id"] != device_id
                or not secrets.compare_digest(status["comparison_code"], comparison_code)):
            raise CompanionDenied("Enrollment does not match the phone screen.")
        row = self.pending
        self._grants()  # Validate/migrate before the serialized commit.
        with self.storage.transaction() as db:
            phone = self._phone(row.get("profile_id", PRIMARY_ID))
            if phone.address != row["phone"] or phone.generation != row["generation"]:
                raise CompanionDenied("Enrollment does not match the phone connection.")
            self._commit_profile(db, phone.profile_id, phone)
            saved = db.execute("SELECT payload FROM secrets WHERE key=?", (self.grants_key,)).fetchone()
            rows = self._validate_grants(saved[0] if saved else None, multi=bool(self.profiles))
            if len(rows) >= MAX_GRANTS:
                raise CompanionDenied("Revoke an old browser before enrolling another.")
            rows[device_id] = {k: row[k] for k in ("public_key", "phone", "origin", "identity")}
            rows[device_id]["label"] = "iPhone browser"
            if self.profiles:
                rows[device_id]["profile_id"] = phone.profile_id
            self._save_grants(db, rows)
        self.pending = None

    def devices(self, pin: str) -> list[dict]:
        with self.lock:
            self._pin(pin)
            return [{"device_id": key, "label": row["label"],
                     **({"profile_id": row["profile_id"]} if self.profiles else {})}
                    for key, row in self._grants().items()]

    def revoke(self, pin: str, device_id: str) -> None:
        with self.lock:
            self._pin(pin)
            if not isinstance(device_id, str) or not TOKEN.fullmatch(device_id):
                raise CompanionDenied("Remote enrollment is invalid.")
            self._grants()
            with self.storage.transaction() as db:
                saved = db.execute("SELECT payload FROM secrets WHERE key=?", (self.grants_key,)).fetchone()
                rows = self._validate_grants(saved[0] if saved else None, multi=bool(self.profiles))
                rows.pop(device_id, None)
                self._save_grants(db, rows)
            self.challenges = {n: r for n, r in self.challenges.items() if r["device_id"] != device_id}

    def _grant(self, device_id: str, origin: str, identity: str):
        if not isinstance(device_id, str) or not TOKEN.fullmatch(device_id):
            raise CompanionDenied("Remote enrollment is invalid.")
        row = self._grants().get(device_id)
        phone = self._phone(row.get("profile_id", PRIMARY_ID) if row else PRIMARY_ID)
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
                                      "profile_id": phone.profile_id,
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
                    or challenge.get("profile_id", PRIMARY_ID) != phone.profile_id
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
