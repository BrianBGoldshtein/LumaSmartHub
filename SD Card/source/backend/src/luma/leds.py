"""Three low-brightness APA102 status LEDs on ReSpeaker V1 (SPI0, CS1)."""
from __future__ import annotations


def status_frame(phase: str) -> list[int]:
    # Original protocol encoder: start, three BGR pixels, end clocks.
    colors = {"listening": (100, 200, 160), "thinking": (160, 120, 220), "speaking": (80, 170, 220), "error": (220, 80, 50)}
    red, green, blue = colors.get(phase, (0, 0, 0))
    return [0] * 4 + [0xE2, blue, green, red] * 3 + [255] * 4


class StatusLeds:
    def __init__(self):
        self.spi = None
        try:
            import spidev
            self.spi = spidev.SpiDev()
            self.spi.open(0, 1)
            self.spi.max_speed_hz = 1_000_000
        except (ImportError, OSError):
            self.close()

    def phase(self, value: str) -> None:
        if self.spi:
            try:
                self.spi.xfer2(status_frame(value))
            except OSError:
                self.close()

    def close(self) -> None:
        if self.spi:
            try:
                self.spi.xfer2(status_frame("idle"))
            except OSError:
                pass
            self.spi.close()
            self.spi = None
