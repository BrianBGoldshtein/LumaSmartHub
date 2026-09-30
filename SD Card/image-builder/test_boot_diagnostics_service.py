"""The BOOT log is image-owned and must not expose user account data."""
import configparser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "source/system"


class BootDiagnosticsImageTests(unittest.TestCase):
    def test_monitor_is_installed_and_enabled_in_full_image(self):
        installer = (SYSTEM / "install.sh").read_text(encoding="utf-8")
        self.assertIn('"${SOURCE_ROOT}/system/luma_boot_diagnostics.py" /usr/local/libexec/luma-boot-diagnostics.py', installer)
        self.assertIn('"${SOURCE_ROOT}/system/luma-boot-diagnostics.service" /etc/systemd/system/', installer)
        self.assertIn('enable luma-api.service luma-boot-diagnostics.service', installer)

    def test_only_boot_and_volatile_lock_are_writable(self):
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str
        parser.read(SYSTEM / "luma-boot-diagnostics.service")
        service = parser["Service"]
        unit = parser["Unit"]
        self.assertEqual(unit["RequiresMountsFor"], "/boot/firmware")
        self.assertEqual(service["User"], "root")
        self.assertEqual(service["ProtectSystem"], "strict")
        self.assertEqual(service["ReadWritePaths"].split(), ["/boot/firmware", "/run/lock"])
        self.assertEqual(service["RestrictAddressFamilies"], "AF_UNIX")
        self.assertEqual(service["NoNewPrivileges"], "yes")
        source = (SYSTEM / "luma_boot_diagnostics.py").read_text(encoding="utf-8")
        self.assertNotIn("/var/lib/luma", source)
        self.assertNotIn("journalctl", source)


if __name__ == "__main__":
    unittest.main()
