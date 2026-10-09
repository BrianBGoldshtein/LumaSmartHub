"""Read the Pi's built-in CPU sensor without a privileged process or cache."""
from datetime import UTC, datetime
from pathlib import Path
import re

CPU_SENSOR = Path('/sys/class/thermal/thermal_zone0/temp')


def read_temperature() -> dict:
    result = {'celsius': None, 'status': 'unavailable',
              'sampled_at': datetime.now(UTC).isoformat()}
    try:
        with CPU_SENSOR.open('rb') as sensor:
            raw = sensor.read(32)
        if not re.fullmatch(rb'[0-9]{1,6}\n?', raw):
            return result
        value = int(raw) / 1000
        if not 0 < value <= 125:
            return result
    except (OSError, ValueError):
        return result
    # 70 is an early warning chosen by Luma, not a hardware throttling claim.
    value = round(value, 1)
    return {**result, 'celsius': value,
            'status': 'hot' if value >= 80 else 'warm' if value >= 70 else 'normal'}
