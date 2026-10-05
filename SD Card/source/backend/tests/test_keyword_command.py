from array import array
import json
from unittest.mock import Mock

import pytest

from luma.keyword_command import TimedTranscript, TimedWord, command_after_keyword, timed_transcript
from luma.keyword_wake import KeywordEvidence, KeywordWakeError
from luma.voice import WakeGate
from luma.voice_agent import accept_acoustic_utterance, select_command
from luma.voice_wake import WakeAudioBuffer


def frames():
    result = WakeAudioBuffer()
    for _ in range(12):
        result.append(array('h', [1000]*4000).tobytes())
    return result


def recognizer(words):
    decoder = Mock()
    decoder.AcceptWaveform.return_value = False
    decoder.FinalResult.return_value = json.dumps({'text':' '.join(word[0] for word in words),
        'result':[{'word':word, 'start':start, 'end':end, 'conf':.9} for word,start,end in words]})
    return decoder


def test_fresh_word_timing_never_uses_a_live_endpoint_cumulative_clock():
    decoder = recognizer([('hey', .1, .3), ('lunar', .3, .7), ('what', .72, .9), ('time', .9, 1.1)])
    factory = Mock(return_value=decoder)
    result = timed_transcript(factory, frames())
    assert result.text == 'hey lunar what time'
    assert result.words[2] == TimedWord('what', .72, .9)
    factory.assert_called_once_with()
    decoder.Reset.assert_not_called()
    decoder.SetWords.assert_called_once_with(True)
    assert command_after_keyword(result, KeywordEvidence(True,.1,.6), duration=3) == 'what time'


@pytest.mark.parametrize('payload', [None, 'secret upstream', '{}', '[]',
    '{"text":"start timer"}', '{"text":"hidden","result":[]}',
    '{"text":"timer","result":[{"word":"timer","start":true,"end":1}]}',
    '{"text":"timer","result":[{"word":"timer","start":-1,"end":1}]}',
    '{"text":"timer","result":[{"word":"timer","start":1,"end":9}]}',
    '{"text":"timer","result":[{"word":"timer","start":1,"end":0}]}',
    '{"text":"timer","result":[{"word":"timer","start":NaN,"end":1}]}',
])
def test_invalid_or_untimed_asr_never_leaks_words_or_qualifies_a_command(payload):
    decoder = recognizer([])
    decoder.FinalResult.return_value = payload
    # An actually empty ASR result is legitimate wake-only evidence; a bare
    # empty dictionary is also the engine's normal silence representation.
    if payload == '{}':
        assert timed_transcript(lambda:decoder, frames()).text == ''
    else:
        with pytest.raises(KeywordWakeError, match='^keyword_alignment_unavailable$'):
            timed_transcript(lambda:decoder, frames())


def test_endpoint_chunks_must_agree_with_word_metadata_and_remain_in_order():
    decoder = recognizer([('timer', .8, 1.1)])
    decoder.AcceptWaveform.side_effect = [True]+[False]*11
    decoder.Result.return_value = json.dumps({'text':'start', 'result':[{'word':'start','start':.6,'end':.8}]})
    assert timed_transcript(lambda:decoder, frames()).text == 'start timer'
    decoder.AcceptWaveform.side_effect = [True]+[False]*11
    decoder.FinalResult.return_value = json.dumps({'text':'timer','result':[{'word':'timer','start':.4,'end':.5}]})
    with pytest.raises(KeywordWakeError):
        timed_transcript(lambda:decoder, frames())


def test_prefix_allows_hesitation_but_not_short_quoted_or_negated_wakes():
    evidence = KeywordEvidence(True,.4,.9)
    for prefix in ('i', "don't", 'said', '[unk]'):
        transcript = TimedTranscript('', (TimedWord(prefix,0,.2),TimedWord('what',1,1.2)))
        with pytest.raises(KeywordWakeError, match='keyword_prefix_rejected'):
            command_after_keyword(transcript,evidence,duration=3)
    transcript = TimedTranscript('', (TimedWord('okay',0,.2),TimedWord('what',1,1.2)))
    assert command_after_keyword(transcript,evidence,duration=3) == 'what'


def test_boundary_never_drops_negation_by_guessing_wake_word_end():
    evidence = KeywordEvidence(True,.1,.6)
    words = (TimedWord('hey',.1,.3),TimedWord('lunar',.3,.55),TimedWord("don't",.57,.75),
             TimedWord('start',.76,.9),TimedWord('timer',.9,1.2))
    assert command_after_keyword(TimedTranscript('',words),evidence,duration=3) == "don't start timer"
    overlapped = words[:2]+(TimedWord("don't",.49,.7),)+words[3:]
    with pytest.raises(KeywordWakeError, match='keyword_negation_overlap'):
        command_after_keyword(TimedTranscript('',overlapped),evidence,duration=3)


