"""Fixed Stanford SUNet profile, sourced from official CAT profile 8130.

No online profile imports, user-supplied CA paths, TOFU, or global trust changes.
See docs/CAMPUS_NETWORK.md for provenance and campus acceptance requirements.
"""
from hashlib import sha256
from pathlib import Path
import re

CA_PATH = Path("/etc/luma/stanford-eduroam-ca.pem")
CA_SHA256 = "e659812ac49e4400e189115c507cf7d7d8f586adca642f8205d4815e939770e8"
SERVER_NAMES = tuple(f"radius-cert{suffix}.stanford.edu" for suffix in ("", "1", "2", "3", "4"))


def validate_identity(identity: object) -> str:
    # Require the explicit institution realm; never send another institution's
    # credentials through this institution-specific configuration.
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}@stanford\.edu", identity, flags=re.ASCII):
        raise ValueError("Enter your SUNetID@stanford.edu")
    return identity


def settings(identity: str, password: str) -> dict:
    from dbus_next import Variant
    validate_identity(identity)
    if not password or len(password.encode("utf-8")) > 256:
        raise ValueError("Enter your SUNet password")
    try:
        bundle = CA_PATH.read_bytes().replace(b"\r\n", b"\n")
    except OSError:
        raise ValueError("Stanford certificate bundle is unavailable; repair the appliance installation") from None
    if sha256(bundle).hexdigest() != CA_SHA256:
        raise ValueError("Stanford certificate bundle failed validation; repair the appliance installation")
    return {
        "eap": Variant("as", ["ttls"]),
        "identity": Variant("s", identity),
        "password": Variant("s", password),
        "password-flags": Variant("u", 0),
        "ca-cert": Variant("ay", ("file://" + str(CA_PATH) + "\0").encode("utf-8")),
        "system-ca-certs": Variant("b", False),
        "domain-match": Variant("s", ";".join(SERVER_NAMES)),
        # CAT specifies inner EAP type 26, not the TTLS non-EAP MSCHAPv2 mode.
        "phase2-autheap": Variant("s", "mschapv2"),
    }
