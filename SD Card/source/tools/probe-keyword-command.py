#!/usr/bin/env python3
"""Dry-run actual acoustic worker + Vosk timing + existing command safeguards.

Digest-pinned, mono s16 synthetic WAVs only. No microphone/network, API call,
command execution or owner/room/latency acceptance claim. Reports omit words;
an explicit synthetic-only debug flag prints selected word timings to stderr.
"""
from array import array
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from time import monotonic
import wave

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend/src'))
from luma.keyword_process import IsolatedKeywordVerifier
from luma.voice import WakeGate, command_grammar, parse_local_command
from luma.voice_agent import accept_acoustic_utterance, select_command
from luma.voice_wake import WakeAudioBuffer


def signature(text):
    command = parse_local_command(text) if text else None
    return (command.name.value,command.value) if command else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interpreter',type=Path,required=True)
    parser.add_argument('--keyword-model',type=Path,required=True)
    parser.add_argument('--vosk-model',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--only-synthetic',action='append',default=[],
                        help='Limit inference to explicit manifest sample IDs; labels remain synthetic-only')
    parser.add_argument('--debug-synthetic',action='append',default=[],
                        help='Print word timings to stderr only for explicit digest-pinned synthetic sample IDs')
    args = parser.parse_args()
    from vosk import Model,KaldiRecognizer,SetLogLevel
    SetLogLevel(-1)
    model = Model(str(args.vosk_model))
    grammar = json.dumps(command_grammar())
    fixed = lambda: KaldiRecognizer(model,16000,grammar)
    free = lambda: KaldiRecognizer(model,16000)
    manifest_path = args.cache/'synthetic.json'
    if manifest_path.stat().st_size>65536:
        raise ValueError('Invalid synthetic manifest size.')
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest['files'],dict) or not 1<=len(manifest['files'])<=1000:
        raise ValueError('Invalid synthetic file count.')
    if not set(args.only_synthetic).issubset(manifest['files']) or not set(args.debug_synthetic).issubset(manifest['files']):
        raise ValueError('Unknown synthetic sample ID.')
    verifier = IsolatedKeywordVerifier(args.interpreter,args.keyword_model)
    rows = []
    worker_peak_rss_kib = None
    warm_ms = None
    try:
        started = monotonic()
        verifier.prepare()  # match production: warm before processing capture
        warm_ms = round((monotonic()-started)*1000,2)
        for name,digest in sorted(manifest['files'].items()):
            if args.only_synthetic and name not in args.only_synthetic:
                continue
            match = re.fullmatch(r'kristin-[0-9.]+-(positive|negative)-([0-9]+)\.wav',name)
            if not match:
                raise ValueError('Invalid synthetic file name.')
            path = args.cache/name
            if path.is_symlink() or not 0<path.stat().st_size<1024*1024:
                raise ValueError('Invalid synthetic file size.')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('Synthetic digest mismatch.')
            with wave.open(str(path)) as audio:
                rate = audio.getframerate()
                if (audio.getnchannels()!=1 or audio.getsampwidth()!=2
                        or rate not in (16000,22050,24000,44100,48000)
                        or not 0<audio.getnframes()<=9*rate):
                    raise ValueError('Invalid synthetic WAV format.')
                pcm = audio.readframes(audio.getnframes())
            if rate!=16000:
                original = array('h',pcm)
                if sys.byteorder!='little': original.byteswap()
                canonical = array('h')
                for index in range(int(len(original)*16000/rate)):
                    position = index*rate/16000
                    left = int(position); right = min(left+1,len(original)-1)
                    canonical.append(max(-32768,min(32767,round(original[left]+
                        (original[right]-original[left])*(position-left)))))
                if sys.byteorder!='little': canonical.byteswap()
                pcm = canonical.tobytes()
            positive = match[1]=='positive'
            reference = manifest['specification']['positives' if positive else 'negatives'][int(match[2])]
            expected = signature(reference.casefold().split('hey luma',1)[-1].strip()) if positive else None
            buffered = WakeAudioBuffer()
            for offset in range(0,len(pcm),8000): buffered.append(pcm[offset:offset+8000])
            if name in args.debug_synthetic:
                from dataclasses import asdict
                from luma.keyword_command import timed_transcript
                evidence = verifier.verify(buffered)
                print(json.dumps({'synthetic_sample':name,'evidence':asdict(evidence),
                    'fixed':asdict(timed_transcript(fixed,buffered)),
                    'free':asdict(timed_transcript(free,buffered))}),file=sys.stderr)
            errors = []
            gate = WakeGate()
            started = monotonic()
            accepted, varied, discard = accept_acoustic_utterance('',buffered,fixed,free,
                gate,100,verifier,report_error=errors.append)
            chosen, selection = (select_command(accepted,varied or '',gate.phrase)
                if accepted is not None else (None,''))
            actual = signature(chosen)
            elapsed_ms = round((monotonic()-started)*1000,2)
            if verifier.process is not None:
                try:
                    # Only this owned research child; no command line or other
                    # process data is read. Linux host RSS is NOT Pi memory.
                    with open(f'/proc/{verifier.process.pid}/status') as status:
                        resident = re.search(r'^VmRSS:\s+(\d+) kB$',status.read(4096),re.M)
                    if resident:
                        worker_peak_rss_kib = max(worker_peak_rss_kib or 0,int(resident[1]))
                except OSError:
                    pass
            wake_only = positive and not reference.casefold().split('hey luma',1)[-1].strip()
            rows.append({'sample':name,'positive':positive,'command_expected':expected is not None,
                'pcm_sha256':hashlib.sha256(pcm).hexdigest(),
                'wake_accepted':accepted is not None,'discard':discard,'selection':selection,
                'pipeline_ms':elapsed_ms,
                'intent_matched':actual==expected,'command_selected':actual is not None,
                'wake_only_window_correct':gate.until==107 if wake_only else None,
                'errors':errors})
    finally:
        verifier.close()
    print(json.dumps({'kind':'actual-worker-timed-asr-dry-run-not-hardware',
        'worker_warm_ms':warm_ms,'worker_observed_peak_rss_kib':worker_peak_rss_kib,
        'performance_scope':'owned isolated worker on research host, not Pi latency/memory; pipeline includes timed ASR and selection',
        'positive_total':sum(row['positive'] for row in rows),
        'positive_wakes':sum(row['positive'] and row['wake_accepted'] for row in rows),
        'negative_wakes':sum(not row['positive'] and row['wake_accepted'] for row in rows),
        'expected_commands':sum(row['command_expected'] for row in rows),
        'matched_commands':sum(row['command_expected'] and row['intent_matched'] for row in rows),
        'unexpected_negative_commands':sum(not row['positive'] and row['command_selected'] for row in rows),
        'samples':rows},sort_keys=True))


if __name__=='__main__': main()
