#!/usr/bin/env python3
"""Offline libnm/OpenSSL qualification; never connects to D-Bus or a network.

Build-host dependencies: gir1.2-nm-1.0 python3-gi python3-dbus-next openssl.
Use Debian's /usr/bin/python3. All credentials are fake and memory-only.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import gi
gi.require_version("NM", "1.0")
from gi.repository import GLib, NM

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source/backend/src"))
from luma import eduroam
from luma.network import connection_settings


def main():
    asset = Path(eduroam.__file__).with_name("assets") / "stanford-eduroam-ca.pem"
    # Only the diagnostic process changes this path. No appliance trust install.
    eduroam.CA_PATH = asset
    settings = connection_settings({"Ssid": b"eduroam", "Mode": 2, "Flags": 1, "RsnFlags": 0x288},
                                   "fake-diagnostic-password", "example@stanford.edu")
    variant = GLib.Variant("a{sa{sv}}", {group: {key: GLib.Variant(value.signature, value.value)
                           for key, value in entries.items()} for group, entries in settings.items()})
    connection = NM.SimpleConnection.new_from_dbus(variant)
    assert connection.verify() and connection.verify_secrets()
    auth = connection.get_setting_802_1x()
    assert auth.get_phase2_autheap() == "mschapv2" and not auth.get_phase2_auth()
    assert auth.get_domain_match() == ";".join(eduroam.SERVER_NAMES)
    assert auth.get_ca_cert_path() == str(asset)
    assert not auth.get_system_ca_certs()
    assert auth.get_password() == "fake-diagnostic-password"
    print("libnm: profile/schema/secrets valid; CA path and exact server constraints retained")
    certs = re.findall(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", asset.read_text(), re.S)
    assert len(certs) == 2
    with tempfile.TemporaryDirectory(prefix="luma-eduroam-check-") as directory:
        paths = [Path(directory) / name for name in ("root.pem", "intermediate.pem")]
        for path, cert in zip(paths, certs):
            path.write_text(cert + "\n")
            subprocess.run(["openssl", "x509", "-in", str(path), "-noout", "-checkend", "0"], check=True)
        for path in paths:
            subprocess.run(["openssl", "verify", "-check_ss_sig", "-CAfile", str(paths[0]), str(path)], check=True)
    print("OpenSSL: root self-signature and intermediate chain valid at current host time")
    print("No daemon contacted, no network joined; campus RADIUS and Pi Wi-Fi remain untested")


if __name__ == "__main__":
    main()
