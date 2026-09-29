"""Regressions for packages that must be explicit in the minimal OS image."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WirelessImagePackageTests(unittest.TestCase):
    def test_no_recommends_image_explicitly_installs_wifi_supplicant(self):
        layer = (ROOT / "image-builder/layer/luma-base.yaml").read_text()
        self.assertIn("- wpasupplicant", layer)
        # The old candidate proves this is not redundant: wpasupplicant is only
        # a Debian Recommends of NetworkManager and was absent from its SPDX SBOM.

    def test_pi_connect_is_shipped_but_not_pre_enrolled_or_enabled(self):
        layer = (ROOT / "image-builder/layer/luma-base.yaml").read_text()
        installer = (ROOT / "source/system/install.sh").read_text()
        self.assertIn("- rpi-connect", layer)
        self.assertNotIn("rpi-connect on", installer)
        self.assertNotIn("rpi-connect signin", installer)
        self.assertIn("- qrencode", layer)
        self.assertIn("luma-pi-connect-setup.socket", installer)
        self.assertIn("/var/lib/systemd/linger/luma-admin", installer)
        self.assertIn("luma-pi-connect-setup.socket", installer)
        service = (ROOT / "source/system/luma-pi-connect-setup.service").read_text()
        self.assertIn("User=luma-admin", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6", service)

    def test_chromium_removable_media_monitor_is_explicit(self):
        layer = (ROOT / "image-builder/layer/luma-base.yaml").read_text()
        installer = (ROOT / "source/system/install.sh").read_text()
        checker = (ROOT / "image-builder/check-campus-image.py").read_text()
        self.assertIn("- gvfs-backends", layer)
        self.assertIn("udisks2 gvfs-backends", installer)
        self.assertIn('"gvfs-backends", "gvfs-daemons"', checker)


if __name__ == "__main__":
    unittest.main()
