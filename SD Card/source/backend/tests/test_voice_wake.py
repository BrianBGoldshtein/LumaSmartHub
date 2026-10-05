from luma.voice_wake import WakeAudioBuffer, has_wake, read_wake_mode, wake_confirmed, wake_near_start


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
    assert not wake_near_start('[unk] um hey luma what time is it')
    assert wake_near_start('okay hey luma what time is it')
    assert not wake_near_start('I told my friend hey luma yesterday')
    assert not wake_near_start('can you say hey luma for me')
    assert not wake_near_start('um please uh hey luma')
    assert not wake_confirmed('hey luma good morning',
                              'I heard hey luma on the call', 'dual_decoder')
    assert not wake_confirmed('the caller said hey luma good morning',
                              'hey luma good morning', 'dual_decoder')
    assert not wake_confirmed('the caller said hey luma good morning', '', 'standard')


def test_wake_mode_defaults_and_legacy_settings_migrate_to_acoustic_protection():
    assert read_wake_mode({'version': 3, 'mode': 'acoustic'}) == 'acoustic'
    assert read_wake_mode({'version': 2, 'mode': 'standard'}) == 'standard'
    assert read_wake_mode({'version': 2, 'mode': 'dual_decoder'}) == 'acoustic'
    for mode in ('standard','dual_decoder','acoustic'):
        assert read_wake_mode({'version': 3, 'mode': mode}) == mode
    for value in (None, 'dual_decoder', {'version': 4, 'mode': 'dual_decoder'},
                  {'version': 1, 'mode': 'unsafe'}, {'version': 1, 'mode': 'standard'},
                  {'version': 1, 'mode': 'dual_decoder'}):
        assert read_wake_mode(value) == 'acoustic'
    assert read_wake_mode({'version': 2, 'mode': 'acoustic'}) == 'acoustic'
    assert read_wake_mode({'version': 3.0, 'mode': 'standard'}) == 'acoustic'


def test_long_conversation_cannot_be_verified_using_only_its_tail():
    frames = WakeAudioBuffer()
    for _ in range(37):
        frames.append(bytes(8000))
    assert len(frames) == 36 and not frames.complete
    for mode in ('standard', 'dual_decoder'):
        assert not wake_confirmed('hey luma good morning', 'hey luma good morning', mode,
                                  complete=frames.complete)
    frames.clear()
    frames.append(bytes(8000))
    assert frames.complete


def test_invalid_mode_fails_closed_and_no_fuzzy_wake_alias_is_accepted():
    assert not wake_confirmed('hey luma', '', 'corrupt')
    for phrase in ('hey laura', 'hey lou', 'a lumen', 'they bloom at',
                   'my friend says hey luma', '[unk] hey luma'):
        assert not wake_confirmed('hey luma good morning', phrase, 'dual_decoder')
