"""One-time compatibility repairs for signed Luma appliance updates."""

import hashlib
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile

STOCK_RULES_SHA256 = "2f525f9c2a8cd1404f96d99feffb99d0e1874626ad9b2d6565f52d20d32bcb5e"
RT2870_SHA256 = "251b8918391eac6415d60dca239e415aad0177e885376f2a17782e64fcbbe317"


def require_owned(path: Path, *, directory: bool = False) -> os.stat_result:
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("Expected a protected appliance path")
    return info


def durable_write(path: Path, content: bytes, mode: int, *, replace: bool = False) -> None:
    require_owned(path.parent, directory=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)


def repair_firewall(path: Path) -> str:
    require_owned(path.parent, directory=True)
    info = require_owned(path)
    if info.st_size > 65536:
        raise ValueError("Unexpected Tailscale firewall file size")
    original = path.read_bytes()
    fixed = original.replace(b"\r\n", b"\n")
    if fixed == original:
        return "Tailscale firewall already uses Unix line endings"
    if hashlib.sha256(fixed).hexdigest() != STOCK_RULES_SHA256:
        raise ValueError("Tailscale firewall differs from the shipped rules")
    backup = path.with_name(path.name + ".luma-before-lf")
    try:
        durable_write(backup, original, 0o600)
    except FileExistsError:
        require_owned(backup)
        if backup.read_bytes() != original:
            raise ValueError("Tailscale firewall backup differs from its original") from None
    durable_write(path, fixed, stat.S_IMODE(info.st_mode), replace=True)
    return "Repaired line endings in the shipped Tailscale firewall"


def install_rt2870(directory: Path) -> str:
    require_owned(directory, directory=True)
    for suffix in ("", ".xz", ".zst"):
        if (directory / f"rt2870.bin{suffix}").exists():
            return "RT2870 firmware is already present"
    firmware = Path(__file__).with_name("firmware") / "rt2870.bin"
    content = firmware.read_bytes()
    if hashlib.sha256(content).hexdigest() != RT2870_SHA256:
        raise ValueError("RT2870 firmware checksum did not match")
    durable_write(directory / "rt2870.bin", content, 0o644)
    return "Installed RT2870 firmware for supported Ralink USB Wi-Fi adapters"


def main() -> None:
    failed = False
    for repair, path in ((repair_firewall, Path("/etc/luma/tailscale.nft")),
                         (install_rt2870, Path("/usr/lib/firmware"))):
        try:
            print(repair(path), flush=True)
        except (OSError, ValueError) as error:
            failed = True
            print(f"{repair.__name__}: {error}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
