"""Local update signing-key custody and image-key match checks."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "source/tools/build-update-bundle.py"
SPEC = importlib.util.spec_from_file_location("build_update_bundle", BUILDER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def key_pair(tmp_path: Path, *, public_key: Ed25519PrivateKey | None = None):
    delivery = tmp_path / "delivery"
    public_path = delivery / "source/system/luma-update-ed25519.pub"
    public_path.parent.mkdir(parents=True)
    signer = Ed25519PrivateKey.generate()
    pinned = public_key or signer
    public_path.write_bytes(pinned.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    private_path = tmp_path / "offline-key.pem"
    private_path.write_bytes(signer.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    private_path.chmod(0o600)
    return delivery, private_path, signer


class OfflineSigningTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="luma-update-signing-")
        self.addCleanup(temporary.cleanup)
        self.tmp_path = Path(temporary.name)

    def test_local_signer_must_match_the_public_key_pinned_in_the_image(self):
        delivery, private_path, signer = key_pair(self.tmp_path)
        loaded = MODULE.load_signing_key(delivery, private_path)
        self.assertEqual(
            loaded.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
            signer.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            ),
        )

    def test_refuses_a_different_offline_signer(self):
        delivery, private_path, _ = key_pair(
            self.tmp_path, public_key=Ed25519PrivateKey.generate()
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.load_signing_key(delivery, private_path)

    def test_private_key_must_stay_outside_the_delivery_tree(self):
        delivery, _, signer = key_pair(self.tmp_path)
        inside = delivery / "private.pem"
        inside.write_bytes(signer.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        inside.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "outside the delivery tree"):
            MODULE.load_signing_key(delivery, inside)

    def test_signed_bundle_output_must_stay_outside_delivery_tree(self):
        delivery, private_path, _ = key_pair(self.tmp_path)
        output = delivery / "nested/bundle.lup"
        result = subprocess.run([
            MODULE.sys.executable, str(BUILDER), str(delivery),
            "--key", str(private_path), "--output", str(output),
        ], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("signed bundles must be written outside the delivery tree", result.stderr)
        self.assertFalse(output.exists())

    def test_local_release_helper_has_valid_bash_syntax_and_offline_signing_only(self):
        bash = shutil.which("bash")
        if bash is None:
            candidate = Path("C:/Program Files/Git/bin/bash.exe")
            if not candidate.is_file():
                self.skipTest("Bash syntax checker is unavailable")
            bash = str(candidate)
        script = ROOT / "source/tools/publish-update-release.sh"
        subprocess.run([bash, "-n", str(script)], check=True, capture_output=True, text=True)
        source = script.read_text(encoding="utf-8")
        self.assertNotIn("secrets.", source)
        self.assertIn("--publish", source)
        self.assertIn("luma-update-ed25519.pem", source)
        self.assertIn("qualify-update-bundle.py", source)
        self.assertIn("verify_and_extract", source)
        self.assertIn("SD Card/image-builder", source)
        self.assertIn('--store-dir "$(dirname -- "${OUTPUT}")/pnpm-store"', source)
        self.assertIn('elif [[ "${VERSION}" == "0.2.6" ]]', source)
        self.assertIn('QUALIFY_FROM="0.2.5"', source)
        self.assertIn('elif [[ "${VERSION}" == "0.2.7" ]]', source)
        self.assertIn('QUALIFY_FROM="0.2.6"', source)
        self.assertIn('elif [[ "${VERSION}" == "0.2.9" ]]', source)
        self.assertIn('QUALIFY_FROM="0.2.8"', source)
        self.assertIn('elif [[ "${VERSION}" == "0.2.11" ]]', source)
        self.assertIn('QUALIFY_FROM="0.2.10"', source)
        self.assertIn('0.2.9 requires its separately signed acoustic wake asset', source)
        self.assertIn('RELEASE_ASSETS+=("${KEYWORD_OUTPUT}")', source)
        self.assertLess(source.index('qualify-keyword-asset.py'), source.index('read -r CONFIRMATION'))
        self.assertLess(source.index('qualify-keyword-arm64-install.py'), source.index('read -r CONFIRMATION'))
        self.assertLess(source.index("qualify-update-bundle.py"), source.index('read -r CONFIRMATION'))
        self.assertLess(source.index("verify_and_extract"), source.index('read -r CONFIRMATION'))

    @unittest.skipUnless(os.name == "posix", "POSIX mode bits are not portable to Windows")
    def test_private_key_permissions_must_be_owner_only(self):
        delivery, private_path, _ = key_pair(self.tmp_path)
        private_path.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "permissions are too open"):
            MODULE.load_signing_key(delivery, private_path)
