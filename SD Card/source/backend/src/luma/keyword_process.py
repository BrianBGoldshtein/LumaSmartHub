"""Killable acoustic wake verifier; optional native code stays isolated.

Only trusted installer-provided paths may construct this controller. It does
not download/install assets, choose commands or establish owner presence.
Optional native dependencies stay outside the application's interpreter.
"""
from contextlib import suppress
import math
import os
from pathlib import Path
import selectors
import struct
import subprocess
from time import monotonic

from .keyword_wake import KeywordEvidence, KeywordWakeError, validate_audio

WORKER_PATH = Path(__file__).with_name('keyword_worker.py')
START_SECONDS = 45.0
DECODE_SECONDS = 5.0
RETRY_SECONDS = 30.0


def _transfer(pipe, *, length=None, data=None, deadline):
    """Nonblocking reads AND writes; a worker not reading cannot hang us."""
    descriptor = pipe.fileno()
    os.set_blocking(descriptor, False)
    writing = data is not None
    size = len(data) if writing else length
    result = bytearray()
    offset = 0
    with selectors.DefaultSelector() as selector:
        selector.register(descriptor, selectors.EVENT_WRITE if writing else selectors.EVENT_READ)
        while offset < size:
            remaining = deadline - monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError
            try:
                if writing:
                    count = os.write(descriptor, memoryview(data)[offset:offset+65536])
                else:
                    block = os.read(descriptor, size-offset)
                    count = len(block)
                    result.extend(block)
            except BlockingIOError:
                continue
            if not count:
                raise EOFError
            offset += count
    return bytes(result)


class IsolatedKeywordVerifier:
    def __init__(self, interpreter: Path, model_directory: Path):
        self.interpreter = interpreter
        self.model_directory = model_directory
        self.process = None
        self.retry_after = 0.0
        self.last_error = None

    def close(self):
        process, self.process = self.process, None
        if process is None:
            return
        # No graceful wait on a native deadlock. Kill, reap, close both pipes.
        with suppress(OSError):
            process.kill()
        with suppress(OSError, subprocess.SubprocessError):
            process.wait(timeout=2)
        for pipe in (process.stdin, process.stdout):
            if pipe:
                with suppress(OSError):
                    pipe.close()

    def _start(self):
        self.process = subprocess.Popen(
            [str(self.interpreter), '-I', str(WORKER_PATH), str(self.model_directory)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, close_fds=True)
        marker = _transfer(self.process.stdout, length=6, deadline=monotonic()+START_SECONDS)
        if marker != b'KWS02\n':
            raise KeywordWakeError('keyword_start_failed')

    def prepare(self):
        """Load BEFORE listening, not halfway through a captured command.

        Callers must discard capture queued during this bounded warm-up. A
        dead worker is reaped even on an interpreter exit or signal exception.
        """
        if monotonic() < self.retry_after:
            raise KeywordWakeError('keyword_retry_wait')
        if self.process is not None:
            if self.process.poll() is None:
                return False
            self.close()
        try:
            self._start()
            self.last_error = None
            return True
        except BaseException as error:
            self.close()
            self.retry_after = monotonic() + RETRY_SECONDS
            if not isinstance(error, Exception):
                raise
            code = (str(error) if isinstance(error, KeywordWakeError) else
                    'keyword_start_timeout' if isinstance(error, TimeoutError) else 'keyword_worker_failed')
            self.last_error = code
            raise KeywordWakeError(code) from None

    def verify(self, frames, *, complete=True):
        seconds = validate_audio(frames, complete=complete)
        if monotonic() < self.retry_after:
            raise KeywordWakeError('keyword_retry_wait')
        starting = self.process is None
        stage = 'startup' if starting else 'decode'
        try:
            if starting:
                self._start()
            stage = 'decode'
            pcm = b''.join(frames)
            deadline = monotonic() + DECODE_SECONDS
            _transfer(self.process.stdin, data=struct.pack('>I', len(pcm))+pcm, deadline=deadline)
            status, timestamp, last = struct.unpack('>Bdd', _transfer(
                self.process.stdout, length=17, deadline=deadline))
            if status == 2 and timestamp == last == -1:
                raise KeywordWakeError('keyword_decode_failed')
            if (status not in (0, 1) or not math.isfinite(timestamp) or not math.isfinite(last)
                    or (status == 0 and (timestamp != -1 or last != -1))
                    or (status == 1 and not 0 <= timestamp <= last <= seconds+1)):
                raise KeywordWakeError('keyword_result_invalid')
            self.last_error = None
            return KeywordEvidence(bool(status), timestamp if status else None,
                                   last if status else None)
        except BaseException as error:
            self.close()
            self.retry_after = monotonic() + RETRY_SECONDS
            if not isinstance(error, Exception):
                raise
            if isinstance(error, KeywordWakeError):
                code = str(error)
            elif isinstance(error, TimeoutError):
                code = 'keyword_start_timeout' if stage == 'startup' else 'keyword_decode_timeout'
            else:
                code = 'keyword_worker_failed'
            self.last_error = code
            raise KeywordWakeError(code) from None
