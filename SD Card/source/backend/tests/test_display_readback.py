import subprocess

import pytest

from luma.hardware import DisplayController


def controller(outputs):
    calls = []
    def run(args):
        calls.append(args)
        value = outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return subprocess.CompletedProcess(args,0,value,'')
    return DisplayController(runner=run),calls


def test_confirmed_brightness_uses_real_maximum_and_reads_back():
    display,calls = controller(['VCP 10 C 160 255\n','','VCP 10 C 12 255\n'])
    assert display.set_brightness_confirmed(5)
    assert calls == [['ddcutil','getvcp','10','--terse'],['ddcutil','setvcp','10','12'],['ddcutil','getvcp','10','--terse']]
    assert 12/255*100 <= 5


@pytest.mark.parametrize('reading',['VCP 10 ERR','VCP 10 C 0 0','VCP 10 C 200 100','VCP 10 C 0 65536','VCP 12 C 50 100','VCP 10 C 50 100\nVCP 10 C 60 100',''])
def test_bad_or_ambiguous_initial_readback_never_sets_panel(reading):
    display,calls = controller([reading])
    assert not display.set_brightness_confirmed(5)
    assert len(calls) == 1


@pytest.mark.parametrize('reading',['VCP 10 C 70 100','VCP 10 C 5 255','VCP 10 ERR'])
def test_unconfirmed_value_never_releases_conservative_fallback(reading):
    display,calls = controller(['VCP 10 C 70 100','',reading])
    assert not display.set_brightness_confirmed(5)


def test_timed_out_readback_is_not_assumed_unchanged():
    display,calls = controller(['VCP 10 C 70 100','',subprocess.TimeoutExpired('ddcutil',8)])
    assert not display.set_brightness_confirmed(5)


@pytest.mark.parametrize('value',[True,-1,101,5.5,'5'])
def test_only_strict_whole_percentage_accepted(value):
    display,calls = controller([])
    with pytest.raises(ValueError):display.set_brightness_confirmed(value)
    assert calls == []
