"""Install owner-authorized, signed Luma application releases atomically.

Updates contain only the Python wheel, its dependency declaration and the
compiled web client. OS packages, systemd units, hardware rules, credentials,
and /var/lib/luma are outside the update boundary and require a full image
build or remain on-device.
"""
from __future__ import annotations

import ast
import argparse
try:
    import fcntl
except ImportError:  # pragma: no cover - the appliance is Linux
    fcntl = None
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


MAX_BUNDLE_BYTES = 32 * 1024 * 1024
MAX_PAYLOAD_BYTES = 24 * 1024 * 1024
MAX_FILES = 512
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
APP_ROOT = Path("/opt/luma")
RELEASES_ROOT = Path("/opt/luma-releases")
PUBLIC_KEY = Path("/etc/luma/luma-update-ed25519.pub")
SYSTEM_SOCKET_UNITS = ("luma-backup.socket",)
SYSTEM_SERVICE_UNITS = ("luma-api.service", "luma-backup.service")
SYSTEM_UNITS = (*SYSTEM_SOCKET_UNITS, *SYSTEM_SERVICE_UNITS)
# Chromium keeps the already-loaded update progress surface visible while the
# API is swapped and health-checked. Only helpers with release-bound binaries
# are stopped; the kiosk reloads after success.
USER_UNITS = ("luma-device.service", "luma-voice.service")


@contextmanager
def staged_bundle(bundle: bytes, *, prefix: str):
    """Stage bytes in a private directory, closing the writer before readers open it.

    Keeping a NamedTemporaryFile handle open while another API opens the same
    path works on POSIX but fails under Windows' default file-sharing rules.
    The private directory also keeps the signed payload inaccessible to other
    local users while it is verified or installed.
    """
    try:
        with tempfile.TemporaryDirectory(prefix=prefix) as directory:
            path = Path(directory) / "luma-update.lup"
            path.write_bytes(bundle)
            yield path
    except OSError:
        raise UpdateError("The update bundle could not be staged safely.") from None


