"""Warm offline Piper replies with bounded espeak-ng fallback."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
from contextlib import suppress
from time import monotonic
import wave

from .voice_asset import ASSET_ROOT, MODEL, VOICE_ID, ready


MAX_WAV = 10 * 1024 * 1024


def wav_to_pcm(data: bytes) -> bytes:
    with wave.open(io.BytesIO(data), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 22050:
            raise ValueError("unexpected Piper output format")
        if wav.getnframes() > 22050 * 90:
            raise ValueError("Piper output is too long")
        return wav.readframes(wav.getnframes())


def _read_exact(process: subprocess.Popen, length: int, deadline: float) -> bytes:
    result = bytearray()
    descriptor = process.stdout.fileno()
    while len(result) < length:
        remaining = deadline - monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise TimeoutError("offline voice worker timed out")
        block = os.read(descriptor, min(length - len(result), 1024 * 1024))
        if not block:
            raise EOFError("offline voice worker stopped")
        result.extend(block)
    return bytes(result)


class OfflineSpeaker:
    def __init__(self, root: Path = ASSET_ROOT):
        self.root = root
        self.process: subprocess.Popen | None = None
        self.retry_after = 0.0

    def close(self) -> None:
        process = self.process
        self.process = None
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
            process.wait(timeout=2)
        except (OSError, subprocess.SubprocessError):
            with suppress(OSError):
                process.kill()
            with suppress(OSError, subprocess.SubprocessError):
                process.wait(timeout=2)

    def _start(self) -> subprocess.Popen:
        folder = self.root / VOICE_ID
        process = subprocess.Popen(
            [str(folder / "venv/bin/python"), str(Path(__file__).with_name("piper_worker.py")),
             str(folder / MODEL)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, close_fds=True)
        try:
            if _read_exact(process, 6, monotonic() + 45) != b"READY\n":
                raise ValueError("offline voice worker did not start")
        except Exception:
            process.kill()
            process.wait(timeout=2)
            raise
        self.process = process
        return process

    def _piper(self, reply: str) -> None:
        process = self.process or self._start()
        if process.poll() is not None or process.stdin is None:
            raise EOFError("offline voice worker stopped")
        process.stdin.write(json.dumps({"text": reply}, ensure_ascii=True).encode("ascii") + b"\n")
        process.stdin.flush()
        deadline = monotonic() + 60
        size = struct.unpack(">I", _read_exact(process, 4, deadline))[0]
        if not 44 < size <= MAX_WAV:
            raise ValueError("offline voice worker returned no audio")
        pcm = wav_to_pcm(_read_exact(process, size, deadline))
        subprocess.run(["paplay", "--raw", "--format=s16le", "--rate=22050", "--channels=1"],
                       input=pcm, check=True, timeout=90, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,
                       env={**os.environ, "PULSE_SINK": "luma_speaker"})

    def speak(self, reply: str) -> str:
        # The API already bounds answers; guard the worker regardless.
        reply = reply[:500]
        if not reply:
            return "silent"
        if sys.platform == "linux" and ready(self.root) and monotonic() >= self.retry_after:
            try:
                self._piper(reply)
                return "piper"
            except (OSError, EOFError, ValueError, wave.Error, TimeoutError, subprocess.SubprocessError):
                self.close()
                self.retry_after = monotonic() + 120
        subprocess.run(["espeak-ng", "--stdin", "-s", "155"], input=reply, text=True,
                       check=True, timeout=45, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return "fallback"


def play_preview(root: Path = ASSET_ROOT) -> None:
    """Owner-local fixed phrase; never falls back and never reads private data."""
    if not ready(root):
        raise ValueError("offline voice not installed")
    speaker = OfflineSpeaker(root)
    try:
        speaker._piper("Hello, I'm Luma. It's good to see you.")
    finally:
        speaker.close()
