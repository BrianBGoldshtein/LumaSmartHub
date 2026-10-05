#!/usr/bin/env python3
"""Exercise signed install through isolated ARM64 QEMU, not the Pi or host OS.

The production installer and its normal timeouts/protocol are unchanged. Only
the runtime-support check and subprocess runner select the dedicated ARM64
lab. Successful emulation is NOT Pi latency, mic, speaker or wake acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/src'))
from luma import keyword_asset as asset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--lab-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('Choose a new isolated qualification directory.')
    lab_root = args.lab_root.resolve(strict=True)
    qemu = shutil.which('qemu-aarch64')
    base = lab_root/'usr/bin/python3.13'
    if not qemu or not base.is_file():
        parser.error('Prepared ARM64 root and qemu-aarch64 are required.')
    output.mkdir(mode=0o700)
    sentinel = output/'saved-state.txt'
    sentinel.write_bytes(b'qualification-only saved state sentinel')
    calls = []
    environment = {key:value for key,value in os.environ.items()
                   if key not in {'PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'}}
    environment['QEMU_LD_PREFIX'] = str(lab_root)
    def run(command,**kwargs):
        executable = base if command[1:3]==['-m','venv'] else Path(command[0])
        phase = 'venv' if command[1:3]==['-m','venv'] else 'pip' if 'pip' in command else 'worker'
        started = monotonic()
        row = {'phase':phase,'final_path':asset.KEYWORD_ID in str(executable)}
        calls.append(row)
        try:
            result = subprocess.run([qemu,'-L',str(lab_root),'-E',
                'LD_LIBRARY_PATH='+str(lab_root/'usr/lib/aarch64-linux-gnu'),
                '-E','QEMU_LD_PREFIX='+str(lab_root),
                str(executable),*command[1:]],env=environment,**kwargs)
            row['returncode'] = result.returncode
            return result
        except subprocess.CalledProcessError as error:
            row['returncode'] = error.returncode
            raise
        finally:
            row['elapsed_ms'] = round((monotonic()-started)*1000,2)
    report = {'kind':'isolated-arm64-install-not-hardware-acceptance','calls':calls}
    try:
        with patch.object(asset,'_runtime_supported',return_value=True):
            result = asset.install_asset(args.bundle,root=output/'keyword-assets',
                public_key=args.public_key,run=run)
        report.update(result=result,ready=asset.ready(output/'keyword-assets',args.public_key))
    except asset.KeywordAssetError as error:
        report.update(error=str(error),ready=asset.ready(output/'keyword-assets',args.public_key))
    report['saved_state_preserved'] = sentinel.read_bytes()==b'qualification-only saved state sentinel'
    print(json.dumps(report,sort_keys=True))
    if report.get('error') or not report.get('ready') or not report['saved_state_preserved']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
