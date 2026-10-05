#!/usr/bin/env python3
"""Replay a position guard against digest-matched public corpus/model evidence.

No new model inference: this is post-filter research, NOT a fresh holdout.
Preserve the original raw false detections; oversized clips are reported as
invalid, not passed negatives. No audio/transcripts are extracted or saved.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import tarfile

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/src'))
from luma.keyword_gate import keyword_near_sound_start
from luma.keyword_wake import KeywordEvidence, KeywordWakeError, MAX_NAME_PHONE_GAP_SECONDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    args = parser.parse_args()
    if args.report.stat().st_size > 10*1024*1024:
        raise ValueError('Report too large.')
    report = json.loads(args.report.read_text())
    if report.get('kind') != 'synthetic-wake-research-not-hardware-qualification':
        raise ValueError('Unexpected report kind.')
    with args.archive.open('rb') as source:
        if hashlib.file_digest(source,'sha256').hexdigest() != report['corpus']['sha256']:
            raise ValueError('Corpus digest mismatch.')
    rows = {row['sample']:row for row in report['samples']}
    if len(rows) != len(report['samples']) or not 0<len(rows)<=3000:
        raise ValueError('Invalid or duplicate report sample.')
    seen = set()
    passed = invalid = accepted = raw_hits = 0
    detections = []
    with tarfile.open(args.archive,'r|gz') as corpus:
        for member in corpus:
            if not member.isfile() or not member.name.endswith('.flac'):
                continue
            if not re.fullmatch(r'LibriSpeech/dev-clean/\d+/\d+/\d+-\d+-\d+\.flac',member.name):
                raise ValueError('Unexpected corpus name.')
            key = 'librispeech-dev-clean/'+Path(member.name).stem
            if key not in rows:
                continue
            if key in seen or not 0<member.size<2*1024*1024:
                raise ValueError('Invalid corpus member.')
            seen.add(key)
            row = rows[key]
            if row['expected'] is not False:
                raise ValueError('Expected public-speech negative.')
            with sf.SoundFile(io.BytesIO(corpus.extractfile(member).read())) as audio:
                if audio.channels != 1 or audio.samplerate != 16000 or len(audio)>45*16000:
                    raise ValueError('Invalid public PCM format.')
                original = audio.read(dtype='float32')
            raw = np.clip(np.rint(original*32768),-32768,32767).astype('<i2').tobytes()
            canonical = np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
            if hashlib.sha256(canonical.tobytes()).hexdigest() != row['pcm_sha256']:
                raise ValueError('Report PCM digest mismatch.')
            targets = [hit['timestamps'] for hit in row['hits'] if hit['keyword']=='HEY_LUMA'
                       and len(hit['timestamps'])==6 and all(b-a<=MAX_NAME_PHONE_GAP_SECONDS
                           for a,b in zip(hit['timestamps'][2:],hit['timestamps'][3:]))]
            first = min(times[0] for times in targets) if targets else None
            raw_hits += bool(row['detected'])
            try:
                hit = keyword_near_sound_start(KeywordEvidence(first is not None,first),
                    [raw[offset:offset+8000] for offset in range(0,len(raw),8000)])
                passed += 1
                accepted += hit
                if row['detected']:
                    detections.append({'sample':key,'raw_detected':True,'gate_detected':hit})
            except KeywordWakeError as error:
                invalid += 1
                if row['detected']:
                    detections.append({'sample':key,'raw_detected':True,'gate_error':str(error)})
    if seen != set(rows):
        raise ValueError('Corpus did not cover report evidence.')
    print(json.dumps({'kind':'post-filter-replay-not-fresh-holdout',
                      'samples':len(seen),'valid_negatives':passed,'invalid_clips':invalid,
                      'raw_negative_hits':raw_hits,'gate_negative_hits':accepted,
                      'raw_detection_results':detections},sort_keys=True))


if __name__ == '__main__':
    main()
