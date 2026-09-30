"""Signed, optional offline Piper voice install, independent of app rollback.

The already-installed 0.2.3 updater deliberately accepts only small app
bundles. A separate signed release asset is installed in Luma's persistent
data partition after an app update; failure always leaves espeak-ng available.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request
import zipfile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .update_agent import PUBLIC_KEY
from .github_updates import _opener


VOICE_ID = "en_US-kristin-medium"
MAX_ASSET_BYTES = 180 * 1024 * 1024
MAX_UNPACKED_BYTES = 180 * 1024 * 1024
MAX_MEMBER_BYTES = 80 * 1024 * 1024
MODEL = f"model/{VOICE_ID}.onnx"
CONFIG = f"model/{VOICE_ID}.onnx.json"
ASSET_ROOT = Path("/var/lib/luma/voice-assets")
VOICE_RELEASE_VERSION = "0.2.4"
VOICE_ASSET_NAME = f"luma-voice-kristin-{VOICE_RELEASE_VERSION}.lva"
VOICE_RELEASE_URL = ("https://api.github.com/repos/BrianBGoldshtein/LumaSmartHub/"
                     f"releases/tags/v{VOICE_RELEASE_VERSION}")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VoiceAssetError(ValueError):
    """Fixed, non-secret error for the local setup UI."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate manifest field")
        value[key] = item
    return value


