"""Linux-only recovery tests using tiny synthetic images, never real candidates."""
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("finish-candidate.sh")
SOURCE_SHA = "a" * 64
GENERATOR = "dbd775d191a2e2cafec95bb218f2002213eff2ff"


@unittest.skipUnless(os.name == "posix" and shutil.which("xz"), "Linux build-host tools required")
class FinishCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luma-recovery-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "image"
        self.image.mkdir()
        self.raw = self.root / "image-builder/work/output/image-luma-pi4/luma-pi4.img"
        self.raw.parent.mkdir(parents=True)
        self.raw.write_bytes(b"synthetic-image\0" * 1000)
        (self.root / "image-builder/work/rpi-image-gen").mkdir()
        (self.image / "source-manifest.json").write_text(json.dumps({"source_sha256": SOURCE_SHA}))
        (self.root / "fingerprint.txt").write_text(SOURCE_SHA)
        (self.root / "image-builder/source-manifest.py").write_text(
            "import pathlib,sys\nprint((pathlib.Path(sys.argv[1])/'fingerprint.txt').read_text())\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.executable("git", "#!/bin/sh\nprintf '%s\\n' '" + GENERATOR + "'\n")
        self.env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"]}
        self.candidate = self.image / "luma-pi4-UNVERIFIED.img.xz"
        self.partial = self.image / (self.candidate.name + ".recovery.partial")
        self.original_partial = self.image / (self.candidate.name + ".partial")
        self.original_partial.write_bytes(b"preserve-original-interrupted-output")

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def run_recovery(self):
        return subprocess.run(["bash", str(SCRIPT), str(self.root)], env=self.env,
                              capture_output=True, text=True, timeout=20)

    def assert_no_final(self):
        self.assertFalse(self.candidate.exists())
        self.assertFalse((self.image / "build-manifest.txt").exists())
        self.assertEqual(self.original_partial.read_bytes(), b"preserve-original-interrupted-output")

    def test_recovers_exact_bytes_with_portable_checksum_and_unverified_manifest(self):
        completed = self.run_recovery()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(lzma.decompress(self.candidate.read_bytes()), self.raw.read_bytes())
        self.assertFalse(self.partial.exists())
        self.assertEqual(self.original_partial.read_bytes(), b"preserve-original-interrupted-output")
        expected = hashlib.sha256(self.candidate.read_bytes()).hexdigest() + "  " + self.candidate.name + "\n"
        self.assertEqual((self.image / (self.candidate.name + ".sha256")).read_text(), expected)
        manifest = (self.image / "build-manifest.txt").read_text()
        self.assertIn("boot_verified=false\n", manifest)
        self.assertIn("compression_recovered=true\n", manifest)
        self.assertIn("raw_image_sha256=" + hashlib.sha256(self.raw.read_bytes()).hexdigest(), manifest)
        self.assertIn("source_sha256=" + SOURCE_SHA, manifest)

    def test_existing_final_is_never_overwritten(self):
        self.candidate.write_bytes(b"existing-final")
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertEqual(self.candidate.read_bytes(), b"existing-final")
        self.assertFalse(self.partial.exists())

    def test_existing_recovery_is_never_overwritten(self):
        self.partial.write_bytes(b"previous-recovery")
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertEqual(self.partial.read_bytes(), b"previous-recovery")
        self.assert_no_final()

    def test_missing_raw_fails_before_compression(self):
        self.raw.unlink()
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertFalse(self.partial.exists())
        self.assert_no_final()

    def test_changed_source_fails_before_compression(self):
        (self.root / "fingerprint.txt").write_text("b" * 64)
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertFalse(self.partial.exists())
        self.assert_no_final()

    def test_wrong_generator_fails_before_compression(self):
        self.executable("git", "#!/bin/sh\nprintf wrong-generator\n")
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assert_no_final()

    def test_compression_failure_preserves_partial_without_publishing(self):
        self.executable("xz", "#!/bin/sh\nprintf incomplete\nexit 1\n")
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertEqual(self.partial.read_bytes(), b"incomplete")
        self.assert_no_final()

    def test_invalid_archive_never_publishes(self):
        real_xz = shutil.which("xz")
        self.executable("xz", f'#!/bin/sh\nif [ "$1" = "-t" ]; then exec "{real_xz}" "$@"; fi\nprintf invalid-xz\n')
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assert_no_final()

    def test_raw_changed_during_compression_never_publishes(self):
        real_xz = shutil.which("xz")
        self.executable("xz", f'#!/bin/sh\n"{real_xz}" "$@" || exit $?\nif [ "$1" != "-t" ]; then printf changed >> "{self.raw}"; fi\n')
        self.assertNotEqual(self.run_recovery().returncode, 0)
        self.assertTrue(self.partial.exists())
        self.assert_no_final()


if __name__ == "__main__":
    unittest.main()
