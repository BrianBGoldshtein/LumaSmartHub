"""Source packaging assertions, not a claim of real sandbox/device acceptance."""
import configparser
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT / 'source/system'


def section(file, name):
    value = configparser.ConfigParser(interpolation=None)
    value.optionxform = str
    value.read(SYSTEM / file)
    return value[name]


class InfraredServiceTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'linux', 'Native Linux unit/rule parsers')
    def test_native_service_rule_and_installer_syntax(self):
        # Syntax validation only, no service/user creation or hardware operation.
        # Substitute the nonexistent image-only executable with this existing
        # interpreter solely for systemd-analyze's executable-existence check.
        with tempfile.TemporaryDirectory(prefix='luma-ir-unit-') as directory:
            staging = Path(directory)
            for name in ('luma-ir.service', 'luma-ir.socket', '72-luma-ir.rules', 'install.sh'):
                content = (SYSTEM / name).read_text()
                if name == 'luma-ir.service':
                    original = 'ExecStart=/opt/luma/venv/bin/luma-ir'
                    self.assertEqual(content.count(original), 1)
                    content = content.replace(original, 'ExecStart=' + sys.executable)
                (staging / name).write_text(content)
            for command in (
                ['systemd-analyze', 'verify', '--man=no', '--generators=no', str(staging / 'luma-ir.service'), str(staging / 'luma-ir.socket')],
                ['udevadm', 'verify', '--resolve-names=never', str(staging / '72-luma-ir.rules')],
                ['bash', '-n', str(staging / 'install.sh')],
            ):
                result = subprocess.run(command, capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dedicated_identity_limits_and_no_network(self):
        unit = section('luma-ir.service', 'Service')
        for key, expected in {'User': 'luma-ir', 'Group': 'luma-ir', 'NoNewPrivileges': 'yes',
                              'CapabilityBoundingSet': '', 'AmbientCapabilities': '',
                              'ProtectSystem': 'strict', 'ProtectHome': 'yes',
                              'RestrictAddressFamilies': 'AF_UNIX', 'TasksMax': '24',
                              'MemoryMax': '96M', 'KillMode': 'control-group', 'TimeoutStopSec': '5',
                              'ExecStart': '/opt/luma/venv/bin/luma-ir'}.items():
            self.assertEqual(unit[key], expected)
        self.assertNotIn('ReadWritePaths', unit)
        self.assertNotIn('SupplementaryGroups', unit)
        self.assertIn('-/var/lib/luma', unit['InaccessiblePaths'].split())

    def test_socket_only_owner_group_and_usb_only_device_rule(self):
        unit = section('luma-ir.socket', 'Socket')
        self.assertEqual(unit['SocketMode'], '0660')
        self.assertEqual(unit['SocketGroup'], 'luma')
        self.assertEqual(unit['SocketUser'], 'root')
        self.assertEqual(unit['ListenStream'], '/run/luma-ir.sock')
        self.assertEqual(unit['RemoveOnStop'], 'true')
        rule = (SYSTEM / '72-luma-ir.rules').read_text()
        self.assertIn('SUBSYSTEM=="lirc", SUBSYSTEMS=="usb", GROUP="luma-ir", MODE="0660", TAG-="uaccess"', rule)

    def test_installer_and_exact_image_inventory_include_new_files(self):
        installer = (SYSTEM / 'install.sh').read_text()
        self.assertIn('--gid luma-ir --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin luma-ir', installer)
        self.assertNotIn('usermod -a -G luma-ir', installer)
        enabled = [line for line in installer.splitlines() if 'systemctl --root=/ enable' in line]
        self.assertTrue(any('luma-ir.socket' in line for line in enabled))
        self.assertFalse(any('luma-ir.service' in line for line in enabled))
        spec = importlib.util.spec_from_file_location('luma_image_audit', ROOT / 'image-builder/audit-image-files.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name in ('luma-ir.service', 'luma-ir.socket', '72-luma-ir.rules'):
            self.assertIn(name, installer)
            self.assertIn(name, module.SYSTEM)


if __name__ == '__main__': unittest.main()
