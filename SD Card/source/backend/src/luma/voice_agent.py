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
import math
import re

import httpx

from .voice import WakeGate, command_grammar, parse_local_command
from .models import CommandName
from .leds import StatusLeds
from .voice_audio import AudioCaptureError, PulseCapture
from .voice_speech import OfflineSpeaker, VoicePlaybackError
from .voice_signal import AudioPreprocessor, CalibrationSegmenter, pcm_measurements, read_profile


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


def _unrestricted_transcript(recognizer, frames: list[bytes]) -> str:
    """Replay one bounded utterance through the same decoder used for commands."""
    recognizer.Reset()
    parts = []
    for frame in frames:
        if recognizer.AcceptWaveform(frame):
            parts.append(json.loads(recognizer.Result()).get('text', ''))
    parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
    return ' '.join(part for part in parts if part)


def partial_has_wake(partial_result: str, wake_phrase: str) -> bool:
    """Only animate early; a partial Vosk hypothesis never authorizes a command."""
    try:
        partial = json.loads(partial_result).get("partial", "")
    except (TypeError, ValueError):
        return False
    return isinstance(partial, str) and bool(re.search(
        r"\b" + re.escape(wake_phrase) + r"\b", re.sub(r"\s+", " ", partial.casefold())
    ))


def choose_command(constrained: str, free_transcript: str, wake_phrase: str) -> tuple[str | None, str]:
    """Choose a valid interpretation, never override it with invalid dictation.

    The grammar often recognizes a supported command more reliably, while the
    unrestricted decoder is needed for varied phrasing. Neither decoder may
    silently change a numeric slot or a command with side effects.
    """
    varied = _free_command(free_transcript, wake_phrase)
    if not varied or varied == wake_phrase:
        return (constrained or None), "constrained"
    if re.search(r"\b(?:don't|dont|do not|never|not)\b", varied):
        return None, "negated"
    constrained_command = parse_local_command(constrained) if constrained else None
    varied_command = parse_local_command(varied)
    if constrained_command and varied_command:
        if (constrained_command.name, constrained_command.value) == (varied_command.name, varied_command.value):
            return varied, "agree"
        if constrained_command.name == varied_command.name == CommandName.LOCAL_QUERY:
            return varied, "free_query"
        return None, "conflict"
    if constrained_command:
        return constrained, "constrained"
    if varied_command:
        return varied, "free"
    return varied if len(varied.split()) > 1 else (constrained or varied), "unmatched"


def _discard_pending_audio(chunks: queue.Queue) -> None:
    """Drop speech feedback while preserving a capture failure or EOF."""
    while not chunks.empty():
        try:
            pending = chunks.get_nowait()
        except queue.Empty:
            break
        if isinstance(pending, AudioCaptureError) or pending is None:
            try:
                chunks.put_nowait(pending)
            except queue.Full:
                # A producer may refill the queue between get and put.
                try:
                    chunks.get_nowait()
                    chunks.put_nowait(pending)
                except (queue.Empty, queue.Full):
                    pass
            break


