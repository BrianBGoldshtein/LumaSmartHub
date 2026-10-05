from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from luma.keyword_wake import (KeywordEvidence, KeywordVerifier, KeywordWakeError,
                              NON_WAKE_KEYWORDS, load_pinned_candidate)
from luma.voice_wake import WakeAudioBuffer


def spotter(*, keyword='HEY_LUMA', timestamps=None):
    stream = SimpleNamespace(accept_waveform=Mock())
    model = SimpleNamespace(create_stream=Mock(return_value=stream),
        is_ready=Mock(side_effect=[True, *([False]*40)]),
        decode_stream=Mock(), keyword_spotter=SimpleNamespace(get_result=Mock(
            return_value=SimpleNamespace(keyword=keyword,
                timestamps=[.02, .04, .06, .08, .10, .12] if timestamps is None else timestamps))),
        reset_stream=Mock())
    return model, stream


def test_fresh_bounded_replay_reports_evidence_not_a_command():
    model, stream = spotter()
    result = KeywordVerifier(model).verify([bytes(8000)])
    assert result == KeywordEvidence(True, .02, .12)
    assert stream.accept_waveform.call_count == 5  # audio + one-second padding
    assert stream.accept_waveform.call_args.args[0] == 16000
    model.create_stream.assert_called_once()
    model.reset_stream.assert_called_once_with(stream)
    model.keyword_spotter.get_result.assert_called_once_with(stream)


def test_no_keyword_is_not_acceptance():
    model, _ = spotter(keyword='')
    assert KeywordVerifier(model).verify([bytes(8000)]) == KeywordEvidence(False)
    model.reset_stream.assert_not_called()


@pytest.mark.parametrize('keyword', sorted(NON_WAKE_KEYWORDS))
def test_acoustic_competitors_are_rejections_not_fuzzy_wake_aliases(keyword):
    model, stream = spotter(keyword=keyword)
    assert KeywordVerifier(model).verify([bytes(8000)]) == KeywordEvidence(False)
    model.reset_stream.assert_called_once_with(stream)


def test_target_cannot_be_assembled_across_words_or_missing_phonemes():
    model, stream = spotter(timestamps=[0, .24, .32, .48, 1.08, 1.16])
    assert KeywordVerifier(model).verify([bytes(8000)]*8) == KeywordEvidence(False)
    model.reset_stream.assert_called_once_with(stream)
    model, _ = spotter(timestamps=[0, .1])
    with pytest.raises(KeywordWakeError, match='keyword_result_invalid'):
        KeywordVerifier(model).verify([bytes(8000)])


def test_stretched_hey_does_not_fail_the_within_name_contiguity_bound():
    model, _ = spotter(timestamps=[0, .7, .8, 1, 1.2, 1.4])
    assert KeywordVerifier(model).verify([bytes(8000)]*8) == KeywordEvidence(True, 0, 1.4)


@pytest.mark.parametrize('frames,complete', [([], True), ([bytes(8000)]*37, True),
    ([b'x'], True), ([bytes(8002)], True), ([b''], True), ([None], True),
    ([bytes(8000)], False), ([bytes(8000)], 1)])
def test_invalid_or_truncated_audio_never_reaches_the_model(frames, complete):
    model, _ = spotter()
    with pytest.raises(KeywordWakeError, match='keyword_audio_invalid'):
        KeywordVerifier(model).verify(frames, complete=complete)
    model.create_stream.assert_not_called()


@pytest.mark.parametrize('times', [[], [float('nan')], [float('inf')], [-.1], [2], [True], [.04,.02]])
def test_invalid_timestamps_fail_closed(times):
    model, _ = spotter(timestamps=times)
    with pytest.raises(KeywordWakeError, match='keyword_result_invalid'):
        KeywordVerifier(model).verify([bytes(8000)])


def test_unexpected_keyword_or_native_failure_never_echoes_exception_data():
    model, _ = spotter(keyword='someone else')
    with pytest.raises(KeywordWakeError, match='keyword_result_invalid'):
        KeywordVerifier(model).verify([bytes(8000)])
    model.create_stream.side_effect = RuntimeError('private upstream details')
    with pytest.raises(KeywordWakeError) as failure:
        KeywordVerifier(model).verify([bytes(8000)])
    assert str(failure.value) == 'keyword_decode_failed'


def test_nonprogressing_decoder_is_bounded():
    model, _ = spotter(keyword='')
    model.is_ready.side_effect = None
    model.is_ready.return_value = True
    with pytest.raises(KeywordWakeError, match='keyword_decode_timeout'):
        KeywordVerifier(model).verify([bytes(8000)])
    assert model.decode_stream.call_count == 2048


def test_buffer_truncation_metadata_cannot_be_overridden_by_default_argument():
    frames = WakeAudioBuffer()
    for _ in range(37):
        frames.append(bytes(8000))
    model, _ = spotter()
    with pytest.raises(KeywordWakeError, match='keyword_audio_invalid'):
        KeywordVerifier(model).verify(frames)
    model.create_stream.assert_not_called()


def test_missing_model_fails_before_importing_optional_runtime(tmp_path):
    with pytest.raises(KeywordWakeError, match='keyword_model_invalid'):
        load_pinned_candidate(tmp_path)
