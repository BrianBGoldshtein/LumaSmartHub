"""Bounded ANCS protocol parsing. No notification actions (answer/decline) are sent."""
from dataclasses import dataclass
from datetime import UTC, datetime
import struct

from ..models import PhoneNotification

SERVICE = "7905f431-b5ce-4e99-a40f-4b1e122d00d0"
SOURCE = "9fbf120d-6301-42d9-8c58-25e699a21dbd"
CONTROL = "69d1d8f3-45e1-49a8-9821-9bbdfdaad9d9"
DATA = "22eac6e9-24d6-4bb5-be44-b36ace7c7bfb"


@dataclass
class Notice:
    event: int
    flags: int
    category: int
    uid: int


def parse_source(payload: bytes) -> Notice:
    if len(payload) != 8 or payload[0] > 2:
        raise ValueError("Invalid ANCS notification header")
    event, flags, category, count, uid = struct.unpack("<BBBBI", payload)
    return Notice(event, flags, category, uid)


def request_attributes(uid: int) -> bytes:
    # App ID, title (128 bytes), body (256 bytes).
    return struct.pack("<BI", 0, uid) + bytes([0, 1]) + struct.pack("<H", 128) + bytes([3]) + struct.pack("<H", 256)


class AttributeResponse:
    def __init__(self, uid: int):
        self.uid = uid
        self.buffer = bytearray()

    def feed(self, fragment: bytes) -> dict[int, str] | None:
        self.buffer.extend(fragment)
        if len(self.buffer) > 2048:
            raise ValueError("ANCS response exceeds limit")
        if len(self.buffer) < 5:
            return None
        command, uid = struct.unpack_from("<BI", self.buffer)
        if command != 0 or uid != self.uid:
            raise ValueError("Unexpected ANCS response")
        offset = 5
        values = {}
        for expected in (0, 1, 3):
            if len(self.buffer) < offset + 3:
                return None
            attr, size = struct.unpack_from("<BH", self.buffer, offset)
            if attr != expected or size > 1024:
                raise ValueError("Invalid ANCS attribute")
            offset += 3
            if len(self.buffer) < offset + size:
                return None
            values[attr] = bytes(self.buffer[offset:offset+size]).decode("utf-8", errors="replace")
            offset += size
        if offset != len(self.buffer):
            raise ValueError("Unexpected trailing ANCS data")
        return values


def notification(notice: Notice, values: dict[int, str]) -> PhoneNotification:
    app_id = values[0]
    names = {"com.apple.mobilephone": "Phone", "net.whatsapp.WhatsApp": "WhatsApp", "com.hammerandchisel.discord": "Discord"}
    return PhoneNotification(str(notice.uid), app_id, names.get(app_id, app_id), values[1], values[3], datetime.now(UTC), "incoming-call" if notice.category == 1 else "notification")
