from __future__ import annotations

import hashlib
import json
import base64
import csv
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile
from types import SimpleNamespace

import pytest
from luma import update_agent
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from luma.update_agent import (
    UpdateError, SystemdController, _canonical, apply_bundle, dependency_fingerprint, verify_bundle,
)
from luma.github_updates import GitHubUpdateError, RELEASES_API, latest_release
from luma.update_broker import UpdateBroker


def make_bundle(tmp_path: Path, *, version: str = "0.3.0", corrupt: bool = False,
                dependency_change: bool = False, storage_schema: int = 1):
    private = Ed25519PrivateKey.generate()
    public_path = tmp_path / "test-public.pem"
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
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
        # The deployed service venv is anchored to the OS-managed interpreter,
        # not the hosted CI's separately installed setup-python runtime.
        subprocess.run(["/usr/bin/python3", "-m", "venv", str(current / "venv")], check=True)
    else:
        (current / "venv/bin").mkdir(parents=True)
        if sys.platform == "win32":
            (current / "venv/bin/python").write_text("test stub")
        else:
            (current / "venv/bin/python").symlink_to("/usr/bin/python3")
            (current / "venv/lib").mkdir()
            (current / "venv/lib64").symlink_to("lib", target_is_directory=True)
    # The fixture models the already-flashed base image, not the version of
    # the source tree currently preparing a later app-only update.
    project = re.sub(rb'(?m)^version = "[^"]+"$', b'version = "0.2.0"',
                     (Path(__file__).parents[1] / "pyproject.toml").read_bytes(), count=1)
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


class FakeHTTPResponse(io.BytesIO):
    def __init__(self, content, url):
        super().__init__(content)
        self.headers = {}
        self.url = url

    def geturl(self):
        return self.url


