import base64
import hashlib
from pathlib import Path
import re
import ssl
from unittest.mock import AsyncMock
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from luma import eduroam
from luma.api import create_app
from luma.network import ROOT, connection_settings, security_kind, validate_request
from test_network import fake_manager

ASSETS = Path(eduroam.__file__).with_name("assets")
PROPS = {"Ssid": b"eduroam", "Mode": 2, "Flags": 1, "RsnFlags": 0x288}
REQUEST = {"action": "connect", "device": ROOT + "/Devices/2", "access_point": ROOT + "/AccessPoint/1", "identity": "example@stanford.edu", "password": "test-only-not-a-real-password"}


@pytest.fixture
def certificate_path(monkeypatch):
    path = ASSETS / "stanford-eduroam-ca.pem"
    monkeypatch.setattr(eduroam, "CA_PATH", path)
    return path


def test_official_profile_snapshot_and_certificate_provenance():
    raw = (ASSETS / "stanford-eduroam.eap-config").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "f10db53312b2ba95697480608edd4da7197c571aa6b165ebf388855a9f30973f"
    root = ET.fromstring(raw)
    provider = root.find("EAPIdentityProvider")
    assert provider.attrib["ID"] == "stanford.edu"
    method = provider.find("AuthenticationMethods/AuthenticationMethod")
    assert method.findtext("EAPMethod/Type") == "21"
    assert method.findtext("InnerAuthenticationMethod/EAPMethod/Type") == "26"
    assert method.findtext("ClientSideCredential/InnerIdentitySuffix") == "stanford.edu"
    assert tuple(n.text for n in method.findall("ServerSideCredential/ServerID")) == eduroam.SERVER_NAMES
    assert provider.findtext("CredentialApplicability/IEEE80211/SSID") == "eduroam"
    assert provider.findtext("CredentialApplicability/IEEE80211/MinRSNProto") == "CCMP"
    certs = [base64.b64decode(n.text, validate=True) for n in method.findall("ServerSideCredential/CA")]
    assert [hashlib.sha256(c).hexdigest() for c in certs] == [
        "38b9a448072ba750faef663affbbb0aec4a8270a4b38bdbdaedef8fe66f5a607",
        "17d431f9d968f1907a415c4f5c9e13b827f15f7027eff83cdb75f77d95dd9113",
    ]
    bundle = (ASSETS / "stanford-eduroam-ca.pem").read_text()
    bundled = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", bundle, re.S)
    assert [ssl.PEM_cert_to_DER_cert(c) for c in bundled] == certs
    assert hashlib.sha256(bundle.encode()).hexdigest() == eduroam.CA_SHA256


def test_enterprise_settings_require_exact_pinned_trust_and_inner_eap(certificate_path):
    result = connection_settings(PROPS, REQUEST["password"], REQUEST["identity"])
    auth = {k: v.value for k, v in result["802-1x"].items()}
    assert auth == {"eap": ["ttls"], "identity": REQUEST["identity"], "password": REQUEST["password"], "password-flags": 0,
                    "ca-cert": ("file://" + str(certificate_path) + "\0").encode(), "system-ca-certs": False,
                    "domain-match": ";".join(eduroam.SERVER_NAMES), "phase2-autheap": "mschapv2"}
    wifi = {k: v.value for k, v in result["802-11-wireless-security"].items()}
    assert wifi == {"key-mgmt": "wpa-eap", "proto": ["rsn"], "pairwise": ["ccmp"], "group": ["ccmp"]}
    assert result["connection"]["autoconnect-priority"].value == 20


@pytest.mark.parametrize("props", [
    {**PROPS, "RsnFlags": 0, "Flags": 0}, {**PROPS, "RsnFlags": 0x188},
    {**PROPS, "RsnFlags": 0x488}, {**PROPS, "RsnFlags": 0, "WpaFlags": 0x288},
    {**PROPS, "RsnFlags": 0x244}, {**PROPS, "Ssid": b"eduroam impostor"},
])
def test_no_open_psk_wpa1_tkip_or_similar_name_downgrade(props, certificate_path):
    assert security_kind(props) == "unsupported"
    with pytest.raises(ValueError):
        connection_settings(props, REQUEST["password"], REQUEST["identity"])


