"""Encrypted, settings-only portable backups; never a SQLite/database export.

This module deliberately separates portable preferences from private recovery
backups. It does not discover or write removable media; callers must use the
privileged USB broker and supply only a selected, verified removable target.
"""
from __future__ import annotations

from copy import deepcopy
import base64
from datetime import UTC, datetime
import math
import json
import os
import struct
from zoneinfo import ZoneInfo
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .backup_envelope import (_no_duplicate_pairs, MAGIC, MAX_ARCHIVE_BYTES, NONCE_BYTES, SALT_BYTES,
                              SCRYPT_N, SCRYPT_P, SCRYPT_R, TAG_BYTES, VERSION,
                              validate_archive_envelope)
from .countdowns import Countdowns, manual_values
from .models import Settings
from .serde import settings_from_dict, to_primitive
from .scenes import SCENES, definition as scene_definition
from .transit import Transit, favorite_values


MAX_DOCUMENT_BYTES = 768 * 1024
MAX_PASSPHRASE_CHARS = 128

# Account-specific calendar identifiers and phone pairing identity are
# intentionally excluded. Those links must be configured again on the target.
PORTABLE_SETTING_KEYS = frozenset({
    "device_name", "theme", "orientation", "brightness", "night_clock_enabled",
    "night_brightness", "volume", "timezone", "latitude", "longitude",
    "weather_location_label", "departure_enabled", "departure_prep_minutes",
    "departure_travel_minutes", "departure_include_virtual", "sleep_event_title",
    "timer_focus_minutes", "timer_break_minutes", "weather_nudges_enabled",
    "weather_rain_percent", "weather_gust_mph", "weather_hot_f", "weather_cold_f",
    "voice_enabled", "cycle",
})
DOCUMENT_KEYS = frozenset({"version", "created_at", "settings", "countdowns", "transit_favorites", "scenes", "games"})
GAME_FIELDS = {
    "snake": ({"body", "food", "head", "score", "best", "pause", "won"},
              {"previousBody", "elapsed", "moveDelay", "moves"}),
    "breaker": ({"x", "y", "vx", "vy", "paddle", "score", "level", "misses", "best", "layout", "bricks", "clearedPause", "lost", "pendingLevel"},
                {"paddleVelocity", "paddleAim"}),
    "rally": ({"x", "y", "vx", "vy", "left", "right", "score", "rallies", "pause", "matchOver"},
              {"leftVelocity", "rightVelocity", "shotOffset", "reactionDelay", "receiverSpeed", "tempoVersion"}),
    "blocks": ({"board", "queue", "active", "lines", "points", "cleared", "phase", "ticks", "target"},
               {"pieceId", "decisionTicks", "fallProgress"}),
    "invaders": ({"alive", "shots", "playerX", "playerVelocity", "turnCooldown", "aimX", "fleetX", "fleetY", "direction",
                  "score", "best", "wave", "lives", "phase", "pause", "shield", "shootTimer", "enemyTimer",
                  "thinkTimer", "rng"}, set()),
}
PIECES = {"I", "J", "L", "O", "S", "T", "Z"}


