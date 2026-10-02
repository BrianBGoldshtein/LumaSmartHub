import hashlib
import io
import json
from pathlib import Path
import subprocess
import warnings
import zipfile

import pytest

from luma import speaker_asset


def archive_bytes(*, missing: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(speaker_asset.MODEL_NAME + '/', b'')
        for name in sorted(speaker_asset.FILES - ({missing} if missing else set())):
            archive.writestr(f'{speaker_asset.MODEL_NAME}/{name}', b'model-' + name.encode())
    return buffer.getvalue()


class Response:
    def __init__(self, data: bytes, url: str = speaker_asset.URL):
        self.data, self.url = data, url
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def geturl(self):
        return self.url
    def read(self, limit: int):
        return self.data[:limit]


def test_pinned_model_install_is_opt_in_atomic_and_contains_no_voice_profile(tmp_path, monkeypatch):
    data = archive_bytes()
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(data).hexdigest())
    root = tmp_path / 'speaker-model'
    calls = []
    def run(command, **kwargs):
        stage = Path(command[-1])
        assert stage.is_dir() and all((stage / name).is_file() for name in speaker_asset.FILES)
        assert kwargs['check'] and kwargs['timeout'] <= 45
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    installed = speaker_asset.install(root, opener=lambda *_a, **_k: Response(data), run=run)
    assert installed == root / speaker_asset.MODEL_NAME
    assert speaker_asset.ready(root)
    assert len(calls) == 1
    assert json.loads((installed / '.installed.json').read_text()) == {
        'version': 1, 'sha256': speaker_asset.SHA256}
    assert not list(root.glob('.speaker-stage-*'))
    assert speaker_asset.install(root, opener=lambda *_a, **_k: pytest.fail('redownloaded')) == installed
    assert all('voice' not in path.name and 'profile' not in path.name
               for path in installed.iterdir())


def test_wrong_checksum_redirect_and_archive_layout_never_replace_existing_data(tmp_path, monkeypatch):
    data = archive_bytes()
    root = tmp_path / 'speaker-model'
    with pytest.raises(speaker_asset.SpeakerAssetError, match='checksum'):
        speaker_asset.install(root, opener=lambda *_a, **_k: Response(data))
    assert not (root / speaker_asset.MODEL_NAME).exists()
    with pytest.raises(speaker_asset.SpeakerAssetError, match='source changed'):
        speaker_asset.install(root, opener=lambda *_a, **_k: Response(data, 'https://elsewhere.test'))
    assert not (root / speaker_asset.MODEL_NAME).exists()
    malformed = archive_bytes(missing='mfcc.conf')
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(malformed).hexdigest())
    with pytest.raises(speaker_asset.SpeakerAssetError, match='layout'):
        speaker_asset.install(root, opener=lambda *_a, **_k: Response(malformed))
    assert not (root / speaker_asset.MODEL_NAME).exists()
    assert not list(root.glob('.speaker-stage-*'))


def test_failed_model_load_keeps_existing_siblings_and_no_partial_install(tmp_path, monkeypatch):
    data = archive_bytes()
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(data).hexdigest())
    root = tmp_path / 'speaker-model'
    root.mkdir()
    sibling = root / 'owner-settings.json'
    sibling.write_text('preserve me')
    def failed(_command, **_kwargs):
        raise subprocess.CalledProcessError(1, 'vosk smoke')
    with pytest.raises(speaker_asset.SpeakerAssetError, match='could not load'):
        speaker_asset.install(root, opener=lambda *_a, **_k: Response(data), run=failed)
    assert sibling.read_text() == 'preserve me'
    assert not (root / speaker_asset.MODEL_NAME).exists()
    assert not list(root.glob('.speaker-stage-*'))


def test_existing_incomplete_or_symlinked_model_is_not_deleted(tmp_path, monkeypatch):
    data = archive_bytes()
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(data).hexdigest())
    root = tmp_path / 'speaker-model'
    existing = root / speaker_asset.MODEL_NAME
    existing.mkdir(parents=True)
    sentinel = existing / 'do-not-remove'
    sentinel.write_text('owner data')
    with pytest.raises(speaker_asset.SpeakerAssetError, match='existing'):
        speaker_asset.install(root, opener=lambda *_a, **_k: pytest.fail('downloaded'))
    assert sentinel.read_text() == 'owner data'
    sentinel.unlink()
    existing.rmdir()
    existing.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(speaker_asset.SpeakerAssetError, match='existing'):
        speaker_asset.install(root, opener=lambda *_a, **_k: pytest.fail('downloaded'))


def test_unpacked_size_is_checked_before_decompression(tmp_path, monkeypatch):
    data = archive_bytes()
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(data).hexdigest())
    monkeypatch.setattr(speaker_asset, 'MAX_UNPACKED', 20)
    with pytest.raises(speaker_asset.SpeakerAssetError, match='too large'):
        speaker_asset.install(tmp_path / 'speaker', opener=lambda *_a, **_k: Response(data))


def test_duplicate_archive_member_is_rejected_before_decompression(tmp_path, monkeypatch):
    buffer = io.BytesIO(archive_bytes())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(buffer, 'a') as archive:
            archive.writestr(f'{speaker_asset.MODEL_NAME}/mfcc.conf', b'duplicate')
    data = buffer.getvalue()
    monkeypatch.setattr(speaker_asset, 'SHA256', hashlib.sha256(data).hexdigest())
    with pytest.raises(speaker_asset.SpeakerAssetError, match='too large'):
        speaker_asset.install(tmp_path / 'speaker', opener=lambda *_a, **_k: Response(data))