@pytest.mark.parametrize("identity", [None, "", "example", "example@other.edu", "example@stanford.edu.evil", "example@stanford.edu\n", "x" * 65 + "@stanford.edu"])
def test_invalid_identity_rejected_without_echo(identity):
    with pytest.raises(ValueError, match="Enter your SUNetID"):
        validate_request({**REQUEST, "identity": identity})


def test_bounded_secrets_and_no_arbitrary_enterprise_options():
    assert validate_request({**REQUEST, "password": "x" * 256})
    for extra in [{"password": "é" * 129}, {"password": ""}, {"password": "x\n"}, {"password": "\ud800"}, {"ca_cert": "/tmp/evil"}, {"domain_match": "evil.test"}]:
        with pytest.raises(ValueError):
            validate_request({**REQUEST, **extra})
    with pytest.raises(ValueError):
        connection_settings({"Ssid": b"Stanford Visitor", "Mode": 2}, "", REQUEST["identity"])


def test_eduroam_requires_identity_even_when_personal_request_shape_is_valid(certificate_path):
    personal = {key: value for key, value in REQUEST.items() if key != "identity"}
    validate_request(personal)
    with pytest.raises(ValueError, match="SUNetID"):
        connection_settings(PROPS, personal["password"])


def test_missing_or_modified_bundle_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "ca.pem"
    monkeypatch.setattr(eduroam, "CA_PATH", path)
    with pytest.raises(ValueError, match="unavailable"):
        connection_settings(PROPS, REQUEST["password"], REQUEST["identity"])
    path.write_text("invalid")
    with pytest.raises(ValueError, match="failed validation"):
        connection_settings(PROPS, REQUEST["password"], REQUEST["identity"])


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [2, 4])
async def test_enterprise_credentials_saved_only_after_success(state, certificate_path):
    manager, connection = fake_manager(state)
    manager.properties.side_effect = [PROPS, {"State": state}]
    if state == 2:
        assert (await manager.connect(REQUEST))["connected"]
        connection.call_save.assert_awaited_once()
    else:
        with pytest.raises(ValueError):
            await manager.connect(REQUEST)
        connection.call_save.assert_not_called()
        connection.call_delete.assert_awaited_once()
    assert connection.call_add_and_activate_connection2.call_args.args[3]["persist"].value == "memory"


@pytest.mark.asyncio
async def test_existing_eduroam_connection_cannot_skip_applying_verified_profile(certificate_path):
    manager, connection = fake_manager()
    manager.scan.return_value["networks"][0]["connected"] = True
    manager.properties.side_effect = [PROPS, {"State": 2}]
    assert not (await manager.connect(REQUEST))["already_connected"]
    assert connection.call_add_and_activate_connection2.call_args.args[0]["802-1x"]["domain-match"].value == ";".join(eduroam.SERVER_NAMES)


def test_api_accepts_local_sunet_request_but_never_echoes_invalid_secrets(tmp_path, monkeypatch):
    broker = AsyncMock(return_value={"connected": True})
    monkeypatch.setattr("luma.api.network_request", broker)
    app = create_app(data_dir=tmp_path)
    local = TestClient(app)
    assert local.post("/api/v1/network", json=REQUEST).status_code == 200
    broker.assert_awaited_once_with(REQUEST)
    for extra in [{"identity": "private@other.edu"}, {"password": "private" * 100}]:
        response = local.post("/api/v1/network", json={**REQUEST, **extra})
        assert response.status_code == 422 and "private" not in response.text
    remote = TestClient(app, client=("192.168.1.2", 4321))
    assert remote.post("/api/v1/network", json=REQUEST).status_code == 403
    assert local.post("/api/v1/network", json=REQUEST, headers={"Origin": "https://attacker.example"}).status_code == 403
    assert broker.await_count == 1
