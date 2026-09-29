"""A frame-acknowledged handoff between the kiosk dimmer and display bridge.

Panel state is deliberately NOT durable: after either backend or bridge restart
it may be unknown. Until confirmed, software scales against a 100% reference.
Only one bounded hardware job can be in flight. No DDC calls run in this module.
"""
import time
import subprocess
from uuid import uuid4


class DisplayHandoff:
    FRAME_TTL = 10
    JOB_TTL = 45  # Three bounded DDC operations plus power, at most 4×8s.
    RETRY_DELAY = 60
    MIN_INTERVAL = 4

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.physical_brightness = None
        self.physical_power = None
        self.desired = None
        self.pending = None
        self.frame_at = None
        self.claimed_at = None
        self.next_attempt = 0.
        self.off_retry_at = 0.
        self.last_failure = False

    def _expire(self):
        if self.claimed_at is not None and self.clock() - self.claimed_at >= self.JOB_TTL:
            # The driver may have committed before losing its reply. Don't
            # infer failure means "unchanged"; 100% is the safe upper bound.
            if self.pending and not self.pending['power']:
                self.off_retry_at = self.clock() + self.RETRY_DELAY
            self.physical_brightness = self.physical_power = None
            self.pending = self.frame_at = self.claimed_at = None
            self.next_attempt = self.clock() + self.RETRY_DELAY
            self.last_failure = True

    def prepare(self, *, power, brightness):
        if type(power) is not bool or type(brightness) is not int or not 0 <= brightness <= 100:
            raise ValueError('Invalid physical display target')
        self._expire()
        self.desired = {'power': power, 'brightness': brightness if power else None}
        if self.pending and self.claimed_at is None and self.desired != {k:self.pending[k] for k in self.desired}:
            # No hardware request was issued, so a superseded job can be dropped.
            self.pending = self.frame_at = None
        self._queue()
        return self.snapshot()

    def _queue(self):
        if self.pending or self.desired is None:
            return
        retry_at = self.next_attempt if self.desired['power'] else self.off_retry_at
        if self.clock() < retry_at:
            return
        matches = self.physical_power == self.desired['power']
        if self.desired['power']:
            matches = matches and self.physical_brightness == self.desired['brightness']
        if matches:
            return
        self.pending = {'revision': str(uuid4()), **self.desired}
        self.frame_at = None

    def frame_ready(self, revision):
        self._expire()
        if not self.pending or revision != self.pending['revision'] or self.claimed_at is not None:
            return False
        self.frame_at = self.clock()
        return True

    def claim(self):
        self._expire()
        self._queue()
        if not self.pending or self.claimed_at is not None:
            return None
        if self.pending['power'] and (self.frame_at is None or self.clock() - self.frame_at >= self.FRAME_TTL):
            return None
        self.claimed_at = self.clock()
        self.next_attempt = self.clock() + self.MIN_INTERVAL
        return dict(self.pending)

    def report(self, revision, *, brightness_ok, power_ok):
        self._expire()
        if type(brightness_ok) is not bool or type(power_ok) is not bool:
            raise ValueError('Invalid hardware confirmation')
        if not self.pending or self.claimed_at is None or revision != self.pending['revision']:
            return False
        if self.pending['power']:
            self.physical_brightness = self.pending['brightness'] if brightness_ok else None
        self.physical_power = self.pending['power'] if power_ok else None
        failed = not power_ok or (self.pending['power'] and not brightness_ok)
        self.last_failure = failed
        if failed:
            self.next_attempt = self.clock() + self.RETRY_DELAY
            if not self.pending['power']:
                self.off_retry_at = self.clock() + self.RETRY_DELAY
        self.pending = self.frame_at = self.claimed_at = None
        self._queue()
        return True

    def invalidate_bridge(self):
        """A new bridge generation cannot inherit an old physical-state claim."""
        self.physical_brightness = self.physical_power = None
        self.pending = self.frame_at = self.claimed_at = None
        self.next_attempt = self.off_retry_at = self.clock()
        self._queue()

    def snapshot(self):
        self._expire()
        reference = self.physical_brightness if self.physical_brightness is not None else 100
        if self.pending and self.pending['power']:
            reference = max(reference, self.pending['brightness'])
        pending = self.pending
        fresh_frame = self.frame_at is not None and self.clock() - self.frame_at < self.FRAME_TTL
        status = ('applying' if self.claimed_at is not None else 'waiting-frame' if pending and pending['power'] and not fresh_frame
                  else 'pending' if pending else 'unavailable' if self.last_failure else 'unknown' if self.physical_power is None else 'ready')
        return {'revision': pending['revision'] if pending else None,
                'needs_frame': bool(pending and pending['power'] and self.claimed_at is None and not fresh_frame),
                'reference_brightness': max(1, reference),
                'physical_brightness': self.physical_brightness,
                'physical_power': self.physical_power,
                'status': status}


def apply_display_job(display, job):
    """Called by the sole desktop bridge; operations are serial and bounded.

The browser must acknowledge a safe dimmed frame BEFORE a power-on/increase.
Unsupported DDC still allows power-on under the conservative software dimmer.
"""
    brightness_ok = True
    if job['power']:
        try:
            brightness_ok = display.set_brightness_confirmed(job['brightness']) is True
        except (OSError, RuntimeError, subprocess.SubprocessError):
            brightness_ok = False
    try:
        power_ok = display.power(job['power']) is not False
    except (OSError, RuntimeError, subprocess.SubprocessError):
        power_ok = False
    return {'revision': job['revision'], 'brightness_ok': brightness_ok, 'power_ok': power_ok}
