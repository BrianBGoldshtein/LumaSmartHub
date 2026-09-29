from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from luma.api import create_app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.app = create_app(data_dir=Path(self.temporary_directory.name))
        self.client = TestClient(self.app)

    def test_health_and_private_initial_state(self) -> None:
        health = self.client.get("/api/v1/health")
        state = self.client.get("/api/v1/state")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["database"], "ok")
        self.assertEqual(state.status_code, 200)
        self.assertTrue(state.json()["privacy_redacted"])

    def test_settings_and_command_round_trip(self) -> None:
        patched = self.client.patch(
            "/api/v1/settings",
            json={"theme": "hearth", "brightness": 38, "orientation": "portrait-clockwise"},
        )
        command = self.client.post(
            "/api/v1/commands",
            json={"name": "set_volume", "value": 63},
        )

        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["theme"], "hearth")
        self.assertEqual(command.status_code, 200)
        self.assertTrue(command.json()["result"]["accepted"])
        self.assertEqual(command.json()["snapshot"]["settings"]["volume"], 63)

    def test_invalid_command_returns_validation_error_without_mutation(self) -> None:
        response = self.client.post(
            "/api/v1/commands",
            json={"name": "set_brightness", "value": 101},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/v1/settings").json()["brightness"], 70)

    def test_pin_setup_and_unlock(self) -> None:
        setup = self.client.post("/api/v1/security/pin", json={"pin": "0427"})
        incorrect = self.client.post("/api/v1/security/unlock", json={"pin": "9999"})
        unlocked = self.client.post("/api/v1/security/unlock", json={"pin": "0427"})

        self.assertEqual(setup.status_code, 200)
        self.assertEqual(incorrect.status_code, 401)
        self.assertEqual(unlocked.status_code, 200)
        self.assertFalse(unlocked.json()["privacy_redacted"])

    def test_local_ui_can_retrieve_stable_shortcut_token(self) -> None:
        first = self.client.get("/api/v1/security/lan-token")
        second = self.client.get("/api/v1/security/lan-token")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())

    def test_websocket_starts_with_complete_snapshot(self) -> None:
        with self.client.websocket_connect("/api/v1/events") as websocket:
            message = websocket.receive_json()

        self.assertEqual(message["type"], "snapshot")
        self.assertIn("settings", message["data"])


if __name__ == "__main__":
    unittest.main()
