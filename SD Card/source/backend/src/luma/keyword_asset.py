"""Signed optional keyword model/runtime; independent of app/settings rollback.

This module does not activate a detector or authorize voice commands. Vendor
payloads are fixed by the application's source pins as well as the owner's
offline signature. Install into persistent private data, never the app venv.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from time import monotonic
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request
import zipfile
try:
    import fcntl
except ImportError:  # appliance installation is Linux-only
    fcntl = None

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .update_agent import PUBLIC_KEY
from .github_updates import _opener,REDIRECT_HOSTS

ASSET_ROOT = Path('/var/lib/luma/keyword-assets')
KEYWORD_ID = 'phonetic-english-3m-v1'
ASSET_VERSION = '0.2.9'
ASSET_NAME = f'luma-keyword-{ASSET_VERSION}.lka'
RELEASE_URL = f'https://api.github.com/repos/BrianBGoldshtein/LumaSmartHub/releases/tags/v{ASSET_VERSION}'
DOWNLOAD_URL = f'https://github.com/BrianBGoldshtein/LumaSmartHub/releases/download/v{ASSET_VERSION}/{ASSET_NAME}'
MAX_ASSET_BYTES = 64*1024*1024
MAX_MANIFEST_BYTES = 32768
MAX_MEMBER_BYTES = 16*1024*1024
SOURCE_LOCK = json.loads(Path(__file__).with_name('keyword_assets.json').read_text())
NOTICE = ("Luma optional acoustic keyword asset\n"
    "Model: sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20\n"
    "Author distribution: pkufool/icefall-kws-zipformer-zh-en-3M-2025-12-20\n"
    "https://www.modelscope.cn/models/pkufool/icefall-kws-zipformer-zh-en-3M-2025-12-20\n"
    "Author revision: 541d04e28be57efc6fdf46a341da09e043a37b52\n"
    "Model weights/tokens are unmodified. Model card and Apache 2.0 license included.\n"
    "The external tokenizer/g2p dictionary is not included or required.\n"
    "Runtime: sherpa-onnx/core 1.13.8; NumPy 2.5.3, official ARM64 wheels.\n"
    "Runtime copyright, license and third-party notices remain inside the original wheels\n"
    "and installed package metadata; no such notices are removed.\n"
    "Luma's fixed keyword configuration and worker are separate application code.\n").encode('ascii')
PINNED_FILES = {**SOURCE_LOCK['files'], 'NOTICE.txt': {
    'size':len(NOTICE), 'sha256':hashlib.sha256(NOTICE).hexdigest()}}
PROVENANCE = {key:SOURCE_LOCK[key] for key in (
    'model','model_author_revision','model_license','model_source')}


class KeywordAssetError(ValueError):
    """Fixed non-private failure codes; no paths, speech or upstream tracebacks."""


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True,allow_nan=False).encode('ascii')


def _unique_fields(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def expected_manifest():
    return {'format':1,'kind':'luma-offline-keyword','version':ASSET_VERSION,
            'keyword_id':KEYWORD_ID,'python':'cp313-aarch64',
            'provenance':PROVENANCE,'files':PINNED_FILES}


def verified_manifest(raw, signature, public_key):
    if not 0<len(raw)<=MAX_MANIFEST_BYTES or len(signature)!=64:
        raise KeywordAssetError('keyword_manifest_invalid')
    try:
        key = serialization.load_pem_public_key(public_key.read_bytes())
        if not isinstance(key,Ed25519PublicKey):
            raise KeywordAssetError('keyword_key_invalid')
        key.verify(signature,raw)
        manifest = json.loads(raw,object_pairs_hook=_unique_fields)
        if raw!=canonical(manifest) or raw!=canonical(expected_manifest()):
            raise KeywordAssetError('keyword_manifest_invalid')
        return manifest
    except KeywordAssetError:
        raise
    except InvalidSignature:
        raise KeywordAssetError('keyword_signature_invalid') from None
    except (OSError,ValueError,TypeError,UnicodeError):
        raise KeywordAssetError('keyword_manifest_invalid') from None


def verify_and_extract(bundle:Path, staging:Path, public_key:Path=PUBLIC_KEY):
    """Check the entire manifest/layout before writing any verified payload."""
    try:
        if (bundle.is_symlink() or not bundle.is_file()
                or not 0<bundle.stat().st_size<=MAX_ASSET_BYTES
                or staging.is_symlink() or not staging.is_dir()):
            raise KeywordAssetError('keyword_package_invalid')
        boundary = staging.resolve(strict=True)
        with zipfile.ZipFile(bundle) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names)!=len(set(names)) or set(names)!=set(PINNED_FILES)|{'manifest.json','manifest.sig'}
                    or len(names)>16 or any(info.is_dir() or stat.S_ISLNK(info.external_attr>>16)
                        or info.flag_bits&1 or info.compress_type not in (zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED)
                        for info in infos)
                    or sum(info.file_size for info in infos)>MAX_ASSET_BYTES+MAX_MANIFEST_BYTES):
                raise KeywordAssetError('keyword_package_layout_invalid')
            if (not 0<archive.getinfo('manifest.json').file_size<=MAX_MANIFEST_BYTES
                    or archive.getinfo('manifest.sig').file_size!=64):
                raise KeywordAssetError('keyword_manifest_invalid')
            raw, signature = archive.read('manifest.json'),archive.read('manifest.sig')
            manifest = verified_manifest(raw,signature,public_key)
            for name,record in manifest['files'].items():
                if (name!='NOTICE.txt' and not re.fullmatch(r'(model|wheels|licenses)/[A-Za-z0-9_.-]+',name)):
                    raise KeywordAssetError('keyword_package_layout_invalid')
                if (type(record['size']) is not int or not 0<record['size']<=MAX_MEMBER_BYTES
                        or not re.fullmatch('[0-9a-f]{64}',record['sha256'])
                        or archive.getinfo(name).file_size!=record['size']):
                    raise KeywordAssetError('keyword_file_invalid')
            for name,record in manifest['files'].items():
                target = staging/name
                target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                if target.parent.is_symlink() or not target.parent.resolve(strict=True).is_relative_to(boundary):
                    raise KeywordAssetError('keyword_storage_invalid')
                hashed, copied = hashlib.sha256(),0
                with archive.open(name) as source, target.open('xb') as output:
                    for block in iter(lambda:source.read(256*1024),b''):
                        copied += len(block)
                        if copied>record['size']:
                            raise KeywordAssetError('keyword_file_invalid')
                        hashed.update(block); output.write(block)
                    output.flush(); os.fsync(output.fileno())
                if copied!=record['size'] or hashed.hexdigest()!=record['sha256']:
                    raise KeywordAssetError('keyword_file_invalid')
            for name,data in (('manifest.json',raw),('manifest.sig',signature)):
                with (staging/name).open('xb') as output:
                    output.write(data); output.flush(); os.fsync(output.fileno())
            return manifest
    except KeywordAssetError:
        raise
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,zipfile.BadZipFile,RuntimeError):
        raise KeywordAssetError('keyword_package_invalid') from None


def _fsync_directory(path):
    descriptor = os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path, value):
    descriptor, temporary = tempfile.mkstemp(prefix='.keyword-json-',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as output:
            output.write(canonical(value)); output.flush(); os.fsync(output.fileno())
        os.replace(temporary,path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_small(path, *, limit=2048):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=limit:
        raise KeywordAssetError('keyword_state_invalid')
    value = json.loads(path.read_text(),object_pairs_hook=_unique_fields)
    if not isinstance(value,dict):
        raise KeywordAssetError('keyword_state_invalid')
    return value


def _owned(path, token):
    if path.is_symlink() or not path.is_dir() or not re.fullmatch('[0-9a-f]{32}',token or ''):
        return False
    try:
        value = _read_small(path/'ownership.json')
        return type(value.get('format')) is int and value=={'format':1,'token':token}
    except (OSError,ValueError,TypeError):
        return False


def _folder_ready(folder, public_key):
    try:
        if folder.is_symlink() or not folder.is_dir():
            return False
        raw_path, sig_path = folder/'manifest.json',folder/'manifest.sig'
        if (raw_path.is_symlink() or sig_path.is_symlink()
                or not 0<raw_path.stat().st_size<=MAX_MANIFEST_BYTES
                or sig_path.stat().st_size!=64):
            return False
        raw = raw_path.read_bytes()
        manifest = verified_manifest(raw,sig_path.read_bytes(),public_key)
        token = _read_small(folder/'ownership.json')['token']
        marker = _read_small(folder/'ready.json')
        if not _owned(folder,token) or type(marker.get('format')) is not int or marker != {
                'format':1,'manifest_sha256':hashlib.sha256(raw).hexdigest(),'token':token}:
            return False
        for name,record in manifest['files'].items():
            path = folder/name
            if path.is_symlink() or path.parent.is_symlink() or not path.is_file() or path.stat().st_size!=record['size']:
                return False
        # The venv interpreter itself is normally a symlink to system Python.
        # Its parent directories must be genuine installer-owned directories.
        return (not (folder/'venv').is_symlink() and not (folder/'venv/bin').is_symlink()
                and (folder/'venv/bin/python').is_file())
    except (OSError,ValueError,TypeError,KeyError):
        return False


def ready(root:Path=ASSET_ROOT, public_key:Path=PUBLIC_KEY):
    return not root.is_symlink() and _folder_ready(root/KEYWORD_ID,public_key)


def check_worker_smoke(output):
    # Silence must never be reported as a wake. This tests the actual worker
    # after model/runtime load; it does not test speaker, mic, owner or latency.
    if output!=b'KWS02\n'+struct.pack('>Bdd',0,-1.0,-1.0):
        raise KeywordAssetError('keyword_smoke_failed')


def _runtime_supported():
    return sys.version_info[:2]==(3,13) and platform.machine().lower() in {'aarch64','arm64'}


def write_status(root, phase, *, error=None, downloaded=0, total=0):
    if phase not in {'checking','downloading','verifying','installing','ready','failed','recovering'}:
        raise ValueError('invalid keyword phase')
    _atomic_json(root/'status.json', {'phase':phase,'error':error,
        'downloaded_bytes':downloaded,'total_bytes':total})


@contextmanager
def installation_lock(root, *, name='.install.lock'):
    if fcntl is None:
        raise KeywordAssetError('keyword_runtime_unsupported')
    if name not in {'.install.lock','.fetch.lock'}:
        raise ValueError('invalid internal lock name')
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode)&0o077:
        raise KeywordAssetError('keyword_storage_invalid')
    descriptor = os.open(root/name,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise KeywordAssetError('keyword_storage_invalid')
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise KeywordAssetError('keyword_asset_busy') from None
        yield
    finally:
        os.close(descriptor)


def _remove_owned(path, token, root):
    boundary = root.resolve(strict=True)
    if (path.is_symlink() or path.resolve(strict=False)==boundary
            or not path.resolve(strict=False).is_relative_to(boundary)
            or not _owned(path,token)):
        raise KeywordAssetError('keyword_recovery_required')
    shutil.rmtree(path)
    _fsync_directory(root)


def _transaction(root):
    try:
        value = _read_small(root/'install.json',limit=4096)
    except (OSError,ValueError,TypeError):
        raise KeywordAssetError('keyword_recovery_required') from None
    if (not isinstance(value,dict) or set(value)!={'format','phase','token','prior','stage'}
            or type(value['format']) is not int or value['format']!=1
            or not isinstance(value['phase'],str) or value['phase'] not in {'staging','switching','committed'}
            or not isinstance(value['token'],str) or not re.fullmatch('[0-9a-f]{32}',value['token'])
            or (value['prior'] is not None and (not isinstance(value['prior'],str)
                or not re.fullmatch('[0-9a-f]{32}',value['prior'])))
            or value['stage']!='.keyword-stage-'+value['token']):
        raise KeywordAssetError('keyword_recovery_required')
    return value


def _recover_locked(root, public_key):
    """Recover only journal-identified, ownership-marked directories."""
    journal = root/'install.json'
    final, previous = root/KEYWORD_ID, root/('.keyword-previous-'+KEYWORD_ID)
    exists = lambda path:path.exists() or path.is_symlink()
    if not exists(journal):
        if exists(previous):
            raise KeywordAssetError('keyword_recovery_required')
        return False
    transaction = _transaction(root)
    token, prior = transaction['token'],transaction['prior']
    stage = root/transaction['stage']
    if (transaction['phase']=='committed' and _owned(final,token)
            and _folder_ready(final,public_key)):
        if exists(previous):
            if prior is None:
                raise KeywordAssetError('keyword_recovery_required')
            _remove_owned(previous,prior,root)
        if exists(stage):
            _remove_owned(stage,token,root)
    else:
        if exists(previous):
            # Check the recoverable previous asset BEFORE touching the new one.
            if prior is None or not _owned(previous,prior) or not _folder_ready(previous,public_key):
                raise KeywordAssetError('keyword_recovery_required')
            if exists(final):
                _remove_owned(final,token,root)
            os.replace(previous,final); _fsync_directory(root)
        elif prior is not None:
            if not _owned(final,prior) or not _folder_ready(final,public_key):
                raise KeywordAssetError('keyword_recovery_required')
        elif exists(final):
            _remove_owned(final,token,root)
        if exists(stage):
            _remove_owned(stage,token,root)
    journal.unlink(); _fsync_directory(root)
    return True


def recover_interrupted_install(root:Path=ASSET_ROOT, public_key:Path=PUBLIC_KEY):
    try:
        with installation_lock(root):
            changed = _recover_locked(root,public_key)
            if changed:
                write_status(root,'ready' if ready(root,public_key) else 'checking')
            return changed
    except KeywordAssetError:
        raise
    except (OSError,ValueError,TypeError,KeyError):
        raise KeywordAssetError('keyword_recovery_required') from None


def _smoke(folder, run):
    result = run([str(folder/'venv/bin/python'),'-I',
                  str(Path(__file__).with_name('keyword_worker.py')),str(folder/'model')],
                 input=struct.pack('>I',8000)+bytes(8000),check=True,timeout=90,
                 stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    check_worker_smoke(result.stdout)


def install_asset(bundle:Path, *, root:Path=ASSET_ROOT, public_key:Path=PUBLIC_KEY,
                  run=subprocess.run, replace_existing=False):
    """Offline-only venv install, staging AND final-path protocol smoke, recovery.

    No OS packages, app venv, settings DB, Google tokens, phone bonds or game
    files are touched. Installation does not enable recognition. The optional
    runtime is ready only after the final relocated path passes its smoke.
    """
    if not _runtime_supported():
        raise KeywordAssetError('keyword_runtime_unsupported')
    try:
        with installation_lock(root):
            _recover_locked(root,public_key)
            if ready(root,public_key) and not replace_existing:
                return {'phase':'ready','installed':False}
            final, previous = root/KEYWORD_ID,root/('.keyword-previous-'+KEYWORD_ID)
            current_exists = final.exists() or final.is_symlink()
            if current_exists and not ready(root,public_key):
                raise KeywordAssetError('keyword_recovery_required')
            if replace_existing and not current_exists:
                raise KeywordAssetError('keyword_repair_unavailable')
            if shutil.disk_usage(root).free<350*1024*1024:
                raise KeywordAssetError('keyword_storage_full')
            token = secrets.token_hex(16)
            prior = _read_small(final/'ownership.json')['token'] if current_exists else None
            stage = root/('.keyword-stage-'+token)
            stage.mkdir(mode=0o700)
            _atomic_json(stage/'ownership.json',{'format':1,'token':token})
            transaction = {'format':1,'phase':'staging','token':token,'prior':prior,'stage':stage.name}
            _atomic_json(root/'install.json',transaction)
            try:
                write_status(root,'verifying')
                verify_and_extract(bundle,stage,public_key)
                write_status(root,'installing')
                run([sys.executable,'-m','venv',str(stage/'venv')],check=True,timeout=90,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                wheels = [str(stage/name) for name in sorted(PINNED_FILES) if name.startswith('wheels/')]
                run([str(stage/'venv/bin/python'),'-m','pip','install','--no-index','--no-deps',
                     '--no-cache-dir','--disable-pip-version-check',*wheels],check=True,timeout=240,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                _smoke(stage,run)
                transaction['phase']='switching'
                _atomic_json(root/'install.json',transaction)
                if current_exists:
                    if not _owned(final,prior) or not _folder_ready(final,public_key):
                        raise KeywordAssetError('keyword_recovery_required')
                    os.replace(final,previous); _fsync_directory(root)
                os.replace(stage,final); _fsync_directory(root)
                _smoke(final,run)
                raw = (final/'manifest.json').read_bytes()
                _atomic_json(final/'ready.json',{'format':1,'token':token,
                    'manifest_sha256':hashlib.sha256(raw).hexdigest()})
                transaction['phase']='committed'
                _atomic_json(root/'install.json',transaction)
                # Committed recovery performs the same narrowly-owned cleanup.
                _recover_locked(root,public_key)
                write_status(root,'ready')
                return {'phase':'ready','installed':True}
            except Exception as error:
                try:
                    _recover_locked(root,public_key)
                    code = str(error) if isinstance(error,KeywordAssetError) else 'keyword_install_failed'
                    write_status(root,'failed',error=code)
                except Exception:
                    raise KeywordAssetError('keyword_recovery_required') from None
                raise KeywordAssetError(code) from None
    except KeywordAssetError:
        raise
    except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
        raise KeywordAssetError('keyword_install_failed') from None


def status(root:Path=ASSET_ROOT, public_key:Path=PUBLIC_KEY):
    available = ready(root,public_key)
    try:
        value = _read_small(root/'status.json',limit=4096)
        if value.get('phase') not in {'checking','downloading','verifying','installing','ready','failed','recovering'}:
            raise ValueError
        for field in ('downloaded_bytes','total_bytes'):
            if type(value.get(field)) is not int or not 0<=value[field]<=MAX_ASSET_BYTES:
                raise ValueError
        error = value.get('error')
        if error is not None and (not isinstance(error,str) or not re.fullmatch('keyword_[a-z_]{1,64}',error)):
            raise ValueError
        if value['phase']=='ready' and not available:
            value.update(phase='failed',error='keyword_files_need_repair')
        return {**value,'asset_available':available}
    except (OSError,ValueError,TypeError):
        return {'phase':'ready' if available else 'not_installed','asset_available':available,
                'error':None,'downloaded_bytes':0,'total_bytes':0}


def _record_fetch_failure(root, code):
    try:
        if root.is_dir() and not root.is_symlink() and not stat.S_IMODE(root.stat().st_mode)&0o077:
            write_status(root,'failed',error=code)
    except (OSError,ValueError):
        pass  # Storage failure must not leak an upstream/path exception.


def fetch_and_install(*, root:Path=ASSET_ROOT, public_key:Path=PUBLIC_KEY,
                      opener=None, installer=install_asset, replace_existing=False):
    """Download only the pinned main release sidecar, then verify/install offline.

    Exact owner/tag/name/URL/size plus the offline signature AND vendor pins.
    HTTPS redirects stay on known GitHub hosts; streaming has a total deadline.
    A separate fetch lock avoids duplicate downloads without recursively taking
    the installation lock. Direct installs still serialize their transactions.
    """
    if not _runtime_supported():
        raise KeywordAssetError('keyword_runtime_unsupported')
    try:
        with installation_lock(root,name='.fetch.lock'):
            recover_interrupted_install(root,public_key)
            if ready(root,public_key) and not replace_existing:
                return {'phase':'ready','installed':False}
            opener = opener or _opener()
            write_status(root,'checking')
            request = Request(RELEASE_URL,headers={'Accept':'application/vnd.github+json',
                                                  'User-Agent':'LumaSmartHub-Keyword/1'})
            with opener.open(request,timeout=15) as response:
                if response.geturl()!=RELEASE_URL:
                    raise KeywordAssetError('keyword_release_invalid')
                raw = response.read(512*1024+1)
            if len(raw)>512*1024:
                raise KeywordAssetError('keyword_release_invalid')
            release = json.loads(raw,object_pairs_hook=_unique_fields)
            if (not isinstance(release,dict) or release.get('draft') is not False
                    or release.get('prerelease') is not False or release.get('target_commitish')!='main'
                    or release.get('tag_name')!=f'v{ASSET_VERSION}'):
                raise KeywordAssetError('keyword_release_invalid')
            entries = release.get('assets')
            matches = ([entry for entry in entries if isinstance(entry,dict) and entry.get('name')==ASSET_NAME]
                       if isinstance(entries,list) else [])
            if len(matches)!=1:
                raise KeywordAssetError('keyword_release_missing')
            metadata = matches[0]
            size, published_digest = metadata.get('size'),metadata.get('digest')
            if (type(size) is not int or not 0<size<=MAX_ASSET_BYTES
                    or metadata.get('browser_download_url')!=DOWNLOAD_URL
                    or (published_digest is not None and (not isinstance(published_digest,str)
                        or not re.fullmatch('sha256:[0-9a-f]{64}',published_digest)))):
                raise KeywordAssetError('keyword_release_invalid')
            descriptor, temporary = tempfile.mkstemp(prefix='.keyword-download-',suffix='.lka',dir=root)
            try:
                hashed, copied = hashlib.sha256(),0
                deadline = monotonic()+300
                write_status(root,'downloading',total=size)
                request = Request(DOWNLOAD_URL,headers={'Accept':'application/octet-stream',
                                                       'User-Agent':'LumaSmartHub-Keyword/1'})
                with os.fdopen(descriptor,'wb') as output:
                    with opener.open(request,timeout=30) as response:
                        final = urlsplit(response.geturl())
                        if (final.scheme!='https' or final.hostname not in REDIRECT_HOSTS
                                or final.username or final.password or final.port not in (None,443)):
                            raise KeywordAssetError('keyword_download_address_invalid')
                        declared = response.headers.get('Content-Length')
                        if declared is not None and (not declared.isdigit() or int(declared)!=size):
                            raise KeywordAssetError('keyword_download_size_invalid')
                        while True:
                            if monotonic()>deadline:
                                raise KeywordAssetError('keyword_download_timeout')
                            block = response.read(256*1024)
                            if not block:
                                break
                            copied += len(block)
                            if copied>size:
                                raise KeywordAssetError('keyword_download_size_invalid')
                            hashed.update(block); output.write(block)
                            if copied//(5*1024*1024)!=(copied-len(block))//(5*1024*1024):
                                write_status(root,'downloading',downloaded=copied,total=size)
                    output.flush(); os.fsync(output.fileno())
                if copied!=size or (published_digest and hashed.hexdigest()!=published_digest[7:]):
                    raise KeywordAssetError('keyword_download_checksum_invalid')
                write_status(root,'verifying',downloaded=copied,total=size)
                return installer(Path(temporary),root=root,public_key=public_key,
                                 replace_existing=replace_existing)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
    except KeywordAssetError as error:
        # Do not overwrite another in-progress job's status on lock failure.
        if str(error)!='keyword_asset_busy':
            _record_fetch_failure(root,str(error))
        raise
    except (OSError,ValueError,TypeError,KeyError,URLError,HTTPError):
        _record_fetch_failure(root,'keyword_download_failed')
        raise KeywordAssetError('keyword_download_failed') from None
