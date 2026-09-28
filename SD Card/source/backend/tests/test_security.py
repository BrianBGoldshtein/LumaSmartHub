from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from luma.security import SecurityManager
from luma.storage import Storage


class SecurityManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        storage = Storage(Path(self.temporary_directory.name) / "luma.db")
        self.security = SecurityManager(storage)

    def test_pin_hash_round_trip_and_wrong_pin(self) -> None:
        self.security.set_pin("0427")

        self.assertTrue(self.security.pin_is_configured())
        self.assertTrue(self.security.verify_pin("0427"))
        self.assertFalse(self.security.verify_pin("0428"))

    def test_pin_format_is_restricted(self) -> None:
        for invalid in ("123", "123456789", "12ab"):
            with self.subTest(pin=invalid):
                with self.assertRaisesRegex(ValueError, "4 to 8 digits"):
                    self.security.set_pin(invalid)

    def test_pin_lockout_survives_service_recreation(self) -> None:
        self.security.set_pin("0427")
        for _ in range(5):
            self.assertFalse(self.security.verify_pin("1111"))
        restarted = SecurityManager(self.security.storage)
        self.assertFalse(restarted.verify_pin("0427"))

    def test_lan_token_is_stable_and_constant_length(self) -> None:
        first = self.security.get_or_create_lan_token()
        second = self.security.get_or_create_lan_token()

        self.assertEqual(first, second)
        self.assertGreaterEqual(len(first), 40)
        self.assertTrue(self.security.verify_lan_token(first))
        self.assertFalse(self.security.verify_lan_token(first + "x"))


if __name__ == "__main__":
    unittest.main()