def _finite(value, minimum=-1e9, maximum=1e9):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _game_record(key, data):
    required, optional = GAME_FIELDS[key]
    if (not isinstance(data, dict) or not required <= set(data)
            or set(data) - required - optional):
        return False
    for name in optional & set(data):
        value = data[name]
        if name == "previousBody":
            if not isinstance(value, list) or not 1 <= len(value) <= 640 or any(not _integer(cell, 0, 639) for cell in value):
                return False
        elif name == "shotOffset":
            if not _finite(value, -80, 80): return False
        elif name == "reactionDelay":
            if not _finite(value, 0, .2): return False
        elif name == "receiverSpeed":
            if not _finite(value, 230 * .78, 280): return False
        elif name == "paddleAim":
            if not _finite(value, 52, 648): return False
        elif name == "decisionTicks":
            if not _integer(value, 0, 4): return False
        elif name == "fallProgress":
            if not _finite(value, 0, 1) or value == 1: return False
        elif name == "tempoVersion":
            if value not in (2, 3, 4) or type(value) is not int: return False
        elif not _finite(value, .01 if name == "moveDelay" else -1000 if name.endswith("Velocity") else 0,
                         1 if name == "moveDelay" else 1e9):
            return False
    if key == "snake":
        body = data["body"]
        return (isinstance(body, list) and 1 <= len(body) <= 640
                and all(_integer(cell, 0, 639) for cell in body) and len(set(body)) == len(body)
                and data["head"] == body[0] and _integer(data["food"], -1, 639)
                and data["food"] not in body and _integer(data["score"], 0, 1e9)
                and _integer(data["best"], 0, 1e9) and _integer(data["pause"], 0, 20)
                and type(data["won"]) is bool)
    if key in {"breaker", "rally"}:
        if not (_finite(data["x"], -20, 720) and _finite(data["y"], 0, 480)
                and _finite(data["vx"], -1000, 1000) and _finite(data["vy"], -1000, 1000)):
            return False
        if key == "breaker":
            return (isinstance(data["bricks"], list) and len(data["bricks"]) == 80
                    and all(type(cell) is bool for cell in data["bricks"])
                    and _integer(data["layout"], 0, 19) and _integer(data["score"], 0, 1e9)
                    and _integer(data["best"], 0, 1e9) and _integer(data["level"], 1, 1e9)
                    and _integer(data["misses"], 0, 1e9) and _finite(data["paddle"], 52, 648)
                    and _finite(data["clearedPause"], -1, 2) and type(data["lost"]) is bool
                    and type(data["pendingLevel"]) is bool)
        return (isinstance(data["score"], list) and len(data["score"]) == 2
                and all(_integer(score, 0, 1e9) for score in data["score"])
                and _finite(data["left"], 52, 408) and _finite(data["right"], 52, 408)
                and _integer(data["rallies"], 0, 1e9) and _finite(data["pause"], -1, 3)
                and type(data["matchOver"]) is bool)
    if key == "invaders":
        return (isinstance(data["alive"], list) and len(data["alive"]) == 55
                and all(type(value) is bool for value in data["alive"])
                and isinstance(data["shots"], list) and len(data["shots"]) <= 4
                and all(isinstance(shot, dict) and set(shot) == {"x", "y", "enemy"}
                        and _finite(shot["x"], 0, 640) and _finite(shot["y"], 0, 400)
                        and type(shot["enemy"]) is bool for shot in data["shots"])
                and _finite(data["playerX"], 22, 618) and data["playerVelocity"] in (-120, 120)
                and _finite(data["turnCooldown"], 0, 1)
                and _finite(data["aimX"], 30, 610) and _finite(data["fleetX"], 8, 136)
                and _finite(data["fleetY"], 42, 240) and type(data["direction"]) is int
                and data["direction"] in (-1, 1) and _integer(data["score"], 0, 1e9)
                and _integer(data["best"], 0, 1e9) and _integer(data["wave"], 1, 1e6)
                and _integer(data["lives"], 0, 3) and data["phase"] in {"play", "wave", "redeploy", "lost"}
                and ((data["phase"] == "lost" and data["lives"] == 0)
                     or (data["phase"] != "lost" and data["lives"] > 0))
                and _finite(data["pause"], 0, 2) and _finite(data["shield"], 0, 1)
                and _finite(data["shootTimer"], -2, 2) and _finite(data["enemyTimer"], -3, 3)
                and _finite(data["thinkTimer"], 0, 1) and _integer(data["rng"], 1, 0xFFFFFFFF))
    board, queue, active, target = (data["board"], data["queue"], data["active"], data["target"])
    return (isinstance(board, list) and len(board) == 20
            and all(isinstance(row, list) and len(row) == 10 and all(cell is None or isinstance(cell, str) and cell in PIECES for cell in row) for row in board)
            and isinstance(queue, list) and 1 <= len(queue) <= 20 and all(isinstance(cell, str) and cell in PIECES for cell in queue)
            and isinstance(active, dict) and set(active) == {"kind", "x", "y", "rotation"}
            and isinstance(active["kind"], str) and active["kind"] in PIECES and _integer(active["x"], -4, 10)
            and _integer(active["y"], -4, 20) and _integer(active["rotation"], 0, 3)
            and _integer(data["lines"], 0, 1e9) and _integer(data["points"], 0, 1e9)
            and isinstance(data["cleared"], list) and len(data["cleared"]) <= 20
            and all(_integer(row, 0, 19) for row in data["cleared"])
            and isinstance(data["phase"], str) and data["phase"] in {"move", "fall", "lock", "clear", "over"}
            and _integer(data["ticks"], 0, 30) and isinstance(target, dict)
            and set(target) == {"x", "rotation", "value"} and _integer(target["x"], -4, 10)
            and _integer(target["rotation"], 0, 3) and _finite(target["value"], -1e6, 1e6))


