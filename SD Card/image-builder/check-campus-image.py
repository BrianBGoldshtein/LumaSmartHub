#!/usr/bin/env python3
"""Read-only checks for the new campus integration, not the final hardware audit.

Verifies the ext4 sidecar is byte-identical to the raw image's Linux partition,
then inspects it with debugfs without mounting or booting it. Emits a small JSON
receipt; never reads credentials or changes the candidate image.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import ssl
import struct
import subprocess
import tarfile


def digest(stream, size):
    result = hashlib.sha256()
    while size:
        chunk = stream.read(min(size, 1024 * 1024))
        if not chunk:
            raise ValueError("Truncated image partition")
        result.update(chunk)
        size -= len(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_dir", type=Path)
    parser.add_argument("staging", type=Path)
    args = parser.parse_args()
    image = args.image_dir / "luma-pi4.img"
    rootfs = args.image_dir / "root.ext4"
    with image.open("rb") as raw:
        mbr = raw.read(512)
        if mbr[510:] != b"\x55\xaa":
            raise ValueError("Expected the pinned builder's MBR image")
        entries = [mbr[446 + i * 16:462 + i * 16] for i in range(4)]
        roots = [entry for entry in entries if entry[4] == 0x83]
        if len(roots) != 1:
            raise ValueError("Expected exactly one Linux root partition")
        start, sectors = struct.unpack_from("<II", roots[0], 8)
        size = sectors * 512
        if size != rootfs.stat().st_size:
            raise ValueError("Root filesystem size differs from raw-image partition")
        raw.seek(start * 512)
        raw_hash = digest(raw, size)
    with rootfs.open("rb") as source:
        if digest(source, size) != raw_hash:
            raise ValueError("Ext4 sidecar does not match the actual image partition")

    def inspect(command):
        result = subprocess.run(["/usr/sbin/debugfs", "-R", command, str(rootfs)],
                                check=True, capture_output=True, timeout=15)
        # debugfs may return zero on lookup errors; callers also validate bytes.
        if any(word in result.stderr for word in (b"not found", b"File not found", b"while opening")):
            raise ValueError("Could not inspect expected image file")
        return result.stdout

    def permissions(path, mode):
        output = inspect("stat " + path).decode()
        if not re.search(r"Mode:\s+0*" + mode + r"\b", output) or not re.search(r"User:\s+0\s+Group:\s+0\b", output):
            raise ValueError("Unexpected ownership or mode for " + path)

    permissions("/etc/luma", "755")
    permissions("/etc/luma/stanford-eduroam-ca.pem", "644")
    permissions("/etc/luma/luma-update-ed25519.pub", "644")
    dpkg_status = inspect("cat /var/lib/dpkg/status").decode(errors="replace")
    installed_packages = set()
    for record in dpkg_status.split("\n\n"):
        fields = {}
        for line in record.splitlines():
            if line and not line[0].isspace() and ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if fields.get("Status") == "install ok installed" and fields.get("Package"):
            installed_packages.add(fields["Package"])
    missing_packages = {"wpasupplicant", "rpi-connect", "qrencode", "gvfs-backends", "gvfs-daemons"} - installed_packages
    if missing_packages:
        raise ValueError("Required wireless/recovery package(s) are missing: " + ", ".join(sorted(missing_packages)))
    inspect("stat /usr/lib/gvfs/gvfs-udisks2-volume-monitor")
    version = re.search(rb"(?m)^version = (\d+\.\d+)\.", inspect("cat /opt/luma/venv/pyvenv.cfg"))
    if not version:
        raise ValueError("Cannot identify installed Python version")
    package = "/opt/luma/venv/lib/python" + version[1].decode() + "/site-packages/luma/"
    files = {
        "/etc/luma/stanford-eduroam-ca.pem": "source/backend/src/luma/assets/stanford-eduroam-ca.pem",
        "/etc/luma/luma-update-ed25519.pub": "source/system/luma-update-ed25519.pub",
        package + "eduroam.py": "source/backend/src/luma/eduroam.py",
        package + "network.py": "source/backend/src/luma/network.py",
        package + "tailscale_setup.py": "source/backend/src/luma/tailscale_setup.py",
        package + "pi_connect_setup.py": "source/backend/src/luma/pi_connect_setup.py",
        "/etc/luma/tailscale.nft": "source/system/luma-tailscale.nft",
        "/etc/systemd/system/luma-tailscaled.service": "source/system/luma-tailscaled.service",
        "/etc/systemd/system/luma-tailscale-firewall.service": "source/system/luma-tailscale-firewall.service",
        "/etc/systemd/system/luma-tailscale-setup.service": "source/system/luma-tailscale-setup.service",
        "/etc/systemd/system/luma-tailscale-setup.socket": "source/system/luma-tailscale-setup.socket",
        "/etc/systemd/system/luma-pi-connect-setup.service": "source/system/luma-pi-connect-setup.service",
        "/etc/systemd/system/luma-pi-connect-setup.socket": "source/system/luma-pi-connect-setup.socket",
        "/opt/luma/licenses/TAILSCALE-LICENSE.txt": "source/assets/licenses/TAILSCALE-LICENSE.txt",
        package + "api.py": "source/backend/src/luma/api.py",
        package + "github_updates.py": "source/backend/src/luma/github_updates.py",
        package + "update_api.py": "source/backend/src/luma/update_api.py",
        package + "update_broker.py": "source/backend/src/luma/update_broker.py",
        package + "security.py": "source/backend/src/luma/security.py",
        package + "models.py": "source/backend/src/luma/models.py",
        package + "serde.py": "source/backend/src/luma/serde.py",
        package + "device_agent.py": "source/backend/src/luma/device_agent.py",
        package + "voice_agent.py": "source/backend/src/luma/voice_agent.py",
        package + "voice_calibration.py": "source/backend/src/luma/voice_calibration.py",
        package + "voice.py": "source/backend/src/luma/voice.py",
        "/home/luma/.config/systemd/user/luma-voice.service": "source/system/luma-voice.service",
        "/home/luma/.config/pipewire/pipewire.conf.d/99-luma-echo-cancel.conf": "source/system/pipewire/99-luma-echo-cancel.conf",
        "/etc/wireplumber/wireplumber.conf.d/80-luma-no-bluetooth-audio.conf": "source/system/80-luma-no-bluetooth-audio.conf",
        "/opt/luma/qualification/device_smoke.py": "source/tests/device_smoke.py",
        "/opt/luma/qualification/tailscale-status.json": "source/tests/tailscale-status.json",
        package + "integrations/google_calendar.py": "source/backend/src/luma/integrations/google_calendar.py",
        package + "shortcut_gateway.py": "source/backend/src/luma/shortcut_gateway.py",
        package + "shortcut_protocol.py": "source/backend/src/luma/shortcut_protocol.py",
        "/etc/systemd/system/luma-shortcut-gateway.service": "source/system/luma-shortcut-gateway.service",
        "/etc/systemd/system/luma-network.service": "source/system/luma-network.service",
        "/etc/systemd/system/luma-network.socket": "source/system/luma-network.socket",
        "/etc/systemd/system/luma-update.service": "source/system/luma-update.service",
        "/etc/systemd/system/luma-update.socket": "source/system/luma-update.socket",
        "/etc/ssh/sshd_config.d/10-luma-ssh.conf": "source/system/10-luma-ssh.conf",
        "/etc/systemd/system/luma-ssh-hostkeys.service": "source/system/luma-ssh-hostkeys.service",
        "/home/luma-admin/.ssh/authorized_keys": "source/system/luma-admin.pub",
        "/opt/luma/frontend/index.html": "source/frontend/dist/index.html",
    }
    frontend = inspect("cat /opt/luma/frontend/index.html")
    scripts = re.findall(rb'src="/assets/([A-Za-z0-9_-]+\.js)"', frontend)
    if len(scripts) != 1:
        raise ValueError("Expected exactly one bundled frontend entry script")
    bundle = scripts[0].decode()
    files["/opt/luma/frontend/assets/" + bundle] = "source/frontend/dist/assets/" + bundle
    verified = {}
    for installed, source in files.items():
        content = inspect("cat " + installed)
        if content != (args.staging / source).read_bytes():
            raise ValueError("Installed file differs from staged source: " + installed)
        verified[installed] = hashlib.sha256(content).hexdigest()
    permissions("/etc/systemd/system/luma-shortcut-gateway.service", "644")
    permissions("/etc/luma/tailscale.nft", "644")
    permissions("/etc/systemd/system/luma-tailscaled.service", "644")
    permissions("/etc/systemd/system/luma-tailscale-setup.service", "644")
    permissions("/etc/systemd/system/luma-tailscale-setup.socket", "644")
    permissions("/etc/systemd/system/luma-update.service", "644")
    permissions("/etc/systemd/system/luma-update.socket", "644")
    permissions("/etc/systemd/system/luma-pi-connect-setup.service", "644")
    permissions("/etc/systemd/system/luma-pi-connect-setup.socket", "644")
    permissions("/opt/luma/venv/bin/luma-tailscale-setup", "755")
    permissions("/opt/luma/venv/bin/luma-update", "755")
    permissions("/opt/luma/venv/bin/luma-update-broker", "755")
    permissions("/opt/luma/venv/bin/luma-pi-connect-setup", "755")
    permissions("/opt/luma/qualification", "755")
    permissions("/opt/luma/qualification/device_smoke.py", "644")
    permissions("/opt/luma/venv/bin/luma-shortcut-gateway", "755")
    if b"luma-shortcut-gateway.service" in inspect("ls -l /etc/systemd/system/multi-user.target.wants"):
        raise ValueError("Gateway must remain disabled pending device enrollment")
    if b"luma-tailscaled.service" in inspect("ls -l /etc/systemd/system/multi-user.target.wants"):
        raise ValueError("Tailscale must remain disabled pending device enrollment")
    if b"luma-tailscale-setup.socket" not in inspect("ls -l /etc/systemd/system/sockets.target.wants"):
        raise ValueError("Local Tailscale setup socket must be enabled")
    if b"luma-pi-connect-setup.socket" not in inspect("ls -l /etc/systemd/system/sockets.target.wants"):
        raise ValueError("Local Pi Connect setup socket must be enabled")
    if b"luma-update.socket" not in inspect("ls -l /etc/systemd/system/sockets.target.wants"):
        raise ValueError("The protected application-update socket must be enabled")
    if b"luma-admin" not in inspect("ls -l /var/lib/systemd/linger"):
        raise ValueError("The dedicated Pi Connect admin user must linger across reboot")
    # Never inspect identity contents: no daemon has run during image assembly.
    if b"luma-tailscale" in inspect("ls -l /var/lib"):
        raise ValueError("Fresh image must not contain Tailscale identity/state directories")
    archive = args.staging / "source/assets/tailscale/tailscale_1.102.4_arm64.tgz"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != "9dd1e6a592a014bbaea0103167ffe299adeda4ba14e078ce9c2895364f6c4c3f":
        raise ValueError("Unexpected Tailscale release archive")
    with tarfile.open(archive, "r:gz") as bundle_archive:
        for binary in ("tailscale", "tailscaled"):
            permissions("/opt/luma/tailscale/" + binary, "755")
            expected = bundle_archive.extractfile("tailscale_1.102.4_arm64/" + binary).read()
            actual = inspect("cat /opt/luma/tailscale/" + binary)
            if actual != expected:
                raise ValueError("Installed Tailscale binary differs from pinned archive")
            verified["/opt/luma/tailscale/" + binary] = hashlib.sha256(actual).hexdigest()
    # Inspect filenames only: never read private host keys or the owner's key.
    if re.search(rb"\bssh_host_[A-Za-z0-9_-]+_key(?:\.pub)?\b", inspect("ls -l /etc/ssh")):
        raise ValueError("Image must not ship shared SSH host keys")
    if b"luma-ssh-hostkeys.service" not in inspect("ls -l /etc/systemd/system/multi-user.target.wants"):
        raise ValueError("First-boot SSH host-key generation must be enabled")
    if inspect("cat /etc/modprobe.d/cfg80211_regdomain.conf").strip() != b"options cfg80211 ieee80211_regdom=US":
        raise ValueError("US wireless country setting was not installed")

    def certificates(data):
        return {hashlib.sha256(ssl.PEM_cert_to_DER_cert(c)).hexdigest() for c in re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", data.decode(), re.S)}

    campus_certs = certificates(inspect("cat /etc/luma/stanford-eduroam-ca.pem"))
    system_certs = certificates(inspect("cat /etc/ssl/certs/ca-certificates.crt"))
    if len(campus_certs) != 2 or not system_certs or campus_certs & system_certs:
        raise ValueError("Stanford trust was not isolated from the system CA bundle")
    print(json.dumps({"root_partition_sha256": raw_hash, "root_partition_matches_sidecar": True,
                      "verified_files": verified, "stanford_ca_root_owned": True,
                      "stanford_ca_not_in_system_trust": True, "wireless_country": "US",
                      "wpasupplicant_installed": True, "rpi_connect_installed": True,
                      "pi_connect_setup_broker_verified": True,
                      "github_signed_update_broker_verified": True,
                      "gateway_shipped_disabled": True, "frontend_bundle_verified": True,
                      "tailscale_shipped_disabled": True, "tailscale_identity_absent": True,
                      "tailscale_binaries_verified": True, "tailscale_setup_socket_enabled": True,
                      "approved_ssh_public_key_matches": True, "shared_ssh_host_keys_absent": True,
                      "first_boot_ssh_host_keys_enabled": True,
                      "hardware_qualified": False}, indent=2))


if __name__ == "__main__":
    main()
