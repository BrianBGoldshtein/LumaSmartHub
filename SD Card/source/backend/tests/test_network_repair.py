from pathlib import Path
import sys

import pytest

from luma.network_repair import install_rt2870, repair_firewall


pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux appliance migration")
RULES = Path(__file__).resolve().parents[2] / "system/luma-tailscale.nft"


def test_shipped_firewall_is_normalized_with_exact_backup(tmp_path):
    expected = RULES.read_bytes().replace(b"\r\n", b"\n")
    original = expected.replace(b"\n", b"\r\n")
    path = tmp_path / "tailscale.nft"
    path.write_bytes(original)
    assert repair_firewall(path).startswith("Repaired")
    assert path.read_bytes() == expected
    assert repair_firewall(path).endswith("Unix line endings")
    assert (tmp_path / "tailscale.nft.luma-before-lf").read_bytes() == original


def test_other_firewall_rules_are_preserved(tmp_path):
    path = tmp_path / "tailscale.nft"
    other = b"# administrator policy\r\n"
    path.write_bytes(other)
    with pytest.raises(ValueError, match="differs from the shipped rules"):
        repair_firewall(path)
    assert path.read_bytes() == other


def test_firmware_is_installed_once_and_preserves_package_files(tmp_path):
    assert install_rt2870(tmp_path).startswith("Installed")
    firmware = tmp_path / "rt2870.bin"
    assert len(firmware.read_bytes()) == 8192
    assert install_rt2870(tmp_path).endswith("already present")
    firmware.unlink()
    (tmp_path / "rt2870.bin.xz").write_bytes(b"package fixture")
    assert install_rt2870(tmp_path).endswith("already present")
    assert not firmware.exists()