def main() -> None:
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    chunks: queue.Queue[bytes | AudioCaptureError | None] = queue.Queue(maxsize=16)
    # Non-command status calls must not stall a four-second audio queue.
    with httpx.Client(base_url="http://127.0.0.1:8742", timeout=1) as client:
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
        preprocessor = AudioPreprocessor()
        calibration_segmenter = CalibrationSegmenter()
        def say(reply: str) -> str:
            try:
                engine = speaker.speak(reply)
            except VoicePlaybackError as exc:
                engine = 'silent'
                speaker.last_error = exc.code
                speaker.last_route = None
            try:
                client.post('/api/v1/voice/output-report', json={
                    'engine': engine, 'error': speaker.last_error,
                    'primary_error': speaker.last_primary_error,
                    'route': speaker.last_route,
                }).raise_for_status()
            except httpx.HTTPError:
                pass
            return engine
        def phase(value):
            leds.phase(value)
            try:
                client.post("/api/v1/voice/phase", json={"phase": value}).raise_for_status()
            except httpx.HTTPError:
                pass

        def heartbeat(dropped_frames: int):
            try:
                client.post("/api/v1/voice/heartbeat", json={
                    "dropped_frames": dropped_frames,
                }).raise_for_status()
            except httpx.HTTPError:
                pass

        try:
            # parec is a PulseAudio-protocol client. Supplying the source name
            # explicitly guarantees capture from PipeWire's echo-cancelled
            # ReSpeaker node instead of PortAudio's machine-dependent default.
            with PulseCapture(chunks) as capture:
                phase("idle")
                calibration = {"active": False, "session": ""}
                next_check = 0.0
                next_preview_check = 0.0
                handled_preview_id = None
                next_heartbeat = time.monotonic() + 5
                next_meter = 0.0
                meter_energy = meter_count = meter_peak = 0
                meter_floors: list[float] = []
                utterance: list[bytes] = []
                seen_drops = recognition_drops = 0
                early_wake = False
                while True:
                    now = time.monotonic()
                    if now >= next_heartbeat:
                        heartbeat(recognition_drops)
                        next_heartbeat = now + 5
                    if now >= next_preview_check:
                        next_preview_check = now + 1
                        try:
                            pending = client.get('/api/v1/voice/asset/preview/pending').json()
                            request_id = pending.get('request_id')
                        except (httpx.HTTPError, ValueError, KeyError):
                            request_id = None
                        if request_id and request_id != handled_preview_id:
                            handled_preview_id = request_id
                            phase('speaking')
                            try:
                                speaker._piper("Hello, I'm Luma. It's good to see you.")
                                result = {'request_id': request_id, 'route': speaker.last_route}
                            except VoicePlaybackError as exc:
                                speaker.close()
                                result = {'request_id': request_id, 'error': exc.code}
                            try:
                                client.post('/api/v1/voice/asset/preview/result', json=result,
                                            timeout=3).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            _discard_pending_audio(chunks)
                            seen_drops = capture.dropped_frames
                            recognizer.Reset()
                            free_recognizer.Reset()
                            utterance.clear()
                            calibration_segmenter.reset()
                            early_wake = False
                            preprocessor.reset()
                            phase('listening' if calibration['active'] else 'idle')
                            continue
                    if now >= next_check:
                        next_check = now + 2
                        try:
                            response = client.get("/api/v1/voice/calibration")
                            response.raise_for_status()
                            fresh = response.json()
                            if (fresh["active"], fresh["session"]) != (calibration["active"], calibration["session"]):
                                recognizer.Reset()
                                utterance.clear()
                                calibration_segmenter.reset()
                                early_wake = False
                                gate.until = 0
                                meter_energy = meter_count = meter_peak = 0
                                meter_floors.clear()
                                next_meter = now
                                phase("listening" if fresh["active"] else "idle")
                            target_profile = read_profile(fresh.get('audio_profile'))
                            if preprocessor.profile != target_profile:
                                preprocessor.reset(target_profile)
                                recognizer.Reset()
                                free_recognizer.Reset()
                                utterance.clear()
                                calibration_segmenter.reset()
                                early_wake = False
                                gate.until = 0
                                _discard_pending_audio(chunks)
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
                    if capture.dropped_frames != seen_drops:
                        recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        recognizer.Reset()
                        free_recognizer.Reset()
                        gate.until = 0
                        utterance.clear()
                        calibration_segmenter.reset()
                        early_wake = False
                        preprocessor.reset()
                        _discard_pending_audio(chunks)
                        phase("listening" if calibration["active"] else "idle")
                        continue  # Never execute a command from a gapped recording.
                    now = time.monotonic()
                    raw_level = pcm_measurements(chunk)
                    raw_chunk = chunk
                    chunk = preprocessor.process(chunk)
                    if calibration["active"]:
                        frame_samples = len(raw_chunk) // 2
                        meter_energy += raw_level['rms'] ** 2 * frame_samples
                        meter_count += frame_samples
                        meter_peak = max(meter_peak, raw_level['peak'])
                        meter_floors.append(raw_level['rms'])
                        if now >= next_meter and meter_count:
                            level_rms = math.sqrt(meter_energy / meter_count)
                            level_peak = meter_peak
                            try:
                                client.post("/api/v1/voice/calibration/level", json={
                                    "session": calibration["session"], "rms": level_rms, "peak": level_peak,
                                    "floor_rms": min(meter_floors) if meter_floors else level_rms,
                                }).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            meter_energy = meter_count = meter_peak = 0
                            meter_floors.clear()
                            next_meter = now + 1
                    if calibration['active'] and calibration.get('ambient_remaining', 0) > 0:
                        # The first four seconds measure the room, not words.
                        # Do not allow a speech fragment to leak into phrase 1.
                        calibration_segmenter.reset()
                        continue
                    if calibration['active']:
                        segment = calibration_segmenter.feed(
                            raw_chunk, chunk,
                            noise_rms=float(calibration.get('room_noise_rms') or 0),
                        )
                        if segment is None:
                            continue
                        raw_spoken, spoken = segment
                        signal = pcm_measurements(b''.join(raw_spoken))
                        # Acoustic boundaries make this check useful even if
                        # Vosk would never emit an endpoint or any words.
                        text = _unrestricted_transcript(recognizer, spoken)
                        free_text = _unrestricted_transcript(free_recognizer, spoken)
                        test_gate = WakeGate(gate.phrase)
                        candidate = test_gate.accept(text, now)
                        if candidate is not None:
                            chosen, selection = choose_command(candidate, free_text, gate.phrase)
                        else:
                            chosen, selection = None, ""
                        try:
                            client.post("/api/v1/voice/calibration/sample", json={
                                "session": calibration["session"], "text": text,
                                "free_text": free_text, "selected_text": chosen,
                                "selection": selection,
                                "rms": signal['rms'], "peak": signal['peak'],
                                "dc": signal['dc'],
                                "clipped_fraction": signal['clipped_fraction'],
                            }).raise_for_status()
                        except httpx.HTTPError:
                            pass
                        continue  # Calibration never executes commands.
                    utterance.append(chunk)
                    if len(utterance)>36:
                        utterance.pop(0)  # At most nine seconds of 16 kHz mono audio.
                    if not recognizer.AcceptWaveform(chunk):
                        if (not calibration["active"] and not early_wake
                                and partial_has_wake(recognizer.PartialResult(), gate.phrase)):
                            # Show the full-screen orb while the owner is
                            # still speaking. Only a final, exact wake match
                            # below can dispatch a command.
                            early_wake = True
                            phase("listening")
                        continue
                    text = json.loads(recognizer.Result()).get("text", "")
                    had_early_wake = early_wake
                    early_wake = False
                    spoken=utterance
                    utterance=[]
                    accepted = gate.accept(text, time.monotonic())
                    if accepted is None:
                        if had_early_wake and gate.until <= time.monotonic():
                            phase("idle")
                        continue
                    # Light the full-screen listening state as soon as the
                    # wake phrase is accepted, including one-shot commands.
                    phase("listening")
                    # The constrained recognizer verifies wake. Re-transcribe
                    # just this bounded utterance without a fixed phrase list,
                    # so the local intent model can hear genuine variations.
                    free_text = _unrestricted_transcript(free_recognizer, spoken)
                    accepted, selection = choose_command(accepted, free_text, gate.phrase)
                    if selection in {"conflict", "negated"}:
                        if selection == "conflict":
                            phase("speaking")
                            say("I heard two different commands. Please repeat that.")
                        _discard_pending_audio(chunks)
                        seen_drops = capture.dropped_frames
                        recognizer.Reset()
                        preprocessor.reset()
                        phase("idle")
                        continue
                    if not accepted:
                        if gate.until <= time.monotonic():
                            phase("idle")
                        continue
                    phase("thinking")
                    try:
                        response = client.post("/api/v1/voice/command", json={"text": accepted}, timeout=8)
                        response.raise_for_status()
                        reply = response.json()["message"]
                        phase("speaking")
                        if say(reply) == 'silent':
                            phase('error')
                    except (httpx.HTTPError, subprocess.SubprocessError, OSError):
                        phase("error")
                    finally:
                        _discard_pending_audio(chunks)
                        seen_drops = capture.dropped_frames
                        recognizer.Reset()
                        preprocessor.reset()
                        phase("idle")
        except AudioCaptureError as error:
            _report_diagnostic(client, error.code)
            raise SystemExit("The configured Luma microphone source could not be read.") from None


if __name__ == "__main__":
    main()
