#!/usr/bin/env python3
"""Verify/extract the real signed asset into a NEW private qualification folder.

No installing, publishing, hardware access, microphone or credentials. This
proves signature/layout/payload pins, not ARM64 execution or wake accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/src'))
from luma.keyword_asset import verify_and_extract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--public-key',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('Choose a new qualification directory; existing content is preserved.')
    output.mkdir(mode=0o700)
    started = monotonic()
    manifest = verify_and_extract(args.bundle,output,args.public_key)
    with args.bundle.open('rb') as source:
        digest = hashlib.file_digest(source,'sha256').hexdigest()
    print(json.dumps({'kind':'signed-payload-verification-not-runtime-or-hardware',
        'version':manifest['version'],'files':len(manifest['files']),
        'payload_bytes':sum(record['size'] for record in manifest['files'].values()),
        'bundle_sha256':digest,'elapsed_ms':round((monotonic()-started)*1000,2)},sort_keys=True))


if __name__=='__main__':
    main()
