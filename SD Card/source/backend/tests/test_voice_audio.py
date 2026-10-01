from __future__ import annotations

from io import BytesIO
import queue
import subprocess

import pytest

from luma.voice_audio import (
    AudioCaptureError, FRAME_BYTES, PulseCapture, capture_command, selected_source,
)


def test_capture_targets_the_echo_cancelled_mono_source_at_vosk_rate():
    assert capture_command("luma_mic") == [
        "parec", "--raw", "--device=luma_mic", "--format=s16le",
        "--rate=16000", "--channels=1",
    ]


def test_source_override_is_validated_and_never_parsed_by_a_shell(monkeypatch):
    monkeypatch.setenv("LUMA_MIC_SOURCE", "respeaker.echo-cancelled")
    monkeypatch.setenv("PULSE_SOURCE", "ignored-default")
    assert selected_source() == "respeaker.echo-cancelled"
    assert "--device=respeaker.echo-cancelled" in capture_command(selected_source())
    with pytest.raises(AudioCaptureError, match="capture_source_invalid"):
        capture_command("luma_mic; touch /tmp/not-a-command")


def test_pulse_reader_produces_exact_frames_and_discards_partial_tail():
    frame = b"\x01\x00" * (FRAME_BYTES // 2)

    class Process:
        def __init__(self):
            self.stdout = BytesIO(frame * 2 + b"partial")
            self.terminated = False

        def poll(self):
            return 0

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.terminated = True

    process = Process()
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return process

    chunks: queue.Queue[bytes | AudioCaptureError | None] = queue.Queue(maxsize=4)
    with PulseCapture(chunks, source="luma_mic", popen=popen):
        first = chunks.get(timeout=2)
        second = chunks.get(timeout=2)
        ended = chunks.get(timeout=2)

    assert first == second == frame
    assert isinstance(ended, AudioCaptureError)
    assert ended.code == "capture_stream_stopped"
    assert process.terminated is False
    command, options = calls[0]
    assert command[0] == "parec" and command[2] == "--device=luma_mic"
    assert options["stdin"] == subprocess.DEVNULL
    assert options["stderr"] == subprocess.DEVNULL


def test_missing_pulse_capture_program_has_a_fixed_diagnostic_code():
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("host path is not surfaced")

    with pytest.raises(AudioCaptureError, match="audio_capture_tool_missing") as error:
        PulseCapture(queue.Queue(), source="luma_mic", popen=missing)
    assert error.value.code == "audio_capture_tool_missing"


def test_missing_source_has_a_fixed_diagnostic_without_exposing_child_stderr():
    class Process:
        stdout = BytesIO()

        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

        def terminate(self):
            pass

        def kill(self):
            pass

    chunks: queue.Queue[bytes | AudioCaptureError | None] = queue.Queue(maxsize=4)
    with PulseCapture(chunks, source="luma_mic", popen=lambda *_args, **_kwargs: Process()):
        diagnostic = chunks.get(timeout=2)

    assert isinstance(diagnostic, AudioCaptureError)
    assert diagnostic.code == "capture_source_unavailable"


def test_capture_counts_but_never_buffers_overflowing_audio():
    class Process:
        stdout = BytesIO()
        def poll(self):
            return 0
    chunks = queue.Queue(maxsize=1)
    capture = PulseCapture(chunks, source="luma_mic", popen=lambda *_a, **_k: Process())
    capture._enqueue(b"first")
    capture._enqueue(b"second")
    assert capture.dropped_frames == 1
    assert chunks.get_nowait() == b"first"
