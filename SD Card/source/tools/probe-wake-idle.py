#!/usr/bin/env python3
"""Check real Vosk endpoints after idle silence, without mic input or commands.

Run with the backend on PYTHONPATH and its pinned Vosk model as argv[1].
The synthetic phrase is disposable; this is not owner/accent qualification.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
from vosk import KaldiRecognizer, Model, SetLogLevel

from luma.voice import command_grammar
from luma.voice_wake import WakeAudioBuffer


def main():
    SetLogLevel(-1)
    model=Model(str(Path(sys.argv[1]).resolve(strict=True)))
    audio=subprocess.run(['espeak-ng','--stdout','-v','en-us','Hey Luma what time is it'],
                         check=True,capture_output=True,timeout=10).stdout
    with wave.open(io.BytesIO(audio)) as sample:
        pcm=np.frombuffer(sample.readframes(sample.getnframes()),dtype='<i2')
        rate=sample.getframerate()
    resampled=np.interp(np.arange(int(len(pcm)*16000/rate))*rate/16000,
                        np.arange(len(pcm)),pcm).astype('<i2').tobytes()+bytes(32000*3)
    results=[]
    for seconds in (0,5,15,60):
        decoder=KaldiRecognizer(model,16000,json.dumps(command_grammar('hey luma')))
        frames=WakeAudioBuffer()
        endpoints=[]
        combined=bytes(seconds*32000)+resampled
        for offset in range(0,len(combined),8000):
            frames.append(combined[offset:offset+8000])
            if decoder.AcceptWaveform(combined[offset:offset+8000]):
                endpoints.append({'at_seconds':offset/32000,
                                  'text':json.loads(decoder.Result()).get('text',''),
                                  'complete':frames.complete,'frames':len(frames)})
                frames=WakeAudioBuffer()
        results.append({'idle_seconds':seconds,'endpoints':endpoints})
    print(json.dumps({'kind':'real-decoder-idle-smoke-not-hardware-test','samples':results}))


if __name__=='__main__':
    main()
