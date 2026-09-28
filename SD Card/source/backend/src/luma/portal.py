"""User-requested captive portal browser in the non-root desktop session."""
from __future__ import annotations

import subprocess
from pathlib import Path

PORTAL_PROBE = "http://neverssl.com/"


class PortalBrowser:
    def __init__(self, launch=subprocess.Popen):
        self.launch = launch
        self.process = None
        self.last_request = None

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=1)
            self.process = None

    def apply(self, request_id: str | None, awake: bool):
        if not awake:
            self.close()
            # Consume an old portal request so waking never replays it.
            if request_id:
                self.last_request = request_id
        elif request_id:
            self.open(request_id)

    def open(self, request_id: str) -> bool:
        if request_id == self.last_request:
            return True
        if self.process is None or self.process.poll() is not None:
            # A separate non-kiosk profile exposes the real address bar and close
            # button. Never bypass certificates or auto-accept network terms.
            profile = Path.home() / ".config" / "luma-portal"
            profile.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.process = self.launch([
                "/usr/bin/chromium", f"--user-data-dir={profile}",
                "--no-first-run", "--new-window", "--start-maximized",
                "--ozone-platform=wayland", PORTAL_PROBE,
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.last_request = request_id
        return True
