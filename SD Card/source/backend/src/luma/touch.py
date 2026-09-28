"""Watch only devices with touchscreen capabilities, never keyboard events."""
import select
import time


def is_touchscreen(capabilities: dict) -> bool:
    # Linux input ABI: EV_KEY=1, EV_ABS=3, BTN_TOUCH=330,
    # ABS_MT_POSITION_X/Y=53/54, ABS_X/Y=0/1.
    absolute = capabilities.get(3, [])
    return (53 in absolute and 54 in absolute) or (330 in capabilities.get(1, []) and 0 in absolute and 1 in absolute)


class TouchWake:
    def __init__(self):
        self.devices = []
        self.next_scan = 0.0

    def touched(self) -> bool:
        from evdev import InputDevice, list_devices
        if time.monotonic() >= self.next_scan:
            for device in self.devices:
                device.close()
            self.devices = []
            for path in list_devices():
                try:
                    device = InputDevice(path)
                    if is_touchscreen(device.capabilities(absinfo=False)):
                        self.devices.append(device)
                    else:
                        device.close()
                except OSError:
                    continue
            self.next_scan = time.monotonic() + 60
        touched = False
        if self.devices:
            ready, _, _ = select.select(self.devices, [], [], 0)
            for device in ready:
                try:
                    for event in device.read():
                        if (event.type == 1 and event.code == 330 and event.value == 1) or (event.type == 3 and event.code == 57 and event.value >= 0):
                            touched = True
                except (OSError, BlockingIOError):
                    self.next_scan = 0
        return touched
