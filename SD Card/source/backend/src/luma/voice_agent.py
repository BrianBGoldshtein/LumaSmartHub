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

import httpx

from .voice import WakeGate, command_grammar
from .leds import StatusLeds


def main() -> None:
    # Optional dependencies stay out of the API process and ordinary test suite.
    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel

    model_path = Path(os.environ.get("LUMA_VOSK_MODEL", "/opt/luma/models/vosk"))
    if not (model_path / "am").is_dir():
        raise SystemExit("Install a licensed Vosk model and set LUMA_VOSK_MODEL before enabling voice.")
    SetLogLevel(-1)
    gate = WakeGate(os.environ.get("LUMA_WAKE_PHRASE", "hey luma"))
    recognizer = KaldiRecognizer(Model(str(model_path)), 16000, json.dumps(command_grammar(gate.phrase)))
    leds = StatusLeds()
    atexit.register(leds.close)
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    chunks: queue.Queue[bytes] = queue.Queue(maxsize=16)
    device = os.environ.get("LUMA_MIC_DEVICE") or None
    if device and device.isdigit():
        device = int(device)

    def capture(data, frames, timing, status):
        try:
            chunks.put_nowait(bytes(data))
        except queue.Full:
            pass  # Bounded memory, even if TTS or the backend stalls.

    with httpx.Client(base_url="http://127.0.0.1:8742", timeout=8) as client:
        current_phase = "idle"

        def phase(value):
            nonlocal current_phase
            current_phase = value
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

        with sd.RawInputStream(samplerate=16000, blocksize=4000, device=device, dtype="int16", channels=1, callback=capture):
            phase("idle")
            calibration = {"active": False, "session": ""}
            next_check = 0.0
            next_heartbeat = time.monotonic() + 5
            next_meter = 0.0
            energy = count = peak = 0
            meter_energy = meter_count = meter_peak = 0
            while True:
                chunk = chunks.get()
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
                            gate.until = 0
                            energy = count = peak = 0
                            meter_energy = meter_count = meter_peak = 0
                            next_meter = now
                            phase("listening" if fresh["active"] else "idle")
                        calibration = fresh
                    except httpx.HTTPError:
                        # Preserve calibration suppression if the API becomes unreachable.
                        pass
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
                if gate.until and time.monotonic() >= gate.until:
                    gate.until = 0
                    phase("idle")
                if not recognizer.AcceptWaveform(chunk):
                    continue
                text = json.loads(recognizer.Result()).get("text", "")
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
                if not accepted:
                    phase("listening")
                    continue
                phase("thinking")
                try:
                    response = client.post("/api/v1/voice/command", json={"text": accepted})
                    response.raise_for_status()
                    reply = response.json()["message"]
                    phase("speaking")
                    # stdin avoids argument interpretation of calendar text beginning with '-'.
                    subprocess.run(["espeak-ng", "--stdin", "-s", "155"], input=reply, text=True, check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (httpx.HTTPError, subprocess.SubprocessError, OSError):
                    phase("error")
                finally:
                    while not chunks.empty():
                        try:
                            chunks.get_nowait()
                        except queue.Empty:
                            break
                    recognizer.Reset()
                    phase("idle")


if __name__ == "__main__":
    main()
