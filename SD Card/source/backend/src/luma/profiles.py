"""Bounded user profiles, keeping the legacy primary account canonical.

No new SQLite tables/schema or Bluetooth operations. Controllers must enforce
PIN/role/presence before calling mutations; this repository enforces identity,
capacity and account isolation atomically, including between processes.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
import unicodedata
from uuid import uuid4

from .models import Settings
from .serde import settings_from_dict, to_primitive
from .storage import Storage


PRIMARY_ID = "primary"
REGISTRY_KEY = "user_profiles_v1"
GRANTS_KEY = "companion_browser_grants_v2"
REMOTE_POLICY_KEY = "profile_remote_policy_v1"
REMOTE_POLICIES = frozenset({"all_profiles", "primary_only"})
MAX_PROFILES = 5
PERSONAL_KEYS = frozenset({
    "visible_calendar_ids", "todo_calendar_id", "todo_completed_color_id",
    "departure_calendar_ids", "departure_enabled", "departure_prep_minutes",
    "departure_travel_minutes", "departure_include_virtual",
})
SETUP_STAGES = ("phone", "remote", "google", "calendars", "ready")
ID_RE = re.compile(r"(?:primary|[0-9a-f]{32})\Z")
PHONE_RE = re.compile(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}\Z")


class ProfileError(ValueError):
    """Fixed owner-safe failure, without raw stored account data."""


def profile_id(value: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ProfileError("Choose a valid user profile.")
    return value


def nickname(value: str) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise ProfileError("Use a name from 1 to 24 characters.")
    clean = unicodedata.normalize("NFC", value).strip()
    if not 1 <= len(clean) <= 24 or any(unicodedata.category(c).startswith("C") for c in clean):
        raise ProfileError("Use a name from 1 to 24 printable characters.")
    return clean


def phone_address(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not PHONE_RE.fullmatch(value.upper()):
        raise ProfileError("Choose a paired phone with a valid Bluetooth address.")
    return value.upper()


def personal_settings(updates: dict, base: dict | None = None) -> dict:
    if not isinstance(updates, dict) or not updates.keys() <= PERSONAL_KEYS:
        raise ProfileError("Only personal calendar and reminder settings can be changed here.")
    defaults = to_primitive(Settings())
    values = {key: defaults[key] for key in PERSONAL_KEYS}
    if base is not None:
        if not isinstance(base, dict) or set(base) != PERSONAL_KEYS:
            raise ProfileError("Saved personal settings need local recovery.")
        values.update(deepcopy(base))
    values.update(deepcopy(updates))
    for key in ("visible_calendar_ids", "departure_calendar_ids"):
        ids = values[key]
        if (not isinstance(ids, list) or len(ids) > 50 or
                any(not isinstance(item, str) or not 1 <= len(item) <= 1024 or
                    any(ord(c) < 32 for c in item) for item in ids) or len(set(ids)) != len(ids)):
            raise ProfileError("Choose at most 50 distinct calendars.")
    item = values["todo_calendar_id"]
    if item is not None and (not isinstance(item, str) or not 1 <= len(item) <= 1024 or any(ord(c) < 32 for c in item)):
        raise ProfileError("Choose a valid to-do calendar.")
    for key in ("departure_enabled", "departure_include_virtual"):
        if type(values[key]) is not bool:
            raise ProfileError("Reminder options must be enabled or disabled.")
    try:
        settings_from_dict({**defaults, **values})
    except (ValueError, TypeError):
        raise ProfileError("Personal calendar settings are invalid.") from None
    return values


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: str
    role: str
    nickname: str
    phone_address: str | None
    personal: dict
    setup_stage: str
    wall_share_approved: bool
    remote_enabled: bool

    @property
    def primary(self) -> bool:
        return self.id == PRIMARY_ID and self.role == "primary"


class ProfileRepository:
    def __init__(self, storage: Storage):
        self.storage = storage
        with storage.transaction() as connection:
            row = connection.execute("SELECT value FROM metadata WHERE key=?", (REGISTRY_KEY,)).fetchone()
            if row is None:
                # Keep all old settings/secrets/cache in place for rollback.
                self._save(connection, [{"id": PRIMARY_ID, "role": "primary", "nickname": "Primary",
                    "phone_address": None, "personal": {}, "setup_stage": "ready",
                    "wall_share_approved": True, "remote_enabled": True}])
            else:
                self._read(connection)

    @staticmethod
    def _legacy(connection) -> Settings:
        row = connection.execute("SELECT payload FROM settings WHERE id=1").fetchone()
        return settings_from_dict(json.loads(row[0]))

    @classmethod
    def _read(cls, connection) -> list[dict]:
        row = connection.execute("SELECT value FROM metadata WHERE key=?", (REGISTRY_KEY,)).fetchone()
        try:
            if row is None or len(row[0]) > 512 * 1024:
                raise ValueError
            record = json.loads(row[0])
            if not isinstance(record, dict) or set(record) != {"version", "users"} or type(record["version"]) is not int or record["version"] != 1:
                raise ValueError
            users = record["users"]
            if not isinstance(users, list) or not 1 <= len(users) <= MAX_PROFILES:
                raise ValueError
            ids, names, phones = set(), set(), set()
            legacy = cls._legacy(connection)
            for user in users:
                if not isinstance(user, dict) or set(user) != {
                    "id", "role", "nickname", "phone_address", "personal", "setup_stage",
                    "wall_share_approved", "remote_enabled",
                }:
                    raise ValueError
                uid = profile_id(user["id"])
                if uid in ids or user["role"] != ("primary" if uid == PRIMARY_ID else "secondary"):
                    raise ValueError
                ids.add(uid)
                name = nickname(user["nickname"])
                if name != user["nickname"] or name.casefold() in names:
                    raise ValueError
                names.add(name.casefold())
                if user["setup_stage"] not in SETUP_STAGES or any(type(user[key]) is not bool for key in ("wall_share_approved", "remote_enabled")):
                    raise ValueError
                if uid == PRIMARY_ID:
                    if user["phone_address"] is not None or user["personal"] != {} or not user["remote_enabled"]:
                        raise ValueError
                    phone = phone_address(legacy.phone_address)
                else:
                    phone = phone_address(user["phone_address"])
                    if phone != user["phone_address"] or personal_settings({}, user["personal"]) != user["personal"]:
                        raise ValueError
                if phone:
                    if phone in phones:
                        raise ValueError
                    phones.add(phone)
            if PRIMARY_ID not in ids:
                raise ValueError
            return users
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ProfileError("Saved user profiles need local recovery; no accounts were reset.") from None

    @staticmethod
    def _save(connection, users):
        encoded = json.dumps({"version": 1, "users": users}, sort_keys=True, separators=(",", ":"))
        connection.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                           (REGISTRY_KEY, encoded))

    @staticmethod
    def _find(users, uid):
        profile_id(uid)
        found = next((row for row in users if row["id"] == uid), None)
        if found is None:
            raise ProfileError("That user profile is no longer available.")
        return found

    def list(self) -> list[UserProfile]:
        with closing(self.storage.connect()) as connection:
            users = self._read(connection)
            legacy = self._legacy(connection)
        result = []
        for row in users:
            values = deepcopy(row)
            if row["id"] == PRIMARY_ID:
                values["phone_address"] = phone_address(legacy.phone_address)
                # Old-version edits during rollback remain authoritative.
                values["personal"] = {key: deepcopy(getattr(legacy, key)) for key in PERSONAL_KEYS}
            result.append(UserProfile(**values))
        return result

    def get(self, uid: str) -> UserProfile:
        profile_id(uid)
        found = next((user for user in self.list() if user.id == uid), None)
        if found is None:
            raise ProfileError("That user profile is no longer available.")
        return found

    def by_phone(self, address: str) -> UserProfile | None:
        value = phone_address(address)
        if value is None:
            return None
        return next((user for user in self.list() if user.phone_address == value), None)

    def create_secondary(self, name: str) -> UserProfile:
        name = nickname(name)
        uid = uuid4().hex
        with self.storage.transaction() as connection:
            users = self._read(connection)
            if len(users) >= MAX_PROFILES:
                raise ProfileError("Luma supports one primary and up to four secondary users.")
            if any(user["nickname"].casefold() == name.casefold() for user in users):
                raise ProfileError("Choose a different name so users are easy to distinguish.")
            users.append({"id": uid, "role": "secondary", "nickname": name,
                "phone_address": None, "personal": personal_settings({}), "setup_stage": "phone",
                "wall_share_approved": False, "remote_enabled": True})
            self._save(connection, users)
        return self.get(uid)

    def rename(self, uid: str, name: str) -> UserProfile:
        name = nickname(name)
        with self.storage.transaction() as connection:
            users = self._read(connection)
            user = self._find(users, uid)
            if any(row["id"] != uid and row["nickname"].casefold() == name.casefold() for row in users):
                raise ProfileError("Choose a different name so users are easy to distinguish.")
            user["nickname"] = name
            self._save(connection, users)
        return self.get(uid)

    @staticmethod
    def _revoke(connection, uid):
        row = connection.execute("SELECT payload FROM secrets WHERE key=?", (GRANTS_KEY,)).fetchone()
        if row:
            try:
                grants = json.loads(row[0])
                if not isinstance(grants, dict):
                    raise ValueError
                kept = {key: value for key, value in grants.items()
                        if isinstance(value, dict) and value.get("profile_id") != uid}
                connection.execute("UPDATE secrets SET payload=? WHERE key=?",
                                   (json.dumps(kept, separators=(",", ":")), GRANTS_KEY))
            except (ValueError, TypeError):
                # Corrupt grants cannot grant access or prevent revocation.
                connection.execute("DELETE FROM secrets WHERE key=?", (GRANTS_KEY,))
        if uid == PRIMARY_ID:
            connection.execute("DELETE FROM secrets WHERE key IN (?,?)",
                ("companion_browser_grants_v1", "companion_google_oauth_state_v1"))

    def bind_phone(self, uid: str, address: str | None) -> UserProfile:
        address = phone_address(address)
        with self.storage.transaction() as connection:
            users = self._read(connection)
            user = self._find(users, uid)
            legacy = self._legacy(connection)
            for row in users:
                existing = phone_address(legacy.phone_address) if row["id"] == PRIMARY_ID else row["phone_address"]
                if row["id"] != uid and address is not None and existing == address:
                    raise ProfileError("That phone is already registered to another user.")
            old = phone_address(legacy.phone_address) if uid == PRIMARY_ID else user["phone_address"]
            if old != address:
                self._revoke(connection, uid)
                if uid == PRIMARY_ID:
                    legacy.phone_address = address
                    legacy.validate()
                    connection.execute("UPDATE settings SET payload=?,updated_at=? WHERE id=1",
                        (json.dumps(to_primitive(legacy), separators=(",", ":")), datetime.now(UTC).isoformat()))
                else:
                    user["phone_address"] = address
                    user["setup_stage"] = "remote" if address else "phone"
                self._save(connection, users)
        return self.get(uid)

    def update_personal(self, uid: str, updates: dict) -> UserProfile:
        with self.storage.transaction() as connection:
            users = self._read(connection)
            user = self._find(users, uid)
            if uid == PRIMARY_ID:
                legacy = self._legacy(connection)
                base = {key: deepcopy(getattr(legacy, key)) for key in PERSONAL_KEYS}
                values = personal_settings(updates, base)
                for key, value in values.items():
                    setattr(legacy, key, value)
                connection.execute("UPDATE settings SET payload=?,updated_at=? WHERE id=1",
                    (json.dumps(to_primitive(legacy), separators=(",", ":")), datetime.now(UTC).isoformat()))
            else:
                user["personal"] = personal_settings(updates, user["personal"])
                self._save(connection, users)
        return self.get(uid)

    def set_setup(self, uid: str, stage: str, *, wall_share_approved: bool | None = None) -> UserProfile:
        if stage not in SETUP_STAGES or (wall_share_approved is not None and type(wall_share_approved) is not bool):
            raise ProfileError("Choose a valid setup step.")
        with self.storage.transaction() as connection:
            users = self._read(connection)
            user = self._find(users, uid)
            user["setup_stage"] = stage
            if wall_share_approved is not None:
                user["wall_share_approved"] = wall_share_approved
            self._save(connection, users)
        return self.get(uid)

    def set_remote_enabled(self, uid: str, enabled: bool) -> UserProfile:
        if type(enabled) is not bool or (uid == PRIMARY_ID and not enabled):
            raise ProfileError("Primary remote access must remain available.")
        with self.storage.transaction() as connection:
            users = self._read(connection)
            user = self._find(users, uid)
            if user["remote_enabled"] != enabled:
                user["remote_enabled"] = enabled
                self._revoke(connection, uid)
                self._save(connection, users)
        return self.get(uid)

    @staticmethod
    def _remote_policy(connection) -> str:
        row = connection.execute("SELECT value FROM metadata WHERE key=?", (REMOTE_POLICY_KEY,)).fetchone()
        if row is None:
            return "all_profiles"
        if row[0] not in REMOTE_POLICIES:
            raise ProfileError("Saved remote access policy needs local recovery.")
        return row[0]

    def remote_policy(self) -> str:
        with closing(self.storage.connect()) as connection:
            return self._remote_policy(connection)

    def remote_allowed(self, uid: str) -> bool:
        """Admission check for every enrollment, proof and slow-operation recheck.

        This is not authorization by itself: callers must still require their
        own signed browser grant, live ANCS generation and primary admin PIN.
        Restricting remotes never changes wall consent, pairing or timers.
        """
        with closing(self.storage.connect()) as connection:
            connection.execute("BEGIN")
            user = self._find(self._read(connection), uid)
            policy = self._remote_policy(connection)
            return user["remote_enabled"] and (uid == PRIMARY_ID or policy == "all_profiles")

    def set_remote_policy(self, policy: str) -> None:
        """Primary-admin controller only; revoke guest browsers atomically.

        RAM enrollment/proof/OAuth state must additionally be cleared by that
        controller. Returning to all_profiles never restores revoked grants.
        """
        if not isinstance(policy, str) or policy not in REMOTE_POLICIES:
            raise ProfileError("Choose all users or primary-only remote access.")
        with self.storage.transaction() as connection:
            users = self._read(connection)
            if policy == "primary_only":
                for user in users:
                    if user["id"] != PRIMARY_ID:
                        self._revoke(connection, user["id"])
            connection.execute("INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                               (REMOTE_POLICY_KEY, policy))

    def remove(self, uid: str) -> None:
        if profile_id(uid) == PRIMARY_ID:
            raise ProfileError("The primary user cannot be removed.")
        with self.storage.transaction() as connection:
            users = self._read(connection)
            self._find(users, uid)
            self._revoke(connection, uid)
            self._save(connection, [user for user in users if user["id"] != uid])
            # Validated hex IDs make these fixed prefixes unambiguous in LIKE.
            connection.execute("DELETE FROM secrets WHERE key LIKE ?", (f"profile:{uid}:%",))
            connection.execute("DELETE FROM cache WHERE namespace LIKE ?", (f"profile:{uid}:%",))

    def account_storage(self, uid: str):
        self.get(uid)
        return ProfileStorage(self, uid)


class ProfileStorage:
    """Account-scoped cache/secrets, checking lifetime on every access.

