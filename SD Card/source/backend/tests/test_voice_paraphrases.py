"""Held-out everyday wordings; not added to neural training rows."""
import pytest

from luma.models import CommandName
from luma.voice import parse_local_command


@pytest.mark.parametrize("phrase,intent", [
    ("what time is it", "time"),
    ("what's the time", "time"),
    ("could you tell me the time", "time"),
    ("tell me the current time", "time"),
    ("what's the time now", "time"),
    ("what's the weather tomorrow", "weather_tomorrow"),
    ("how's the weather tomorrow", "weather_tomorrow"),
    ("tell me tomorrow's forecast", "weather_tomorrow"),
    ("will it rain tomorrow", "rain_tomorrow"),
    ("when is my next event", "next_event"),
    ("when's my next event", "next_event"),
    ("what's on my calendar today", "calendar_today"),
    ("what's on my agenda today", "calendar_today"),
    ("what do i have going on today", "calendar_today"),
    ("what are my tasks today", "tasks_today"),
    ("what tasks are due today", "tasks_due"),
    ("is my phone connected", "phone_status"),
    ("how much time is left on my timer", "timer_status"),
])
def test_safe_query_variants(phrase, intent):
    command = parse_local_command(phrase)
    assert command is not None
    assert (command.name, command.value) == (CommandName.LOCAL_QUERY, intent)


@pytest.mark.parametrize("phrase,name", [
    ("good morning", CommandName.GOOD_MORNING),
    ("good night", CommandName.GOOD_NIGHT),
    ("show the weather", CommandName.SHOW_PAGE),
    ("open my calendar", CommandName.SHOW_PAGE),
    ("make the screen brighter", CommandName.SHOW_BRIGHTNESS),
    ("turn down the volume", CommandName.SHOW_VOLUME),
    ("start a ten minute timer", CommandName.START_TIMER),
    ("set a timer for ten minutes", CommandName.START_TIMER),
    ("switch to the arcade theme", CommandName.SET_THEME),
])
def test_action_variants(phrase, name):
    command = parse_local_command(phrase)
    assert command is not None and command.name == name


@pytest.mark.parametrize("phrase", [
    "don't set brightness to zero",
    "do not turn the screen off",
    "what's the weather next month",
    "tell me my calendar yesterday",
    "turn it down",  # ambiguous target: screen, volume, speaker or appliance
])
def test_ambiguous_or_unsupported_phrases_do_not_mutate(phrase):
    command = parse_local_command(phrase)
    assert command is None or command.name == CommandName.LOCAL_QUERY
