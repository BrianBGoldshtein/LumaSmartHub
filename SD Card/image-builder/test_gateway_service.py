"""Packaging regressions; real enforcement is checked by gateway-sandbox-smoke."""
import configparser
from pathlib import Path
import unittest

SYSTEM = Path(__file__).resolve().parents[1] / "source/system"


class GatewayServiceTests(unittest.TestCase):
    def setUp(self):
        unit = configparser.ConfigParser(interpolation=None)
        unit.optionxform = str
        unit.read(SYSTEM / "luma-shortcut-gateway.service")
        self.service = unit["Service"]

    def test_separate_nonprivileged_identity(self):
        for key, value in {"DynamicUser": "yes", "User": "luma-shortcut", "NoNewPrivileges": "yes",
                           "CapabilityBoundingSet": "", "AmbientCapabilities": ""}.items():
            self.assertEqual(self.service[key], value)

    def test_no_data_or_device_access(self):
        for key, value in {"ProtectSystem": "strict", "ReadOnlyPaths": "/run", "ProtectHome": "yes",
                           "PrivateDevices": "yes", "PrivateTmp": "yes"}.items():
            self.assertEqual(self.service[key], value)
        paths = self.service["InaccessiblePaths"].split()
        for path in ["-/var/lib/luma", "-/etc/luma", "-/run/dbus", "-/run/luma-network.sock", "-/run/luma-ir.sock"]:
            self.assertIn(path, paths)
        self.assertNotIn("ReadWritePaths", self.service)
        self.assertNotIn("SupplementaryGroups", self.service)

    def test_network_and_resource_bounds(self):
        self.assertEqual(self.service["IPAddressDeny"], "any")
        self.assertEqual(self.service["IPAddressAllow"], "localhost")
        self.assertEqual(self.service["TasksMax"], "32")
        self.assertEqual(self.service["MemoryMax"], "192M")
        self.assertEqual(self.service["CPUQuota"], "30%")

    def test_installer_ships_but_never_enables_or_starts_gateway(self):
        installer = (SYSTEM / "install.sh").read_text()
        self.assertIn('install -m 0644 "${SOURCE_ROOT}/system/luma-shortcut-gateway.service"', installer)
        for line in installer.splitlines():
            if "systemctl" in line:
                self.assertNotIn("luma-shortcut", line)
        self.assertEqual(self.service["ExecStart"], "/opt/luma/venv/bin/luma-shortcut-gateway")


if __name__ == "__main__":
    unittest.main()
