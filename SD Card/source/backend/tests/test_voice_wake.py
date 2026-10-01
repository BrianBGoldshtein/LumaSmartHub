from luma.voice_wake import has_wake, read_wake_mode, wake_confirmed


def test_dual_decoder_requires_an_independent_explicit_wake():
    assert has_wake('HEY  LUMA, what time is it?')
    assert not has_wake('the lumen is bright')
    assert wake_confirmed('hey luma good morning', 'hey luma good morning', 'dual_decoder')
    assert not wake_confirmed('hey luma good morning', 'the call is going', 'dual_decoder')
    assert not wake_confirmed('hey luma', '', 'dual_decoder')
    assert wake_confirmed('hey luma', '', 'standard')
    assert not wake_confirmed('good morning', 'hey luma good morning', 'standard')


def test_wake_mode_fails_back_to_standard_on_corruption():
    assert read_wake_mode({'version': 1, 'mode': 'dual_decoder'}) == 'dual_decoder'
    for value in (None, 'dual_decoder', {'version': 4, 'mode': 'dual_decoder'},
                  {'version': 1, 'mode': 'unsafe'}):
        assert read_wake_mode(value) == 'standard'
