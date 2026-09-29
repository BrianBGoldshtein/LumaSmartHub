#!/usr/bin/env python3
"""Read-only exhaustive shipped Luma file comparison, not a hardware/security certification.

Requires the matching successful raw-image-check receipt, independently rechecks
the ext4 digest, and compares every application/model/frontend/license file and
explicitly mapped system configuration against the immutable staging tree.
Never mounts the image, executes image code, or reads credentials/private keys.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


SYSTEM = {
    "luma-api.service": "/etc/systemd/system/luma-api.service",
    "luma-shortcut-gateway.service": "/etc/systemd/system/luma-shortcut-gateway.service",
    "luma-tailscaled.service": "/etc/systemd/system/luma-tailscaled.service",
    "luma-tailscale-firewall.service": "/etc/systemd/system/luma-tailscale-firewall.service",
    "luma-tailscale-setup.service": "/etc/systemd/system/luma-tailscale-setup.service",
    "luma-tailscale-setup.socket": "/etc/systemd/system/luma-tailscale-setup.socket",
    "luma-pi-connect-setup.service": "/etc/systemd/system/luma-pi-connect-setup.service",
    "luma-pi-connect-setup.socket": "/etc/systemd/system/luma-pi-connect-setup.socket",
    "luma-tailscale.nft": "/etc/luma/tailscale.nft",
    "luma-update-ed25519.pub": "/etc/luma/luma-update-ed25519.pub",
    "luma-network.service": "/etc/systemd/system/luma-network.service",
    "luma-network.socket": "/etc/systemd/system/luma-network.socket",
    "luma-backup.service": "/etc/systemd/system/luma-backup.service",
    "luma-backup.socket": "/etc/systemd/system/luma-backup.socket",
    "luma-update.service": "/etc/systemd/system/luma-update.service",
    "luma-update.socket": "/etc/systemd/system/luma-update.socket",
    "luma-update.service": "/etc/systemd/system/luma-update.service",
    "luma-update.socket": "/etc/systemd/system/luma-update.socket",
    "luma-ir.service": "/etc/systemd/system/luma-ir.service",
    "luma-ir.socket": "/etc/systemd/system/luma-ir.socket",
    "72-luma-ir.rules": "/etc/udev/rules.d/72-luma-ir.rules",
    "30-luma-connectivity.conf": "/etc/NetworkManager/conf.d/30-luma-connectivity.conf",
    "80-luma-no-bluetooth-audio.conf": "/etc/wireplumber/wireplumber.conf.d/80-luma-no-bluetooth-audio.conf",
    "luma-kiosk.service": "/home/luma/.config/systemd/user/luma-kiosk.service",
    "luma-device.service": "/home/luma/.config/systemd/user/luma-device.service",
    "luma-voice.service": "/home/luma/.config/systemd/user/luma-voice.service",
    "luma-tmpfiles.conf": "/usr/lib/tmpfiles.d/luma.conf",
    "pipewire/99-luma-echo-cancel.conf": "/home/luma/.config/pipewire/pipewire.conf.d/99-luma-echo-cancel.conf",
    "labwc-autostart": "/home/luma/.config/labwc/autostart",
    "60-luma.conf": "/etc/lightdm/lightdm.conf.d/60-luma.conf",
    "70-luma-spi.rules": "/etc/udev/rules.d/70-luma-spi.rules",
    "10-luma-ssh.conf": "/etc/ssh/sshd_config.d/10-luma-ssh.conf",
    "luma-ssh-hostkeys.service": "/etc/systemd/system/luma-ssh-hostkeys.service",
    "luma-admin-sudoers": "/etc/sudoers.d/luma-admin",
    "luma-admin.pub": "/home/luma-admin/.ssh/authorized_keys",
    "build-keyboard.sh": "/opt/luma/third-party/wvkbd/build-keyboard.sh",
    "wvkbd-overlay.patch": "/opt/luma/third-party/wvkbd/wvkbd-overlay.patch",
}
BUILD_ONLY_SYSTEM = {"install.sh", "luma-hardware.txt"}


def sha_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging", type=Path)
    parser.add_argument("raw_receipt", type=Path)
    args = parser.parse_args()
    root = args.staging.resolve(strict=True)
    image_dir = root / "image-builder/work/output/image-luma-pi4"
    ext4 = image_dir / "root.ext4"
    receipt = json.loads(args.raw_receipt.read_text())
    if not receipt["root_partition_matches_sidecar"] or sha_file(ext4) != receipt["root_partition_sha256"]:
        raise ValueError("Filesystem differs from the raw-image receipt")

    def inspect(command):
        result = subprocess.run(["/usr/sbin/debugfs", "-R", command, str(ext4)],
                                capture_output=True, check=True, timeout=30)
        if b"not found" in result.stderr.lower() or b"while opening" in result.stderr:
            raise ValueError("Missing installed file: " + command)
        return result.stdout

    version = re.search(rb"(?m)^version = (\d+\.\d+)\.", inspect("cat /opt/luma/venv/pyvenv.cfg"))[1].decode()
    mappings = {}
    for source_prefix, destination in (
        ("source/backend/src/luma", f"/opt/luma/venv/lib/python{version}/site-packages/luma"),
        ("source/frontend/dist", "/opt/luma/frontend"),
        ("source/assets/models/vosk", "/opt/luma/models/vosk"),
        ("source/assets/licenses", "/opt/luma/licenses"),
    ):
        directory = root / source_prefix
        for path in sorted(directory.rglob("*")):
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            if path.is_symlink():
                raise ValueError("Unexpected input symlink")
            if path.is_file():
                mappings[destination + "/" + path.relative_to(directory).as_posix()] = path
    actual_system = {p.relative_to(root / "source/system").as_posix()
                     for p in (root / "source/system").rglob("*") if p.is_file()}
    if actual_system != set(SYSTEM) | BUILD_ONLY_SYSTEM:
        raise ValueError("System source inventory changed; classify every new file explicitly")
    mappings.update({dest: root / "source/system" / src for src, dest in SYSTEM.items()})
    for name in ("device_smoke.py", "tailscale-status.json"):
        mappings["/opt/luma/qualification/" + name] = root / "source/tests" / name
    mappings["/opt/luma/third-party/wvkbd/wvkbd_0.15.orig.tar.xz"] = root / "source/assets/keyboard/wvkbd_0.15.orig.tar.xz"
    verified = {}
    for installed, source in mappings.items():
        content = inspect("cat " + installed)
        digest = hashlib.sha256(content).hexdigest()
        if digest != sha_file(source):
            raise ValueError("Installed bytes differ: " + installed)
        verified[installed] = digest

    # FAT boot files are outside ext4 and include the real HAT configuration.
    for installed, source in {
        "luma-hardware.txt": root / "source/system/luma-hardware.txt",
        "overlays/respeaker-2mic-v1_0.dtbo": root / "source/assets/overlays/respeaker-2mic-v1_0.dtbo",
    }.items():
        content = subprocess.run(["mtype", "-i", str(image_dir / "boot.vfat"), "::" + installed],
                                 capture_output=True, check=True, timeout=15).stdout
        if hashlib.sha256(content).hexdigest() != sha_file(source):
            raise ValueError("Boot configuration differs: " + installed)
        verified["boot:" + installed] = hashlib.sha256(content).hexdigest()

    # Relevant generated binaries must be 64-bit little-endian AArch64 ELF.
    native = {}
    for binary in ("/opt/luma/tailscale/tailscale", "/opt/luma/tailscale/tailscaled", "/opt/luma/bin/luma-keyboard"):
        data = inspect("cat " + binary)
        if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
            raise ValueError("Not an AArch64 ELF: " + binary)
        native[binary] = hashlib.sha256(data).hexdigest()
    source_manifest = json.loads((root / "image/source-manifest.json").read_text())
    print(json.dumps({"root_partition_sha256": receipt["root_partition_sha256"],
                      "source_sha256": source_manifest["source_sha256"],
                      "verified_file_count": len(verified), "verified_files": verified,
                      "native_aarch64_binaries": native, "python_version": version,
                      "all_luma_system_source_files_classified": True,
                      "build_only_system_inputs": sorted(BUILD_ONLY_SYSTEM - {"luma-hardware.txt"}),
                      "upstream_os_inventory": "software-inventory.spdx.json",
                      "hardware_qualified": False,
                      "limits": "Byte/architecture audit of all shipped Luma source, frontend, model, licenses and mapped configuration; not exhaustive OS vulnerability analysis or physical acceptance"}, indent=2))


if __name__ == "__main__":
    main()
