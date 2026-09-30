"""Static and native-unit checks for owner-approved Pi Connect setup."""
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


def section(filename, name):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(SYSTEM / filename)
    return parser[name]


class PiConnectServiceTests(unittest.TestCase):
    def test_service_is_a_fixed_unprivileged_admin_broker(self):
        service = section("luma-pi-connect-setup.service", "Service")
        expected = {
            "ExecStart": "/opt/luma/venv/bin/luma-pi-connect-setup",
            "User": "luma-admin",
            "Group": "luma-admin",
            "NoNewPrivileges": "true",
            "RestrictSUIDSGID": "true",
            "PrivateTmp": "true",
            "PrivateDevices": "true",
            "ProtectSystem": "strict",
            "ProtectHome": "read-only",
            "ProtectKernelTunables": "true",
            "ProtectKernelModules": "true",
            "ProtectControlGroups": "true",
            "LockPersonality": "true",
            "MemoryMax": "128M",
            "TasksMax": "32",
        }
        for key, value in expected.items():
            self.assertEqual(service[key], value)
        self.assertEqual(service["RestrictAddressFamilies"].split(), ["AF_UNIX", "AF_INET", "AF_INET6"])
        self.assertEqual(service["ReadWritePaths"].split(), [
            "/home/luma-admin/.config/com.raspberrypi.connect",
            "/home/luma-admin/.config/systemd/user",
            "/home/luma-admin/.config/luma",
            "/home/luma-admin/.cache",
            "/home/luma-admin/.local/share",
        ])
        self.assertEqual(section("luma-pi-connect-setup.service", "Unit")["Requires"],
                         "luma-pi-connect-setup.socket")

    def test_socket_and_image_installation_keep_enrollment_owner_gated(self):
        sock = section("luma-pi-connect-setup.socket", "Socket")
        self.assertEqual(sock["ListenStream"], "/run/luma-pi-connect-setup.sock")
        self.assertEqual(sock["SocketUser"], "root")
        self.assertEqual(sock["SocketGroup"], "luma")
        self.assertEqual(sock["SocketMode"], "0660")
        self.assertEqual(sock["RemoveOnStop"], "true")

        installer = (SYSTEM / "install.sh").read_text()
        self.assertIn('useradd --create-home --shell /bin/bash luma-admin', installer)
        self.assertIn('/var/lib/systemd/linger/luma-admin', installer)
        self.assertIn('"${SOURCE_ROOT}/system/luma-pi-connect-setup.socket" /etc/systemd/system/', installer)
        self.assertIn('systemctl --root=/ enable luma-pi-connect-setup.socket', installer)
        self.assertNotIn('systemctl --root=/ enable luma-pi-connect-setup.service', installer)
        self.assertNotIn('rpi-connect on', installer)
        self.assertNotIn('rpi-connect signin', installer)

        package = (ROOT / "source/backend/pyproject.toml").read_text()
        self.assertIn('luma-pi-connect-setup = "luma.pi_connect_setup:main"', package)
        audit_spec = importlib.util.spec_from_file_location(
            "luma_image_audit", ROOT / "image-builder/audit-image-files.py")
        audit = importlib.util.module_from_spec(audit_spec)
        audit_spec.loader.exec_module(audit)
        self.assertEqual(audit.SYSTEM["luma-pi-connect-setup.service"],
                         "/etc/systemd/system/luma-pi-connect-setup.service")
        self.assertEqual(audit.SYSTEM["luma-pi-connect-setup.socket"],
                         "/etc/systemd/system/luma-pi-connect-setup.socket")
        image_check = (ROOT / "image-builder/check-campus-image.py").read_text()
        self.assertIn('"pi_connect_setup.py": "source/backend/src/luma/pi_connect_setup.py"', image_check)
        self.assertIn('"pi_connect_setup_broker_verified": True', image_check)

    def test_disposable_qemu_check_uses_local_broker_without_enrollment(self):
        smoke = (ROOT / "image-builder/qemu-smoke.sh").read_text()
        self.assertIn("--pi-connect-check", smoke)
        self.assertIn("systemd.wants=luma-pi-connect-setup.socket", smoke)
        self.assertIn("exec(bytes([", smoke)
        self.assertIn("pi-connect-setup-response True False", smoke)
        self.assertIn("== --pi-connect-check", smoke)

    def test_linux_backend_runner_stages_service_files_used_by_packaging_tests(self):
        runner = (ROOT / "image-builder/test-linux.sh").read_text()
        self.assertIn('DELIVERY_ROOT=', runner)
        self.assertIn('"${DELIVERY_ROOT}/source/system/" "${QA_ROOT}/system/"', runner)

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("systemd-analyze"),
                         "Native Linux systemd unit parser required")
    def test_native_systemd_parser_accepts_units_and_installer(self):
        with tempfile.TemporaryDirectory(prefix="luma-pi-connect-unit-") as directory:
            staging = Path(directory)
            service = (SYSTEM / "luma-pi-connect-setup.service").read_text()
            command = "ExecStart=/opt/luma/venv/bin/luma-pi-connect-setup"
            self.assertEqual(service.count(command), 1)
            service = service.replace(command, "ExecStart=" + sys.executable)
            for path in (".config/com.raspberrypi.connect", ".config/systemd/user",
                         ".cache", ".local/share"):
                (staging / "home/luma-admin" / path).mkdir(parents=True, exist_ok=True)
            service = service.replace("/home/luma-admin", str(staging / "home/luma-admin"))
            (staging / "luma-pi-connect-setup.service").write_text(service)
            shutil.copyfile(SYSTEM / "luma-pi-connect-setup.socket",
                            staging / "luma-pi-connect-setup.socket")
            result = subprocess.run(
                ["systemd-analyze", "verify", "--man=no", "--generators=no",
                 str(staging / "luma-pi-connect-setup.service"),
                 str(staging / "luma-pi-connect-setup.socket")],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            shell = subprocess.run(["bash", "-n", str(SYSTEM / "install.sh")],
                                   capture_output=True, text=True, timeout=15)
            self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)


if __name__ == "__main__":
    unittest.main()
