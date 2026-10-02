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


def test_two_confirmed_variants_are_saved_atomically():
    learned = PhraseAdaptations()
    assert learned.add_many(['whats the tea', 'whats the tee'], 'what time is it')
    assert learned.resolve('whats the tea') == 'what time is it'
    assert learned.resolve('whats the tee') == 'what time is it'
    before = learned.public()
    assert not learned.add_many(['another variation', 'good morning'], 'what time is it')
    assert learned.public() == before
    assert not learned.add_many(['one', 'two', 'three'], 'what time is it')


def test_two_confirmed_mishearings_generalize_only_to_close_safe_variants():
    learned = PhraseAdaptations()
    assert learned.add_many(['whats the tea', 'whats the tee'], 'what time is it')
    assert learned.resolve('whats the te') == 'what time is it'
    assert learned.resolve('whats the weather') is None
    saved = learned.public()
    assert 'whats the tea' not in str(saved)
    assert 'whats the tee' not in str(saved)
    assert PhraseAdaptations(saved).resolve('whats the te') == 'what time is it'
    assert len(saved['families']) == 1


def test_one_confirmed_example_does_not_enable_approximate_matching():
    learned = PhraseAdaptations()
    assert learned.add('whats the tea', 'what time is it')
    assert learned.resolve('whats the tea') == 'what time is it'
    assert learned.resolve('whats the te') is None
    assert learned.public()['families'] == []


def test_fuzzy_correction_never_reinterprets_supported_commands():
    learned = PhraseAdaptations()
    assert learned.add_many(['how is the whether', 'hows the whether'],
                            "what's the weather tomorrow")
    assert learned.resolve('what is the weather today') is None
    assert learned.resolve('set volume to fifty') is None
    assert learned.resolve('do not show my calendar') is None
    assert learned.resolve('whats not the tea') is None
    assert learned.resolve('whats the tea 2') is None


def test_corrupt_fuzzy_fingerprints_fail_closed():
    learned = PhraseAdaptations()
    assert learned.add_many(['whats the tea', 'whats the tee'], 'what time is it')
    saved = learned.public()
    saved['families'][0]['variants'][0] = ['not-a-hash']
    restored = PhraseAdaptations(saved)
    assert not restored.entries and not restored.families


def test_corrupt_personal_phrase_map_fails_closed():
    learned = PhraseAdaptations()
    assert learned.add('the whether tomorrow', "what's the weather tomorrow")
    saved = learned.public()
    saved['entries'][next(iter(saved['entries']))] = 'set volume to one hundred'
    assert not PhraseAdaptations(saved).entries
    assert not PhraseAdaptations({'version': 1, 'salt': 'bad', 'entries': {}}).entries
