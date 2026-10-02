"""Bounded raw capture from Luma's explicit PipeWire/PulseAudio source."""
from __future__ import annotations

import os
from pathlib import Path
import queue
import re
import subprocess
import sys
from threading import Thread
from time import monotonic


SAMPLE_RATE = 16_000
FRAME_SAMPLES = 4_000
FRAME_BYTES = FRAME_SAMPLES * 2  # mono signed 16-bit PCM
SOURCE_RE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,160}$")


class AudioCaptureError(RuntimeError):
    """A fixed audio startup/runtime failure suitable for local diagnostics."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def selected_source() -> str:
    """Use the configured echo-cancelled Pulse source, never an implicit ALSA default."""
    source = os.environ.get("LUMA_MIC_SOURCE") or "luma_mic"
    if not SOURCE_RE.fullmatch(source):
        raise AudioCaptureError("capture_source_invalid")
    return source


def capture_environment() -> dict[str, str]:
    """Bind capture to the appliance user's PipeWire session, not a login default."""
    env = dict(os.environ)
    env.pop("PULSE_SOURCE", None)  # --device below is authoritative.
    if sys.platform == "linux":
        runtime = Path(f"/run/user/{os.getuid()}")
        socket = runtime / "pulse/native"
        if not socket.is_socket():
            raise AudioCaptureError("capture_source_unavailable")
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env["PULSE_SERVER"] = f"unix:{socket}"
    return env


def capture_command(source: str) -> list[str]:
    if not isinstance(source, str) or not SOURCE_RE.fullmatch(source):
        raise AudioCaptureError("capture_source_invalid")
    return [
        "parec", "--raw", f"--device={source}", "--format=s16le",
        f"--rate={SAMPLE_RATE}", "--channels=1",
    ]


class PulseCapture:
    """Read fixed-size PCM frames on a worker thread into a bounded queue."""

    def __init__(self, chunks: queue.Queue[bytes | AudioCaptureError | None], *, source: str | None = None,
                 popen=subprocess.Popen, environment: dict[str, str] | None = None):
        self.chunks = chunks
        self.dropped_frames = 0
        self.started_at = 0.0
        self.last_frame_at = 0.0
        self.source = selected_source() if source is None else source
        command = capture_command(self.source)
        env = capture_environment() if environment is None else environment
        try:
            self.process = popen(command, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 bufsize=0, env=env)
        except FileNotFoundError as exc:
            raise AudioCaptureError("audio_capture_tool_missing") from exc
        except OSError as exc:
            raise AudioCaptureError("capture_source_unavailable") from exc
        if self.process.stdout is None:
            self.process.terminate()
            raise AudioCaptureError("capture_source_unavailable")
        self.thread = Thread(target=self._read, name="luma-mic-capture", daemon=True)

    def __enter__(self):
        self.started_at = monotonic()
        self.thread.start()
        return self

    def stalled(self, now: float | None = None) -> bool:
        """A quiet live mic supplies silent PCM; no frames means a dead stream."""
        now = monotonic() if now is None else now
        anchor = self.last_frame_at or self.started_at
        return bool(anchor and now - anchor >= 15)

    def __exit__(self, _type, _value, _traceback):
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        if self.process.stdout is not None:
            self.process.stdout.close()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def _enqueue(self, data: bytes | AudioCaptureError | None) -> None:
        try:
            self.chunks.put_nowait(data)
        except queue.Full:
            if data is None or isinstance(data, AudioCaptureError):
                # Preserve a terminal event so the consumer cannot mistake a
                # dead capture process for a quiet microphone. Evicting an
                # audio frame still creates a gap: the consumer must discard
                # that utterance before it sees the terminal marker.
                try:
                    evicted = self.chunks.get_nowait()
                    if isinstance(evicted, bytes):
                        self.dropped_frames += 1
                    self.chunks.put_nowait(data)
                except (queue.Empty, queue.Full):
                    pass
            else:
                # The consumer must discard the resulting incomplete utterance.
                self.dropped_frames += 1

    def _read(self) -> None:
        pending = bytearray()
        received_audio = False
        terminal_error: AudioCaptureError | None = None
        try:
            stream = self.process.stdout
            while True:
                data = stream.read(FRAME_BYTES)
                if not data:
                    break
                pending.extend(data)
                while len(pending) >= FRAME_BYTES:
                    frame = bytes(pending[:FRAME_BYTES])
                    del pending[:FRAME_BYTES]
                    received_audio = True
                    self.last_frame_at = monotonic()
                    self._enqueue(frame)
            if pending:
                # An EOF between whole PCM frames is also an incomplete
                # utterance, even when earlier frames reached the queue.
                self.dropped_frames += 1
            if not received_audio and self.process.poll() not in (None, 0):
                terminal_error = AudioCaptureError("capture_source_unavailable")
            elif received_audio or self.process.poll() not in (None, 0):
                terminal_error = AudioCaptureError("capture_stream_stopped")
        except OSError:
            terminal_error = AudioCaptureError(
                "capture_source_unavailable" if not received_audio else "capture_stream_stopped"
            )
        finally:
            self._enqueue(terminal_error or None)
