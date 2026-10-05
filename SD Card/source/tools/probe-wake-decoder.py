"""Synthetic, real-Vosk smoke check; not a room/accent false-wake benchmark.

Run in Linux with espeak-ng and the installed Luma voice extra. Audio stays in
a TemporaryDirectory and is never uploaded. Optional model path is argv[1].
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
model = Model(sys.argv[1])
phrases = [
    'Hey Luma', 'Hey Luma what time is it', 'Hey Luma good morning',
    'Hey Luma start a timer for five minutes',
    'What time is it', 'Good morning everyone', 'Hey Laura what time is it',
    'Hey Lou good morning', 'The room is brighter today',
    'I told my friend hey Luma yesterday',
    'Can you say hey Luma for me', 'Okay let us move on to the next slide',
]
with tempfile.TemporaryDirectory(prefix='luma-wake-smoke-') as directory:
    for phrase in phrases:
        path = Path(directory) / 'sample.wav'
        subprocess.run(['espeak-ng', '-v', 'en-us', '-s', '145', '-w', str(path), phrase], check=True)
        with wave.open(str(path)) as wav:
            assert wav.getsampwidth() == 2 and wav.getnchannels() == 1
            source_rate = wav.getframerate()
            data = wav.readframes(wav.getnframes())
        samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
        # Linear resampling only for the disposable synthetic probe.
        output = []
        for i in range(int(len(samples) * 16000 / source_rate)):
            pos = i * source_rate / 16000
            lo = int(pos)
            fraction = pos - lo
            output.append(round(samples[lo] * (1 - fraction) + samples[min(lo + 1, len(samples) - 1)] * fraction))
        pcm = struct.pack('<' + 'h' * len(output), *output) + bytes(32000)
        recognizer = KaldiRecognizer(model, 16000)
        recognizer.SetWords(True)
        parts = []
        for offset in range(0, len(pcm), 8000):
            if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
                parts.append(json.loads(recognizer.Result()))
        parts.append(json.loads(recognizer.FinalResult()))
        print(json.dumps({'input': phrase, 'results': parts}))
