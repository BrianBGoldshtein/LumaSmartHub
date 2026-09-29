"""Bounded single-button raw IR representation; no protocol/semantic guesses."""
import hashlib
import json

MAX_EDGES = 511
MAX_FRAME_US = 250_000
FRAME_GAP_US = 20_000
MIN_CARRIER = 20_000
MAX_CARRIER = 60_000


class InfraredError(ValueError):
    pass


def carrier(value, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or not MIN_CARRIER <= value <= MAX_CARRIER:
        raise InfraredError('Use a measured or documented carrier from 20000 to 60000 Hz.')
    return value


def signal(value):
    if not isinstance(value, dict) or set(value) != {'carrier_hz', 'durations'}:
        raise InfraredError('Invalid single-button IR signal.')
    frequency = carrier(value['carrier_hz'])
    durations = value['durations']
    # Reject common short repeat fragments. This is framing, NOT protocol or
    # button-semantics validation. The owner must still test every learned key.
    # Odd length starts AND ends with a pulse as required by the Linux write ABI.
    if (not isinstance(durations, list) or not 7 <= len(durations) <= MAX_EDGES or len(durations) % 2 != 1
            or any(type(item) is not int or not 1 <= item < FRAME_GAP_US for item in durations)
            or sum(durations) > MAX_FRAME_US):
        raise InfraredError('Record one short, complete button press, not a held button.')
    return {'carrier_hz': frequency, 'durations': list(durations)}


def signal_key(value):
    return hashlib.sha256(json.dumps(signal(value), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Frame:
    """Incremental Linux MODE2 parser. Never trusts truncated/overflowed captures."""
    def __init__(self, fallback_carrier=None):
        self.frequency = carrier(fallback_carrier, optional=True)
        self.measured = False
        self.durations = []
        self.complete = False
        self.total = 0

    def feed(self, word):
        if type(word) is not int or not 0 <= word <= 0xFFFFFFFF:
            raise InfraredError('Unsupported IR receiver data.')
        if self.complete:
            return
        kind, value = word & 0xFF000000, word & 0x00FFFFFF
        if kind == 0x02000000:
            measured = carrier(value)
            if self.measured and abs(measured - self.frequency) > self.frequency * .1:
                raise InfraredError('The carrier changed during recording. Try one button again.')
            self.frequency, self.measured = measured, True
            return
        if kind == 0x04000000:
            raise InfraredError('IR recording overflowed. Try one button again.')
        if kind not in (0, 0x01000000, 0x03000000):
            raise InfraredError('Unsupported IR receiver data.')
        if kind == 0x03000000 and value < FRAME_GAP_US:
            return  # A short driver timeout is not our frame delimiter.
        if kind == 0x03000000 or kind == 0 and value >= FRAME_GAP_US:
            if self.durations:
                self.complete = True
            return
        if not self.durations and kind == 0:
            return  # Leading silence is not a signal edge.
        expected = 0x01000000 if len(self.durations) % 2 == 0 else 0
        if kind != expected or not 1 <= value < FRAME_GAP_US:
            raise InfraredError('IR pulse sequence was incomplete. Record again.')
        self.durations.append(value)
        self.total += value
        if len(self.durations) > MAX_EDGES or self.total > MAX_FRAME_US:
            raise InfraredError('Hold the remote button briefly, then release it.')

    def result(self):
        if not self.complete:
            raise InfraredError('No complete button press was received.')
        return {**signal({'carrier_hz': self.frequency, 'durations': self.durations}),
                'carrier_source': 'measured' if self.measured else 'owner_supplied'}
