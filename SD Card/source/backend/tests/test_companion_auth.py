"""Dormant core tests; no Serve, iPhone or real PIN/account access."""
import base64
from dataclasses import replace
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from luma.companion_auth import (
    CompanionAuth, CompanionDenied, GRANTS_KEY, MAX_CHALLENGES, MAX_GRANTS,
    PhonePresence, enrollment_message, private_origin, request_message,
)
from luma.security import SecurityManager
from luma.storage import Storage

ORIGIN = "https://luma.example-tail.ts.net"
IDENTITY = "owner@example.test"
PHONE = PhonePresence("AA:BB:CC:DD:EE:FF", True, "session-1")
PATH = "/remote/api/preview"


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def key_pair():
    key = ec.generate_private_key(ec.SECP256R1())
    public = b64(key.public_key().public_bytes(serialization.Encoding.X962,
                                               serialization.PublicFormat.UncompressedPoint))
    return key, public


def sign(key, message):
    r, s = decode_dss_signature(key.sign(message, ec.ECDSA(hashes.SHA256())))
    return b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


@pytest.fixture
def rig(tmp_path):
    storage = Storage(tmp_path / "luma.db")
    SecurityManager(storage).set_pin("123456")
    state = {"phone": PHONE, "time": 100.0}
    auth = CompanionAuth(storage, lambda: state["phone"], clock=lambda: state["time"])
    return auth, storage, state


def enroll(auth):
    key, public = key_pair()
    ticket = auth.issue_ticket("123456", ORIGIN)
    claim = auth.claim(ticket, ORIGIN, IDENTITY, public,
                       sign(key, enrollment_message(ticket, ORIGIN, IDENTITY, public)))
    auth.approve("123456", claim["device_id"], claim["comparison_code"])
    return key, claim["device_id"]


def proof(auth, key, device_id, *, method="GET", path=PATH, body=b""):
    nonce = auth.challenge(device_id, ORIGIN, IDENTITY, method, path,
                           hashlib.sha256(body).hexdigest())["nonce"]
    signature = sign(key, request_message(device_id, nonce, ORIGIN, IDENTITY, method, path, body))
    return (device_id, nonce, ORIGIN, IDENTITY, method, path, body, signature)


def test_enrollment_requires_matching_local_pin_approval(rig):
    auth, storage, _ = rig
    key, public = key_pair()
    ticket = auth.issue_ticket("123456", ORIGIN)
    claim = auth.claim(ticket, ORIGIN, IDENTITY, public,
                       sign(key, enrollment_message(ticket, ORIGIN, IDENTITY, public)))
    assert storage.get_secret(GRANTS_KEY) is None
    with pytest.raises(CompanionDenied):
        auth.challenge(claim["device_id"], ORIGIN, IDENTITY, "GET", PATH, hashlib.sha256(b"").hexdigest())
    with pytest.raises(CompanionDenied):
        auth.approve("111111", claim["device_id"], claim["comparison_code"])
    with pytest.raises(CompanionDenied):
        auth.approve("123456", claim["device_id"], "incorrect")
    assert auth.pending_status("123456") == claim
    auth.approve("123456", claim["device_id"], claim["comparison_code"])
    assert auth.verify(*proof(auth, key, claim["device_id"])) == PHONE
    assert auth.pending_status("123456") is None
    with pytest.raises(CompanionDenied):
        auth.claim(ticket, ORIGIN, IDENTITY, public,
                   sign(key, enrollment_message(ticket, ORIGIN, IDENTITY, public)))


def test_ticket_not_persisted_and_new_ticket_invalidates_old(rig):
    auth, storage, _ = rig
    key, public = key_pair()
    old = auth.issue_ticket("123456", ORIGIN)
    auth.issue_ticket("123456", ORIGIN)
    with pytest.raises(CompanionDenied):
        auth.claim(old, ORIGIN, IDENTITY, public,
                   sign(key, enrollment_message(old, ORIGIN, IDENTITY, public)))
    with storage.connect() as db:
        content = json.dumps([list(row) for row in db.execute("SELECT payload FROM secrets")])
    assert old not in content


def test_unavailable_presence_clears_ephemeral_authority_with_fixed_error(rig):
    auth, _, _ = rig
    key, device_id = enroll(auth)
    args = proof(auth, key, device_id)
    def unavailable():
        raise RuntimeError('private provider data must not escape')
    auth.presence = unavailable
    with pytest.raises(CompanionDenied, match='Connect the selected iPhone') as error:
        auth.verify(*args)
    assert 'provider' not in str(error.value)
    assert auth.challenges == {}
    assert auth.ticket is auth.pending is None


@pytest.mark.parametrize("change", ["expired", "disconnect", "generation", "phone"])
def test_pending_enrollment_expires_or_loses_presence(rig, change):
    auth, _, state = rig
    key, public = key_pair()
    ticket = auth.issue_ticket("123456", ORIGIN)
    claim = auth.claim(ticket, ORIGIN, IDENTITY, public,
                       sign(key, enrollment_message(ticket, ORIGIN, IDENTITY, public)))
    if change == "expired": state["time"] += 300
    elif change == "disconnect": state["phone"] = replace(PHONE, authorized=False)
    elif change == "generation": state["phone"] = replace(PHONE, generation="session-2")
    else: state["phone"] = replace(PHONE, address="11:22:33:44:55:66")
    with pytest.raises(CompanionDenied):
        auth.approve("123456", claim["device_id"], claim["comparison_code"])


