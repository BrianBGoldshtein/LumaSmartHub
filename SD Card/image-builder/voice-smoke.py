"""Synthetic offline recognition smoke check; NOT a microphone acceptance test."""
import io
import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source/backend/src"))
from luma.voice import command_grammar

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
model = Model(sys.argv[1])
phrases = ["hey luma set volume to fifty", "hey luma change theme to arcade", "hey luma good morning"]
for phrase in phrases:
    audio = subprocess.run(["espeak-ng", "--stdout", "-v", "en-us", "-s", "145", "--stdin"], input=phrase.encode(), capture_output=True, check=True).stdout
    with wave.open(io.BytesIO(audio)) as wav:
        recognizer = KaldiRecognizer(model, wav.getframerate(), json.dumps(command_grammar()))
        parts = []
        while chunk := wav.readframes(4000):
            if recognizer.AcceptWaveform(chunk):
                parts.append(json.loads(recognizer.Result()).get("text", ""))
        parts.append(json.loads(recognizer.FinalResult()).get("text", ""))
    print(json.dumps({"synthetic_phrase": phrase, "recognized": " ".join(filter(None, parts))}))
