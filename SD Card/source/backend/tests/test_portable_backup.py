from copy import deepcopy
from datetime import UTC, datetime
import json

import pytest

from luma.models import Settings
from luma.portable_backup import (
    DOCUMENT_KEYS, MAGIC, PORTABLE_SETTING_KEYS, PortableBackupError,
    apply_document, decrypt, encrypt, merge_settings, snapshot, validate_document,
)
from luma.storage import Storage


NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
PASSWORD = "correct horse battery staple"


def empty_document():
    settings = Settings()
    from luma.serde import to_primitive
    raw = to_primitive(settings)
    return {
        "version": 1, "created_at": NOW.isoformat(),
        "settings": {key: raw[key] for key in PORTABLE_SETTING_KEYS},
        "countdowns": [], "transit_favorites": [],
        "scenes": {name: {"enabled": False, "automatic": False, "actions": []}
                   for name in ("morning", "night", "arrive", "away")},
        "games": {},
    }


def valid_games():
    return {
        "snake": {"body": [1, 0], "food": 3, "head": 1, "score": 120, "best": 120,
                  "pause": 0, "won": False, "previousBody": [1, 0], "elapsed": 0,
                  "moveDelay": .15, "moves": 4},
        "breaker": {"x": 350, "y": 100, "vx": 120, "vy": 220, "paddle": 340,
                    "score": 5, "level": 1, "misses": 0, "best": 5, "layout": 0,
                    "bricks": [True] * 80, "clearedPause": -1, "lost": False,
                    "pendingLevel": False, "paddleVelocity": 0, "paddleAim": 350},
        "rally": {"x": 350, "y": 230, "vx": 180, "vy": 60, "left": 230, "right": 230,
                  "score": [1, 2], "rallies": 4, "pause": 0, "matchOver": False,
                  "leftVelocity": 0, "rightVelocity": 0, "shotOffset": 0,
                  "reactionDelay": .1, "receiverSpeed": 195, "tempoVersion": 4},
        "blocks": {"board": [[None] * 10 for _ in range(20)], "queue": ["I", "O"],
                   "active": {"kind": "T", "x": 3, "y": 0, "rotation": 0}, "lines": 0,
                   "points": 0, "cleared": [], "phase": "move", "ticks": 0,
                   "target": {"x": 3, "rotation": 0, "value": 0}, "pieceId": 1,
                   "decisionTicks": 2, "fallProgress": 0},
        "invaders": {"alive": [True] * 55, "shots": [], "playerX": 320, "playerVelocity": 120,
                     "turnCooldown": .4,
                     "aimX": 320, "fleetX": 40, "fleetY": 42, "direction": 1,
                     "score": 10, "best": 10, "wave": 1, "lives": 3, "phase": "play",
                     "pause": 0, "shield": .3, "shootTimer": .2, "enemyTimer": .9,
                     "thinkTimer": .1, "rng": 7},
    }


def test_encrypted_archive_round_trip_and_randomized_salt_nonce():
    document = empty_document()
    first = encrypt(document, PASSWORD)
    second = encrypt(document, PASSWORD)
    assert first.startswith(MAGIC) and second.startswith(MAGIC)
    assert first != second
    assert decrypt(first, PASSWORD) == validate_document(document)


@pytest.mark.parametrize("password", ["", "short", "x" * 129, "contains\nnewline"])
def test_weak_or_controlled_passphrase_rejected(password):
    with pytest.raises(PortableBackupError):
        encrypt(empty_document(), password)


def test_wrong_password_tamper_and_foreign_file_fail_closed():
    encoded = encrypt(empty_document(), PASSWORD)
    with pytest.raises(PortableBackupError, match="passphrase is incorrect"):
        decrypt(encoded, "a different valid but incorrect passphrase")
    damaged = bytearray(encoded)
    damaged[-1] ^= 1
    with pytest.raises(PortableBackupError, match="passphrase is incorrect"):
        decrypt(damaged, PASSWORD)
    with pytest.raises(PortableBackupError, match="not a supported"):
        decrypt(b"not a Luma backup", PASSWORD)


def test_kdf_header_parameters_are_fixed_before_expensive_derivation():
    import struct
    encoded = encrypt(empty_document(), PASSWORD)
    start = len(MAGIC) + 2
    header_length = struct.unpack(">H", encoded[len(MAGIC):start])[0]
    header = json.loads(encoded[start:start + header_length])
    header["n"] = 2**30
    changed = json.dumps(header, sort_keys=True, separators=(",", ":")).encode()
    malicious = MAGIC + struct.pack(">H", len(changed)) + changed + encoded[start + header_length:]
    with pytest.raises(PortableBackupError):
        decrypt(malicious, PASSWORD)