class UpdateError(ValueError):
    """A fixed, user-safe update rejection or failed update."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _no_duplicate_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def dependency_fingerprint(pyproject: bytes) -> str:
    try:
        project = tomllib.loads(pyproject.decode("utf-8"))["project"]
        contract = {
            "dependencies": sorted(project["dependencies"]),
            "optional-dependencies": {
                key: sorted(value) for key, value in sorted(
                    project.get("optional-dependencies", {}).items())
            },
        }
    except (UnicodeError, KeyError, TypeError, tomllib.TOMLDecodeError):
        raise UpdateError("The application dependency declaration is invalid.") from None
    return hashlib.sha256(_canonical(contract)).hexdigest()


def _safe_member(name: str) -> bool:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return False
    if name == "backend/pyproject.toml":
        return True
    if name.startswith("frontend/assets/"):
        return len(path.parts) == 3 and bool(re.fullmatch(r"[A-Za-z0-9._-]+", path.name))
    if name.startswith("frontend/licenses/"):
        return len(path.parts) == 3 and bool(re.fullmatch(r"[A-Za-z0-9._-]+", path.name))
    return (name == "frontend/index.html" or
            (name.startswith("backend/") and name.endswith("-py3-none-any.whl")
             and len(path.parts) == 2 and bool(re.fullmatch(
                 r"luma_smart_screen-[0-9.]+-py3-none-any\.whl", path.name))))


def _wheel_version(wheel: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            metadata = [name for name in archive.namelist()
                        if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError
            lines = archive.read(metadata[0]).decode("utf-8").splitlines()
            name = next(line[6:] for line in lines if line.startswith("Name: "))
            version = next(line[9:] for line in lines if line.startswith("Version: "))
            if name.lower().replace("_", "-") != "luma-smart-screen":
                raise ValueError
            return version
    except (OSError, ValueError, KeyError, StopIteration, UnicodeError, zipfile.BadZipFile):
        raise UpdateError("The signed update does not contain a valid Luma package.") from None


def _storage_schema(source: bytes) -> int:
    try:
        tree = ast.parse(source.decode("utf-8"))
        for item in tree.body:
            if (isinstance(item, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "SCHEMA_VERSION"
                            for target in item.targets)
                    and isinstance(item.value, ast.Constant)
                    and type(item.value.value) is int and item.value.value >= 1):
                return item.value.value
    except (UnicodeError, SyntaxError):
        pass
    raise UpdateError("The Luma package has no supported durable-data schema marker.")


def _wheel_storage_schema(wheel: bytes) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(wheel)) as archive:
            return _storage_schema(archive.read("luma/storage.py"))
    except (OSError, KeyError, zipfile.BadZipFile):
        raise UpdateError("The Luma package is missing its durable-data schema marker.") from None


def verify_bundle(bundle_path: Path, public_key_path: Path) -> dict:
    """Verify signature, exact member set, sizes, hashes and package metadata."""
    try:
        if bundle_path.is_symlink() or not bundle_path.is_file():
            raise UpdateError("Choose a regular update bundle file.")
        if bundle_path.stat().st_size > MAX_BUNDLE_BYTES:
            raise UpdateError("The update bundle is too large.")
        key = serialization.load_pem_public_key(public_key_path.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise UpdateError("The installed update verification key is invalid.")
        with zipfile.ZipFile(bundle_path) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or len(names) > MAX_FILES + 2:
                raise UpdateError("The update bundle has duplicate or excessive files.")
            if set(names) < {"manifest.json", "manifest.sig"}:
                raise UpdateError("The update bundle is incomplete.")
            if any(item.is_dir() for item in infos):
                raise UpdateError("The update bundle contains an invalid directory entry.")
            if sum(item.file_size for item in infos) > MAX_PAYLOAD_BYTES + 128 * 1024:
                raise UpdateError("The uncompressed update is too large.")
            for item in infos:
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or item.file_size > MAX_PAYLOAD_BYTES:
                    raise UpdateError("The update bundle contains an unsupported file.")
            raw_manifest = archive.read("manifest.json")
            if len(raw_manifest) > 128 * 1024:
                raise UpdateError("The update manifest is too large.")
            manifest = json.loads(raw_manifest, object_pairs_hook=_no_duplicate_pairs)
            if not isinstance(manifest, dict) or raw_manifest != _canonical(manifest):
                raise UpdateError("The update manifest is not canonical.")
            signature = archive.read("manifest.sig")
            if len(signature) != 64:
                raise UpdateError("The update signature is invalid.")
            try:
                key.verify(signature, raw_manifest)
            except InvalidSignature:
                raise UpdateError("The update signature is invalid.") from None

            if manifest.get("format") != 1:
                raise UpdateError("This update format is not supported.")
            version = manifest.get("version")
            if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                raise UpdateError("The update version is invalid.")
            if not SHA256_RE.fullmatch(str(manifest.get("source_sha256", ""))):
                raise UpdateError("The update source fingerprint is invalid.")
            files = manifest.get("files")
            if not isinstance(files, dict) or not files or len(files) > MAX_FILES:
                raise UpdateError("The update file list is invalid.")
            payload_names = set(names) - {"manifest.json", "manifest.sig"}
            if payload_names != set(files):
                raise UpdateError("The update file list does not match its contents.")
            if not all(_safe_member(path) for path in files):
                raise UpdateError("The update contains a path outside the application scope.")
            required = {"backend/pyproject.toml", "frontend/index.html"}
            if not required.issubset(files):
                raise UpdateError("The update is missing required application files.")
            wheels = [name for name in files if name.startswith("backend/") and name.endswith(".whl")]
            scripts = [name for name in files if name.startswith("frontend/assets/") and name.endswith(".js")]
            styles = [name for name in files if name.startswith("frontend/assets/") and name.endswith(".css")]
            if len(wheels) != 1 or not scripts or not styles:
                raise UpdateError("The update is missing its package or compiled web client.")
            payload: dict[str, bytes] = {}
            for name, record in files.items():
                if (not isinstance(record, dict) or set(record) != {"sha256", "size"}
                        or not SHA256_RE.fullmatch(str(record.get("sha256", "")))
                        or type(record.get("size")) is not int
                        or record["size"] < 0):
                    raise UpdateError("The update file metadata is invalid.")
                data = archive.read(name)
                if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
                    raise UpdateError("An update file failed its integrity check.")
                payload[name] = data
            pyproject = payload["backend/pyproject.toml"]
            project = tomllib.loads(pyproject.decode("utf-8"))["project"]
            if project.get("name") != "luma-smart-screen" or project.get("version") != version:
                raise UpdateError("The package version does not match the signed release.")
            if _wheel_version(payload[wheels[0]]) != version:
                raise UpdateError("The wheel version does not match the signed release.")
            if dependency_fingerprint(pyproject) != manifest.get("dependencies_sha256"):
                raise UpdateError("The dependency fingerprint does not match the signed release.")
            return {"version": version, "storage_schema": _wheel_storage_schema(payload[wheels[0]]),
                    "source_sha256": manifest["source_sha256"],
                    "dependencies_sha256": manifest["dependencies_sha256"],
                    "files": payload, "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest()}
    except UpdateError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, zipfile.BadZipFile,
            tomllib.TOMLDecodeError, InvalidSignature):
        raise UpdateError("The update bundle could not be verified.") from None


def _plain_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        if path.parent == root / "venv/bin" and path.name.startswith("python"):
            try:
                target = path.resolve(strict=True)
            except (OSError, RuntimeError):
                raise UpdateError("The installed Python environment has an invalid executable link.") from None
            if target.parent == Path("/usr/bin") and target.name.startswith("python3."):
                continue
        if path == root / "venv/lib64" and os.readlink(path) == "lib":
            continue
        raise UpdateError("The installed release has an unsupported symbolic link.")


def _current_release(app_root: Path, releases_root: Path) -> Path:
    if not app_root.is_symlink():
        raise UpdateError("This image needs a fresh image installation before in-place updates.")
    try:
        target = (app_root.parent / os.readlink(app_root)).resolve(strict=True)
        release_root = releases_root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise UpdateError("The installed application release cannot be resolved.") from None
    if not target.is_relative_to(release_root) or not target.is_dir():
        raise UpdateError("The installed application release is outside its protected release directory.")
    _plain_tree(target)
    return target


def _atomic_link(app_root: Path, release: Path) -> None:
    relative = os.path.relpath(release, app_root.parent)
    temporary = app_root.with_name(f".{app_root.name}.next-{os.getpid()}")
    try:
        if temporary.exists() or temporary.is_symlink():
            raise UpdateError("A previous update switch needs administrator review.")
        os.symlink(relative, temporary)
        os.replace(temporary, app_root)
        descriptor = os.open(app_root.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary.is_symlink():
            temporary.unlink()


def _install_wheel(release: Path, wheel_path: Path) -> None:
    python = release / "venv/bin/python"
    if not python.is_file():
        raise UpdateError("The current release has no usable Python environment.")
    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "--force-reinstall",
                    "--no-deps", "--no-index", str(wheel_path)],
                   check=True, timeout=120)


def _relocate_venv_scripts(venv_bin: Path, old_root: Path, new_root: Path) -> None:
    """Repair generated console-script shebangs after a staged release rename."""
    old = str(old_root).encode()
    new = str(new_root).encode()
    for path in venv_bin.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        content = path.read_bytes()
        first = content.splitlines(keepends=True)[0] if content else b""
        if not first.startswith(b"#!") or old not in content:
            continue
        content = content.replace(old, new)
        first = content.splitlines(keepends=True)[0]
        if len(first) > 127:
            raise UpdateError("A staged Python command has an unsupported interpreter path.")
        path.write_bytes(content)


def _sync_tree(root: Path) -> None:
    """Persist staged files and directory entries before publishing a release."""
    directories = [root]
    for path in root.rglob("*"):
        if path.is_dir() and not path.is_symlink():
            directories.append(path)
        elif path.is_file() and not path.is_symlink():
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class SystemdController:
    """Stop and restart only Luma units that were already active."""

    def __init__(self, runner=subprocess.run):
        self.runner = runner
        self.system = self._active(["systemctl", "is-active"], SYSTEM_UNITS)
        self.system_sockets = [unit for unit in self.system if unit in SYSTEM_SOCKET_UNITS]
        self.system_services = [unit for unit in self.system if unit in SYSTEM_SERVICE_UNITS]
        self.user = self._active(["systemctl", "--machine=luma@.host", "--user", "is-active"], USER_UNITS)

    def _active(self, prefix, units):
        active = []
        for unit in units:
            result = self.runner([*prefix, unit], capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip() == "active":
                active.append(unit)
        return active

    def _run(self, user: bool, verb: str, units: tuple[str, ...] | list[str]) -> None:
        prefix = (["systemctl", "--machine=luma@.host", "--user"] if user else ["systemctl"])
        for unit in units:
            self.runner([*prefix, verb, unit], check=True, capture_output=True, text=True, timeout=20)

    def stop(self) -> None:
        self._run(True, "stop", self.user)
        self._run(False, "stop", self.system_sockets)
        self._run(False, "stop", self.system_services)

    def start(self) -> None:
        self._run(False, "start", self.system_sockets)
        self._run(False, "start", self.system_services)
        self._run(True, "start", self.user)


def wait_for_health(version: str, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8742/api/v1/health", timeout=2) as response:
                value = json.loads(response.read(16 * 1024))
            if (response.status == 200 and value.get("status") == "ok"
                    and value.get("database") == "ok" and value.get("version") == version):
                return True
        except (OSError, ValueError, urllib.error.URLError):
            time.sleep(0.5)
    return False


def _apply_bundle_locked(bundle_path: Path, *, app_root: Path,
                         releases_root: Path, public_key_path: Path,
                         controller, health_check, install_wheel,
                         progress: Callable[[str], None] | None = None) -> Path:
    """Stage and atomically switch a verified release, rolling back on bad health."""
    def phase(value: str) -> None:
        if progress:progress(value)
    phase('verifying')
    verified = verify_bundle(bundle_path, public_key_path)
    current = _current_release(app_root, releases_root)
    try:
        current_info = json.loads((current / ".luma-release.json").read_text(encoding="utf-8"))
        current_version = current_info["version"]
    except (OSError, ValueError, KeyError, TypeError):
        raise UpdateError("The installed release metadata is missing or invalid.") from None
    match = VERSION_RE.fullmatch(current_version) if isinstance(current_version, str) else None
    if not match or tuple(map(int, verified["version"].split("."))) <= tuple(map(int, current_version.split("."))):
        raise UpdateError("The signed release must be newer than the installed version.")

    try:
        active_manifest = tomllib.loads((current / "backend/pyproject.toml").read_text(encoding="utf-8"))["project"]
        if active_manifest.get("version") != current_version or current.name != current_version:
            raise UpdateError("The installed release version markers do not agree.")
        active_contract = {"dependencies": sorted(active_manifest["dependencies"]),
                           "optional-dependencies": {key: sorted(value) for key, value in sorted(
                               active_manifest.get("optional-dependencies", {}).items())}}
        installed_fingerprint = hashlib.sha256(_canonical(active_contract)).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError):
        raise UpdateError("The installed dependency declaration cannot be verified.") from None
    if verified["dependencies_sha256"] != installed_fingerprint:
        raise UpdateError("Runtime dependencies changed; install a newly qualified full image instead.")
    try:
        current_schema = _storage_schema((current / "backend/src/luma/storage.py").read_bytes())
    except (OSError, UpdateError):
        raise UpdateError("The installed durable-data schema cannot be verified.") from None
    if verified["storage_schema"] != current_schema:
        raise UpdateError("Durable-data schema changes require a newly qualified full image.")

    candidate = releases_root / verified["version"]
    if candidate.exists() or candidate.is_symlink():
        raise UpdateError("This release version already exists; choose a new version.")
    if not releases_root.is_dir() or releases_root.is_symlink():
        raise UpdateError("The protected application release directory is unavailable.")
    try:
        controller = controller or SystemdController()
    except (OSError, subprocess.SubprocessError):
        raise UpdateError("Could not safely inspect active Luma services.") from None
    stage = Path(tempfile.mkdtemp(prefix=f".{verified['version']}.staging-", dir=releases_root))
    switch_attempted = False
    stopped = False
    promoted = False
    rollback_completed = False
    try:
        phase('copying')
        shutil.copytree(current, stage, dirs_exist_ok=True, symlinks=False)
        _plain_tree(stage)
        for directory in (stage / "backend", stage / "frontend"):
            if directory.is_symlink():
                raise UpdateError("The staged release contains an unsupported link.")
        for relative, data in verified["files"].items():
            destination = stage.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_symlink():
                raise UpdateError("The staged release contains an unsupported link.")
            if relative == "frontend/index.html" or relative.startswith("frontend/assets/"):
                continue
            destination.write_bytes(data)
        shutil.rmtree(stage / "frontend")
        (stage / "frontend/assets").mkdir(parents=True)
        for relative, data in verified["files"].items():
            if relative.startswith("frontend/"):
                destination = stage.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
        wheel_name = next(name for name in verified["files"] if name.endswith(".whl"))
        wheel_path = stage / Path(wheel_name).name
        wheel_path.write_bytes(verified["files"][wheel_name])
        phase('installing')
        install_wheel(stage, wheel_path)
        wheel_path.unlink()
        (stage / ".luma-release.json").write_bytes(_canonical({
            "version": verified["version"], "source_sha256": verified["source_sha256"],
            "manifest_sha256": verified["manifest_sha256"],
            "dependencies_sha256": verified["dependencies_sha256"]}) + b"\n")
        os.chmod(stage / ".luma-release.json", 0o644)
        staged_path = stage
        os.chmod(staged_path, 0o755)
        phase('syncing')
        _sync_tree(staged_path)
        os.rename(staged_path, candidate)
        promoted = True
        directory_fd = os.open(releases_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        _relocate_venv_scripts(candidate / "venv/bin", staged_path, candidate)
        _sync_tree(candidate / "venv/bin")

        phase('switching')
        stopped = True
        controller.stop()
        # _atomic_link can replace the pointer successfully and then fail while
        # syncing its parent directory. Treat the whole operation as a switch
        # attempt before calling it so every post-replace error takes rollback.
        switch_attempted = True
        _atomic_link(app_root, candidate)
        phase('restarting')
        controller.start()
        phase('checking')
        if not health_check(verified["version"]):
            raise UpdateError("The new release did not pass its local health check.")
        phase('complete')
        return candidate
    except Exception as exc:
        if switch_attempted:
            try:
                phase('restoring')
                controller.stop()
                _atomic_link(app_root, current)
                controller.start()
                rollback_completed = True
            except Exception:
                raise UpdateError("Update failed and automatic rollback needs local recovery.") from None
        elif stopped:
            try:
                phase('restoring')
                controller.start()
            except Exception:
                raise UpdateError("Update failed before switching; service recovery needs local review.") from None
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError("The update could not be installed; the previous release was restored.") from None
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if promoted and not switch_attempted and candidate.exists():
            shutil.rmtree(candidate)
        elif rollback_completed and candidate.exists():
            shutil.rmtree(candidate)


def apply_bundle(bundle_path: Path, *, app_root: Path = APP_ROOT,
                 releases_root: Path = RELEASES_ROOT, public_key_path: Path = PUBLIC_KEY,
                 controller=None, health_check=wait_for_health, install_wheel=_install_wheel,
                 progress: Callable[[str], None] | None = None) -> Path:
    """Serialize installation so two admin requests cannot race the active pointer."""
    if fcntl is None:
        raise UpdateError("In-place updates require the Linux appliance runtime.")
    if not releases_root.is_dir() or releases_root.is_symlink():
        raise UpdateError("The protected application release directory is unavailable.")
    lock_path = releases_root / ".luma-update.lock"
    descriptor = -1
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_mode & 0o022:
            raise OSError("unsafe update lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        raise UpdateError("Could not acquire the local update lock.") from None
    try:
        return _apply_bundle_locked(bundle_path, app_root=app_root,
                                    releases_root=releases_root, public_key_path=public_key_path,
                                    controller=controller, health_check=health_check,
                                    install_wheel=install_wheel,progress=progress)
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    verify = commands.add_parser("verify", help="verify a signed bundle without installing it")
    verify.add_argument("bundle", type=Path)
    apply = commands.add_parser("apply", help="install a signed application release")
    apply.add_argument("bundle", type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Run this command through the key-only administrator account and sudo.")
    try:
        if args.operation == "verify":
            verified = verify_bundle(args.bundle, PUBLIC_KEY)
            print(f"Verified Luma {verified['version']} · {len(verified['files'])} files · no changes made")
            return
        release = apply_bundle(args.bundle)
    except UpdateError as exc:
        raise SystemExit(str(exc)) from None
    print(f"Luma {release.name} is active. Prior releases are retained for rollback.")


if __name__ == "__main__":
    main()
