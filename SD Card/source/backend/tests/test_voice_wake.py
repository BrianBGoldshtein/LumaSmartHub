from luma.voice_wake import has_wake, read_wake_mode, wake_confirmed, wake_near_start


def test_dual_decoder_requires_an_independent_explicit_wake():
    assert has_wake('HEY  LUMA, what time is it?')
    assert not has_wake('the lumen is bright')
    assert wake_confirmed('hey luma good morning', 'hey luma good morning', 'dual_decoder')
    assert not wake_confirmed('hey luma good morning', 'the call is going', 'dual_decoder')
    assert not wake_confirmed('hey luma', '', 'dual_decoder')
    assert wake_confirmed('hey luma', '', 'standard')
    assert not wake_confirmed('good morning', 'hey luma good morning', 'standard')


def test_strict_wake_must_lead_the_utterance_not_appear_in_quoted_call_audio():
    assert wake_near_start('hey luma what time is it')
    assert wake_near_start('[unk] um hey luma what time is it')
    assert wake_near_start('okay hey luma what time is it')
    assert not wake_near_start('I told my friend hey luma yesterday')
    assert not wake_near_start('can you say hey luma for me')
    assert not wake_near_start('um please uh hey luma')
    assert not wake_confirmed('hey luma good morning',
                              'I heard hey luma on the call', 'dual_decoder')
    assert not wake_confirmed('the caller said hey luma good morning',
                              'hey luma good morning', 'dual_decoder')
    # Standard mode stays as shipped while strict-mode recall needs a Pi trial.
    assert wake_confirmed('the caller said hey luma good morning', '', 'standard')


def test_wake_mode_fails_back_to_standard_on_corruption():
    assert read_wake_mode({'version': 1, 'mode': 'dual_decoder'}) == 'dual_decoder'
    for value in (None, 'dual_decoder', {'version': 4, 'mode': 'dual_decoder'},
                  {'version': 1, 'mode': 'unsafe'}):
        assert read_wake_mode(value) == 'standard'
