#!/usr/bin/env python3
"""Fixed-phrase worker probe: no microphone, speaker, user words or audio files.

Native or emulated host measurements do not prove latency on the owner's Pi.
Run with the application interpreter and select the pinned Piper interpreter.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/src'))
from luma.voice_speech import _read_exact, _stream_frames
from luma.voice_asset import _check_worker_smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    args = parser.parse_args()
    worker = Path(__file__).resolve().parents[1] / 'backend/src/luma/piper_worker.py'
    began = monotonic()
    process = subprocess.Popen([str(args.python), str(worker), str(args.model)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, bufsize=0)
    try:
        assert _read_exact(process, 6, monotonic()+45) == b'READY\n'
        startup_ms = round((monotonic()-began)*1000, 1)
        results = []
        for index, text in enumerate(('It is twelve thirty.', 'It is twelve thirty.',
                                     'Good morning. It is twelve thirty. Enjoy your day.')):
            began = monotonic()
            process.stdin.write(json.dumps({'text':text, 'stream':True}).encode()+b'\n')
            process.stdin.flush()
            first_ms, count, size = None, 0, 0
            for frame in _stream_frames(process, monotonic()+60):
                if first_ms is None:
                    first_ms = round((monotonic()-began)*1000,1)
                count += 1
                size += len(frame)
            results.append({'trial':index+1, 'first_pcm_ms':first_ms,
                            'generation_total_ms':round((monotonic()-began)*1000,1),
                            'frames':count, 'audio_seconds':round(size/44100,2)})
        # Preserve the pre-0.2.11 signed-asset installer WAV smoke contract.
        process.stdin.write(b'{"text":"Hello, I am Luma."}\n')
        process.stdin.flush()
        header = _read_exact(process, 4, monotonic()+60)
        import struct
        size = struct.unpack('>I',header)[0]
        if not 44 < size <= 10*1024*1024:
            raise ValueError('invalid legacy WAV size')
        _check_worker_smoke(b'READY\n'+header+_read_exact(process,size,monotonic()+60))
        print(json.dumps({'scope':'Selected interpreter on this host; not speaker audibility or owner-Pi latency',
                          'startup_ms':startup_ms,'trials':results,'legacy_wav_smoke':'passed'},indent=2))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        for pipe in (process.stdin,process.stdout):
            if pipe:
                pipe.close()


if __name__ == '__main__':
    main()
