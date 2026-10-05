#!/usr/bin/env python3
"""Build the separate pinned ARM64 wake asset with the owner's OFFLINE key.

No downloads, installation or publishing. All payloads and notices must match
the application's exact source pins. Private keys must stay outside delivery
and Git trees, and are never printed or bundled. Output is created exclusively.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/src'))
from luma import keyword_asset as policy


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def _entry(name):
    info = zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
    info.create_system = 3
    info.external_attr = 0o100600 << 16
    info.compress_type = zipfile.ZIP_STORED
    return info


def build(root:Path, model:Path, wheels:Path, model_card:Path, license_text:Path,
          key_path:Path, output:Path):
    root = root.resolve(strict=True)
    key_path = key_path.resolve(strict=True)
    output = output.absolute()
    delivery_boundary = root.parent if (root.parent/'.git').exists() else root
    if (output.exists() or output.is_symlink()
            or output.resolve(strict=False).is_relative_to(delivery_boundary)
            or key_path.is_relative_to(delivery_boundary)):
        raise ValueError('Keep the key/output outside the delivery and repository trees; choose a new output.')
    if os.name=='posix' and stat.S_IMODE(key_path.stat().st_mode)&0o077:
        raise ValueError('Offline key permissions must be private (0600).')
    key = serialization.load_pem_private_key(key_path.read_bytes(),password=None)
    public = serialization.load_pem_public_key((root/'source/system/luma-update-ed25519.pub').read_bytes())
    if (not isinstance(key,Ed25519PrivateKey) or not isinstance(public,Ed25519PublicKey)
            or key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
               != public.public_bytes(Encoding.Raw,PublicFormat.Raw)):
        raise ValueError('Offline key does not match the image-pinned Ed25519 public key.')
    paths = {}
    for name, record in policy.PINNED_FILES.items():
        if name=='NOTICE.txt':
            continue
        if name.startswith('model/'):
            source = model/name.split('/')[1]
        elif name.startswith('wheels/'):
            source = wheels/name.split('/')[1]
        elif name=='licenses/model-card.txt':
            source = model_card
        elif name=='licenses/Apache-2.0.txt':
            source = license_text
        else:
            raise ValueError('Unsupported source pin.')
        if (source.is_symlink() or not source.is_file()
                or source.stat().st_size!=record['size'] or digest(source)!=record['sha256']):
            raise ValueError('A vendor payload/license differs from its source pin.')
        paths[name] = source
    raw = policy.canonical(policy.expected_manifest())
    if len(raw)>policy.MAX_MANIFEST_BYTES:
        raise ValueError('Manifest too large.')
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_STORED) as archive:
        for name,data in (('manifest.json',raw),('manifest.sig',key.sign(raw)),('NOTICE.txt',policy.NOTICE)):
            archive.writestr(_entry(name),data)
        for name,path in sorted(paths.items()):
            hashed, copied = hashlib.sha256(),0
            with path.open('rb') as source, archive.open(_entry(name),'w') as target:
                for block in iter(lambda:source.read(256*1024),b''):
                    copied += len(block)
                    if copied>policy.PINNED_FILES[name]['size']:
                        raise ValueError('Vendor input changed while building.')
                    hashed.update(block); target.write(block)
            if copied!=policy.PINNED_FILES[name]['size'] or hashed.hexdigest()!=policy.PINNED_FILES[name]['sha256']:
                raise ValueError('Vendor input changed while building.')
    if output.stat().st_size>policy.MAX_ASSET_BYTES:
        raise ValueError('Asset exceeds install limit.')
    return {'version':policy.ASSET_VERSION,'name':policy.ASSET_NAME,
            'bytes':output.stat().st_size,'sha256':digest(output),'files':len(policy.PINNED_FILES)}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path,help='SD Card source/delivery tree')
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--wheels',type=Path,required=True)
    parser.add_argument('--model-card',type=Path,required=True)
    parser.add_argument('--license',dest='license_text',type=Path,required=True)
    parser.add_argument('--key',dest='key_path',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(**vars(args)),sort_keys=True))
    except (OSError,ValueError,TypeError,KeyError):
        parser.error('Keyword asset build failed its local key, pin or output checks. No asset was published.')