def _safe_games(value):
    if not isinstance(value, dict) or set(value) - set(GAME_FIELDS) or len(value) > len(GAME_FIELDS):
        raise PortableBackupError("The saved game section is invalid.")
    try:
        if len(json.dumps(value, separators=(",", ":"), allow_nan=False)) > 100_000:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise PortableBackupError("The saved game section is too large or invalid.") from None
    if any(not _game_record(key, game) for key, game in value.items()):
        raise PortableBackupError("A game checkpoint failed its versioned safety check.")
    return deepcopy(value)


class PortableBackupError(ValueError):
    """Safe, non-sensitive error for malformed, unsupported or unauthentic data."""


def _json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _passphrase(value: str) -> bytes:
    if (not isinstance(value, str) or not 12 <= len(value) <= MAX_PASSPHRASE_CHARS
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise PortableBackupError("Use a passphrase of 12 to 128 printable characters.")
    return value.encode("utf-8")


def _derive(password: bytes, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(password)


def _safe_settings(value):
    if not isinstance(value, dict) or set(value) != PORTABLE_SETTING_KEYS:
        raise PortableBackupError("The portable settings section is invalid.")
    try:
        candidate = settings_from_dict({**to_primitive(Settings()), **deepcopy(value)})
        candidate.validate()
    except Exception as exc:
        raise PortableBackupError("One or more saved settings are invalid.") from exc
    return {key: to_primitive(getattr(candidate, key)) for key in PORTABLE_SETTING_KEYS}


def _safe_countdowns(value):
    if not isinstance(value, list) or len(value) > 12:
        raise PortableBackupError("The portable countdown section is invalid.")
    clean = []
    for row in value:
        if not isinstance(row, dict) or set(row) != {"title", "date", "time", "timezone", "annual", "public"}:
            raise PortableBackupError("A saved countdown is invalid.")
        try:
            manual_values(row["title"], row["date"], row["time"], row["timezone"], row["annual"], row["public"])
        except Exception as exc:
            raise PortableBackupError("A saved countdown is invalid.") from exc
        clean.append(deepcopy(row))
    return clean


def _safe_transit(value):
    if not isinstance(value, list) or len(value) > 6:
        raise PortableBackupError("The portable transit section is invalid.")
    fields = ("title", "operator_id", "operator_name", "agency", "stop_id", "stop_name", "route_id", "line", "direction", "monitored", "public")
    clean = []
    try:
        for row in value:
            if not isinstance(row, dict) or set(row) != set(fields):
                raise ValueError()
            clean.append(favorite_values(**row))
    except Exception as exc:
        raise PortableBackupError("A saved transit favorite is invalid.") from exc
    return clean


def _safe_scenes(value):
    if not isinstance(value, dict) or set(value) != {"morning", "night", "arrive", "away"}:
        raise PortableBackupError("The portable scene section is invalid.")
    clean = {}
    for name, row in value.items():
        if (not isinstance(row, dict) or set(row) != {"enabled", "automatic", "actions"}
                or type(row["enabled"]) is not bool or type(row["automatic"]) is not bool
                or not isinstance(row["actions"], list) or len(row["actions"]) > 8):
            raise PortableBackupError("A saved scene is invalid.")
        actions = []
        for item in row["actions"]:
            if (not isinstance(item, dict) or set(item) not in
                    ({"device", "action", "value"}, {"device", "action", "value", "binding"})
                    or "binding" in item and item["binding"] != "0" * 64):
                raise PortableBackupError("A saved scene action is invalid.")
            # Bindings are hardware identities and must never migrate. Preserve
            # only the intent; the restore path will disable it pending review.
            actions.append({"device": item["device"], "action": item["action"],
                            "value": deepcopy(item["value"]), "binding": "0" * 64})
        try:
            checked = scene_definition({"enabled": False, "automatic": False, "actions": actions})
            clean[name] = {"enabled": False, "automatic": False,
                           "actions": [{key: item[key] for key in ("device", "action", "value")} for item in checked["actions"]]}
        except Exception as exc:
            raise PortableBackupError("A saved scene action is invalid.") from exc
    return clean


def validate_document(value):
    if (not isinstance(value, dict) or set(value) != DOCUMENT_KEYS
            or type(value.get("version")) is not int or value["version"] != VERSION):
        raise PortableBackupError("This is not a supported Luma settings backup.")
    try:
        created = datetime.fromisoformat(value["created_at"])
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError()
    except (ValueError, TypeError):
        raise PortableBackupError("The backup date is invalid.") from None
    games = _safe_games(value["games"])
    return {"version": VERSION, "created_at": created.astimezone(UTC).isoformat(),
            "settings": _safe_settings(value["settings"]),
            "countdowns": _safe_countdowns(value["countdowns"]),
            "transit_favorites": _safe_transit(value["transit_favorites"]),
            "scenes": _safe_scenes(value["scenes"]), "games": games}


def snapshot(storage, *, now=None, games=None):
    """Create the explicit portable allowlist from durable stores only."""
    raw_settings = to_primitive(storage.load_settings())
    portable = {key: deepcopy(raw_settings[key]) for key in PORTABLE_SETTING_KEYS}
    countdown_store, transit_store = Countdowns(storage), Transit(storage)
    if countdown_store.recovery_error or transit_store.recovery_error:
        raise PortableBackupError("Saved dates or transit settings need recovery; nothing was exported.")
    dates = []
    for row in countdown_store.items:
        if row["source"] == "manual":
            dates.append({key: deepcopy(row[key]) for key in ("title", "date", "time", "timezone", "annual", "public")})
        else:
            # Keep the useful date as a local, unlinked reminder. No Google
            # calendar/event identifiers, ETags or account metadata migrate.
            start = datetime.fromisoformat(row["start"]).astimezone(ZoneInfo(row["timezone"]))
            dates.append({"title": row["title"], "date": start.date().isoformat(),
                          "time": None if row["all_day"] else start.strftime("%H:%M"),
                          "timezone": row["timezone"], "annual": False, "public": row["public"]})
    scenes_raw = storage.get_cache("room", "scenes")
    if scenes_raw is None:
        scenes = {name: {"enabled": False, "automatic": False, "actions": []} for name in ("morning", "night", "arrive", "away")}
    else:
        try:
            from .scenes import Scenes
            Scenes.validate(scenes_raw)
            scenes = {name: {"enabled": False, "automatic": False,
                             "actions": [{key: deepcopy(action[key]) for key in ("device", "action", "value")}
                                         for action in scenes_raw["definitions"][name]["actions"]]}
                      for name in ("morning", "night", "arrive", "away")}
        except Exception as exc:
            raise PortableBackupError("Saved scenes need recovery; nothing was exported.") from exc
    document = {"version": VERSION, "created_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
                "settings": portable, "countdowns": dates,
                "transit_favorites": [{key: deepcopy(row[key]) for key in
                                       ("title", "operator_id", "operator_name", "agency", "stop_id", "stop_name", "route_id", "line", "direction", "monitored", "public")}
                                      for row in transit_store.items],
                "scenes": scenes, "games": {} if games is None else games}
    return validate_document(document)


def merge_settings(current: Settings, portable: dict) -> Settings:
    """Overlay portable preferences while preserving linked accounts and mute."""
    safe = _safe_settings(portable)
    merged = {**to_primitive(current), **safe}
    merged["voice_enabled"] = bool(current.voice_enabled and safe["voice_enabled"])
    # Deliberately never import calendar IDs, phone identity, onboarding state,
    # PIN policy, cloud settings, provider credentials or radio/privacy state.
    result = settings_from_dict(merged)
    result.validate()
    return result


def apply_document(storage, document, current: Settings | None = None) -> Settings:
    """Validate first, then replace only portable records in one SQLite transaction.

    Callers must quiesce their in-memory integrations and install the returned
    Settings plus reload Countdown/Transit/Scenes state after this commits.
    Existing secrets, calendar/task links, room device bindings and live state
    are never touched here.
    """
    clean = validate_document(document)
    restored = merge_settings(current or storage.load_settings(), clean["settings"])
    now = datetime.now(UTC).isoformat()
    countdown_items = []
    for item in clean["countdowns"]:
        countdown_items.append({"source": "manual", **deepcopy(item), "id": str(uuid4()), "revision": str(uuid4())})
    transit_items = [{**deepcopy(item), "id": str(uuid4()), "revision": str(uuid4()), "sample": None}
                     for item in clean["transit_favorites"]]
    scene_definitions = {}
    for name in SCENES:
        portable_scene = clean["scenes"][name]
        # The placeholder binding cannot match a discovered device. The regular
        # scene UI will require explicit review and rebind before use.
        scene_definitions[name] = scene_definition({"enabled": False, "automatic": False,
            "actions": [{**action, "binding": "0" * 64} for action in portable_scene["actions"]]})
    scene_record = {"version": 1, "revision": str(uuid4()),
                    "definitions": scene_definitions, "runs": []}
    try:
        from .scenes import Scenes
        Scenes.validate(scene_record)
    except Exception as exc:
        raise PortableBackupError("The restored scenes could not be validated.") from exc
    settings_payload = json.dumps(to_primitive(restored), separators=(",", ":"), sort_keys=True)
    countdown_payload = json.dumps({"version": 1, "items": countdown_items}, separators=(",", ":"), sort_keys=True)
    transit_payload = json.dumps({"version": 1, "items": transit_items}, separators=(",", ":"), sort_keys=True)
    scene_payload = json.dumps(scene_record, separators=(",", ":"), sort_keys=True)
    with storage.transaction() as connection:
        connection.execute("UPDATE settings SET payload=?, updated_at=? WHERE id=1", (settings_payload, now))
        connection.execute("INSERT INTO audit_log(kind,payload,created_at) VALUES(?,?,?)",
                           ("settings.portable_restore", settings_payload, now))
        for namespace, key, payload in (("countdowns", "items", countdown_payload),
                                        ("transit", "favorites", transit_payload),
                                        ("room", "scenes", scene_payload)):
            connection.execute("""INSERT INTO cache(namespace,key,payload,updated_at,expires_at)
                VALUES(?,?,?,?,NULL) ON CONFLICT(namespace,key) DO UPDATE SET
                payload=excluded.payload,updated_at=excluded.updated_at,expires_at=NULL""",
                (namespace, key, payload, now))
    return restored


def encrypt(document, passphrase: str) -> bytes:
    password = _passphrase(passphrase)
    try:
        clean = validate_document(document)
        plaintext = _json_bytes(clean)
    except PortableBackupError:
        raise
    except Exception as exc:
        raise PortableBackupError("The portable backup could not be prepared.") from exc
    if len(plaintext) > MAX_DOCUMENT_BYTES:
        raise PortableBackupError("The settings backup is larger than the supported limit.")
    salt, nonce = os.urandom(SALT_BYTES), os.urandom(NONCE_BYTES)
    header = {"version": VERSION, "cipher": "AES-256-GCM", "kdf": "scrypt", "n": SCRYPT_N,
              "r": SCRYPT_R, "p": SCRYPT_P, "salt": base64.urlsafe_b64encode(salt).decode(),
              "nonce": base64.urlsafe_b64encode(nonce).decode()}
    aad = _json_bytes(header)
    encrypted = AESGCM(_derive(password, salt)).encrypt(nonce, plaintext, MAGIC + aad)
    result = MAGIC + struct.pack(">H", len(aad)) + aad + encrypted
    if len(result) > MAX_ARCHIVE_BYTES:
        raise PortableBackupError("The settings backup is larger than the supported limit.")
    return result


def decrypt(blob: bytes, passphrase: str):
    password = _passphrase(passphrase)
    if not validate_archive_envelope(blob):
        raise PortableBackupError("This file is not a supported Luma settings backup.")
    raw = bytes(blob)
    header_length = struct.unpack(">H", raw[len(MAGIC):len(MAGIC) + 2])[0]
    start = len(MAGIC) + 2
    if not 1 <= header_length <= 1024 or start + header_length + TAG_BYTES > len(raw):
        raise PortableBackupError("This file is not a supported Luma settings backup.")
    aad, encrypted = raw[start:start + header_length], raw[start + header_length:]
    try:
        header = json.loads(aad, object_pairs_hook=_no_duplicate_pairs)
        expected = {"version": VERSION, "cipher": "AES-256-GCM", "kdf": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}
        if not isinstance(header, dict) or any(header.get(key) != value for key, value in expected.items()) or set(header) != set(expected) | {"salt", "nonce"}:
            raise ValueError()
        salt, nonce = base64.b64decode(header["salt"], altchars=b"-_", validate=True), base64.b64decode(header["nonce"], altchars=b"-_", validate=True)
        if len(salt) != SALT_BYTES or len(nonce) != NONCE_BYTES:
            raise ValueError()
        plaintext = AESGCM(_derive(password, salt)).decrypt(nonce, encrypted, MAGIC + aad)
        if len(plaintext) > MAX_DOCUMENT_BYTES:
            raise ValueError()
        document = json.loads(plaintext, object_pairs_hook=_no_duplicate_pairs)
        return validate_document(document)
    except (InvalidTag, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise PortableBackupError("The passphrase is incorrect or the backup is damaged.") from None
