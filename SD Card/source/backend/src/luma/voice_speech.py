"""Warm offline Piper replies with explicit user-session playback diagnostics."""
from __future__ import annotations

import io
import json
import math
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
SPEAKER_SINK = "luma_speaker"


class VoicePlaybackError(RuntimeError):
    """A fixed, non-private reason suitable for the local Voice settings page."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def pulse_playback_environment() -> dict[str, str]:
    """System API and user voice service must reach the same PipeWire socket.

    A system service running as `luma` does not inherit the graphical user's
    XDG_RUNTIME_DIR. Never fall through to an arbitrary default audio server.
    """
    env = dict(os.environ)
    if sys.platform == "linux":
        runtime = Path(f"/run/user/{os.getuid()}")
        socket = runtime / "pulse/native"
        if not socket.is_socket():
            raise VoicePlaybackError("audio_session_unavailable")
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env["PULSE_SERVER"] = f"unix:{socket}"
    env["PULSE_SINK"] = SPEAKER_SINK
    return env


def _speaker_routes(env: dict[str, str]) -> list[str]:
    """Prefer Luma's echo-cancel sink; allow only the selected local ALSA fallback."""
    try:
        result = subprocess.run(["pactl", "list", "short", "sinks"], check=True,
                                capture_output=True, text=True, timeout=6, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VoicePlaybackError("speaker_route_unavailable") from exc
    names = {fields[1] for line in result.stdout.splitlines()
             if len(fields := line.split()) >= 2}
    routes = [SPEAKER_SINK] if SPEAKER_SINK in names else []
    try:
        default = subprocess.run(["pactl", "get-default-sink"], check=True,
                                 capture_output=True, text=True, timeout=6, env=env).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        default = ""
    # Never redirect speech to a paired phone, Bluetooth headset, dummy sink,
    # or an arbitrary first sink. Device Setup owns the local ALSA selection.
    if default in names and default.startswith("alsa_output.") and default not in routes:
        routes.append(default)
    if not routes:
        raise VoicePlaybackError("speaker_route_unavailable")
    return routes


def _play_pcm(pcm: bytes, env: dict[str, str]) -> str:
    routes = _speaker_routes(env)
    for sink in routes:
        try:
            # pacat is the raw-PCM player; the device is explicit on each try.
            subprocess.run(["pacat", "--playback", f"--device={sink}", "--raw", "--format=s16le",
                            "--rate=22050", "--channels=1"], input=pcm, check=True,
                           timeout=90, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, env={**env, "PULSE_SINK": sink})
            return "luma_speaker" if sink == SPEAKER_SINK else "system_speaker"
        except (OSError, subprocess.SubprocessError):
            continue
    raise VoicePlaybackError("speaker_playback_failed")


def play_test_tone() -> str:
    """A bounded non-speech chime to distinguish the speaker path from Piper."""
    env = pulse_playback_environment()
    pcm = bytearray()
    count = int(22050 * .65)
    for index in range(count):
        envelope = min(1.0, index / 440, (count - index - 1) / 440)
        frequency = 523.25 if index < count // 2 else 659.25
        value = int(32767 * .16 * envelope * math.sin(2 * math.pi * frequency * index / 22050))
        pcm.extend(struct.pack("<h", value))
    return _play_pcm(bytes(pcm), env)


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
        self.last_error: str | None = None
        self.last_route: str | None = None

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
        env = pulse_playback_environment()
        try:
            process = self.process or self._start()
        except (OSError, EOFError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
            raise VoicePlaybackError("piper_start_failed") from exc
        try:
            if process.poll() is not None or process.stdin is None:
                raise EOFError("offline voice worker stopped")
            process.stdin.write(json.dumps({"text": reply}, ensure_ascii=True).encode("ascii") + b"\n")
            process.stdin.flush()
            deadline = monotonic() + 60
            size = struct.unpack(">I", _read_exact(process, 4, deadline))[0]
            if not 44 < size <= MAX_WAV:
                raise ValueError("offline voice worker returned no audio")
            output = _read_exact(process, size, deadline)
        except (OSError, EOFError, ValueError, TimeoutError, subprocess.SubprocessError) as exc:
            raise VoicePlaybackError("piper_synthesis_failed") from exc
        try:
            pcm = wav_to_pcm(output)
        except (ValueError, wave.Error) as exc:
            raise VoicePlaybackError("piper_audio_invalid") from exc
        self.last_route = _play_pcm(pcm, env)

    def speak(self, reply: str) -> str:
        # The API already bounds answers; guard the worker regardless.
        reply = reply[:500]
        if not reply:
            return "silent"
        self.last_error = None
        self.last_route = None
        if sys.platform == "linux" and ready(self.root) and monotonic() >= self.retry_after:
            try:
                self._piper(reply)
                return "piper"
            except VoicePlaybackError as exc:
                self.last_error = exc.code
                self.close()
                self.retry_after = monotonic() + 120
        elif not ready(self.root):
            self.last_error = "voice_asset_unavailable"
        else:
            self.last_error = "piper_retry_wait"
        subprocess.run(["espeak-ng", "--stdin", "-s", "155"], input=reply, text=True,
                       check=True, timeout=45, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
        return "fallback"


def play_preview(root: Path = ASSET_ROOT) -> str:
    """Owner-local fixed phrase; never falls back and never reads private data."""
    if not ready(root):
        raise ValueError("offline voice not installed")
    speaker = OfflineSpeaker(root)
    try:
        speaker._piper("Hello, I'm Luma. It's good to see you.")
        return speaker.last_route or "unknown"
    finally:
        speaker.close()
