"""Short local tone; at-most-once claim from the timer owner, no saved audio."""
import math
import struct
import subprocess


def chime_pcm():
    rate = 24000
    return b''.join(struct.pack('<h', round(5000 * math.sin(2*math.pi*(660 if i < rate*.22 else 880)*i/rate)
                                           * min(1, i/(rate*.015)) * max(0, 1-i/(rate*.55))))
                    for i in range(round(rate*.55)))


def play_chime():
    subprocess.run(['paplay','--raw','--rate=24000','--channels=1','--format=s16le'], input=chime_pcm(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=3)


class TimerChimeBridge:
    def __init__(self, play=play_chime):
        self.play, self.seen = play, None

    def apply(self, snapshot, claim):
        timer = snapshot.get('timer') or {}
        if timer.get('status') != 'complete' or not timer.get('id') or timer['id'] == self.seen:
            return None
        # Mark first; neither playback failure nor bridge polling replays it.
        self.seen = timer['id']
        if not claim():
            return 'silent'
        if snapshot['state']['display_power'] == 'off' or snapshot['settings']['volume'] == 0 or (snapshot.get('display') or {}).get('quiet'):
            return 'silent'
        try:
            self.play()
            return 'played'
        except (OSError, subprocess.SubprocessError):
            return 'unavailable; not replayed'
