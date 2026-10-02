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
import sys
from statistics import median

import httpx

from .voice import WakeGate, command_grammar, parse_local_command
from .leds import StatusLeds
from .voice_audio import AudioCaptureError, PulseCapture
from .voice_speech import (OfflineSpeaker, PIPER_WORKER_FAILURES, VoicePlaybackError, play_test_tone,
                           speaker_route_warning)
from .voice_signal import (AudioPreprocessor, AudioProfile, CalibrationSegmenter, pcm_measurements,
                           low_frequency_fraction, read_profile, speech_measurements)
from .voice_wake import (command_after_wake, has_wake, read_wake_mode,
                         wake_confirmed, wake_near_start)
from .voice_adaptation import PhraseAdaptations
from .voice_speaker import SpeakerVectorError, decode_speaker_observation


def _report_diagnostic(client: httpx.Client, code: str) -> None:
    try:
        client.post("/api/v1/voice/diagnostic", json={"code": code}).raise_for_status()
    except httpx.HTTPError:
        pass


def _recover_preview_failure(speaker: OfflineSpeaker, error: VoicePlaybackError) -> None:
    """Keep a healthy warm model after a speaker-only sample failure."""
    if error.code in PIPER_WORKER_FAILURES:
        speaker.close()


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


def calibration_decoding_payload(constrained, unrestricted, raw_spoken: list[bytes],
                                 spoken: list[bytes], *, wake_phrase: str,
                                 noise_rms: float, profile: AudioProfile,
                                 now: float, adaptations: PhraseAdaptations | None = None) -> dict:
    """Decode a setup-only segment after audio conditioning, without acting.

    The raw comparison reuses the unrestricted decoder only after the tuned
    decode has completed. No captured audio or transcript leaves this local
    process except the short-lived check payload sent to the loopback API.
    """
    signal = speech_measurements(raw_spoken, noise_rms=noise_rms)
    text = _unrestricted_transcript(constrained, spoken)
    free_text = _unrestricted_transcript(unrestricted, spoken)
    raw_compared = profile.gain > 1 or profile.high_pass
    raw_constrained_wake = (wake_near_start(_unrestricted_transcript(constrained, raw_spoken),
                                           wake_phrase) if raw_compared else None)
    raw_free_text = (_unrestricted_transcript(unrestricted, raw_spoken)
                     if raw_compared else "")
    candidate = WakeGate(wake_phrase).accept(text, now)
    chosen, selection = (select_command(candidate, free_text, wake_phrase, adaptations)
                         if candidate is not None else (None, ""))
    return {"text": text, "free_text": free_text, "selected_text": chosen,
            "raw_free_text": raw_free_text, "raw_compared": raw_compared,
            "raw_constrained_wake": raw_constrained_wake,
            "selection": selection, "rms": signal['rms'], "peak": signal['peak'],
            "dc": signal['dc'], "clipped_fraction": signal['clipped_fraction']}


