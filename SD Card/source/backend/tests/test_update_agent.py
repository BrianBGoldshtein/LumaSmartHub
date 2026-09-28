from __future__ import annotations

import hashlib
import json
import base64
import csv
import io
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from luma.update_agent import (
    UpdateError, _canonical, apply_bundle, dependency_fingerprint, verify_bundle,
)


def make_bundle(tmp_path: Path, *, version: str = "0.3.0", corrupt: bool = False,
                dependency_change: bool = False, storage_schema: int = 1):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "test-public.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    import re
    pyproject = re.sub(r'^version = "[^"]+"$', f'version = "{version}"', pyproject, count=1, flags=re.M).encode()
    if dependency_change:
        pyproject = pyproject.replace(b'  "httpx>=0.27,<1",', b'  "httpx>=0.27,<1",\n  "requests>=2,<3",')
    wheel_name = f"luma_smart_screen-{version}-py3-none-any.whl"
    wheel_buffer = io.BytesIO()
    dist_info = f"luma_smart_screen-{version}.dist-info"
    wheel_files = {
        f"{dist_info}/METADATA": f"Metadata-Version: 2.1\nName: luma-smart-screen\nVersion: {version}\n\n".encode(),
        f"{dist_info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: luma-tests\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        f"{dist_info}/entry_points.txt": b"[console_scripts]\nluma-test-command = luma.test_cli:main\n",
        "luma/__init__.py": b"",
        "luma/storage.py": f"SCHEMA_VERSION = {storage_schema}\n".encode(),
        "luma/test_cli.py": b"def main():\n    print('wheel-ok')\n",
    }
    rows = []
    for name, data in wheel_files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((name, f"sha256={digest}", str(len(data))))
    rows.append((f"{dist_info}/RECORD", "", ""))
    record = io.StringIO(newline="")
    csv.writer(record, lineterminator="\n").writerows(rows)
    wheel_files[f"{dist_info}/RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(wheel_buffer, "w") as wheel:
        for name, data in wheel_files.items():
            wheel.writestr(name, data)
    payload = {
        "backend/pyproject.toml": pyproject,
        f"backend/{wheel_name}": wheel_buffer.getvalue(),
        "frontend/index.html": b"<main>new app</main>",
        "frontend/assets/app.js": b"console.log('new')",
        "frontend/assets/app.css": b"body{color:#123}",
        "frontend/licenses/fonts.txt": b"font license notice",
    }
    contract = {
        "dependencies": sorted(__import__("tomllib").loads(pyproject.decode())["project"]["dependencies"]),
        "optional-dependencies": {key: sorted(value) for key, value in sorted(
            __import__("tomllib").loads(pyproject.decode())["project"].get("optional-dependencies", {}).items())},
    }
    manifest = {"format": 1, "version": version, "source_sha256": "a" * 64,
                "dependencies_sha256": hashlib.sha256(_canonical(contract)).hexdigest(),
                "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                          for name, data in sorted(payload.items())}}
    raw = _canonical(manifest)
    signature = private.sign(raw)
    if corrupt:
        signature = bytes([signature[0] ^ 1]) + signature[1:]
    bundle_path = tmp_path / "release.luma-update"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", raw)
        bundle.writestr("manifest.sig", signature)
        for name, data in payload.items():
            bundle.writestr(name, data)
    return bundle_path, public_path


def installed_tree(tmp_path: Path, *, real_venv: bool = False):
    releases = tmp_path / "luma-releases"
    current = releases / "0.2.0"
    (current / "backend").mkdir(parents=True)
    (current / "backend/src/luma").mkdir(parents=True)
    (current / "frontend").mkdir()
    if real_venv:
        subprocess.run([sys.executable, "-m", "venv", str(current / "venv")], check=True)
    else:
        (current / "venv/bin").mkdir(parents=True)
        if sys.platform == "win32":
            (current / "venv/bin/python").write_text("test stub")
        else:
            (current / "venv/bin/python").symlink_to("/usr/bin/python3")
            (current / "venv/lib").mkdir()
            (current / "venv/lib64").symlink_to("lib", target_is_directory=True)
    project = (Path(__file__).parents[1] / "pyproject.toml").read_bytes()
    (current / "backend/pyproject.toml").write_bytes(project)
    (current / "backend/src/luma/storage.py").write_text("SCHEMA_VERSION = 1\n")
    (current / "frontend/index.html").write_text("old app")
    (current / ".luma-release.json").write_text('{"version":"0.2.0"}')
    app = tmp_path / "luma"
    app.symlink_to(Path("luma-releases/0.2.0"), target_is_directory=True)
    return app, releases, current


class FakeController:
    def __init__(self):
        self.actions = []

    def stop(self):
        self.actions.append("stop")

    def start(self):
        self.actions.append("start")


def no_install(release, wheel):
    assert (release / "venv/bin/python").is_file()
    assert wheel.is_file()


def test_verify_bundle_checks_signature_hashes_and_wheel_metadata(tmp_path):
    bundle, public = make_bundle(tmp_path)
    verified = verify_bundle(bundle, public)
    assert verified["version"] == "0.3.0"
    assert b"new app" in verified["files"]["frontend/index.html"]


def test_verify_bundle_rejects_signature_tampering(tmp_path):
    bundle, public = make_bundle(tmp_path, corrupt=True)
    with pytest.raises(UpdateError, match="signature"):
        verify_bundle(bundle, public)


def test_verify_bundle_rejects_traversal_even_when_signed(tmp_path):
    bundle, public = make_bundle(tmp_path)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("../outside", b"no")
    with pytest.raises(UpdateError):
        verify_bundle(bundle, public)


def test_apply_stages_switches_and_keeps_prior_release(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink switch is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    controller = FakeController()
    candidate = apply_bundle(bundle, app_root=app, releases_root=releases,
                             public_key_path=public, controller=controller,
                             health_check=lambda version: version == "0.3.0", install_wheel=no_install)
    assert candidate == releases / "0.3.0"
    assert app.resolve() == candidate
    assert current.exists() and (candidate / "frontend/index.html").read_text() == "<main>new app</main>"
    assert json.loads((candidate / ".luma-release.json").read_text())["version"] == "0.3.0"
    assert controller.actions == ["stop", "start"]


def test_apply_installs_wheel_and_repairs_venv_entrypoint_after_rename(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's Linux venv layout and atomic switch are Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, _current = installed_tree(tmp_path, real_venv=True)
    candidate = apply_bundle(bundle, app_root=app, releases_root=releases,
                             public_key_path=public, controller=FakeController(),
                             health_check=lambda version: version == "0.3.0")
    command = candidate / "venv/bin/luma-test-command"
    assert command.is_file(), [path.name for path in (candidate / "venv/bin").iterdir()]
    result = subprocess.run([str(command)], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "wheel-ok"
    assert str(candidate).encode() in command.read_bytes().splitlines()[0]


def test_failed_health_check_restores_old_release_and_restarts(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink rollback is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    controller = FakeController()
    with pytest.raises(UpdateError, match="health check"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=controller,
                     health_check=lambda _version: False, install_wheel=no_install)
    assert app.resolve() == current
    assert current.exists()
    assert not (releases / "0.3.0").exists()
    assert controller.actions == ["stop", "start", "stop", "start"]


def test_dependency_change_requires_full_image_even_with_valid_signature(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's release layout is Linux-only")
    bundle, public = make_bundle(tmp_path, dependency_change=True)
    app, releases, _current = installed_tree(tmp_path)
    with pytest.raises(UpdateError):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=FakeController(),
                     health_check=lambda _version: True, install_wheel=no_install)
    assert app.resolve() == releases / "0.2.0"


def test_durable_data_schema_change_requires_full_image(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's release layout is Linux-only")
    bundle, public = make_bundle(tmp_path, storage_schema=2)
    app, releases, _current = installed_tree(tmp_path)
    with pytest.raises(UpdateError, match="Durable-data schema changes"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=FakeController(),
                     health_check=lambda _version: True, install_wheel=no_install)
