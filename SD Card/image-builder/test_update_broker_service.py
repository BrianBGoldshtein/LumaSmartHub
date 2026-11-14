"""Image tests for the signed GitHub update broker and its narrow socket."""
import configparser
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


class UpdateBrokerImageTests(unittest.TestCase):
    def test_only_local_luma_process_can_reach_root_broker(self):
        sock = section("luma-update.socket", "Socket")
        self.assertEqual(sock["ListenStream"], "/run/luma-update.sock")
        self.assertEqual(sock["SocketUser"], "root")
        self.assertEqual(sock["SocketGroup"], "luma")
        self.assertEqual(sock["SocketMode"], "0660")
        self.assertEqual(sock["RemoveOnStop"], "true")

        service = section("luma-update.service", "Service")
        self.assertEqual(service["User"], "root")
        self.assertEqual(service["ExecStart"], "/opt/luma/venv/bin/luma-update-broker")
        self.assertEqual(service["NoNewPrivileges"], "yes")
        self.assertEqual(service["ProtectSystem"], "strict")
        self.assertEqual(service["ReadWritePaths"].split(), ["/opt"])
        self.assertEqual(service["UMask"], "0022")
        self.assertEqual(service["RestrictAddressFamilies"].split(), ["AF_UNIX", "AF_INET", "AF_INET6"])

        installer = (SYSTEM / "install.sh").read_text()
        self.assertIn('"${SOURCE_ROOT}/system/luma-update.service" "${SOURCE_ROOT}/system/luma-update.socket"', installer)
        self.assertIn("enable luma-api.service luma-boot-diagnostics.service luma-network.socket luma-backup.socket luma-update.socket", installer)
        package = (ROOT / "source/backend/pyproject.toml").read_text()
        self.assertIn('luma-update-broker = "luma.update_broker:main"', package)

    def test_atomic_update_worker_is_not_stopped_by_its_own_application_switch(self):
        spec = __import__("importlib.util", fromlist=["spec_from_file_location"])
        module_spec = spec.spec_from_file_location("luma_update_agent", ROOT / "source/backend/src/luma/update_agent.py")
        # Parse the system-unit allowlist from source without importing the Linux-only fcntl runtime on Windows.
        source = module_spec.loader.get_source(module_spec.name)
        self.assertIn('SYSTEM_UNITS = (*SYSTEM_SOCKET_UNITS, *SYSTEM_SERVICE_UNITS)', source)
        self.assertNotIn('"luma-update.service"', source)
        self.assertNotIn('"luma-update.socket"', source)
        broker = (ROOT / "source/backend/src/luma/update_broker.py").read_text()
        self.assertIn("asyncio.create_task(broker.install(task_bundle))", broker)

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("systemd-analyze"),
                         "Native Linux systemd unit parser required")
    def test_systemd_accepts_update_broker_units_and_installer(self):
        with tempfile.TemporaryDirectory(prefix="luma-update-unit-") as directory:
            staging = Path(directory)
            writable = staging / "app"
            writable.mkdir()
            service = (SYSTEM / "luma-update.service").read_text()
            service = service.replace("/opt/luma/venv/bin/luma-update-broker", sys.executable)
            service = service.replace("ReadWritePaths=/opt", f"ReadWritePaths={writable}")
            (staging / "luma-update.service").write_text(service)
            shutil.copyfile(SYSTEM / "luma-update.socket", staging / "luma-update.socket")
            result = subprocess.run(
                ["systemd-analyze", "verify", "--man=no", "--generators=no",
                 str(staging / "luma-update.service"), str(staging / "luma-update.socket")],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            shell = subprocess.run(["bash", "-n", str(SYSTEM / "install.sh")],
                                   capture_output=True, text=True, timeout=15)
            self.assertEqual(shell.returncode, 0, shell.stdout + shell.stderr)


if __name__ == "__main__":
    unittest.main()