class FakeReleaseOpener:
    def __init__(self, metadata, bundle):
        import hashlib
        from urllib.parse import urlparse
        asset_url = "https://github.com/BrianBGoldshtein/LumaSmartHub/releases/download/v0.3.0/luma-update-0.3.0.lup"
        metadata["assets"] = [{"name": "luma-update-0.3.0.lup", "size": len(bundle),
                               "digest": "sha256:" + hashlib.sha256(bundle).hexdigest(),
                               "browser_download_url": asset_url}]
        self.content = {RELEASES_API: json.dumps(metadata).encode(), asset_url: bundle}
        self.calls = []

    def open(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        return FakeHTTPResponse(self.content[url], url)


def release_metadata(**updates):
    value = {"draft": False, "prerelease": False, "target_commitish": "main", "tag_name": "v0.3.0",
             "body": "Fixes and improvements", "published_at": "2026-09-29T12:00:00Z",
             "html_url": "https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.0"}
    value.update(updates)
    return value


def test_github_release_is_downloaded_only_when_newer_and_its_signature_matches(tmp_path):
    bundle_path, public = make_bundle(tmp_path)
    bundle = bundle_path.read_bytes()
    opener = FakeReleaseOpener(release_metadata(), bundle)
    release = latest_release("0.2.0", public_key_path=public, opener=opener)
    assert release["state"] == "available"
    assert release["version"] == "0.3.0"
    assert release["bundle"] == bundle
    assert len(opener.calls) == 2
    assert opener.calls[0] == RELEASES_API
    assert opener.calls[1].endswith("luma-update-0.3.0.lup")


def test_github_latest_release_cannot_be_used_to_downgrade(tmp_path):
    bundle_path, public = make_bundle(tmp_path)
    opener = FakeReleaseOpener(release_metadata(), bundle_path.read_bytes())
    result = latest_release("0.3.0", public_key_path=public, opener=opener)
    assert result == {"state": "current", "current_version": "0.3.0"}
    assert opener.calls == [RELEASES_API]


def test_github_release_requires_exact_tag_asset_checksum_and_luma_signature(tmp_path):
    bundle_path, public = make_bundle(tmp_path)
    bundle = bundle_path.read_bytes()
    opener = FakeReleaseOpener(release_metadata(tag_name="v0.3.1"), bundle)
    with pytest.raises(GitHubUpdateError, match="metadata"):
        latest_release("0.2.0", public_key_path=public, opener=opener)

    bad_hash = FakeReleaseOpener(release_metadata(), bundle)
    bad_metadata = json.loads(bad_hash.content[RELEASES_API])
    bad_metadata["assets"][0]["digest"] = "sha256:" + "0" * 64
    bad_hash.content[RELEASES_API] = json.dumps(bad_metadata).encode()
    with pytest.raises(GitHubUpdateError, match="checksum"):
        latest_release("0.2.0", public_key_path=public, opener=bad_hash)

    tampered = tmp_path / "tampered"
    tampered.mkdir()
    bad_signature_path, _ = make_bundle(tampered, corrupt=True)
    bad_signature = FakeReleaseOpener(release_metadata(), bad_signature_path.read_bytes())
    with pytest.raises(GitHubUpdateError, match="signature"):
        latest_release("0.2.0", public_key_path=public, opener=bad_signature)


@pytest.mark.asyncio
async def test_root_update_broker_accepts_only_signed_bundle_and_reports_health_result(tmp_path):
    bundle_path, public = make_bundle(tmp_path)
    installed = []
    refreshed = []

    def install(path, *, public_key_path, progress):
        progress('copying')
        installed.append(verify_bundle(path, public_key_path)["version"])

    broker = UpdateBroker(installer=install, public_key_path=public,
                          refresh_service=lambda: refreshed.append(True))
    request = {"action": "install", "bundle": base64.b64encode(bundle_path.read_bytes()).decode()}
    accepted, bundle = await broker.accept(request)
    assert accepted == {"accepted": True, "version": "0.3.0"}
    assert broker.status()["state"] == "installing"
    await broker.install(bundle)
    assert installed == ["0.3.0"]
    assert broker.status()["state"] == "installed"
    assert refreshed == [True]

    corrupt_dir = tmp_path / "corrupt"
    corrupt_dir.mkdir()
    corrupted_path, _ = make_bundle(corrupt_dir, corrupt=True)
    corrupted = {"action": "install", "bundle": base64.b64encode(corrupted_path.read_bytes()).decode()}
    rejected, no_bundle = await UpdateBroker(public_key_path=public).accept(corrupted)
    assert "error" in rejected
    assert no_bundle is None


@pytest.mark.asyncio
async def test_root_update_broker_does_not_refresh_after_failed_install(tmp_path):
    bundle_path, public = make_bundle(tmp_path)
    refreshed = []

    def fail_install(_path, *, public_key_path, progress):
        progress('copying')
        raise UpdateError("simulated install failure")

    broker = UpdateBroker(installer=fail_install, public_key_path=public,
                          refresh_service=lambda: refreshed.append(True))
    request = {"action": "install", "bundle": base64.b64encode(bundle_path.read_bytes()).decode()}
    accepted, bundle = await broker.accept(request)
    assert accepted == {"accepted": True, "version": "0.3.0"}
    await broker.install(bundle)
    assert broker.status()["state"] == "failed"
    assert refreshed == []


@pytest.mark.asyncio
async def test_update_progress_survives_broker_restart_and_reports_interruption(tmp_path):
    if sys.platform == "win32":
        pytest.skip("durable directory fsync for update progress requires POSIX")
    bundle_path,public=make_bundle(tmp_path)
    status_path=tmp_path/'release-status.json'
    phases=[]
    def install(_path,*,public_key_path,progress):
        progress('copying');progress('switching');phases.append('done')
    broker=UpdateBroker(installer=install,public_key_path=public,status_path=status_path)
    request={'action':'install','bundle':base64.b64encode(bundle_path.read_bytes()).decode()}
    accepted,bundle=await broker.accept(request)
    assert accepted['accepted'] and status_path.is_file()
    assert broker.status()['phase']=='verifying'
    await broker.install(bundle)
    assert phases==['done'] and broker.status()['phase']=='complete'
    restarted=UpdateBroker(public_key_path=public,status_path=status_path)
    assert restarted.status()['state']=='installed'
    assert restarted.status()['target_version']=='0.3.0'
    assert restarted.status()['elapsed_seconds']>=0

    interrupted_path=tmp_path/'interrupted-status.json'
    interrupted=UpdateBroker(public_key_path=public,status_path=interrupted_path)
    await interrupted.accept(request)
    recovered=UpdateBroker(public_key_path=public,status_path=interrupted_path)
    assert recovered.status()['state']=='failed' and recovered.status()['phase']=='interrupted'
    assert 'interrupted' in recovered.status()['message']


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
    saved_state = tmp_path / "var/lib/luma/settings.sqlite"
    saved_state.parent.mkdir(parents=True)
    saved_state.write_bytes(b"owner's saved state")
    controller = FakeController()
    phases=[]
    candidate = apply_bundle(bundle, app_root=app, releases_root=releases,
                             public_key_path=public, controller=controller,
                             health_check=lambda version: version == "0.3.0", install_wheel=no_install,
                             progress=phases.append)
    assert candidate == releases / "0.3.0"
    assert app.resolve() == candidate
    assert current.exists() and (candidate / "frontend/index.html").read_text() == "<main>new app</main>"
    assert json.loads((candidate / ".luma-release.json").read_text())["version"] == "0.3.0"
    assert controller.actions == ["stop", "start"]
    assert saved_state.read_bytes() == b"owner's saved state"
    assert phases==['verifying','copying','installing','syncing','switching','restarting','checking','complete']


def test_systemd_updater_leaves_kiosk_running_while_api_is_switched():
    calls=[]
    def runner(command,**kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0,stdout='active\n')
    controller=SystemdController(runner=runner)
    calls.clear()
    controller.stop();controller.start()
    assert not any('luma-kiosk.service' in command for command in calls)
    assert any('luma-api.service' in command for command in calls)


def test_systemd_restart_attempts_api_even_when_backup_socket_fails():
    calls=[]
    def runner(command,**kwargs):
        calls.append(command)
        if command[:2] == ['systemctl', 'start'] and command[-1] == 'luma-backup.socket':
            raise subprocess.CalledProcessError(1, command)
        return SimpleNamespace(returncode=0,stdout='active\n')
    controller=SystemdController(runner=runner)
    calls.clear()
    with pytest.raises(UpdateError, match='luma-backup.socket'):
        controller.start()
    assert ['systemctl', 'start', 'luma-api.service'] in calls
    assert any(command[-1] == 'luma-device.service' for command in calls)
    assert any(command[-1] == 'luma-voice.service' for command in calls)


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
    # This smoke checks the installed wheel, so it must not inherit a test
    # runner's checkout-only PYTHONPATH and accidentally import source instead.
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run([str(command)], check=True, capture_output=True,
                            text=True, env=environment)
    assert result.stdout.strip() == "wheel-ok"
    assert str(candidate).encode() in command.read_bytes().splitlines()[0]


def test_failed_health_check_restores_old_release_and_restarts(tmp_path):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink rollback is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    saved_state = tmp_path / "var/lib/luma/settings.sqlite"
    saved_state.parent.mkdir(parents=True)
    saved_state.write_bytes(b"owner's saved state")
    controller = FakeController()
    with pytest.raises(UpdateError, match="health check"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=controller,
                     health_check=lambda _version: False, install_wheel=no_install)
    assert app.resolve() == current
    assert current.exists()
    assert not (releases / "0.3.0").exists()
    assert controller.actions == ["stop", "start", "stop", "start"]
    assert saved_state.read_bytes() == b"owner's saved state"


def test_directory_sync_failure_after_pointer_replace_rolls_back(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink switch is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    controller = FakeController()
    original_open = update_agent.os.open
    failed = False

    def fail_first_pointer_sync(path, flags, *args, **kwargs):
        nonlocal failed
        if (Path(path) == app.parent and flags & getattr(os, "O_DIRECTORY", 0)
                and not failed):
            failed = True
            raise OSError("simulated directory sync failure after pointer replacement")
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(update_agent.os, "open", fail_first_pointer_sync)
    with pytest.raises(UpdateError, match="previous release was restored"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=controller,
                     health_check=lambda _version: True, install_wheel=no_install)
    assert failed
    assert app.resolve() == current
    assert current.exists()
    assert not (releases / "0.3.0").exists()
    assert controller.actions == ["stop", "stop", "start"]


def test_read_only_pointer_parent_restores_services_without_second_switch(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink rollback is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    controller = FakeController()
    original_symlink = update_agent.os.symlink
    failures=[]

    def read_only_parent(target, link_name, *args, **kwargs):
        if Path(link_name).parent == app.parent and Path(link_name).name.startswith('.luma.next-'):
            failures.append(link_name)
            raise OSError("simulated read-only /opt parent")
        return original_symlink(target, link_name, *args, **kwargs)

    monkeypatch.setattr(update_agent.os, "symlink", read_only_parent)
    with pytest.raises(UpdateError, match="previous release was restored"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=controller,
                     health_check=lambda _: True, install_wheel=no_install)
    assert len(failures) == 1  # Do not repeat the forbidden pointer operation.
    assert app.resolve() == current
    assert controller.actions == ["stop", "start"]
    assert not (releases / "0.3.0").exists()


def test_failed_pointer_rollback_still_attempts_service_restart(tmp_path, monkeypatch):
    if sys.platform == "win32":
        pytest.skip("the updater's atomic symlink switch is Linux-only")
    bundle, public = make_bundle(tmp_path)
    app, releases, current = installed_tree(tmp_path)
    controller = FakeController()
    original_link = update_agent._atomic_link
    switches = []

    def fail_restore(app_root, release):
        switches.append(release)
        if release == current:
            raise OSError("simulated restore failure")
        return original_link(app_root, release)

    monkeypatch.setattr(update_agent, "_atomic_link", fail_restore)
    with pytest.raises(UpdateError, match="local service status"):
        apply_bundle(bundle, app_root=app, releases_root=releases,
                     public_key_path=public, controller=controller,
                     health_check=lambda _: False, install_wheel=no_install)
    assert switches == [releases / "0.3.0", current]
    assert controller.actions == ["stop", "start", "stop", "start"]
    assert app.resolve() == releases / "0.3.0"
    assert (releases / "0.3.0").exists()  # Active candidate must never be deleted.


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
