"""Persistent Piper model worker; run only by the verified voice-asset venv.

Protocol on stdio: READY\n, then one JSON text line per request. Legacy
requests return a 4-byte WAV length plus in-memory WAV (zero means failure).
stream=true returns bounded PCM frames with 4-byte lengths, zero terminates
and 0xffffffff reports failure. Neither text nor audio is saved to a file.
"""
from __future__ import annotations

import io
import json
import struct
import sys
import wave

MAX_TEXT = 500
MAX_WAV = 10 * 1024 * 1024
STREAM_ERROR = 0xffffffff


def load_voice(model: str):
    # Pi 4 has four cores shared with Chromium, ASR and the device bridge.
    # Bound ORT threads and disable idle spinning instead of letting each
    # native runtime occupy every core. Keep this in the isolated asset venv.
    import onnxruntime as ort
    from piper import PiperVoice
    from piper.config import PiperConfig

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    options.add_session_config_entry("session.inter_op.allow_spinning", "0")
    with open(model + ".json", encoding="utf-8") as config:
        return PiperVoice(config=PiperConfig.from_dict(json.load(config)),
                          session=ort.InferenceSession(model, sess_options=options,
                                                      providers=["CPUExecutionProvider"]))


def stream_audio(voice, text: str, output):
    """Bounded mono PCM frames; zero ends a reply, 0xffffffff rejects it.

    Piper produces sentence-sized chunks. Send each immediately so a longer
    answer starts playing while later sentences are still being synthesized.
    Legacy WAV requests below remain valid for the signed-asset smoke check.
    """
    total = 0
    try:
        for chunk in voice.synthesize(text):
            pcm = chunk.audio_int16_bytes
            if (chunk.sample_rate != 22050 or chunk.sample_width != 2
                    or chunk.sample_channels != 1 or not pcm or len(pcm) % 2):
                raise ValueError
            total += len(pcm)
            if total > 22050 * 90 * 2:
                raise ValueError
            for offset in range(0, len(pcm), 16384):
                frame = pcm[offset:offset + 16384]
                output.write(struct.pack(">I", len(frame)))
                output.write(frame)
                output.flush()
        if not total:
            raise ValueError
        output.write(struct.pack(">I", 0))
    except Exception:
        # Never emit a traceback or words into the protocol.
        output.write(struct.pack(">I", STREAM_ERROR))
    output.flush()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(2)
    output = sys.stdout.buffer
    # Fixed six-byte startup results keep private paths and library tracebacks
    # out of the local API while distinguishing repairable failure stages.
    try:
        from piper import PiperVoice
    except (ImportError, OSError):
        output.write(b"NOMOD\n"); output.flush()
        raise SystemExit(3) from None
    try:
        voice = load_voice(sys.argv[1])
        # The first phonemizer/inference call is also cold. Pay that cost
        # before READY, using a fixed phrase in RAM and never a speaker.
        for _ in voice.synthesize("Ready."):
            pass
    except MemoryError:
        output.write(b"MEMRY\n"); output.flush()
        raise SystemExit(4) from None
    except Exception:
        output.write(b"MODEL\n"); output.flush()
        raise SystemExit(5) from None
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
            if request.get("stream") is True:
                stream_audio(voice, text, output)
                continue
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
