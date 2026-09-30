"""Fixed ReSpeaker V1 capture controls; never changes speaker/playback volume."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

CARD = "seeed2micvoicec"
GAIN_FILE = Path("/var/lib/luma/mic-capture-gain")
DEFAULT_GAIN = 39  # Seeed's published WM8960 capture state, not a measured Pi result.
ROUTE_ON = (
    "Left Boost Mixer LINPUT1 Switch",
    "Right Boost Mixer RINPUT1 Switch",
    "Left Input Mixer Boost Switch",
    "Right Input Mixer Boost Switch",
)


class MicHardwareError(RuntimeError):
    pass


def _run(*args: str) -> str:
    try:
        result = subprocess.run(("/usr/bin/amixer", "-c", CARD, *args),
                                capture_output=True, text=True, timeout=4, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MicHardwareError("ReSpeaker mixer is unavailable") from exc
    if result.returncode:
        raise MicHardwareError("ReSpeaker V1 sound card or mixer control was not found")
    return result.stdout


def _values(name: str) -> list[str]:
    output = _run("cget", f"name={name}")
    match = re.search(r"(?m)^\s*:\s*values=([^\r\n]+)", output)
    if not match:
        raise MicHardwareError("ReSpeaker mixer returned an unreadable value")
    return [part.strip() for part in match.group(1).split(",")]


def saved_gain(path: Path = GAIN_FILE) -> int:
    try:
        value = int(path.read_text(encoding="ascii").strip())
        if 0 <= value <= 63:
            return value
    except (OSError, UnicodeError, ValueError):
        pass
    return DEFAULT_GAIN


def status(path: Path = GAIN_FILE) -> dict[str, object]:
    desired = saved_gain(path)
    try:
        volume = [int(value) for value in _values("Capture Volume")]
        switches = _values("Capture Switch")
        route = all(all(value in {"on", "true", "1"} for value in _values(name))
                    for name in ROUTE_ON)
    except (MicHardwareError, ValueError):
        return {"available": False, "gain": desired, "max_gain": 63,
                "capture_on": False, "route_ready": False}
    return {"available": True, "gain": volume[0] if volume else desired,
            "max_gain": 63, "capture_on": bool(switches) and all(
                value in {"on", "true", "1"} for value in switches),
            "route_ready": route}


def apply(gain: int) -> None:
    if type(gain) is not int or not 0 <= gain <= 63:
        raise ValueError("Capture gain must be a whole number from 0 to 63")
    # Verify the expected V1 card before touching any mixer controls.
    _values("Capture Volume")
    for name in ROUTE_ON:
        _run("cset", f"name={name}", "on")
    _run("cset", "name=Capture Switch", "on,on")
    _run("cset", "name=Capture Volume", f"{gain},{gain}")


def save_and_apply(gain: int, path: Path = GAIN_FILE) -> dict[str, object]:
    apply(gain)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(f"{gain}\n", encoding="ascii")
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return status(path)


def main() -> None:
    # The HAT may not be attached; do not prevent the voice agent from
    # reporting its normal capture diagnostic in that case.
    try:
        apply(saved_gain())
    except MicHardwareError:
        pass


if __name__ == "__main__":
    main()
