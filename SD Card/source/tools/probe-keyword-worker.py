#!/usr/bin/env python3
"""Replay digest-pinned synthetic WAVs through the actual isolated worker.

No microphone, account, commands, recording or network access. Desktop timing
does not prove Pi timing. Mono signed-16 synthetic WAVs <=9s are canonicalized
to 16kHz exactly as in the companion research probe, never device capture.
"""
from array import array
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/src'))
from luma.keyword_process import IsolatedKeywordVerifier
from luma.keyword_wake import KeywordWakeError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpreter', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.cache/'synthetic.json'
    if manifest_path.stat().st_size > 65536:
        raise ValueError('Invalid synthetic manifest size.')
    manifest = json.loads(manifest_path.read_text())
    files = manifest['files']
    if not isinstance(files, dict) or not 1 <= len(files) <= 1000:
        raise ValueError('Invalid synthetic manifest files.')
    verifier = IsolatedKeywordVerifier(args.interpreter, args.model)
    rows = []
    try:
        for name, digest in sorted(files.items()):
            if Path(name).name != name or not name.endswith('.wav'):
                raise ValueError('Invalid synthetic file name.')
            path = args.cache/name
            if path.is_symlink() or not 0 < path.stat().st_size < 1024*1024:
                raise ValueError('Invalid synthetic file size.')
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('Synthetic digest mismatch.')
            with wave.open(str(path)) as audio:
                if (audio.getnchannels() != 1 or audio.getsampwidth() != 2
                        or audio.getframerate() not in (16000,22050,24000,44100,48000)
                        or not 0 < audio.getnframes() <= 9*audio.getframerate()):
                    raise ValueError('Unexpected synthetic PCM format.')
                rate = audio.getframerate()
                pcm = audio.readframes(audio.getnframes())
            if rate != 16000:
                original = array('h', pcm)
                if sys.byteorder != 'little':
                    original.byteswap()
                canonical = array('h')
                for index in range(int(len(original)*16000/rate)):
                    position = index*rate/16000
                    left = int(position)
                    right = min(left+1, len(original)-1)
                    value = round(original[left]+(original[right]-original[left])*(position-left))
                    canonical.append(max(-32768,min(32767,value)))
                if sys.byteorder != 'little':
                    canonical.byteswap()
                pcm = canonical.tobytes()
            started = monotonic()
            row = {'sample': name, 'expected': '-positive-' in name,
                   'pcm_sha256': hashlib.sha256(pcm).hexdigest()}
            try:
                result = verifier.verify([pcm[offset:offset+8000] for offset in range(0,len(pcm),8000)])
                row.update(detected=result.detected, first_token_seconds=result.first_token_seconds,
                           last_token_seconds=result.last_token_seconds)
            except KeywordWakeError as error:
                row['error'] = str(error)
            row['elapsed_ms'] = round((monotonic()-started)*1000, 2)
            rows.append(row)
    finally:
        verifier.close()
    print(json.dumps({'kind':'real-worker-synthetic-not-hardware-qualification',
                      'errors':sum('error' in row for row in rows),
                      'positive_hits':sum(row['expected'] and row.get('detected',False) for row in rows),
                      'negative_hits':sum(not row['expected'] and row.get('detected',False) for row in rows),
                      'samples':rows}, sort_keys=True))


if __name__ == '__main__':
    main()
