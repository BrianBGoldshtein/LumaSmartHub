import io
from pathlib import Path
import struct
import sys
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from luma.keyword_wake import KeywordEvidence, KeywordWakeError
from luma.keyword_worker import serve
from luma import keyword_process as process_module
from luma.keyword_process import IsolatedKeywordVerifier


def test_worker_replays_bounded_frames_and_keeps_only_evidence():
    pcm = bytes(9000)
    source = io.BytesIO(struct.pack('>I', len(pcm))+pcm)
    output = io.BytesIO()
    verifier = Mock(verify=Mock(return_value=KeywordEvidence(True, .12, .2)))
    serve(verifier, source, output)
    verifier.verify.assert_called_once_with([bytes(8000), bytes(1000)])
    assert output.getvalue() == b'KWS02\n'+struct.pack('>Bdd', 1, .12, .2)


@pytest.mark.parametrize('length', [0, 1, 288002, 4294967295])
def test_worker_rejects_header_before_reading_any_payload(length):
    source = io.BytesIO(struct.pack('>I', length)+b'private payload')
    verifier = Mock()
    output = io.BytesIO()
    serve(verifier, source, output)
    assert source.tell() == 4
    verifier.verify.assert_not_called()
    assert output.getvalue() == b'KWS02\n'


def test_worker_exception_exposes_no_library_details_and_next_request_is_fresh():
    verifier = Mock(verify=Mock(side_effect=[RuntimeError('secret'), KeywordEvidence(False)]))
    output = io.BytesIO()
    serve(verifier, io.BytesIO((struct.pack('>I', 2)+bytes(2))*2), output)
    assert output.getvalue() == b'KWS02\n'+struct.pack('>Bdd', 2, -1, -1)+struct.pack('>Bdd', 0, -1, -1)


@pytest.fixture
def controller(tmp_path, monkeypatch):
    if sys.platform != 'linux':
        pytest.skip('production POSIX pipe transport')
    script = tmp_path / 'fake worker.py'
    monkeypatch.setattr(process_module, 'WORKER_PATH', script)
    monkeypatch.setattr(process_module, 'START_SECONDS', .3)
    monkeypatch.setattr(process_module, 'DECODE_SECONDS', .3)
    instance = IsolatedKeywordVerifier(Path(sys.executable), tmp_path)
    children = []
    original_popen = process_module.subprocess.Popen
    def track_child(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(process_module.subprocess, 'Popen', track_child)
    def configure(code):
        script.write_text(code, encoding='utf-8')
        return instance
    yield configure
    instance.close()
    assert all(child.poll() is not None for child in children), 'worker must be reaped, not merely forgotten'


READER = '''import sys, struct
source=sys.stdin.buffer
out=sys.stdout.buffer
out.write(b'KWS02\\n'); out.flush()
while True:
    raw=source.read(4)
    if not raw: break
    length=struct.unpack('>I',raw)[0]
    if len(source.read(length))!=length: break
'''


def test_real_worker_reuses_process_and_explicit_close_reaps_it(controller):
    instance = controller(READER+"    out.write(struct.pack('>Bdd',1,.02,.12)); out.flush()\n")
    assert instance.verify([bytes(8000)]) == KeywordEvidence(True, .02, .12)
    child = instance.process
    assert instance.verify([bytes(8000)]) == KeywordEvidence(True, .02, .12)
    assert instance.process is child
    instance.close()
    assert child.poll() is not None
    assert child.stdin.closed and child.stdout.closed


def test_warmup_precedes_capture_reuses_healthy_child_and_reaps_a_dead_one(controller):
    instance = controller(READER+"    out.write(struct.pack('>Bdd',0,-1,-1)); out.flush()\n")
    assert instance.prepare() is True
    first = instance.process
    assert instance.prepare() is False
    assert instance.process is first
    first.kill(); first.wait(timeout=2)
    assert instance.prepare() is True
    assert instance.process is not first and first.stdin.closed and first.stdout.closed
    assert instance.verify([bytes(8000)]) == KeywordEvidence(False)


@pytest.mark.parametrize('during', ['prepare','verify'])
def test_service_exit_during_native_transport_always_reaps_worker(controller, monkeypatch, during):
    instance = controller(READER+"    out.write(struct.pack('>Bdd',0,-1,-1)); out.flush()\n")
    if during == 'verify': instance.prepare()
    monkeypatch.setattr(process_module,'_transfer',Mock(side_effect=SystemExit(0)))
    with pytest.raises(SystemExit):
        instance.prepare() if during == 'prepare' else instance.verify([bytes(8000)])
    assert instance.process is None


@pytest.mark.parametrize('script,code', [
    ("import time; time.sleep(10)", 'keyword_start_timeout'),
    ("import sys,time; sys.stdout.buffer.write(b'KWS02\\n'); sys.stdout.buffer.flush(); time.sleep(10)", 'keyword_decode_timeout'),
    (READER+"    import time; time.sleep(10)\n", 'keyword_decode_timeout'),
])
def test_real_native_hang_or_blocked_pipe_is_killed_with_backoff(controller, script, code):
    instance = controller(script)
    started = monotonic()
    with pytest.raises(KeywordWakeError, match=code):
        # Large enough to fill a pipe whose worker never reads.
        instance.verify([bytes(8000)]*36)
    assert monotonic()-started < 2
    assert instance.process is None and instance.last_error == code
    with pytest.raises(KeywordWakeError, match='keyword_retry_wait'):
        instance.verify([bytes(8000)])


@pytest.mark.parametrize('status,timestamp,last', [(1,float('nan'),.2), (1,9,9), (0,0,-1), (3,-1,-1), (2,0,-1), (1,.2,.1), (1,.1,-1), (0,-1,0), (1,.1,float('nan'))])
def test_real_malformed_output_cannot_accept_a_wake(controller, status, timestamp, last):
    instance = controller(READER+f"    out.write(struct.pack('>Bdd',{status},{timestamp!r},{last!r})); out.flush()\n".replace('nan', "float('nan')"))
    with pytest.raises(KeywordWakeError, match='keyword_result_invalid'):
        instance.verify([bytes(8000)])
    assert instance.process is None


def test_worker_fixed_error_and_early_eof_fail_closed(controller):
    instance = controller(READER+"    out.write(struct.pack('>Bdd',2,-1,-1)); out.flush()\n")
    with pytest.raises(KeywordWakeError, match='keyword_decode_failed'):
        instance.verify([bytes(8000)])
    instance.retry_after = 0
    controller("import sys; sys.stdout.buffer.write(b'KWS02\\n'); sys.stdout.buffer.flush()")
    with pytest.raises(KeywordWakeError, match='keyword_worker_failed'):
        instance.verify([bytes(8000)])


def test_invalid_input_does_not_start_or_kill_a_healthy_worker(controller):
    instance = controller(READER+"    out.write(struct.pack('>Bdd',0,-1,-1)); out.flush()\n")
    with pytest.raises(KeywordWakeError, match='keyword_audio_invalid'):
        instance.verify([bytes(8000)], complete=False)
    assert instance.process is None
    assert instance.verify([bytes(8000)]) == KeywordEvidence(False)
    child = instance.process
    with pytest.raises(KeywordWakeError, match='keyword_audio_invalid'):
        instance.verify([])
    assert instance.process is child and child.poll() is None


def test_old_worker_protocol_is_rejected_not_silently_misparsed(controller):
    instance = controller("import sys; sys.stdout.buffer.write(b'READY\\n'); sys.stdout.buffer.flush()")
    with pytest.raises(KeywordWakeError, match='keyword_start_failed'):
        instance.verify([bytes(8000)])
    assert instance.process is None
