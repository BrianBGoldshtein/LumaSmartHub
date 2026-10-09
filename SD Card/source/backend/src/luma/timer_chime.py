"""Distinct synthesized timer alarm; at-most-once claim, no saved audio."""
import math
import struct
import subprocess


def chime_pcm():
    rate = 24000
    # Five restrained alarm-clock double beeps, not an ascending melody.
    sequence = ((880, 180), (0, 100), (880, 180), (0, 540)) * 5
    samples = []
    for frequency, milliseconds in sequence:
        frames = rate * milliseconds // 1000
        for frame in range(frames):
            if not frequency:
                samples.append(struct.pack('<h', 0))
                continue
            envelope = min(1, frame/(rate*.012), (frames-frame)/(rate*.025))
            value = round(10000 * math.sin(2*math.pi*frequency*frame/rate) * envelope)
            samples.append(struct.pack('<h', value))
    return b''.join(samples)


def play_chime():
    subprocess.run(['paplay','--raw','--rate=24000','--channels=1','--format=s16le'], input=chime_pcm(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=8)


class TimerChimeBridge:
    def __init__(self, play=play_chime):
        self.play, self.seen = play, set()

    def apply(self, snapshot, claim):
        timers = [snapshot.get('timer') or {}, *(snapshot.get('personal_timers') or [])]
        complete = {timer['id'] for timer in timers if timer.get('status') == 'complete' and timer.get('id')}
        fresh = complete - self.seen
        self.seen &= complete  # At most six durable completed IDs, not an unbounded history.
        if not fresh:
            return None
        # Mark first; neither playback failure nor bridge polling replays it.
        self.seen |= fresh
        if not claim():
            return 'silent'
        # Sleep/display-off is not mute: the timer alarm remains audible.
        if snapshot['settings']['volume'] == 0:
            return 'silent'
        try:
            self.play()
            return 'played'
        except (OSError, subprocess.SubprocessError):
            return 'unavailable; not replayed'