def _safe_name(name: str) -> bool:
    return (name in {MODEL, CONFIG, "sources/piper_tts-1.8.0.tar.gz"} or
            (name.startswith("wheels/") and name.count("/") == 1
             and re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", name.split("/", 1)[1]) is not None))


def voice_status(root: Path = ASSET_ROOT) -> dict:
    if ready(root):
        return {"phase": "ready", "message": "Offline voice ready."}
    status_path = root / "status.json"
    try:
        if status_path.is_symlink() or status_path.stat().st_size > 4096:
            raise ValueError
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if (not isinstance(status, dict) or status.get("phase") not in
                {"checking", "downloading", "verifying", "installing", "ready", "failed"}):
            raise ValueError
        if status["phase"] == "ready":
            return {"phase": "failed", "message": "Offline voice files need repair; using fallback voice."}
        return {"phase": status["phase"], "message": str(status.get("message", ""))[:160],
                "downloaded_bytes": int(status.get("downloaded_bytes", 0)),
                "total_bytes": int(status.get("total_bytes", 0))}
    except (OSError, ValueError, TypeError, KeyError):
        return {"phase": "ready", "message": "Offline voice ready."} if ready(root) else {
            "phase": "checking", "message": "Checking the offline voice asset."}


def write_status(root: Path, phase: str, message: str, *, downloaded: int = 0,
                 total: int = 0) -> None:
    if phase not in {"checking", "downloading", "verifying", "installing", "ready", "failed"}:
        raise ValueError("invalid voice phase")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise VoiceAssetError("Offline voice storage is unavailable.")
    value = {"phase": phase, "message": message[:160], "downloaded_bytes": downloaded,
             "total_bytes": total}
    descriptor, temporary = tempfile.mkstemp(prefix=".voice-status-", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, root / "status.json")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def ready(root: Path = ASSET_ROOT) -> bool:
    folder = root / VOICE_ID
    model, config, python = folder / MODEL, folder / CONFIG, folder / "venv/bin/python"
    return (folder.is_dir() and not folder.is_symlink() and model.is_file() and not model.is_symlink()
            and config.is_file() and not config.is_symlink() and python.is_file())


def _runtime_supported() -> bool:
    return sys.version_info[:2] == (3, 13) and platform.machine().lower() in {"aarch64", "arm64"}


def _reap_interrupted_work(root: Path) -> None:
    """Remove only old installer-owned scratch paths after an interrupted boot."""
    if not root.is_dir() or root.is_symlink():
        return
    boundary = root.resolve(strict=True)
    for path in root.iterdir():
        if (not (re.fullmatch(r"\.voice-download-[A-Za-z0-9_-]+\.lva", path.name)
                 or re.fullmatch(r"\.voice-stage-[A-Za-z0-9_-]+", path.name))
                or path.is_symlink() or not path.resolve(strict=False).is_relative_to(boundary)):
            continue
        try:
            if time.time() - path.stat().st_mtime < 3600:
                continue
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError:
            pass


def verify_and_extract(bundle: Path, staging: Path, public_key: Path = PUBLIC_KEY) -> dict:
    """Verify owner signature and per-file hashes while streaming into staging."""
    try:
        if bundle.is_symlink() or not bundle.is_file() or bundle.stat().st_size > MAX_ASSET_BYTES:
            raise VoiceAssetError("The offline voice package is invalid or too large.")
        key = serialization.load_pem_public_key(public_key.read_bytes())
        if not isinstance(key, Ed25519PublicKey):
            raise VoiceAssetError("The installed voice verification key is invalid.")
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or len(names) > 32 or any(item.is_dir() for item in infos):
                raise VoiceAssetError("The offline voice package has invalid entries.")
            if not {"manifest.json", "manifest.sig"}.issubset(names):
                raise VoiceAssetError("The offline voice package is incomplete.")
            if any(stat.S_ISLNK(item.external_attr >> 16) for item in infos):
                raise VoiceAssetError("The offline voice package contains a link.")
            if archive.getinfo("manifest.json").file_size > 128 * 1024 or archive.getinfo("manifest.sig").file_size != 64:
                raise VoiceAssetError("The offline voice manifest is invalid.")
            raw = archive.read("manifest.json")
            signature = archive.read("manifest.sig")
            if len(raw) > 128 * 1024 or len(signature) != 64:
                raise VoiceAssetError("The offline voice manifest is invalid.")
            manifest = json.loads(raw, object_pairs_hook=_no_duplicates)
            if not isinstance(manifest, dict) or raw != _canonical(manifest):
                raise VoiceAssetError("The offline voice manifest is not canonical.")
            try:
                key.verify(signature, raw)
            except InvalidSignature:
                raise VoiceAssetError("The offline voice signature is invalid.") from None
            if (manifest.get("format") != 1 or manifest.get("kind") != "luma-offline-voice"
                    or manifest.get("voice_id") != VOICE_ID or manifest.get("python") != "cp313-aarch64"):
                raise VoiceAssetError("This offline voice package is not compatible with Luma.")
            files = manifest.get("files")
            if (not isinstance(files, dict) or not {MODEL, CONFIG, "sources/piper_tts-1.8.0.tar.gz"}.issubset(files)
                    or not any(name.startswith("wheels/piper_tts-1.8.0-") for name in files)
                    or set(names) != set(files) | {"manifest.json", "manifest.sig"}
                    or not all(_safe_name(name) for name in files)):
                raise VoiceAssetError("The offline voice file list is invalid.")
            if sum(item.file_size for item in infos) > MAX_UNPACKED_BYTES + 128 * 1024:
                raise VoiceAssetError("The offline voice package expands too large.")
            for name, record in files.items():
                if (not isinstance(record, dict) or set(record) != {"sha256", "size"}
                        or type(record["size"]) is not int or not 0 < record["size"] <= MAX_MEMBER_BYTES
                        or not isinstance(record["sha256"], str) or not SHA256_RE.fullmatch(record["sha256"])):
                    raise VoiceAssetError("The offline voice file metadata is invalid.")
                if archive.getinfo(name).file_size != record["size"]:
                    raise VoiceAssetError("An offline voice file has the wrong size.")
                target = staging / name
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                hashed, copied = hashlib.sha256(), 0
                with archive.open(name) as source, target.open("xb") as output:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        copied += len(block)
                        if copied > record["size"]:
                            raise VoiceAssetError("An offline voice file exceeds its signed size.")
                        hashed.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if copied != record["size"] or hashed.hexdigest() != record["sha256"]:
                    raise VoiceAssetError("An offline voice file failed its signed checksum.")
            return manifest
    except VoiceAssetError:
        raise
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, UnicodeError):
        raise VoiceAssetError("The offline voice package could not be verified.") from None


def install_asset(bundle: Path, *, root: Path = ASSET_ROOT,
                  public_key: Path = PUBLIC_KEY, run=subprocess.run) -> dict:
    """Install pinned wheels without network and rename only after smoke test."""
    if ready(root):
        return {"phase": "ready", "message": "Offline voice ready."}
    if not _runtime_supported():
        raise VoiceAssetError("The offline voice package requires the Pi's ARM64 Python 3.13.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise VoiceAssetError("Offline voice storage is unavailable.")
    if shutil.disk_usage(root).free < 550 * 1024 * 1024:
        raise VoiceAssetError("Not enough free space to install the offline voice.")
    staging = Path(tempfile.mkdtemp(prefix=".voice-stage-", dir=root))
    try:
        manifest = verify_and_extract(bundle, staging, public_key)
        write_status(root, "installing", "Installing the verified offline voice.")
        venv = staging / "venv"
        run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=90,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        python = venv / "bin/python"
        wheels = sorted((staging / "wheels").glob("*.whl"))
        if len(wheels) != len([name for name in manifest["files"] if name.startswith("wheels/")]):
            raise VoiceAssetError("The offline voice wheel set is incomplete.")
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", "--no-cache-dir",
             "--disable-pip-version-check", *(str(wheel) for wheel in wheels)],
            check=True, timeout=240, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        smoke = ("from piper import PiperVoice; import io,wave; "
                 "v=PiperVoice.load(__import__('sys').argv[1]); b=io.BytesIO(); "
                 "w=wave.open(b,'wb'); v.synthesize_wav('Hello.',w); w.close(); "
                 "assert len(b.getvalue())>1024")
        run([str(python), "-c", smoke, str(staging / MODEL)], check=True, timeout=90,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        final = root / VOICE_ID
        if final.exists() or final.is_symlink():
            raise VoiceAssetError("An incomplete offline voice installation needs review.")
        os.replace(staging, final)
        write_status(root, "ready", "Offline voice ready.")
        return {"phase": "ready", "message": "Offline voice ready."}
    except VoiceAssetError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise VoiceAssetError("The offline voice did not pass its local install check; fallback voice remains available.") from None
    finally:
        if staging.exists() and staging.resolve(strict=False).is_relative_to(root.resolve(strict=True)):
            shutil.rmtree(staging)


def fetch_and_install(*, root: Path = ASSET_ROOT, public_key: Path = PUBLIC_KEY,
                      opener=None, installer=install_asset) -> dict:
    """Fetch only the release's exact sidecar URL, then verify its owner signature."""
    if ready(root):
        return {"phase": "ready", "message": "Offline voice ready."}
    opener = opener or _opener()
    _reap_interrupted_work(root)
    write_status(root, "checking", "Checking the signed offline voice release.")
    try:
        request = Request(VOICE_RELEASE_URL, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "LumaSmartHub-Voice/1"})
        with opener.open(request, timeout=15) as response:
            if response.geturl() != VOICE_RELEASE_URL:
                raise VoiceAssetError("The offline voice release address changed unexpectedly.")
            metadata = response.read(512 * 1024 + 1)
        if len(metadata) > 512 * 1024:
            raise VoiceAssetError("The offline voice release metadata is too large.")
        release = json.loads(metadata)
        if (not isinstance(release, dict) or release.get("draft") is not False
                or release.get("prerelease") is not False
                or release.get("target_commitish") != "main"
                or release.get("tag_name") != f"v{VOICE_RELEASE_VERSION}"):
            raise VoiceAssetError("The offline voice release is not a stable Luma release.")
        assets = release.get("assets")
        matches = ([item for item in assets if isinstance(item, dict)
                    and item.get("name") == VOICE_ASSET_NAME] if isinstance(assets, list) else [])
        if len(matches) != 1:
            raise VoiceAssetError("The signed offline voice file is not published yet.")
        asset = matches[0]
        size, url = asset.get("size"), asset.get("browser_download_url")
        expected = (f"https://github.com/BrianBGoldshtein/LumaSmartHub/"
                    f"releases/download/v{VOICE_RELEASE_VERSION}/{VOICE_ASSET_NAME}")
        if type(size) is not int or not 0 < size <= MAX_ASSET_BYTES or url != expected:
            raise VoiceAssetError("The offline voice release file metadata is invalid.")
        published_digest = asset.get("digest")
        if published_digest is not None and (not isinstance(published_digest, str)
                                             or not re.fullmatch(r"sha256:[0-9a-f]{64}", published_digest)):
            raise VoiceAssetError("The offline voice release checksum is invalid.")
        descriptor, temporary = tempfile.mkstemp(prefix=".voice-download-", suffix=".lva", dir=root)
        try:
            hashed, copied = hashlib.sha256(), 0
            with os.fdopen(descriptor, "wb") as output:
                request = Request(url, headers={
                    "Accept": "application/octet-stream", "User-Agent": "LumaSmartHub-Voice/1"})
                with opener.open(request, timeout=30) as response:
                    final = urlsplit(response.geturl())
                    if final.scheme != "https" or final.hostname not in _HTTPSGitHubRedirectHosts:
                        raise VoiceAssetError("The offline voice download address is invalid.")
                    declared = response.headers.get("Content-Length")
                    if declared is not None and (not declared.isdigit() or int(declared) != size):
                        raise VoiceAssetError("The offline voice download size changed.")
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        copied += len(block)
                        if copied > size:
                            raise VoiceAssetError("The offline voice download is too large.")
                        hashed.update(block)
                        output.write(block)
                        if copied // (5 * 1024 * 1024) != (copied - len(block)) // (5 * 1024 * 1024):
                            write_status(root, "downloading", "Downloading the offline voice.",
                                         downloaded=copied, total=size)
                output.flush()
                os.fsync(output.fileno())
            if copied != size or (published_digest and hashed.hexdigest() != published_digest[7:]):
                raise VoiceAssetError("The offline voice download failed its release checksum.")
            write_status(root, "verifying", "Verifying the signed offline voice.")
            return installer(Path(temporary), root=root, public_key=public_key)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    except VoiceAssetError as error:
        write_status(root, "failed", str(error))
        raise
    except (OSError, URLError, HTTPError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        message = "Could not download the offline voice; existing speech remains available."
        write_status(root, "failed", message)
        raise VoiceAssetError(message) from None


_HTTPSGitHubRedirectHosts = {"github.com", "release-assets.githubusercontent.com",
                             "objects.githubusercontent.com"}
