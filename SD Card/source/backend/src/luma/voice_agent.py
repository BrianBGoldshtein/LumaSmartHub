"""Optional offline speech service. Audio is processed in RAM and never uploaded."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import time
import atexit
import signal
from array import array
import math
import re

import httpx

from .voice import WakeGate, command_grammar
from .leds import StatusLeds
from .voice_audio import AudioCaptureError, PulseCapture
from .voice_speech import OfflineSpeaker


def _report_diagnostic(client: httpx.Client, code: str) -> None:
    try:
        client.post("/api/v1/voice/diagnostic", json={"code": code}).raise_for_status()
    except httpx.HTTPError:
        pass


def _free_command(text: str, wake_phrase: str) -> str:
    """Use unrestricted transcription after the constrained recognizer hears wake."""
    words=re.sub(r'\s+', ' ', text.casefold()).strip()
    match=re.search(r'\b'+re.escape(wake_phrase)+r'\b',words)
    return words[match.end():].strip(' ,.') if match else words


def main() -> None:
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    chunks: queue.Queue[bytes | AudioCaptureError | None] = queue.Queue(maxsize=16)
    with httpx.Client(base_url="http://127.0.0.1:8742", timeout=8) as client:
        # Optional dependencies and models live outside the API process. Report
        # startup failures through a fixed local code instead of silently
        # leaving calibration waiting for a service heartbeat.
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel
        except Exception:
            _report_diagnostic(client, "recognizer_unavailable")
            raise SystemExit("The local speech recognizer is unavailable.") from None

        model_path = Path(os.environ.get("LUMA_VOSK_MODEL", "/opt/luma/models/vosk"))
        if not (model_path / "am").is_dir():
            _report_diagnostic(client, "model_unavailable")
            raise SystemExit("The installed local speech model is unavailable.")
        try:
            SetLogLevel(-1)
            gate = WakeGate(os.environ.get("LUMA_WAKE_PHRASE", "hey luma"))
            model = Model(str(model_path))
            recognizer = KaldiRecognizer(
                model, 16000,
                json.dumps(command_grammar(gate.phrase)),
            )
            free_recognizer = KaldiRecognizer(model, 16000)
        except Exception:
            _report_diagnostic(client, "model_unavailable")
            raise SystemExit("The installed local speech model could not be loaded.") from None

        leds = StatusLeds()
        atexit.register(leds.close)
        speaker = OfflineSpeaker()
        atexit.register(speaker.close)
        def phase(value):
            leds.phase(value)
            try:
                client.post("/api/v1/voice/phase", json={"phase": value}).raise_for_status()
            except httpx.HTTPError:
                pass

        def heartbeat():
            try:
                client.post("/api/v1/voice/heartbeat").raise_for_status()
            except httpx.HTTPError:
                pass

        try:
            # parec is a PulseAudio-protocol client. Supplying the source name
            # explicitly guarantees capture from PipeWire's echo-cancelled
            # ReSpeaker node instead of PortAudio's machine-dependent default.
            with PulseCapture(chunks):
                phase("idle")
                calibration = {"active": False, "session": ""}
                next_check = 0.0
                next_heartbeat = time.monotonic() + 5
                next_meter = 0.0
                energy = count = peak = 0
                meter_energy = meter_count = meter_peak = 0
                utterance: list[bytes] = []
                while True:
                    now = time.monotonic()
                    if now >= next_heartbeat:
                        heartbeat()
                        next_heartbeat = now + 5
                    if now >= next_check:
                        next_check = now + 2
                        try:
                            response = client.get("/api/v1/voice/calibration")
                            response.raise_for_status()
                            fresh = response.json()
                            if (fresh["active"], fresh["session"]) != (calibration["active"], calibration["session"]):
                                recognizer.Reset()
                                utterance.clear()
                                gate.until = 0
                                energy = count = peak = 0
                                meter_energy = meter_count = meter_peak = 0
                                next_meter = now
                                phase("listening" if fresh["active"] else "idle")
                            calibration = fresh
                        except httpx.HTTPError:
                            # Preserve calibration suppression if the API becomes unreachable.
                            pass
                    if gate.until and now >= gate.until:
                        gate.until = 0
                        phase("idle")
                    try:
                        chunk = chunks.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if isinstance(chunk, AudioCaptureError):
                        raise chunk
                    if chunk is None:
                        raise AudioCaptureError("capture_stream_stopped")
                    now = time.monotonic()
                    samples = array("h", chunk)
                    squared = sum(value * value for value in samples)
                    chunk_peak = max((abs(value) for value in samples), default=0)
                    energy += squared
                    count += len(samples)
                    peak = max(peak, chunk_peak)
                    if calibration["active"]:
                        meter_energy += squared
                        meter_count += len(samples)
                        meter_peak = max(meter_peak, chunk_peak)
                        if now >= next_meter and meter_count:
                            level_rms = math.sqrt(meter_energy / meter_count) / 32768
                            level_peak = meter_peak / 32768
                            try:
                                client.post("/api/v1/voice/calibration/level", json={
                                    "session": calibration["session"], "rms": level_rms, "peak": level_peak
                                }).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            meter_energy = meter_count = meter_peak = 0
                            next_meter = now + 1
                    utterance.append(chunk)
                    if len(utterance)>36:
                        utterance.pop(0)  # At most nine seconds of 16 kHz mono audio.
                    if not recognizer.AcceptWaveform(chunk):
                        continue
                    text = json.loads(recognizer.Result()).get("text", "")
                    spoken=utterance
                    utterance=[]
                    rms, maximum = math.sqrt(energy / max(count, 1)) / 32768, peak / 32768
                    energy = count = peak = 0
                    if calibration["active"]:
                        if text:
                            try:
                                client.post("/api/v1/voice/calibration/sample", json={"session": calibration["session"], "text": text, "rms": rms, "peak": maximum}).raise_for_status()
                            except httpx.HTTPError:
                                pass
                        continue  # Test phrases never change brightness, volume or theme.
                    accepted = gate.accept(text, time.monotonic())
                    if accepted is None:
                        continue
                    # Light the full-screen listening state as soon as the
                    # wake phrase is accepted, including one-shot commands.
                    phase("listening")
                    # The constrained recognizer verifies wake. Re-transcribe
                    # just this bounded utterance without a fixed phrase list,
                    # so the local intent model can hear genuine variations.
                    free_recognizer.Reset()
                    parts=[]
                    for frame in spoken:
                        if free_recognizer.AcceptWaveform(frame):
                            parts.append(json.loads(free_recognizer.Result()).get('text',''))
                    parts.append(json.loads(free_recognizer.FinalResult()).get('text',''))
                    free_text=' '.join(part for part in parts if part)
                    varied=_free_command(free_text,gate.phrase)
                    if varied and varied != gate.phrase and (accepted or len(varied.split())>1):
                        accepted=varied
                    if not accepted:
                        continue
                    phase("thinking")
                    try:
                        response = client.post("/api/v1/voice/command", json={"text": accepted})
                        response.raise_for_status()
                        reply = response.json()["message"]
                        phase("speaking")
                        speaker.speak(reply)
                    except (httpx.HTTPError, subprocess.SubprocessError, OSError):
                        phase("error")
                    finally:
                        while not chunks.empty():
                            try:
                                pending = chunks.get_nowait()
                            except queue.Empty:
                                break
                            if isinstance(pending, AudioCaptureError):
                                chunks.put_nowait(pending)
                                break
                            if pending is None:
                                chunks.put_nowait(None)
                                break
                        recognizer.Reset()
                        phase("idle")
        except AudioCaptureError as error:
            _report_diagnostic(client, error.code)
            raise SystemExit("The configured Luma microphone source could not be read.") from None


if __name__ == "__main__":
    main()