Primary uses original keys so an older rollback sees its current Google grant.
Secondary namespaces never share the room's settings, voice assets or games.
"""
    def __init__(self, repository: ProfileRepository, uid: str):
        self.repository, self.id = repository, profile_id(uid)

    def key(self, value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_:-]{0,80}", value):
            raise ProfileError("Account storage key is invalid.")
        self.repository.get(self.id)
        return value if self.id == PRIMARY_ID else f"profile:{self.id}:{value}"

    def get_secret(self, key):
        return self.repository.storage.get_secret(self.key(key))

    def set_secret(self, key, payload):
        # Lifetime check and write share one transaction: deletion cannot race
        # a late OAuth refresh and resurrect a removed account's credentials.
        with self.repository.storage.transaction() as connection:
            self.repository._find(self.repository._read(connection), self.id)
            actual = key if self.id == PRIMARY_ID else f"profile:{self.id}:{key}"
            self.key(key)
            connection.execute("INSERT INTO secrets(key,payload,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                               (actual, payload, datetime.now(UTC).isoformat()))

    def get_cache(self, namespace, key, *, allow_expired=True):
        return self.repository.storage.get_cache(self.key(namespace), key, allow_expired=allow_expired)

    def set_cache(self, namespace, key, payload, *, expires_at=None):
        with self.repository.storage.transaction() as connection:
            self.repository._find(self.repository._read(connection), self.id)
            actual = self.key(namespace)
            connection.execute("INSERT INTO cache(namespace,key,payload,updated_at,expires_at) VALUES(?,?,?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,expires_at=excluded.expires_at",
                (actual, key, json.dumps(to_primitive(payload), separators=(",", ":"), sort_keys=True),
                 datetime.now(UTC).isoformat(), expires_at.isoformat() if expires_at else None))

    def consume_secret(self, key: str, expected: str) -> bool:
        with self.repository.storage.transaction() as connection:
            self.repository._find(self.repository._read(connection), self.id)
            actual = self.key(key)
            return connection.execute("DELETE FROM secrets WHERE key=? AND payload=?", (actual, expected)).rowcount == 1
