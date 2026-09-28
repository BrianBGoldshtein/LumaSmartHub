from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from luma.display_cycle import DisplayCycle, ramp_level
from luma.storage import Storage

NOW = datetime(2026, 9, 26, 15, tzinfo=UTC)


class Clock:
    value = 1000.
    def __call__(self):
        return self.value
    def advance(self, seconds):
        self.value += seconds


def engine(tmp_path):
    clock = Clock()
    return DisplayCycle(Storage(tmp_path/'display.db'), clock=clock), clock


def sync(display, now=NOW, end=None, **changes):
    return display.sync(now, **({'sleep_end': end, 'brightness': 70, 'night_brightness': 5,
                                'night_clock': True, 'trusted': True} | changes))


def test_scheduled_wake_starts_at_end_and_takes_five_minutes(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    for seconds in (0, 1800, 3599):
        state = sync(display, NOW+timedelta(seconds=seconds), end)
        assert state['mode'] == 'night-clock' and state['brightness'] == 5 and state['quiet']
    state = sync(display, end)
    assert state['mode'] == 'waking' and state['brightness'] == 5
    assert state['ramp']['kind'] == 'scheduled' and state['ramp']['duration_seconds'] == 300
    clock.advance(150)
    state = sync(display, end+timedelta(seconds=150))
    assert state['brightness'] == pytest.approx(37.5) and state['quiet']
    clock.advance(149)
    assert sync(display, end+timedelta(seconds=299))['mode'] == 'waking'
    clock.advance(1)
    state = sync(display, end+timedelta(seconds=300))
    assert state['mode'] == 'day' and state['brightness'] == 70 and not state['quiet']


def test_late_tick_is_backdated_to_actual_end_not_a_new_deadline(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    state = sync(display, end+timedelta(seconds=60))
    assert state['ramp']['elapsed_seconds'] == 60
    assert state['brightness'] == pytest.approx(ramp_level(5, 70, 60, 300))
    clock.advance(240)
    assert sync(display, end+timedelta(seconds=300))['mode'] == 'day'


def test_cancelled_sleep_and_extended_overlap_follow_effective_end(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    # The calendar interval merger can extend an interval before its old end.
    extended = end+timedelta(hours=1)
    assert sync(display, end, extended)['mode'] == 'night-clock'
    state = sync(display, end+timedelta(minutes=1), None)
    assert state['mode'] == 'waking' and state['ramp']['elapsed_seconds'] == 0
    # A newly qualifying sleep cancels a scheduled wake immediately.
    clock.advance(10)
    assert sync(display, end+timedelta(minutes=1,seconds=10), extended)['mode'] == 'night-clock'


def test_good_morning_ramps_from_current_level_without_repeat_extension(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    assert display.wake(NOW, morning=True)
    start = display.snapshot()
    assert start['mode'] == 'waking' and start['brightness'] == 5
    assert start['ramp']['duration_seconds'] == 20 and not start['quiet']
    clock.advance(10)
    assert not display.wake(NOW+timedelta(seconds=10), morning=True)
    state = sync(display, NOW+timedelta(seconds=10))
    assert state['ramp']['id'] == start['ramp']['id']
    assert state['brightness'] == pytest.approx(37.5)
    clock.advance(10)
    assert sync(display, NOW+timedelta(seconds=20))['mode'] == 'day'
    assert not display.wake(NOW+timedelta(seconds=21), morning=True)
    assert display.snapshot()['mode'] == 'day'


def test_explicit_morning_during_scheduled_ramp_uses_twenty_seconds_from_current(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    sync(display, end)
    clock.advance(120)
    current = display.brightness()
    assert display.wake(end+timedelta(seconds=120), morning=True)
    state = display.snapshot()
    assert state['brightness'] == current and state['ramp']['from_brightness'] == current
    assert state['ramp']['duration_seconds'] == 20
    clock.advance(20)
    assert sync(display, end+timedelta(seconds=140))['mode'] == 'day'


def test_good_night_and_off_cancel_wake_without_later_replay(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    clock.advance(7)
    display.night(NOW+timedelta(seconds=7), until=NOW+timedelta(hours=2))
    assert display.snapshot()['mode'] == 'night-clock' and display.snapshot()['ramp'] is None
    display.off(NOW+timedelta(seconds=8))
    assert display.snapshot()['mode'] == 'off'
    assert sync(display, NOW+timedelta(hours=3))['mode'] == 'off'
    assert not display.wake(NOW+timedelta(hours=3), morning=False)
    assert display.snapshot()['ramp']['from_brightness'] == 0
    assert display.snapshot()['ramp']['kind'] == 'temporary'


def test_manual_brightness_cancels_ramp_and_never_changes_night_setting(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    clock.advance(3)
    display.manual_brightness(NOW+timedelta(seconds=3), 30)
    assert display.snapshot()['mode'] == 'day' and display.brightness() == 30
    assert sync(display, NOW+timedelta(seconds=4), brightness=30)['ramp'] is None
    assert display.night_brightness == 5
    display.night(NOW+timedelta(seconds=5), until=NOW+timedelta(hours=1))
    assert sync(display, NOW+timedelta(seconds=6), NOW+timedelta(hours=1), brightness=2)['brightness'] == 2


def test_settings_patch_to_day_target_also_cancels_ramp(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    assert sync(display, NOW+timedelta(seconds=1), brightness=44)['mode'] == 'day'
    assert display.brightness() == 44


def test_clock_disabled_sleep_and_manual_off_have_different_wake_behavior(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    assert sync(display, end=end, night_clock=False)['mode'] == 'off'
    state = sync(display, end, night_clock=False)
    assert state['mode'] == 'waking' and state['brightness'] == 0
    display.off(end)
    assert sync(display, end+timedelta(hours=1))['mode'] == 'off'


def test_restart_stays_dark_until_trusted_clock_then_restores_remaining_ramp(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    sync(display, end)
    restarted = DisplayCycle(display.storage, clock=clock)
    assert restarted.snapshot()['mode'] == 'off' and restarted.snapshot()['brightness'] == 0
    assert sync(restarted, end+timedelta(seconds=100), trusted=False)['mode'] == 'off'
    state = sync(restarted, end+timedelta(seconds=100))
    assert state['ramp']['elapsed_seconds'] == 100
    assert state['brightness'] == pytest.approx(ramp_level(5, 70, 100, 300))
    clock.advance(200)
    assert sync(restarted, end+timedelta(seconds=300))['mode'] == 'day'


def test_restart_after_sleep_or_wake_deadline_does_not_replay_morning(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    restarted = DisplayCycle(display.storage, clock=clock)
    assert sync(restarted, end+timedelta(seconds=301))['mode'] == 'day'
    assert restarted.snapshot()['ramp'] is None


def test_live_ramp_uses_monotonic_time_even_if_wall_time_changes(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    clock.advance(10)
    state = sync(display, NOW+timedelta(hours=6))
    assert state['mode'] == 'waking' and state['brightness'] == pytest.approx(37.5)
    clock.advance(10)
    assert sync(display, NOW+timedelta(hours=6,seconds=10))['mode'] == 'day'


def test_clock_rollback_or_untrusted_saved_ramp_requires_explicit_recovery(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    restored = DisplayCycle(display.storage, clock=clock)
    assert sync(restored, NOW-timedelta(minutes=5))['mode'] == 'off'
    restored.wake(NOW-timedelta(minutes=5), morning=True)
    assert restored.snapshot()['mode'] == 'waking'
    untrusted, other_clock = engine(tmp_path/'other')
    sync(untrusted, trusted=False)
    untrusted.wake(NOW, morning=True)
    assert untrusted.snapshot()['awaiting_clock']
    assert DisplayCycle(untrusted.storage, clock=other_clock).sync(NOW+timedelta(seconds=5),sleep_end=None,brightness=70,trusted=True)['mode'] == 'off'


def test_explicit_wake_works_before_clock_sync_but_never_automatic_wake(tmp_path):
    display, clock = engine(tmp_path)
    assert sync(display, trusted=False)['mode'] == 'off'
    display.wake(NOW)
    clock.advance(10)
    state = sync(display, NOW+timedelta(seconds=10), trusted=False)
    assert state['mode'] == 'waking' and state['awaiting_clock']
    assert state['brightness'] == pytest.approx(35)


def test_manual_night_before_time_sync_never_authorizes_automatic_wake(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, trusted=False)
    display.night(NOW, until=NOW+timedelta(hours=8))
    state = sync(display, NOW+timedelta(hours=9), trusted=False)
    assert state['mode'] == 'night-clock' and state['brightness'] == 5 and state['awaiting_clock']
    assert sync(display, NOW+timedelta(hours=9))['mode'] == 'day'


def test_explicit_morning_during_dark_recovery_starts_from_black(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    old_id = display.snapshot()['ramp']['id']
    restarted = DisplayCycle(display.storage, clock=clock)
    sync(restarted, NOW+timedelta(seconds=5), trusted=False)
    restarted.wake(NOW+timedelta(seconds=5), morning=True)
    state = restarted.snapshot()
    assert state['brightness'] == 0 and state['ramp']['from_brightness'] == 0
    assert state['ramp']['id'] != old_id
    clock.advance(10)
    assert restarted.snapshot()['brightness'] == pytest.approx(35)


def test_night_restoration_and_no_per_second_storage_writes(tmp_path):
    display, clock = engine(tmp_path)
    end = NOW+timedelta(hours=1)
    sync(display, end=end)
    restored = DisplayCycle(display.storage, clock=clock)
    assert sync(restored, NOW+timedelta(minutes=2), end)['mode'] == 'night-clock'
    with patch.object(restored.storage, 'set_cache', wraps=restored.storage.set_cache) as writes:
        for second in range(60):
            sync(restored, NOW+timedelta(minutes=2,seconds=second), end)
        writes.assert_not_called()
        restored.wake(NOW+timedelta(minutes=3), morning=True)
        assert writes.call_count == 1
        for second in range(19):
            clock.advance(1)
            sync(restored, NOW+timedelta(minutes=3,seconds=second+1))
        assert writes.call_count == 1
        clock.advance(1)
        sync(restored, NOW+timedelta(minutes=3,seconds=20))
        assert writes.call_count == 2


@pytest.mark.parametrize('bad', [[], {'version': 7}, {'mode': 'day'}, {'version': 1, 'mode': 'off', 'held_off': 'yes'}])
def test_corrupt_recovery_stays_off_without_resetting_other_settings(tmp_path, bad):
    display, clock = engine(tmp_path)
    display.storage.set_cache('display', 'cycle', bad)
    restored = DisplayCycle(display.storage, clock=clock)
    assert sync(restored)['mode'] == 'off'
    assert display.storage.load_settings().brightness == 70


def test_invalid_ramp_payload_is_not_trusted(tmp_path):
    display, clock = engine(tmp_path)
    sync(display, end=NOW+timedelta(hours=1))
    display.wake(NOW, morning=True)
    valid = deepcopy(display.data)
    for change in ({'duration': 99999}, {'from': float('inf')}, {'trusted': 'yes'}, {'kind': 'unknown'}, {'started_at': '2026-09-26T15:00:00'}):
        bad = deepcopy(valid); bad['ramp'].update(change)
        display.storage.set_cache('display', 'cycle', bad)
        assert sync(DisplayCycle(display.storage, clock=clock))['mode'] == 'off'


def test_dst_fallback_and_smooth_curve_bounds(tmp_path):
    display, clock = engine(tmp_path)
    zone = ZoneInfo('America/Los_Angeles')
    start = datetime(2026,11,1,1,40,tzinfo=zone,fold=0)
    end = datetime(2026,11,1,1,20,tzinfo=zone,fold=1)
    assert sync(display,start,end)['mode'] == 'night-clock'
    assert sync(display,end.astimezone(UTC)-timedelta(seconds=1),end)['mode'] == 'night-clock'
    assert sync(display,end)['mode'] == 'waking'
    assert ramp_level(5,70,-100,300) == 5
    assert ramp_level(5,70,400,300) == 70
    samples = [ramp_level(5,70,i,300) for i in range(301)]
    assert samples == sorted(samples)
    assert samples[1]-samples[0] < .01 and samples[-1]-samples[-2] < .01
