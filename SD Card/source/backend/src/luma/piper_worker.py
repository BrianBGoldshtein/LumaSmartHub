"""Persistent Piper model worker; run only by the verified voice-asset venv.

Protocol on stdio: READY\n, then one JSON text line per request; each reply
is a 4-byte big-endian WAV length followed by in-memory WAV data. Zero length
means synthesis failed. Neither speech text nor audio is saved to a file.
"""
from __future__ import annotations

import io
import json
import struct
import sys
import wave

from piper import PiperVoice


MAX_TEXT = 500
MAX_WAV = 10 * 1024 * 1024


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    voice = PiperVoice.load(sys.argv[1])
    output = sys.stdout.buffer
    output.write(b"READY\n")
    output.flush()
    for raw in sys.stdin.buffer:
        if len(raw) > 4096:
            output.write(struct.pack(">I", 0)); output.flush()
            continue
        try:
            request = json.loads(raw)
            text = request.get("text")
            if not isinstance(text, str) or not 0 < len(text) <= MAX_TEXT or "\x00" in text:
                raise ValueError
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                voice.synthesize_wav(text, wav)
            data = buffer.getvalue()
            if not 44 < len(data) <= MAX_WAV:
                raise ValueError
            output.write(struct.pack(">I", len(data)))
            output.write(data)
        except (ValueError, TypeError, RuntimeError):
            output.write(struct.pack(">I", 0))
        output.flush()


if __name__ == "__main__":
    main()
