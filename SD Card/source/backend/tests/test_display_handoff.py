from unittest.mock import Mock
import subprocess

import pytest

from luma.display_handoff import DisplayHandoff, apply_display_job
from test_display_cycle import Clock


def apply(handoff):
    job = handoff.pending
    assert handoff.frame_ready(job['revision'])
    claimed = handoff.claim()
    assert claimed == job
    assert handoff.report(job['revision'], brightness_ok=True, power_ok=True)
    return claimed


def test_no_brightening_or_power_on_before_a_safe_frame():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    state = handoff.prepare(power=True, brightness=5)
    assert state['reference_brightness'] == 100 and state['needs_frame']
    assert handoff.claim() is None
    assert not handoff.frame_ready('stale')
    apply(handoff)
    assert handoff.snapshot()['reference_brightness'] == 5
    clock.advance(4)
    state = handoff.prepare(power=True, brightness=70)
    assert state['reference_brightness'] == 70 and state['needs_frame']
    assert handoff.claim() is None
    apply(handoff)
    assert handoff.snapshot()['physical_brightness'] == 70


def test_dimming_uses_old_higher_reference_until_hardware_confirms():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    handoff.prepare(power=True, brightness=70);apply(handoff)
    clock.advance(4)
    state = handoff.prepare(power=True, brightness=5)
    assert state['reference_brightness'] == 70
    handoff.frame_ready(state['revision']);handoff.claim()
    assert handoff.snapshot()['reference_brightness'] == 70
    handoff.report(state['revision'],brightness_ok=True,power_ok=True)
    assert handoff.snapshot()['reference_brightness'] == 5


def test_only_one_job_in_flight_and_retarget_cannot_lower_its_safety_ceiling():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    handoff.prepare(power=True,brightness=5);apply(handoff);clock.advance(4)
    state = handoff.prepare(power=True,brightness=70)
    handoff.frame_ready(state['revision']); job = handoff.claim()
    clock.advance(4)
    assert handoff.prepare(power=True,brightness=5)['reference_brightness'] == 70
    assert handoff.claim() is None
    assert handoff.report(job['revision'],brightness_ok=True,power_ok=True)
    next_state = handoff.snapshot()
    assert next_state['revision'] != job['revision'] and next_state['reference_brightness'] == 70
    assert not handoff.frame_ready(job['revision'])
    apply(handoff)
    assert handoff.snapshot()['reference_brightness'] == 5


def test_stale_or_missing_frame_never_claims_a_power_on():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    state = handoff.prepare(power=True,brightness=70)
    handoff.frame_ready(state['revision']);clock.advance(10)
    assert handoff.claim() is None and handoff.snapshot()['needs_frame']
    assert handoff.frame_ready(state['revision'])
    assert handoff.claim()


def test_power_off_does_not_wait_for_a_suspended_browser():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    handoff.prepare(power=False,brightness=70)
    job = handoff.claim()
    assert job['power'] is False and job['brightness'] is None
    display = Mock()
    result = apply_display_job(display, job)
    display.set_brightness_confirmed.assert_not_called()
    display.power.assert_called_once_with(False)
    assert handoff.report(**result)
    assert handoff.snapshot()['physical_power'] is False


def test_changing_targets_cannot_bypass_failure_backoff():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    state = handoff.prepare(power=True,brightness=5)
    handoff.frame_ready(state['revision']);handoff.claim()
    handoff.report(state['revision'],brightness_ok=False,power_ok=True)
    for level in range(60):
        clock.advance(1)
        state = handoff.prepare(power=True,brightness=level)
        assert state['reference_brightness'] == 100
        if level<59: assert state['revision'] is None
    assert state['revision'] and state['needs_frame']


def test_expired_job_treats_unknown_commit_as_unknown_physical_state():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    state = handoff.prepare(power=True,brightness=70)
    handoff.frame_ready(state['revision']); job = handoff.claim()
    clock.advance(45)
    state = handoff.snapshot()
    assert state['reference_brightness'] == 100 and state['status'] == 'unavailable'
    assert handoff.claim() is None
    assert not handoff.report(job['revision'],brightness_ok=True,power_ok=True)
    clock.advance(60)
    handoff.prepare(power=True,brightness=5)
    assert handoff.snapshot()['needs_frame']


def test_bridge_restart_invalidates_physical_knowledge_and_pending_ack():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    handoff.prepare(power=True,brightness=5);apply(handoff)
    old = handoff.snapshot()
    assert old['reference_brightness'] == 5
    handoff.invalidate_bridge()
    state = handoff.snapshot()
    assert state['reference_brightness'] == 100 and state['needs_frame']
    assert handoff.claim() is None


def test_unsupported_ddc_still_powers_on_under_software_dimming():
    display = Mock()
    display.set_brightness_confirmed.return_value = False
    result = apply_display_job(display, {'revision':'one','power':True,'brightness':70})
    assert result == {'revision':'one','brightness_ok':False,'power_ok':True}
    assert display.method_calls[0][0] == 'set_brightness_confirmed' and display.method_calls[1][0] == 'power'


def test_power_off_does_not_wait_for_failed_ddc_backoff_but_failed_off_is_bounded():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    state = handoff.prepare(power=True,brightness=5)
    handoff.frame_ready(state['revision']);handoff.claim()
    handoff.report(state['revision'],brightness_ok=False,power_ok=True)
    handoff.prepare(power=False,brightness=5)
    job = handoff.claim()
    assert job and job['power'] is False
    handoff.report(job['revision'],brightness_ok=True,power_ok=False)
    assert handoff.claim() is None
    clock.advance(60)
    assert handoff.claim()['power'] is False


def test_bounded_driver_timeouts_are_reported_not_raised():
    display = Mock()
    display.set_brightness_confirmed.side_effect = subprocess.TimeoutExpired('ddcutil',8)
    display.power.side_effect = subprocess.CalledProcessError(1,'wlr-randr')
    assert apply_display_job(display,{'revision':'x','power':True,'brightness':5}) == {'revision':'x','brightness_ok':False,'power_ok':False}


def test_successful_targets_are_not_reissued_and_minimum_interval_is_bounded():
    clock = Clock(); handoff = DisplayHandoff(clock=clock)
    handoff.prepare(power=True,brightness=70);apply(handoff)
    assert handoff.prepare(power=True,brightness=70)['revision'] is None
    assert handoff.prepare(power=True,brightness=5)['revision'] is None
    clock.advance(4)
    assert handoff.prepare(power=True,brightness=5)['revision']


@pytest.mark.parametrize('power,brightness', [('yes',5),(True,True),(True,101),(True,-1),(True,1.2)])
def test_hardware_targets_are_strict(power,brightness):
    with pytest.raises(ValueError):DisplayHandoff().prepare(power=power,brightness=brightness)
