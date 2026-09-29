"""Static packaging checks for the USB backup socket; no services are installed or started."""
import configparser
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / "source/system"


def section(file, name):
    value = configparser.ConfigParser(interpolation=None)
    value.optionxform = str
    value.read(SYSTEM / file)
    return value[name]


class BackupServiceTests(unittest.TestCase):
    def test_broker_runs_privileged_but_is_confined_to_local_usb_work(self):
        service = section("luma-backup.service", "Service")
        for key, expected in {
            "User": "root", "Group": "root", "NoNewPrivileges": "yes",
            "CapabilityBoundingSet": "", "AmbientCapabilities": "",
            "UMask": "0077", "ProtectSystem": "strict", "ProtectHome": "yes",
            "ReadWritePaths": "/media", "RestrictAddressFamilies": "AF_UNIX",
            "TasksMax": "16", "MemoryMax": "128M", "CPUQuota": "25%",
            "KillMode": "control-group", "TimeoutStopSec": "5",
            "ExecStart": "/opt/luma/venv/bin/luma-backup",
        }.items():
            self.assertEqual(service[key], expected)
        unit = section("luma-backup.service", "Unit")
        self.assertEqual(unit["Requires"], "luma-backup.socket")
        self.assertEqual(unit["After"], "udisks2.service")
        self.assertEqual(unit["Wants"], "udisks2.service")
        self.assertNotIn("SupplementaryGroups", service)

    def test_socket_acl_is_only_for_the_luma_service_group(self):
        unit = section("luma-backup.socket", "Socket")
        self.assertEqual(unit["ListenStream"], "/run/luma-backup.sock")
        self.assertEqual(unit["SocketUser"], "root")
        self.assertEqual(unit["SocketGroup"], "luma")
        self.assertEqual(unit["SocketMode"], "0660")
        self.assertEqual(unit["RemoveOnStop"], "true")
        self.assertEqual(unit["Backlog"], "4")

    def test_installer_installs_and_enables_only_the_socket(self):
        installer = (SYSTEM / "install.sh").read_text()
        self.assertIn('install -m 0644 "${SOURCE_ROOT}/system/luma-backup.service"', installer)
        self.assertIn('"${SOURCE_ROOT}/system/luma-backup.socket" /etc/systemd/system/', installer)
        self.assertIn("groupadd --system -f luma", installer)
        self.assertIn("useradd --create-home --shell /bin/bash --gid luma", installer)
        enabled = [line for line in installer.splitlines() if "systemctl --root=/ enable" in line]
        self.assertTrue(any("luma-backup.socket" in line for line in enabled))
        self.assertFalse(any("luma-backup.service" in line for line in enabled))

        spec = importlib.util.spec_from_file_location("luma_image_audit", ROOT / "image-builder/audit-image-files.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.SYSTEM["luma-backup.service"], "/etc/systemd/system/luma-backup.service")
        self.assertEqual(module.SYSTEM["luma-backup.socket"], "/etc/systemd/system/luma-backup.socket")

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("systemd-analyze"),
                         "Native systemd unit parser required")
    def test_native_unit_and_installer_syntax(self):
        with tempfile.TemporaryDirectory(prefix="luma-backup-unit-") as directory:
            staging = Path(directory)
            service = (SYSTEM / "luma-backup.service").read_text()
            executable = "ExecStart=/opt/luma/venv/bin/luma-backup"
            self.assertEqual(service.count(executable), 1)
            (staging / "luma-backup.service").write_text(service.replace(executable, "ExecStart=" + sys.executable))
            for name in ("luma-backup.socket",):
                shutil.copyfile(SYSTEM / name, staging / name)
            for command in (
                ["systemd-analyze", "verify", "--man=no", "--generators=no",
                 str(staging / "luma-backup.service"), str(staging / "luma-backup.socket")],
                ["bash", "-n", str(SYSTEM / "install.sh")],
            ):
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