def test_snapshot_is_an_explicit_allowlist_and_drops_secrets_and_runtime(tmp_path):
    store = Storage(tmp_path / "luma.db")
    settings = store.load_settings()
    settings.device_name = "Bedroom Luma"
    settings.visible_calendar_ids = ["private-calendar-id"]
    settings.sleep_calendar_ids = ["sleep-calendar-id"]
    settings.phone_address = "AA:BB:CC:DD:EE:FF"
    settings.voice_enabled = False
    store.save_settings(settings)
    store.set_secret("google.refresh", "SENTINEL_OAUTH_SECRET")
    store.set_secret("transit.511", "SENTINEL_TRANSIT_SECRET")
    store.set_cache("calendar", "events", [{"summary": "SENTINEL_PRIVATE_EVENT"}])
    store.set_cache("weather", "forecast", {"private": "SENTINEL_WEATHER"})

    document = snapshot(store, now=NOW)
    encoded = encrypt(document, PASSWORD)
    decoded = decrypt(encoded, PASSWORD)
    serialized = json.dumps(decoded)
    for sentinel in ("SENTINEL_OAUTH_SECRET", "SENTINEL_TRANSIT_SECRET", "SENTINEL_PRIVATE_EVENT",
                     "SENTINEL_WEATHER", "private-calendar-id", "sleep-calendar-id", "AA:BB:CC:DD:EE:FF"):
        assert sentinel not in serialized
    assert set(decoded) == DOCUMENT_KEYS
    assert set(decoded["settings"]) == PORTABLE_SETTING_KEYS
    assert decoded["settings"]["voice_enabled"] is False


def test_google_dates_become_unlinked_local_dates_and_scene_actions_disabled(tmp_path):
    store = Storage(tmp_path / "luma.db")
    store.set_cache("countdowns", "items", {"version": 1, "items": [{
        "id": "11111111-1111-4111-8111-111111111111", "revision": "22222222-2222-4222-8222-222222222222",
        "source": "google", "calendar_id": "private-calendar", "event_id": "private_event",
        "timezone": "America/Los_Angeles", "public": False, "title": "Dentist",
        "start": "2026-10-01T10:30:00-07:00", "all_day": False,
        "calendar_color": "#123456", "event_color": None, "state": "ready", "checked_at": NOW.isoformat(),
    }]})
    action = {"device": "purifier", "action": "power", "value": True,
              "binding": "a" * 64}
    store.set_cache("room", "scenes", {"version": 1, "revision": "33333333-3333-4333-8333-333333333333",
        "definitions": {name: {"enabled": True, "automatic": True, "actions": [action]}
                        for name in ("morning", "night", "arrive", "away")}, "runs": []})
    document = snapshot(store, now=NOW)
    archive = encrypt(document, PASSWORD)
    document = decrypt(archive, PASSWORD)
    encoded = json.dumps(document)
    assert "private-calendar" not in encoded and "private_event" not in encoded
    assert document["countdowns"] == [{"title": "Dentist", "date": "2026-10-01", "time": "10:30",
                                       "timezone": "America/Los_Angeles", "annual": False, "public": False}]
    for scene in document["scenes"].values():
        assert not scene["enabled"] and not scene["automatic"]
        assert "binding" not in scene["actions"][0]


def test_import_merges_allowlisted_preferences_without_relaxing_mute_or_links():
    current = Settings(voice_enabled=False, visible_calendar_ids=["keep-calendar"],
                       sleep_calendar_ids=["keep-sleep"], phone_address="AA:BB:CC:DD:EE:FF")
    portable = empty_document()["settings"]
    portable["voice_enabled"] = True
    portable["theme"] = "hearth"
    restored = merge_settings(current, portable)
    assert restored.theme.value == "hearth"
    assert restored.voice_enabled is False
    assert restored.visible_calendar_ids == ["keep-calendar"]
    assert restored.sleep_calendar_ids == ["keep-sleep"]
    assert restored.phone_address == "AA:BB:CC:DD:EE:FF"


