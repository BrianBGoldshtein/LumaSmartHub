"""Linux-only protocol/process smoke; does not type, capture or prove touch UX.

Run with the qualification venv after test-linux.sh and installation of Debian
labwc, wvkbd and fonts-dejavu-core. Uses a private headless Wayland compositor.
"""
import os
import argparse
from pathlib import Path
import re
import signal
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
import time

from luma.system_keyboard import PALETTES, SystemKeyboard


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", default="/opt/luma/bin/luma-keyboard")
    options = parser.parse_args()
    if os.name != "posix" or os.geteuid() == 0:
        raise SystemExit("Run as a normal Linux user in the qualification venv")
    with TemporaryDirectory(prefix="luma-keyboard-smoke-") as directory:
        root = Path(directory)
        config = root / "config"
        config.mkdir()
        for key in ("WAYLAND_DISPLAY", "DISPLAY", "DBUS_SESSION_BUS_ADDRESS"):
            os.environ.pop(key, None)
        os.environ.update(XDG_RUNTIME_DIR=directory, XDG_CONFIG_HOME=str(config),
                          XDG_CONFIG_DIRS=str(config), WLR_BACKENDS="headless",
                          WLR_RENDERER="pixman", WLR_HEADLESS_OUTPUTS="1",
                          LABWC_UPDATE_ACTIVATION_ENV="0")
        compositor = subprocess.Popen(["/usr/bin/labwc", "-C", str(config)],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)
        # Only this input-free test enables protocol tracing, into an ephemeral
        # file. Production never enables WAYLAND_DEBUG or keyboard output flags.
        trace = TemporaryFile()
        def launch_keyboard(args, **kwargs):
            return subprocess.Popen([options.binary, *args[1:]], **{**kwargs,
                                    "env": {**os.environ, "WAYLAND_DEBUG": "client"}, "stderr": trace})
        keyboard = SystemKeyboard(launch=launch_keyboard)
        try:
            deadline = time.monotonic() + 10
            while True:
                sockets = [p for p in root.glob("wayland-*") if p.is_socket()]
                if sockets:
                    os.environ["WAYLAND_DISPLAY"] = sockets[0].name
                    break
                if compositor.poll() is not None or time.monotonic() >= deadline:
                    stop(compositor)
                    diagnostic = compositor.communicate(timeout=2)[1].decode(errors="replace")[-3000:]
                    raise RuntimeError(f"Headless compositor did not become available: {diagnostic}")
                time.sleep(.1)
            for theme in PALETTES:
                keyboard.apply({"id": theme, "visible": True}, theme, True)
                time.sleep(1)
                assert keyboard.process is not None and keyboard.process.poll() is None, theme
                keyboard.process.send_signal(signal.SIGUSR1)
                keyboard.apply({"id": f"{theme}-show", "visible": True}, theme, True)
                time.sleep(.2)
                assert keyboard.process.poll() is None, theme
                owned = keyboard.process
                keyboard.tick(awake=False)
                assert keyboard.process is None and owned.poll() is not None, theme
                print(f"PASS {theme}: starts, survives hide/show, closes on sleep")
            trace.seek(0)
            protocol = trace.read().decode(errors="replace")
            assert re.search(r'get_layer_surface\([^\n]*, 3, "wlroots"\)', protocol), "Keyboard did not request the overlay layer"
            assert not re.search(r'get_layer_surface\([^\n]*, 2, "wlroots"\)', protocol), "Keyboard still requests the fullscreen-hidden top layer"
            print("PASS: compositor received overlay-layer requests, not top-layer requests")
        finally:
            keyboard.close()
            stop(compositor)
            trace.close()
    print("No keystrokes sent. Native touch/focus and Pi rendering remain unverified.")


if __name__ == "__main__":
    main()
