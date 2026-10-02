"""Optional, hash-pinned offline Vosk speaker model for owner-run trials.

The signed Luma application pins the official model's exact SHA-256. Download
and installation happen only after an explicit local setup action. This module
never enrolls a voice, stores audio, or enables a speaker-based command gate.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zipfile


URL = 'https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip'
SHA256 = 'a74d8f51144484813e16af689bb0f916b7a111e2347f467c4933c1166097b5a7'
MODEL_NAME = 'vosk-model-spk-0.4'
FILES = frozenset({'mfcc.conf', 'README.txt', 'mean.vec', 'transform.mat',
                   'final.ext.raw'})
EXPECTED = frozenset({MODEL_NAME + '/', *(f'{MODEL_NAME}/{name}' for name in FILES)})
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_MEMBER = 15 * 1024 * 1024
MAX_UNPACKED = 16 * 1024 * 1024
ASSET_ROOT = Path('/var/lib/luma/speaker-model')


class SpeakerAssetError(ValueError):
    """Non-private, fixed failure for the optional local trial setup."""


def ready(root: Path = ASSET_ROOT) -> bool:
    folder = root / MODEL_NAME
    marker = folder / '.installed.json'
    try:
        if root.is_symlink() or not folder.is_dir() or folder.is_symlink() \
                or marker.is_symlink() or marker.stat().st_size > 256:
            return False
        installed = json.loads(marker.read_text(encoding='ascii'))
        if installed != {'version': 1, 'sha256': SHA256}:
            return False
        return all((folder / name).is_file() and not (folder / name).is_symlink()
                   and 0 < (folder / name).stat().st_size <= MAX_MEMBER for name in FILES)
    except (OSError, ValueError, TypeError):
        return False


def _download(opener=urlopen) -> bytes:
    try:
        with opener(URL, timeout=30) as response:
            if response.geturl() != URL:
                raise SpeakerAssetError('The speaker model source changed unexpectedly.')
            data = response.read(MAX_ARCHIVE + 1)
    except (OSError, TimeoutError) as exc:
        raise SpeakerAssetError('The speaker model could not be downloaded.') from exc
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != SHA256:
        raise SpeakerAssetError('The speaker model did not match its pinned checksum.')
    return data


def _extract(data: bytes, folder: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if set(archive.namelist()) != EXPECTED:
                raise SpeakerAssetError('The speaker model archive layout is invalid.')
            members = {item.filename: item for item in archive.infolist()}
            if (len(archive.infolist()) != len(EXPECTED) or len(members) != len(EXPECTED)
                    or sum(item.file_size for item in members.values()) > MAX_UNPACKED):
                raise SpeakerAssetError('The speaker model archive is too large.')
            if archive.testzip() is not None:
                raise SpeakerAssetError('The speaker model archive is corrupt.')
            for name in FILES:
                item = members[f'{MODEL_NAME}/{name}']
                if not 0 < item.file_size <= MAX_MEMBER:
                    raise SpeakerAssetError('The speaker model contains an invalid member.')
                # Extract only fixed, pinned basenames. ZIP path metadata never
                # becomes a destination path or a filesystem link.
                contents = archive.read(item)
                if len(contents) != item.file_size:
                    raise SpeakerAssetError('The speaker model archive is incomplete.')
                target = folder / name
                with target.open('xb') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(contents)
                    stream.flush()
                    os.fsync(stream.fileno())
    except (zipfile.BadZipFile, OSError, RuntimeError, KeyError) as exc:
        raise SpeakerAssetError('The speaker model archive is invalid.') from exc


def install(root: Path = ASSET_ROOT, *, opener=urlopen,
            run=subprocess.run) -> Path:
    """Install once after local consent; never replace an existing model here."""
    if ready(root):
        return root / MODEL_NAME
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or (root / MODEL_NAME).exists() or (root / MODEL_NAME).is_symlink():
        raise SpeakerAssetError('An existing speaker model needs local review.')
    if shutil.disk_usage(root).free < 64 * 1024 * 1024:
        raise SpeakerAssetError('Not enough free storage for the speaker model.')
    data = _download(opener)
    with tempfile.TemporaryDirectory(prefix='.speaker-stage-', dir=root) as temporary:
        stage = Path(temporary) / MODEL_NAME
        stage.mkdir(mode=0o700)
        _extract(data, stage)
        try:
            run([sys.executable, '-c',
                 'from vosk import SpkModel; import sys; SpkModel(sys.argv[1])',
                 str(stage)], check=True, timeout=45, capture_output=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise SpeakerAssetError('The speaker model could not load locally.') from exc
        marker = stage / '.installed.json'
        with marker.open('x', encoding='ascii') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({'version': 1, 'sha256': SHA256}, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.rename(stage, root / MODEL_NAME)
        except OSError as exc:
            raise SpeakerAssetError('The speaker model could not be installed.') from exc
    return root / MODEL_NAME