def call_trial_decoding_payload(constrained_text: str, unrestricted,
                                spoken: list[bytes], wake_phrase: str,
                                *, partial_wake: bool = False,
                                raw_spoken: list[bytes] | None = None,
                                constrained=None) -> dict:
    """Compare call false wakes before/after tuning without emitting words."""
    proposed = has_wake(constrained_text, wake_phrase)
    free_text = (_unrestricted_transcript(unrestricted, spoken) if proposed else '')
    result = {
        'partial_wake': partial_wake,
        'constrained_wake': proposed,
        'constrained_near_start': wake_near_start(constrained_text, wake_phrase),
        'free_wake': has_wake(free_text, wake_phrase),
        'free_near_start': wake_near_start(free_text, wake_phrase),
    }
    if raw_spoken is not None:
        if constrained is None:
            raise ValueError('Raw call comparison needs the constrained decoder.')
        raw_text = _unrestricted_transcript(constrained, raw_spoken)
        raw_proposed = has_wake(raw_text, wake_phrase)
        raw_free = (_unrestricted_transcript(unrestricted, raw_spoken)
                    if raw_proposed else '')
        result.update(raw_compared=True, raw_constrained_wake=raw_proposed,
                      raw_constrained_near_start=wake_near_start(raw_text, wake_phrase),
                      raw_free_wake=has_wake(raw_free, wake_phrase),
                      raw_free_near_start=wake_near_start(raw_free, wake_phrase))
    return result


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
    silently change a numeric slot, time horizon, or command with side effects.
    """
    varied = _free_command(free_transcript, wake_phrase)
    if not varied or varied == wake_phrase:
        return (constrained or None), "constrained"
    if re.search(r"\b(?:don't|dont|do not|never|not)\b", varied):
        return None, "negated"
    constrained_command = parse_local_command(constrained) if constrained else None
    varied_command = parse_local_command(varied)
    if re.search(r'\b(?:titled|called|named)\b', varied) and varied_command is None:
        # Do not silently start an unnamed timer when the requested title was
        # truncated or failed recognition.
        return None, "unmatched"
    if constrained_command and varied_command:
        if (constrained_command.name, constrained_command.value) == (varied_command.name, varied_command.value):
            return varied, "agree"
        if (constrained_command.name == varied_command.name and
                constrained_command.name.value == 'start_timer'):
            def seconds(value):
                if type(value) is int:
                    return value * 60
                if isinstance(value, dict):
                    return value.get('seconds', value.get('minutes', 0) * 60)
                return None
            if (seconds(constrained_command.value) == seconds(varied_command.value) and
                    isinstance(varied_command.value, dict) and
                    varied_command.value.get('label', 'Timer') != 'Timer' and
                    (type(constrained_command.value) is int or
                     isinstance(constrained_command.value, dict) and
                     constrained_command.value.get('label', 'Timer') == 'Timer')):
                return varied, "free_title"
        return None, "conflict"
    if constrained_command:
        return constrained, "constrained"
    if varied_command:
        return varied, "free"
    return varied if len(varied.split()) > 1 else (constrained or varied), "unmatched"


def select_command(constrained: str, free_transcript: str, wake_phrase: str,
                   adaptations: PhraseAdaptations | None = None) -> tuple[str | None, str]:
    """Apply only owner-confirmed, post-wake corrections before intent choice."""
    learned = (adaptations.resolve(command_after_wake(free_transcript, wake_phrase) or '')
               if adaptations is not None and has_wake(free_transcript, wake_phrase)
               else None)
    if learned is not None:
        # A personal correction is evidence, not authority to overturn a
        # different valid command from the constrained decoder. Its grammar
        # can be wrong too, so ask for a repeat instead of guessing.
        constrained_command = parse_local_command(constrained)
        learned_command = parse_local_command(learned)
        if (constrained_command and learned_command and
                (constrained_command.name, constrained_command.value) !=
                (learned_command.name, learned_command.value)):
            return None, 'conflict'
        return learned, 'learned'
    return choose_command(constrained, free_transcript, wake_phrase)


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


def collect_speaker_trial_frames(chunks: queue.Queue, capture,
                                 *, frames: int = 24) -> tuple[list[bytes], str | None]:
    """Record six seconds after explicit arm; reject gaps, EOF and malformed PCM.

    This never writes a recording, runs ASR, or dispatches a command. The
    caller discards buffered pre-arm audio before invoking it.
    """
    if frames != 24:
        raise ValueError('Speaker trials require a six-second sample.')
    started_drops = capture.dropped_frames
    deadline = time.monotonic() + 10
    recorded: list[bytes] = []
    while len(recorded) < frames:
        if time.monotonic() >= deadline:
            return [], 'capture_stopped'
        try:
            chunk = chunks.get(timeout=min(.5, max(.01, deadline - time.monotonic())))
        except queue.Empty:
            if capture.stalled():
                return [], 'capture_stopped'
            continue
        if isinstance(chunk, AudioCaptureError) or chunk is None:
            return [], 'capture_stopped'
        if capture.dropped_frames != started_drops or len(chunk) != 8000:
            return [], 'capture_gap'
        recorded.append(chunk)
    return (recorded, None) if capture.dropped_frames == started_drops else ([], 'capture_gap')


def speaker_trial_result(recognizer, frames: list[bytes], *, noise_rms: float) -> dict:
    """Return only a bounded speaker vector or fixed error, never transcript/PCM."""
    try:
        sample = decode_speaker_observation(recognizer, frames, noise_rms=noise_rms)
    except SpeakerVectorError as exc:
        detail = str(exc).casefold()
        code = ('clipped' if 'clipped' in detail else
                'too_quiet' if 'too little speech' in detail else
                'speech_too_short' if 'four to eight' in detail else 'decode_failed')
        return {'error': code}
    return {'vector': list(sample.vector), 'spk_frames': sample.spk_frames,
            'input_seconds': sample.input_seconds}


def voice_process_peak_rss_kib() -> int | None:
    """Linux getrusage reports process peak RSS in KiB; never infer Pi free RAM."""
    if sys.platform != 'linux':
        return None
    try:
        import resource
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, ValueError):
        return None
    return value if 0 < value <= 8_388_608 else None


def _reset_gapped_decoding(chunks: queue.Queue, constrained, unrestricted,
                           preprocessor: AudioPreprocessor, gate: WakeGate) -> None:
    """Reject a late capture gap before any decoded words cause an action."""
    gate.until = 0
    constrained.Reset()
    unrestricted.Reset()
    preprocessor.reset()
    _discard_pending_audio(chunks)


def _reset_voice_transition(chunks: queue.Queue, constrained, unrestricted,
                            preprocessor: AudioPreprocessor, gate: WakeGate,
                            segmenter: CalibrationSegmenter,
                            utterance: list[bytes], raw_utterance: list[bytes]) -> None:
    """Isolate calibration/trial/mode changes from audio captured before them."""
    _reset_gapped_decoding(chunks, constrained, unrestricted, preprocessor, gate)
    segmenter.reset()
    utterance.clear()
    raw_utterance.clear()


def _arm_call_trial(client: httpx.Client, trial: dict) -> dict:
    """Accept only an acknowledgment of the current cleared-audio session."""
    response = client.post('/api/v1/voice/call-trial/armed', json={
        'session': trial['session'],
    }, timeout=3)
    response.raise_for_status()
    armed = response.json()
    if (not isinstance(armed, dict) or armed.get('session') != trial['session']
            or armed.get('armed') is not True or armed.get('active') is not True):
        raise ValueError('The call test was not armed.')
    return armed


def _calibration_boundary_changed(previous: dict, current: dict) -> bool:
    """A mixer change restarts baseline even if the session ID stays the same."""
    return ((previous.get('active'), previous.get('session'),
             previous.get('capture_revision')) !=
            (current.get('active'), current.get('session'),
             current.get('capture_revision')))


def main() -> None:
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    chunks: queue.Queue[bytes | AudioCaptureError | None] = queue.Queue(maxsize=24)
    # Setup-only raw/tuned comparison can briefly use more CPU. Six seconds
    # of capture buffering is under 200 KiB; a gap still invalidates speech.
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
                    'sink_warning': speaker_route_warning(speaker.last_route),
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
                calibration = {"active": False, "session": "", "capture_revision": 0,
                               "call_trial": {"active": False, "session": ""},
                               "speaker_trial": {"active": False, "session": ""}}
                speaker_model = None
                speaker_model_load_ms = 0.0
                handled_speaker_token = None
                wake_mode = 'standard'
                adaptations = PhraseAdaptations()
                next_check = 0.0
                next_preview_check = 0.0
                handled_preview_id = None
                handled_tone_id = None
                next_heartbeat = time.monotonic() + 5
                next_meter = 0.0
                meter_energy = meter_count = meter_peak = 0
                meter_floors: list[float] = []
                meter_low_fractions: list[float] = []
                utterance: list[bytes] = []
                raw_utterance: list[bytes] = []  # Only populated during a call A/B trial.
                seen_drops = recognition_drops = 0
                early_wake = False
                trial_partial_wake = False
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
                            preview_variant = pending.get('variant')
                        except (httpx.HTTPError, ValueError, KeyError):
                            request_id = None
                            preview_variant = None
                        if request_id and request_id != handled_preview_id:
                            handled_preview_id = request_id
                            phase('speaking')
                            try:
                                if preview_variant == 'fallback':
                                    speaker._fallback("Hello, I'm Luma. It's good to see you.")
                                else:
                                    speaker._piper("Hello, I'm Luma. It's good to see you.")
                                result = {'request_id': request_id, 'route': speaker.last_route,
                                          'sink_warning': speaker_route_warning(speaker.last_route)}
                            except VoicePlaybackError as exc:
                                _recover_preview_failure(speaker, exc)
                                result = {'request_id': request_id, 'error': exc.code}
                            try:
                                client.post('/api/v1/voice/asset/preview/result', json=result,
                                            timeout=3).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                    preprocessor, gate, calibration_segmenter,
                                                    utterance, raw_utterance)
                            seen_drops = capture.dropped_frames
                            early_wake = False
                            trial_partial_wake = False
                            phase('listening' if calibration['active'] else 'idle')
                            continue
                        try:
                            pending_tone = client.get('/api/v1/voice/asset/tone/pending').json()
                            tone_id = pending_tone.get('request_id')
                        except (httpx.HTTPError, ValueError, KeyError):
                            tone_id = None
                        if tone_id and tone_id != handled_tone_id:
                            handled_tone_id = tone_id
                            phase('speaking')
                            try:
                                route = play_test_tone()
                                result = {'request_id': tone_id, 'route': route,
                                          'sink_warning': speaker_route_warning(route)}
                            except VoicePlaybackError as exc:
                                result = {'request_id': tone_id, 'error': exc.code}
                            try:
                                client.post('/api/v1/voice/asset/tone/result', json=result,
                                            timeout=3).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                    preprocessor, gate, calibration_segmenter,
                                                    utterance, raw_utterance)
                            seen_drops = capture.dropped_frames
                            early_wake = False
                            trial_partial_wake = False
                            phase('listening' if calibration['active'] else 'idle')
                            continue
                    if now >= next_check:
                        next_check = now + 2
                        try:
                            response = client.get("/api/v1/voice/calibration")
                            response.raise_for_status()
                            fresh = response.json()
                            if _calibration_boundary_changed(calibration, fresh):
                                _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                        preprocessor, gate, calibration_segmenter,
                                                        utterance, raw_utterance)
                                seen_drops = capture.dropped_frames
                                early_wake = False
                                trial_partial_wake = False
                                meter_energy = meter_count = meter_peak = 0
                                meter_floors.clear()
                                meter_low_fractions.clear()
                                next_meter = now
                                phase("listening" if fresh["active"] else "idle")
                            old_trial = calibration.get('call_trial') or {}
                            new_trial = fresh.get('call_trial') or {}
                            if ((old_trial.get('active'), old_trial.get('session')) !=
                                    (new_trial.get('active'), new_trial.get('session'))):
                                # A call trial never consumes audio captured
                                # before it started and never executes words
                                # decoded while it was active.
                                _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                        preprocessor, gate, calibration_segmenter,
                                                        utterance, raw_utterance)
                                seen_drops = capture.dropped_frames
                                early_wake = False
                                trial_partial_wake = False
                                phase('idle')
                            if new_trial.get('active') and not new_trial.get('armed'):
                                # The API does not start the 90-second negative
                                # window until this worker has crossed the
                                # reset boundary and acknowledges its session.
                                try:
                                    fresh['call_trial'] = _arm_call_trial(client, new_trial)
                                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                                    pass  # Retry on the next status poll.
                            old_speaker_trial = calibration.get('speaker_trial') or {}
                            new_speaker_trial = fresh.get('speaker_trial') or {}
                            if ((old_speaker_trial.get('active'), old_speaker_trial.get('session')) !=
                                    (new_speaker_trial.get('active'), new_speaker_trial.get('session'))):
                                # Nothing heard before explicit owner consent
                                # can enter a speaker sample or execute later.
                                _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                        preprocessor, gate, calibration_segmenter,
                                                        utterance, raw_utterance)
                                early_wake = trial_partial_wake = False
                                seen_drops = capture.dropped_frames
                                phase('idle')
                            if not new_speaker_trial.get('active'):
                                speaker_model = None
                                speaker_model_load_ms = 0.0
                            next_wake_mode = read_wake_mode(fresh.get('wake_confirmation'))
                            if next_wake_mode != wake_mode:
                                wake_mode = next_wake_mode
                                _reset_voice_transition(chunks, recognizer, free_recognizer,
                                                        preprocessor, gate, calibration_segmenter,
                                                        utterance, raw_utterance)
                                seen_drops = capture.dropped_frames
                                early_wake = False
                                trial_partial_wake = False
                                phase("listening" if fresh["active"] else "idle")
                            adaptations = PhraseAdaptations(fresh.get('phrase_adaptations'))
                            target_profile = read_profile(fresh.get('audio_profile'))
                            if preprocessor.profile != target_profile:
                                preprocessor.reset(target_profile)
                                recognizer.Reset()
                                free_recognizer.Reset()
                                utterance.clear()
                                raw_utterance.clear()
                                calibration_segmenter.reset()
                                early_wake = False
                                trial_partial_wake = False
                                gate.until = 0
                                _discard_pending_audio(chunks)
                            calibration = fresh
                        except httpx.HTTPError:
                            # Preserve calibration suppression if the API becomes unreachable.
                            pass
                    speaker_state = calibration.get('speaker_trial') or {}
                    if speaker_state.get('active'):
                        token = speaker_state.get('token')
                        if speaker_state.get('phase') == 'arming' and token and token != handled_speaker_token:
                            handled_speaker_token = token
                            _discard_pending_audio(chunks)
                            seen_drops = capture.dropped_frames
                            recognizer.Reset()
                            free_recognizer.Reset()
                            utterance.clear()
                            raw_utterance.clear()
                            gate.until = 0
                            early_wake = trial_partial_wake = False
                            preprocessor.reset()
                            model_failed = False
                            try:
                                if speaker_model is None:
                                    load_started = time.monotonic()
                                    from vosk import SpkModel
                                    data_root = Path(os.environ.get('LUMA_DATA_DIR', '/var/lib/luma'))
                                    speaker_model = SpkModel(str(data_root / 'speaker-model' / 'vosk-model-spk-0.4'))
                                    speaker_model_load_ms = (time.monotonic() - load_started) * 1000
                                trial_recognizer = KaldiRecognizer(model, 16000)
                                trial_recognizer.SetSpkModel(speaker_model)
                            except Exception:
                                model_failed = True
                                speaker_model = None
                            try:
                                client.post('/api/v1/voice/speaker-trial/armed', json={
                                    'session': speaker_state['session'], 'token': token}, timeout=3).raise_for_status()
                            except httpx.HTTPError:
                                next_check = 0.0
                                continue
                            phase('listening')
                            if model_failed:
                                result = {'error': 'model_unavailable'}
                            else:
                                frames, capture_error = collect_speaker_trial_frames(chunks, capture)
                                if capture_error:
                                    result = {'error': capture_error}
                                else:
                                    room_level = float((calibration.get('audio_profile') or {}).get('noise_rms') or 0)
                                    decode_started = time.monotonic()
                                    try:
                                        result = speaker_trial_result(trial_recognizer, frames,
                                                                      noise_rms=room_level)
                                    except Exception:
                                        result = {'error': 'decode_failed'}
                                    result.update(model_load_ms=round(speaker_model_load_ms, 1),
                                                  decode_ms=round((time.monotonic() - decode_started) * 1000, 1),
                                                  rss_kib=voice_process_peak_rss_kib())
                                frames.clear()
                                del frames
                                trial_recognizer = None
                            try:
                                client.post('/api/v1/voice/speaker-trial/observation', json={
                                    'session': speaker_state['session'], 'token': token, **result},
                                    timeout=3).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            _discard_pending_audio(chunks)
                            seen_drops = capture.dropped_frames
                            recognizer.Reset()
                            free_recognizer.Reset()
                            preprocessor.reset()
                            phase('idle')
                            next_check = 0.0
                            continue
                        # Between explicit six-second samples, absorb the mic
                        # stream without running wake or command recognition.
                        try:
                            pending = chunks.get(timeout=.5)
                        except queue.Empty:
                            if capture.stalled():
                                raise AudioCaptureError('capture_stream_stalled')
                            continue
                        if isinstance(pending, AudioCaptureError):
                            raise pending
                        if pending is None:
                            raise AudioCaptureError('capture_stream_stopped')
                        continue
                    if gate.until and now >= gate.until:
                        gate.until = 0
                        phase("idle")
                    try:
                        chunk = chunks.get(timeout=0.5)
                    except queue.Empty:
                        if capture.stalled():
                            raise AudioCaptureError('capture_stream_stalled')
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
                        raw_utterance.clear()
                        calibration_segmenter.reset()
                        early_wake = False
                        trial_partial_wake = False
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
                        if calibration.get('ambient_remaining', 0) > 0:
                            meter_low_fractions.append(low_frequency_fraction(raw_chunk))
                        if now >= next_meter and meter_count:
                            level_rms = math.sqrt(meter_energy / meter_count)
                            level_peak = meter_peak
                            try:
                                client.post("/api/v1/voice/calibration/level", json={
                                    "session": calibration["session"], "rms": level_rms, "peak": level_peak,
                                    "floor_rms": median(meter_floors) if meter_floors else level_rms,
                                    "floor_low_frequency_fraction": (median(meter_low_fractions)
                                                                     if meter_low_fractions else None),
                                }).raise_for_status()
                            except httpx.HTTPError:
                                pass
                            meter_energy = meter_count = meter_peak = 0
                            meter_floors.clear()
                            meter_low_fractions.clear()
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
                        # Acoustic boundaries make this check useful even if
                        # Vosk would never emit an endpoint or any words.
                        payload = calibration_decoding_payload(
                            recognizer, free_recognizer, raw_spoken, spoken,
                            wake_phrase=gate.phrase,
                            noise_rms=float(calibration.get('room_noise_rms') or 0),
                            profile=preprocessor.profile, now=now,
                            adaptations=adaptations)
                        try:
                            client.post("/api/v1/voice/calibration/sample", json={
                                "session": calibration["session"], **payload,
                            }).raise_for_status()
                            next_check = 0.0  # A gain change may restart the quiet-room baseline.
                        except httpx.HTTPError:
                            pass
                        # A/B replay can run slower than live capture on a Pi.
                        # Audio queued during decoding belongs to the old
                        # prompt; do not treat that tail as the next phrase.
                        if capture.dropped_frames > seen_drops:
                            recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        _discard_pending_audio(chunks)
                        recognizer.Reset()
                        free_recognizer.Reset()
                        calibration_segmenter.reset()
                        preprocessor.reset()
                        continue  # Calibration never executes commands.
                    utterance.append(chunk)
                    if len(utterance)>36:
                        utterance.pop(0)  # At most nine seconds of 16 kHz mono audio.
                    if calibration.get('call_trial', {}).get('active'):
                        raw_utterance.append(raw_chunk)
                        if len(raw_utterance) > 36:
                            raw_utterance.pop(0)
                    if not recognizer.AcceptWaveform(chunk):
                        if calibration.get('call_trial', {}).get('active') and not trial_partial_wake:
                            trial_partial_wake = partial_has_wake(
                                recognizer.PartialResult(), gate.phrase)
                        if (not calibration["active"] and not calibration.get('call_trial', {}).get('active')
                                and wake_mode == 'standard' and not early_wake
                                and partial_has_wake(recognizer.PartialResult(), gate.phrase)):
                            # Light the small corner orb while the owner is
                            # still speaking. Only a final, exact wake match
                            # below can dispatch a command.
                            early_wake = True
                            phase("listening")
                        continue
                    text = json.loads(recognizer.Result()).get("text", "")
                    if capture.dropped_frames != seen_drops:
                        # The producer may have overflowed *during* Vosk's
                        # AcceptWaveform/Result call, after the loop's first
                        # gap check but before this decoded text is used.
                        recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        _reset_gapped_decoding(chunks, recognizer, free_recognizer,
                                               preprocessor, gate)
                        utterance.clear()
                        raw_utterance.clear()
                        early_wake = trial_partial_wake = False
                        phase('idle')
                        continue
                    had_early_wake = early_wake
                    early_wake = False
                    spoken=utterance
                    utterance=[]
                    trial = calibration.get('call_trial') or {}
                    if trial.get('active'):
                        raw_spoken = raw_utterance
                        raw_utterance = []
                        observation = call_trial_decoding_payload(
                            text, free_recognizer, spoken, gate.phrase,
                            partial_wake=trial_partial_wake,
                            raw_spoken=(raw_spoken if (preprocessor.profile.gain > 1
                                                        or preprocessor.profile.high_pass) else None),
                            constrained=recognizer)
                        raw_spoken.clear()
                        spoken.clear()
                        trial_partial_wake = False
                        if capture.dropped_frames != seen_drops:
                            recognition_drops += capture.dropped_frames - seen_drops
                            seen_drops = capture.dropped_frames
                            _reset_gapped_decoding(chunks, recognizer, free_recognizer,
                                                   preprocessor, gate)
                            phase('idle')
                            continue  # Do not count a gapped call utterance.
                        try:
                            client.post('/api/v1/voice/call-trial/observation', json={
                                'session': trial['session'], **observation,
                            }).raise_for_status()
                        except httpx.HTTPError:
                            pass
                        recognizer.Reset()
                        gate.until = 0
                        phase('idle')
                        continue  # A call-test utterance can never execute.
                    # The constrained grammar can hallucinate its nearest
                    # allowed phrase over unrelated speech. In the optional
                    # strict mode, a *new* wake must also be present in the
                    # unrestricted transcription before opening the window.
                    new_wake = has_wake(text, gate.phrase)
                    free_text = None
                    if wake_mode == 'dual_decoder' and new_wake:
                        free_text = _unrestricted_transcript(free_recognizer, spoken)
                        if not wake_confirmed(text, free_text, wake_mode, gate.phrase):
                            gate.until = 0
                            recognizer.Reset()
                            phase('idle')
                            continue
                    accepted = gate.accept(text, time.monotonic())
                    if capture.dropped_frames != seen_drops:
                        recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        _reset_gapped_decoding(chunks, recognizer, free_recognizer,
                                               preprocessor, gate)
                        phase('idle')
                        continue
                    if accepted is None:
                        if new_wake and gate.until > time.monotonic():
                            phase('listening')
                        elif had_early_wake and gate.until <= time.monotonic():
                            phase("idle")
                        continue
                    # Light the corner listening state as soon as the
                    # wake phrase is accepted, including one-shot commands.
                    phase("listening")
                    # The constrained recognizer verifies wake. Re-transcribe
                    # just this bounded utterance without a fixed phrase list,
                    # so the local intent model can hear genuine variations.
                    if free_text is None:
                        free_text = _unrestricted_transcript(free_recognizer, spoken)
                    accepted, selection = select_command(accepted, free_text, gate.phrase,
                                                         adaptations)
                    if capture.dropped_frames != seen_drops:
                        # Replaying the unrestricted decoder can take longer
                        # than a live quarter-second frame on a busy Pi.
                        # Check again immediately before feedback or dispatch.
                        recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        _reset_gapped_decoding(chunks, recognizer, free_recognizer,
                                               preprocessor, gate)
                        phase('idle')
                        continue
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
                    if capture.dropped_frames != seen_drops:
                        # Even the phase update is a loopback HTTP call and
                        # can block while capture continues in its thread.
                        recognition_drops += capture.dropped_frames - seen_drops
                        seen_drops = capture.dropped_frames
                        _reset_gapped_decoding(chunks, recognizer, free_recognizer,
                                               preprocessor, gate)
                        phase('idle')
                        continue
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
