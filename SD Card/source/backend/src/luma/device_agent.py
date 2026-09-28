"""Desktop-session hardware bridge. No root and no shell-expanded commands."""
from __future__ import annotations

import os
import subprocess
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from .hardware import AudioController, DisplayController, VoiceController
from .touch import TouchWake
from .portal import PortalBrowser
from .system_keyboard import SystemKeyboard
from .timer_chime import TimerChimeBridge
from .display_handoff import apply_display_job


class DeviceBridge:
    def __init__(self, display: DisplayController, audio: AudioController, voice: VoiceController | None = None):
        self.display = display
        self.audio = audio
        self.voice = voice
        self.applied: dict[str, Any] = {}
        self.retry_at: dict[str, float] = {}
        self.retry_value: dict[str, Any] = {}
        self.status: dict[str, str] = {}

    def apply(self, snapshot: dict, now: float | None = None) -> dict[str, str]:
        now = time.monotonic() if now is None else now
        desired = {key: snapshot["settings"][key] for key in ("orientation", "brightness", "volume")}
        desired = {"audio_output": snapshot["settings"].get("audio_output", "auto"), **desired}
        desired["power"] = snapshot["state"]["display_power"] == "on"
        if snapshot.get('display'):
            # The frame-gated handoff is the sole owner of these controls.
            desired.pop('power')
            desired.pop('brightness')
        actions = {"audio_output": self.audio.set_output, "orientation": self.display.set_orientation, "brightness": self.display.set_brightness, "volume": self.audio.set_volume, "power": self.display.power}
        if self.voice:
            desired["voice"] = snapshot["settings"].get("voice_enabled", False)
            actions["voice"] = self.voice.set_enabled
        for key, value in desired.items():
            if self.applied.get(key) == value or (
                self.retry_value.get(key) == value and now < self.retry_at.get(key, 0)
            ):
                continue
            try:
                success = actions[key](value)
                if success is False:
                    raise RuntimeError("Unsupported hardware control")
                self.applied[key] = value
                self.retry_at.pop(key, None)
                self.retry_value.pop(key, None)
                if key == "audio_output":
                    self.applied.pop("volume", None)
                self.status[key] = "ok"
            except Exception:
                self.status[key] = "unavailable; retrying"
                self.retry_at[key] = now + 60
                self.retry_value[key] = value
        return dict(self.status)


class DisplayJobWorker:
    """Slow DDC cannot block microphone mute, audio, touch or timer polling."""
    def __init__(self, display, executor):
        self.display, self.executor = display, executor
        self.generation, self.registered, self.pending = str(uuid4()), False, None
        self.pending_revision = None

    def poll(self, client, snapshot):
        if not snapshot.get('display'):
            return {}
        if not self.registered:
            client.post('/api/v1/device/display-register',json={'generation':self.generation}).raise_for_status()
            self.registered = True
        if self.pending is not None and self.pending.done():
            try:
                result = self.pending.result()
            except Exception:
                # A driver failure must not kill microphone/touch polling or
                # imply that an interrupted hardware operation never committed.
                result = {'revision': self.pending_revision, 'brightness_ok': False, 'power_ok': False}
            self.pending = None
            self.pending_revision = None
            response = client.post('/api/v1/device/display-confirm',json={'generation':self.generation,**result})
            if response.status_code == 409: self.registered = False
            else: response.raise_for_status()
        if self.pending is None and self.registered:
            request = client.post('/api/v1/device/display-claim',json={'generation':self.generation})
            if request.status_code == 409:
                self.registered = False
            else:
                request.raise_for_status()
                if job := request.json().get('job'):
                    self.pending_revision = job['revision']
                    self.pending = self.executor.submit(apply_display_job, self.display, job)
        handoff = snapshot['display']['handoff']
        return {'brightness':'ok' if handoff['physical_brightness'] is not None else 'unavailable; retrying',
                'power':'ok' if handoff['physical_power'] == (snapshot['state']['display_power']=='on') else 'unavailable; retrying'}


def native_windows_awake(snapshot):
    """Native helpers cannot inherit the browser's dimmer or privacy view."""
    return snapshot['state']['display_power']=='on' and (snapshot.get('display') or {}).get('mode','day')=='day'


def main() -> None:
    bridge = DeviceBridge(DisplayController(os.environ.get("LUMA_DISPLAY_OUTPUT", "HDMI-A-1")), AudioController(), VoiceController())
    touch = TouchWake()
    portal = PortalBrowser()
    keyboard = SystemKeyboard()
    timer_chime = TimerChimeBridge()
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='luma-display') as executor, httpx.Client(base_url="http://127.0.0.1:8742", timeout=5) as client:
        display_jobs = DisplayJobWorker(bridge.display,executor)
        while True:
            try:
                response = client.get("/api/v1/state")
                response.raise_for_status()
                snapshot = response.json()
                # Hide native overlays before a frame-gated physical increase;
                # the browser acknowledgement cannot cover another process.
                awake = native_windows_awake(snapshot)
                keyboard.tick(awake)
                portal.apply(None, awake)
                report = bridge.apply(snapshot)
                report.update(display_jobs.poll(client,snapshot))
                def claim_chime():
                    response = client.post('/api/v1/device/timer-chime')
                    response.raise_for_status()
                    return response.json().get('play') is True
                if sound := timer_chime.apply(snapshot, claim_chime):
                    report['timer_chime'] = sound
                try:
                    keyboard.tick(awake)
                    request = client.get("/api/v1/device/keyboard-request")
                    request.raise_for_status()
                    keyboard.apply(request.json(), snapshot["settings"]["theme"], awake)
                    report["keyboard"] = keyboard.status()
                except OSError:
                    report["keyboard"] = "unavailable; retrying"
                try:
                    touched = touch.touched()  # Drain while awake too, so old touches cannot wake later.
                    if touched and snapshot["state"]["display_power"] == "off":
                        client.post("/api/v1/commands", json={"name": "wake", "source": "touch"}).raise_for_status()
                except (ImportError, OSError):
                    pass  # Touch qualification is still required on the chosen panel.
                client.post("/api/v1/device/report", json={"controls": report}).raise_for_status()
                pending = client.get("/api/v1/network/portal-request")
                pending.raise_for_status()
                try:
                    portal.apply(pending.json().get('id'), native_windows_awake(snapshot))
                except (OSError, RuntimeError):
                    pass  # Keep hardware control alive if the browser cannot launch.
            except (httpx.HTTPError, ValueError, OSError, subprocess.SubprocessError):
                pass  # Do not print snapshots, private events, or credentials to logs.
            try:
                keyboard.tick()  # Expire even when the local API is unreachable.
            except (OSError, subprocess.SubprocessError):
                pass
            time.sleep(2)


if __name__ == "__main__":
    main()
