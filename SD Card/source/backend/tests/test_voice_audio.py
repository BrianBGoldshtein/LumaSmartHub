from __future__ import annotations

from io import BytesIO
import queue
import subprocess

import pytest

from luma.voice_audio import (
    AudioCaptureError, FRAME_BYTES, PulseCapture, capture_command,
    capture_environment, selected_source,
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


def test_capture_ignores_inherited_pulse_source_and_pins_user_socket(monkeypatch):
    monkeypatch.delenv("LUMA_MIC_SOURCE", raising=False)
    monkeypatch.setenv("PULSE_SOURCE", "wrong-microphone")
    monkeypatch.setenv("PULSE_SERVER", "unix:/tmp/wrong-audio-server")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/wrong-user")
    monkeypatch.setattr("luma.voice_audio.sys.platform", "linux")
    monkeypatch.setattr("luma.voice_audio.os.getuid", lambda: 1234)
    monkeypatch.setattr("luma.voice_audio.Path.is_socket", lambda path: True)
    assert selected_source() == "luma_mic"
    env = capture_environment()
    assert "PULSE_SOURCE" not in env
    assert env["PULSE_SERVER"] == "unix:/run/user/1234/pulse/native"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1234"
    monkeypatch.setattr("luma.voice_audio.Path.is_socket", lambda path: False)
    with pytest.raises(AudioCaptureError, match="capture_source_unavailable"):
        capture_environment()


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
    with PulseCapture(chunks, source="luma_mic", popen=popen, environment={}):
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
    assert options["env"] == {}


def test_missing_pulse_capture_program_has_a_fixed_diagnostic_code():
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("host path is not surfaced")

    with pytest.raises(AudioCaptureError, match="audio_capture_tool_missing") as error:
        PulseCapture(queue.Queue(), source="luma_mic", popen=missing, environment={})
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
    with PulseCapture(chunks, source="luma_mic", popen=lambda *_args, **_kwargs: Process(),
                      environment={}):
        diagnostic = chunks.get(timeout=2)

    assert isinstance(diagnostic, AudioCaptureError)
    assert diagnostic.code == "capture_source_unavailable"


def test_capture_counts_but_never_buffers_overflowing_audio():
    class Process:
        stdout = BytesIO()
        def poll(self):
            return 0
    chunks = queue.Queue(maxsize=1)
    capture = PulseCapture(chunks, source="luma_mic", popen=lambda *_a, **_k: Process(),
                           environment={})
    capture._enqueue(b"first")
    capture._enqueue(b"second")
    assert capture.dropped_frames == 1
    assert chunks.get_nowait() == b"first"


def test_capture_stall_is_distinct_from_silent_pcm_frames():
    class Process:
        stdout = BytesIO()
        def poll(self):
            return 0

    capture = PulseCapture(queue.Queue(), source="luma_mic",
                           popen=lambda *_a, **_k: Process(), environment={})
    capture.started_at = 100.0
    assert not capture.stalled(114.9)
    assert capture.stalled(115.0)
    # A zero-amplitude microphone frame is still a live capture frame.
    capture.last_frame_at = 114.0
    assert not capture.stalled(115.0)
    assert capture.stalled(129.0)