def test_boundary_keeps_real_timer_verb_with_different_frame_alignment():
    transcript = TimedTranscript('',(TimedWord('hey',.06,.27),TimedWord('luma',.27,.63),
        TimedWord('start',.63,1.2),TimedWord('a',1.23,1.35),TimedWord('timer',1.35,1.8)))
    assert command_after_keyword(transcript,KeywordEvidence(True,0,.68),duration=3) == 'start a timer'


def test_only_independent_prefix_judgment_can_reject_a_natural_hesitation():
    evidence = KeywordEvidence(True,.56,1)
    fixed = TimedTranscript('',(TimedWord('hey',.18,.42),TimedWord('hey',.42,.66),
        TimedWord('luma',.66,1.05),TimedWord('what',1.05,1.32)))
    with pytest.raises(KeywordWakeError,match='keyword_prefix_rejected'):
        command_after_keyword(fixed,evidence,duration=3)
    assert command_after_keyword(fixed,evidence,duration=3,check_prefix=False) == 'what'


@pytest.mark.parametrize('evidence', [KeywordEvidence(False),KeywordEvidence(True,.1,None),
    KeywordEvidence(True,.6,.1),KeywordEvidence(True,.1,4),KeywordEvidence(True,float('nan'),.5)])
def test_missing_invalid_or_padding_only_boundary_never_opens_window(evidence):
    with pytest.raises(KeywordWakeError):
        command_after_keyword(TimedTranscript('',()),evidence,duration=3)


def test_acoustic_wake_does_not_require_constrained_or_free_name_spelling():
    decoder = recognizer([('hey',.1,.3),('lunar',.3,.7),('what',.72,.9),('time',.9,1.1),('is',1.1,1.2),('it',1.2,1.3)])
    fixed = recognizer([('hey',.1,.3),('luma',.3,.7),('what',.72,.9),('time',.9,1.1),('is',1.1,1.2),('it',1.2,1.3)])
    gate = WakeGate()
    verifier = Mock(verify=Mock(return_value=KeywordEvidence(True,.1,.6)))
    accepted, free, discard = accept_acoustic_utterance('unrelated constrained result',frames(),lambda:fixed,lambda:decoder,gate,100,verifier)
    assert (accepted,free,discard) == ('what time is it','hey luma what time is it',False)
    assert gate.until == 0
    assert select_command(accepted,free,gate.phrase) == ('what time is it','agree')


def test_verified_wake_only_never_dispatches_a_grammar_hallucination():
    gate = WakeGate()
    fixed = recognizer([('hey',.1,.3),('luma',.3,.7),('start',.72,.9),('timer',.9,1.1)])
    free = recognizer([('hey',.1,.3),('lunar',.3,.7)])
    verifier = Mock(verify=Mock(return_value=KeywordEvidence(True,.1,.6)))
    assert accept_acoustic_utterance('hey luma start timer',frames(),lambda:fixed,lambda:free,gate,100,verifier) == ('','hey luma',False)
    assert gate.until == 107


def test_rejected_wake_closes_old_followup_without_asr_or_feedback():
    gate = WakeGate(); gate.until = 107
    fixed, free = Mock(), Mock()
    verifier = Mock(verify=Mock(return_value=KeywordEvidence(False)))
    assert accept_acoustic_utterance('hey luma start timer',frames(),fixed,free,gate,100,verifier) == (None,None,True)
    fixed.Reset.assert_not_called(); free.Reset.assert_not_called()
    assert gate.until == 0


def test_one_followup_consumes_window_and_does_not_reopen_from_text():
    gate = WakeGate(); gate.until = 107
    verifier = Mock(verify=Mock(return_value=KeywordEvidence(False)))
    assert accept_acoustic_utterance('what time is it',frames(),Mock(),Mock(),gate,103,verifier) == ('what time is it',None,False)
    assert gate.until == 0
    assert accept_acoustic_utterance('what time is it',frames(),Mock(),Mock(),gate,104,verifier) == (None,None,False)


def test_truncated_unavailable_and_invalid_native_result_fail_closed():
    gate = WakeGate(); gate.until = 107
    assert accept_acoustic_utterance('hey luma',frames(),Mock(),Mock(),gate,100,None) == (None,None,True)
    assert gate.until == 0
    audio = frames(); audio.complete = False
    verifier = Mock()
    assert accept_acoustic_utterance('hey luma',audio,Mock(),Mock(),gate,100,verifier) == (None,None,True)
    verifier.verify.assert_not_called()