def test_grant_survives_api_restart_but_challenge_does_not(rig):
    auth, storage, state = rig
    key, device_id = enroll(auth)
    old = proof(auth, key, device_id)
    restarted = CompanionAuth(storage, lambda: state["phone"], clock=lambda: state["time"])
    with pytest.raises(CompanionDenied): restarted.verify(*old)
    assert restarted.verify(*proof(restarted, key, device_id)) == PHONE


@pytest.mark.parametrize("changed", ["body", "path", "method", "identity", "origin", "key", "signature"])
def test_tampering_fails_and_consumes_nonce(rig, changed):
    auth, _, _ = rig
    key, device_id = enroll(auth)
    good = proof(auth, key, device_id, method="POST", path="/remote/api/command", body=b'{"name":"wake"}')
    bad = list(good)
    if changed == "body": bad[6] = b'{"name":"good_night"}'
    elif changed == "path": bad[5] = "/remote/api/updates/install"
    elif changed == "method": bad[4] = "PATCH"
    elif changed == "identity": bad[3] = "another@example.test"
    elif changed == "origin": bad[2] = "https://other.example-tail.ts.net"
    elif changed == "key":
        other, _ = key_pair()
        bad[7] = sign(other, request_message(*good[:7]))
    else: bad[7] = b64(bytes(64))
    with pytest.raises(CompanionDenied): auth.verify(*bad)
    with pytest.raises(CompanionDenied): auth.verify(*good)


@pytest.mark.parametrize("change", ["expired", "disconnect", "generation", "phone", "revoked"])
def test_proofs_and_slow_results_fail_when_authority_changes(rig, change):
    auth, _, state = rig
    key, device_id = enroll(auth)
    args = proof(auth, key, device_id)
    if change == "expired": state["time"] += 30
    elif change == "disconnect": state["phone"] = replace(PHONE, authorized=False)
    elif change == "generation": state["phone"] = replace(PHONE, generation="session-2")
    elif change == "phone": state["phone"] = replace(PHONE, address="11:22:33:44:55:66")
    else: auth.revoke("123456", device_id)
    with pytest.raises(CompanionDenied): auth.verify(*args)
    if change != "expired":
        with pytest.raises(CompanionDenied): auth.still_authorized(device_id, ORIGIN, IDENTITY, PHONE)


def test_replay_and_revocation_preserve_unrelated_settings(rig):
    auth, storage, _ = rig
    before = storage.load_settings()
    key, device_id = enroll(auth)
    args = proof(auth, key, device_id)
    auth.verify(*args)
    with pytest.raises(CompanionDenied): auth.verify(*args)
    assert auth.devices("123456") == [{"device_id": device_id, "label": "iPhone browser"}]
    with pytest.raises(CompanionDenied): auth.revoke("111111", device_id)
    auth.revoke("123456", device_id)
    assert auth.devices("123456") == []
    assert storage.load_settings() == before


@pytest.mark.parametrize("origin", ["http://luma.example-tail.ts.net", "https://evil.test",
    "https://luma.example-tail.ts.net/", "https://luma.example-tail.ts.net:443",
    "https://a@luma.example-tail.ts.net", "https://luma.example-tail.ts.net#x", "https://luma.example-tail.ts.net?x"])
def test_private_origin_is_fixed_canonical_https(origin):
    with pytest.raises(CompanionDenied): private_origin(origin)


@pytest.mark.parametrize("method,path,body", [("GET", "/api/v1/settings", b""),
    ("POST", "/remote/api/preview", b""), ("GET", PATH + "?x=1", b""),
    ("GET", PATH, b"x"), ("POST", "/remote/api/command", b"x" * 65537)])
def test_proof_never_authorizes_arbitrary_paths_or_bodies(method, path, body):
    with pytest.raises(CompanionDenied):
        request_message("a" * 43, "b" * 43, ORIGIN, IDENTITY, method, path, body)


def test_challenge_storage_is_bounded_and_expiry_releases_capacity(rig):
    auth, _, state = rig
    _, device_id = enroll(auth)
    for _ in range(MAX_CHALLENGES):
        auth.challenge(device_id, ORIGIN, IDENTITY, "GET", PATH, hashlib.sha256(b"").hexdigest())
    with pytest.raises(CompanionDenied):
        auth.challenge(device_id, ORIGIN, IDENTITY, "GET", PATH, hashlib.sha256(b"").hexdigest())
    state["time"] += 30
    auth.challenge(device_id, ORIGIN, IDENTITY, "GET", PATH, hashlib.sha256(b"").hexdigest())
    assert len(auth.challenges) == 1


def test_enrollment_limit_does_not_silently_evict(rig):
    auth, _, _ = rig
    for _ in range(MAX_GRANTS): enroll(auth)
    with pytest.raises(CompanionDenied): enroll(auth)
    assert len(auth.devices("123456")) == MAX_GRANTS


@pytest.mark.parametrize("encoded", ["[]", '{"invalid":{}}', '{"x":null}', "not json"])
def test_corrupt_grants_fail_closed_without_erasing(rig, encoded):
    auth, storage, _ = rig
    storage.set_secret(GRANTS_KEY, encoded)
    with pytest.raises(CompanionDenied): auth.devices("123456")
    assert storage.get_secret(GRANTS_KEY) == encoded
