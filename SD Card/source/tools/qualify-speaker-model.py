#!/usr/bin/env python3
"""Disposable desktop API smoke for Vosk's pinned offline speaker model.

This does not enroll an owner, prove speaker identity, or benchmark a Pi 4.
It checks the official archive, its layout, Vosk loading, and one synthetic
vector through the same bounded decoder intended for future guided trials.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import io
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen
import zipfile


URL = 'https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip'
SHA256 = 'a74d8f51144484813e16af689bb0f916b7a111e2347f467c4933c1166097b5a7'
MAX_ARCHIVE = 16 * 1024 * 1024
ROOT = 'vosk-model-spk-0.4'
EXPECTED = {ROOT + '/', *(f'{ROOT}/{name}' for name in (
    'mfcc.conf', 'README.txt', 'mean.vec', 'transform.mat', 'final.ext.raw'))}


def read_archive(path: Path | None) -> bytes:
    if path is not None:
        if path.stat().st_size > MAX_ARCHIVE:
            raise ValueError('speaker archive exceeds the pinned size limit')
        data = path.read_bytes()
    else:
        with urlopen(URL, timeout=30) as response:
            if response.geturl() != URL:
                raise ValueError('speaker archive redirected unexpectedly')
            data = response.read(MAX_ARCHIVE + 1)
    if len(data) > MAX_ARCHIVE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('speaker archive differs from the pinned official model')
    return data


def resample_16k(pcm: bytes, source_rate: int) -> bytes:
    if source_rate == 16000:
        return pcm
    if not 8000 <= source_rate <= 48000 or len(pcm) % 2:
        raise ValueError('unsupported synthetic speech format')
    source = array('h')
    source.frombytes(pcm)
    if sys.byteorder != 'little':
        source.byteswap()
    length = round(len(source) * 16000 / source_rate)
    output = array('h')
    for index in range(length):
        position = index * source_rate / 16000
        left = min(int(position), len(source) - 1)
        right = min(left + 1, len(source) - 1)
        fraction = position - left
        output.append(round(source[left] * (1 - fraction) + source[right] * fraction))
    if sys.byteorder != 'little':
        output.byteswap()
    return output.tobytes()


def qualify(archive_bytes: bytes, vosk_model_path: Path) -> dict:
    from vosk import KaldiRecognizer, Model, SetLogLevel, SpkModel

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend/src'))
    from luma.voice_speaker import decode_speaker_observation
    from luma.voice_speech import fallback_wav_to_pcm

    with TemporaryDirectory(prefix='luma-speaker-smoke-') as temporary:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            if set(archive.namelist()) != EXPECTED or archive.testzip() is not None:
                raise ValueError('speaker archive layout or CRC is invalid')
            archive.extractall(temporary)
        SetLogLevel(-1)
        speech_model = Model(str(vosk_model_path))
        speaker_model = SpkModel(str(Path(temporary) / ROOT))
        audio = subprocess.run(
            ['espeak-ng', '--stdout', '-v', 'en-us', '-s', '155', '--stdin'],
            input=(b'Hey Luma, please tell me whether rain is coming tomorrow '
                   b'afternoon and when my next meeting begins.'),
            check=True, capture_output=True, timeout=20).stdout
        pcm, rate = fallback_wav_to_pcm(audio)
        pcm = resample_16k(pcm, rate)
        frames = [pcm[index:index + 8000] for index in range(0, len(pcm), 8000)]
        recognizer = KaldiRecognizer(speech_model, 16000)
        recognizer.SetSpkModel(speaker_model)
        observation = decode_speaker_observation(recognizer, frames)
        return {'model_sha256': SHA256, 'vector_dimensions': len(observation.vector),
                'spk_frames': observation.spk_frames,
                'sample_seconds': round(observation.input_seconds, 2)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='previously downloaded official ZIP')
    parser.add_argument('--vosk-model', required=True, type=Path,
                        help='existing English Vosk speech model directory')
    args = parser.parse_args()
    print(qualify(read_archive(args.archive), args.vosk_model))


if __name__ == '__main__':
    main()
