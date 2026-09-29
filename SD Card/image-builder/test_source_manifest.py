import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("source-manifest.py")
spec = importlib.util.spec_from_file_location("source_manifest", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SourceManifestTests(unittest.TestCase):
    def test_image_version_marker_is_a_required_build_input(self):
        self.assertIn("source/tools/update-base-version.txt", module.FILES)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="luma-manifest-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in module.TREES:
            (self.root / name).mkdir(parents=True)
            (self.root / name / "fixture").write_bytes(b"fixture")
        for name in module.FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")

    def test_deterministic_and_sensitive_to_packaged_bytes(self):
        first = module.manifest(self.root)
        self.assertEqual(first, module.manifest(self.root))
        (self.root / "source/frontend/dist/fixture").write_bytes(b"changed")
        self.assertNotEqual(first["source_sha256"], module.manifest(self.root)["source_sha256"])

    def test_excludes_host_environments_outputs_and_bytecode(self):
        first = module.manifest(self.root)
        for name in ("source/backend/.venv/private", "source/frontend/node_modules/package", "image/manifest", "source/backend/src/__pycache__/test.pyc", "source/backend/src/test.pyc"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not packaged")
        self.assertEqual(first, module.manifest(self.root))

    def test_missing_inputs_are_not_silently_omitted(self):
        (self.root / "source/backend/pyproject.toml").unlink()
        with self.assertRaises(FileNotFoundError):
            module.manifest(self.root)

    def test_symlink_is_rejected(self):
        path = self.root / "source/system/linked"
        try:
            path.symlink_to(self.root / "source/system/fixture")
        except OSError:
            self.skipTest("Host does not permit unprivileged symlinks")
        with self.assertRaises(ValueError):
            module.manifest(self.root)

    def test_cli_never_overwrites_existing_provenance(self):
        output = self.root / "manifest.json"
        command = [sys.executable, str(SCRIPT), str(self.root), "--output", str(output)]
        subprocess.run(command, check=True, capture_output=True)
        original = output.read_bytes()
        result = subprocess.run(command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(original, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
