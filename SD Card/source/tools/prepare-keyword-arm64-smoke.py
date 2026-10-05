#!/usr/bin/env python3
"""Prepare isolated ARM64 user-space for QEMU keyword smoke, not a Pi install.

Official Debian packages are hash-checked and extracted, never installed and
no maintainer scripts are run. Pinned PyPI wheels are unpacked in this folder.
No root mount, host package change, SD access, microphone or credentials.
"""
import argparse
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
from urllib.request import urlopen
import zipfile


PACKAGES = ('python3.13-minimal','libpython3.13-minimal','libpython3.13-stdlib',
            'libc6','libgcc-s1','libstdc++6','libgomp1','libexpat1','zlib1g',
            'libbz2-1.0','liblzma5','libssl3t64','libffi8','libreadline8t64',
            'libtinfo6','libsqlite3-0','libuuid1',
            'python3.13-venv','python3-pip-whl','python3-setuptools-whl')
WHEELS = {
 'numpy-2.5.3-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl':
 ('numpy','2.5.3','c76d5dde9f445058f83d0c02af00557a4db91de9a9a57c0df87d1535001d654b'),
 'sherpa_onnx-1.13.8-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl':
 ('sherpa-onnx','1.13.8','916ec38242e779ee3a99f7b161bd1bf3b02a7fad34cb073d091021c0469e0b58'),
 'sherpa_onnx_core-1.13.8-py3-none-manylinux2014_aarch64.whl':
 ('sherpa-onnx-core','1.13.8','a51a03d55c376c32e15dd63ea852236042ba91a5cd73e253bbf7cf21f6582ba9'),
}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def download(url, path, *, expected=None, limit=32*1024*1024):
    if path.exists():
        if expected and digest(path)!=expected:
            raise ValueError('Existing download does not match pin; preserved for inspection.')
        return
    temporary=path.with_suffix(path.suffix+'.partial')
    count=0
    with urlopen(url,timeout=60) as response, temporary.open('wb') as output:
        while block:=response.read(256*1024):
            count+=len(block)
            if count>limit:
                raise ValueError('Download exceeds research size limit.')
            output.write(block)
    if expected and digest(temporary)!=expected:
        raise ValueError('Download digest mismatch; partial file preserved.')
    temporary.replace(path)


def package_records(index):
    result={}
    record={}
    with lzma.open(index,'rt',encoding='utf-8') as source:
        for line in source:
            if line.strip():
                if not line.startswith(' '):
                    key,_,value=line.partition(':')
                    record[key]=value.strip()
            else:
                name=record.get('Package')
                if name in PACKAGES and record.get('Architecture') in {'arm64','all'}:
                    result[name]={key:record[key] for key in ('Version','Filename','SHA256','Size')}
                record={}
    if set(result)!=set(PACKAGES):
        raise ValueError('Debian index is missing a required ARM64 package.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--wheels',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    if output==Path(output.anchor) or output==Path.home():
        parser.error('Use a dedicated empty research directory, not a broad root.')
    if output.exists() and not (output/'prepare.json').is_file():
        parser.error('Existing output has no preparation marker; it will not be changed.')
    output.mkdir(parents=True,exist_ok=True)
    marker=output/'prepare.json'
    if not marker.exists():
        marker.write_text(json.dumps({'kind':'isolated-arm64-keyword-smoke','stage':'preparing'}))
    else:
        if json.loads(marker.read_text()).get('kind')!='isolated-arm64-keyword-smoke':
            parser.error('Existing output belongs to another workflow.')
    cache=output/'downloads'
    cache.mkdir(exist_ok=True)
    index=cache/'Packages.xz'
    download('https://deb.debian.org/debian/dists/trixie/main/binary-arm64/Packages.xz',index)
    records=package_records(index)
    root=output/'root'
    site=output/'site'
    root.mkdir(exist_ok=True)
    site.mkdir(exist_ok=True)
    for name in PACKAGES:
        record=records[name]
        filename=PurePosixPath(record['Filename'])
        if filename.is_absolute() or '..' in filename.parts or not str(filename).startswith('pool/'):
            raise ValueError('Unexpected Debian package path.')
        package=cache/filename.name
        download('https://deb.debian.org/debian/'+str(filename),package,expected=record['SHA256'])
        subprocess.run(['dpkg-deb','--extract',str(package),str(root)],check=True,timeout=30)
    # Debian's merged-/usr root links normally come from base-files. This
    # minimal test root only needs the library alias for the ARM64 loader.
    alias=root/'lib'
    if not alias.exists() and not alias.is_symlink():
        alias.symlink_to('usr/lib',target_is_directory=True)
    elif not alias.is_symlink() or alias.readlink()!=Path('usr/lib'):
        raise ValueError('Unexpected research-root library alias; preserved.')
    for name,(project,version,pin) in WHEELS.items():
        wheel=args.wheels/name
        if digest(wheel)!=pin:
            raise ValueError('Local wheel does not match its source pin.')
        with urlopen(f'https://pypi.org/pypi/{project}/{version}/json',timeout=30) as response:
            metadata=json.load(response)
        published=next((row for row in metadata['urls'] if row['filename']==name),None)
        if not published or published['digests']['sha256']!=pin:
            raise ValueError('Wheel pin differs from the official PyPI record.')
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                path=PurePosixPath(member.filename)
                if (path.is_absolute() or '..' in path.parts
                        or stat.S_ISLNK(member.external_attr>>16)):
                    raise ValueError('Unexpected wheel member path or symlink.')
            archive.extractall(site)
    result={'kind':'isolated-arm64-keyword-smoke','stage':'prepared',
            'debian_index_sha256':digest(index),'packages':records,
            'wheels':{name:pin for name,(_,_,pin) in WHEELS.items()},
            'qemu':shutil.which('qemu-aarch64'),'root':str(root),'site':str(site)}
    marker.write_text(json.dumps(result,sort_keys=True,indent=2))
    print(json.dumps({'stage':'prepared','root':str(root),'site':str(site)}))


if __name__=='__main__':
    main()
