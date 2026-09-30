"""Small, dependency-light wire envelope for encrypted portable backups.

This module is imported by the privileged USB broker at cold start. Keep it
free of application services and provider/device integrations so socket
activation can answer before the kiosk's much larger dependency graph loads.
"""
from __future__ import annotations

import base64
import json
import struct


MAGIC = b"LUMAUSB\x01"
VERSION = 1
MAX_ARCHIVE_BYTES = 1024 * 1024
TAG_BYTES = 16
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
NONCE_BYTES = 12


def _no_duplicate_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def validate_archive_envelope(blob: bytes) -> bool:
    """Check the bounded, fixed-cost encrypted container before media I/O."""
    if not isinstance(blob, (bytes, bytearray, memoryview)) or not 10 <= len(blob) <= MAX_ARCHIVE_BYTES:
        return False
    raw = bytes(blob)
    if raw[:len(MAGIC)] != MAGIC:
        return False
    header_length = struct.unpack(">H", raw[len(MAGIC):len(MAGIC) + 2])[0]
    start = len(MAGIC) + 2
    if not 1 <= header_length <= 1024 or start + header_length + TAG_BYTES > len(raw):
        return False
    try:
        header = json.loads(raw[start:start + header_length], object_pairs_hook=_no_duplicate_pairs)
        expected = {"version": VERSION, "cipher": "AES-256-GCM", "kdf": "scrypt", "n": SCRYPT_N,
                    "r": SCRYPT_R, "p": SCRYPT_P}
        if (not isinstance(header, dict) or set(header) != set(expected) | {"salt", "nonce"}
                or any(header.get(key) != value for key, value in expected.items())):
            return False
        salt = base64.b64decode(header["salt"], altchars=b"-_", validate=True)
        nonce = base64.b64decode(header["nonce"], altchars=b"-_", validate=True)
        return len(salt) == SALT_BYTES and len(nonce) == NONCE_BYTES
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return False
