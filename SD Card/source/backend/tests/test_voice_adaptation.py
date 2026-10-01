from luma.voice_adaptation import (PhraseAdaptations, conflicts_with_existing_command,
                                   normalized_phrase)


def test_personal_phrase_map_saves_only_a_keyed_digest_and_safe_target():
    learned = PhraseAdaptations()
    assert learned.add('whats the tea', 'what time is it')
    assert learned.resolve('Whats, the tea!') == 'what time is it'
    saved = learned.public()
    assert 'whats the tea' not in str(saved)
    assert PhraseAdaptations(saved).resolve('whats the tea') == 'what time is it'
    assert not learned.add('whats the tea', 'good morning')
    assert not learned.add('set brightness zero', 'set brightness to fifty')
    assert not learned.add('do not say good morning', 'good morning')
    assert normalized_phrase('a') == ''


def test_learning_never_hijacks_an_existing_valid_command():
    learned = PhraseAdaptations()
    assert conflicts_with_existing_command('good morning', 'what time is it')
    assert not learned.add('good morning', 'what time is it')
    assert not learned.add('change theme to hearth', 'change theme to arcade')
    assert not conflicts_with_existing_command("what's the time", 'what time is it')
    # A prior saved digest must also fail closed when the parser gains a new
    # interpretation in a later release.
    digest = learned._digest('good morning')
    learned.entries[digest] = 'what time is it'
    assert learned.resolve('good morning') is None


def test_corrupt_personal_phrase_map_fails_closed():
    learned = PhraseAdaptations()
    assert learned.add('the whether tomorrow', "what's the weather tomorrow")
    saved = learned.public()
    saved['entries'][next(iter(saved['entries']))] = 'set volume to one hundred'
    assert not PhraseAdaptations(saved).entries
    assert not PhraseAdaptations({'version': 1, 'salt': 'bad', 'entries': {}}).entries