def test_apply_is_transactional_and_preserves_secrets_live_links_and_most_restrictive_mute(tmp_path):
    store = Storage(tmp_path / "luma.db")
    current = store.load_settings()
    current.voice_enabled = False
    current.visible_calendar_ids = ["linked-calendar"]
    current.sleep_calendar_ids = ["linked-sleep"]
    current.phone_address = "AA:BB:CC:DD:EE:FF"
    store.save_settings(current)
    store.set_secret("google.refresh", "DO_NOT_REPLACE_REFRESH")
    store.set_secret("transit.511", "DO_NOT_REPLACE_TRANSIT")
    store.set_cache("room", "purifier", {"existing": "keep-room-binding"})
    store.set_cache("room", "fans", {"existing": "keep-fan-binding"})
    document = empty_document()
    document["settings"]["theme"] = "hearth"
    document["settings"]["voice_enabled"] = True
    document["countdowns"] = [{"title": "Dentist", "date": "2026-10-01", "time": "10:30",
                               "timezone": "America/Los_Angeles", "annual": False, "public": False}]
    restored = apply_document(store, document)
    assert restored.theme.value == "hearth" and restored.voice_enabled is False
    assert restored.visible_calendar_ids == ["linked-calendar"]
    assert restored.sleep_calendar_ids == ["linked-sleep"]
    assert restored.phone_address == "AA:BB:CC:DD:EE:FF"
    assert store.get_secret("google.refresh") == "DO_NOT_REPLACE_REFRESH"
    assert store.get_secret("transit.511") == "DO_NOT_REPLACE_TRANSIT"
    assert store.get_cache("room", "purifier") == {"existing": "keep-room-binding"}
    assert store.get_cache("room", "fans") == {"existing": "keep-fan-binding"}
    from luma.countdowns import Countdowns
    imported_dates = Countdowns(store)
    assert not imported_dates.recovery_error and imported_dates.items[0]["title"] == "Dentist"
    from luma.scenes import Scenes
    imported_scenes = Scenes(store)
    assert not imported_scenes.recovery_error
    assert all(not row["enabled"] and not row["automatic"] for row in imported_scenes.definitions.values())


def test_failed_restore_validation_leaves_database_untouched(tmp_path):
    store = Storage(tmp_path / "luma.db")
    before = store.load_settings()
    document = empty_document()
    document["settings"]["theme"] = "not-a-theme"
    with pytest.raises(PortableBackupError):
        apply_document(store, document)
    assert store.load_settings() == before
    assert store.get_cache("countdowns", "items") is None


def test_document_rejects_unknown_fields_bad_settings_and_unvalidated_game_saves():
    document = empty_document()
    extra = deepcopy(document)
    extra["oauth_token"] = "secret"
    with pytest.raises(PortableBackupError):
        validate_document(extra)
    malformed = deepcopy(document)
    malformed["settings"]["brightness"] = 10000
    with pytest.raises(PortableBackupError):
        validate_document(malformed)
    games = deepcopy(document)
    games["games"]["snake"] = {"arbitrary": "not schema validated"}
    with pytest.raises(PortableBackupError, match="game checkpoint"):
        validate_document(games)


def test_all_five_browser_game_checkpoints_round_trip_only_after_schema_validation():
    document = empty_document()
    document["games"] = valid_games()
    restored = decrypt(encrypt(document, PASSWORD), PASSWORD)
    assert restored["games"] == document["games"]
    redeploying = deepcopy(document)
    redeploying["games"]["invaders"].update(phase="redeploy", pause=.6, lives=1, score=330, wave=2)
    assert validate_document(redeploying)["games"]["invaders"]["phase"] == "redeploy"
    impossible = deepcopy(document)
    impossible["games"]["invaders"].update(phase="play", lives=0)
    with pytest.raises(PortableBackupError):
        validate_document(impossible)
    for key, mutation in (("snake", lambda g: g.update(food=g["body"][0])),
                          ("breaker", lambda g: g.update(bricks=[True])),
                          ("rally", lambda g: g.update(score=[1, -1])),
                          ("blocks", lambda g: g.update(board=[[{}] * 10] * 20)),
                          ("invaders", lambda g: g.update(alive=[True]))):
        bad = deepcopy(document)
        mutation(bad["games"][key])
        with pytest.raises(PortableBackupError):
            validate_document(bad)


def test_archive_and_plaintext_size_limits():
    document = empty_document()
    document["settings"]["weather_location_label"] = "x" * 800000
    with pytest.raises(PortableBackupError, match="larger than"):
        encrypt(document, PASSWORD)
    with pytest.raises(PortableBackupError):
        decrypt(b"x" * (1024 * 1024 + 1), PASSWORD)
