from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from luma.api import create_app
from luma.models import CalendarEvent
from luma.voice import WakeGate, parse_local_command
from luma.voice_agent import choose_command


def test_wake_gate_requires_phrase_and_expires():
    gate = WakeGate()
    assert gate.accept("good night", 100) is None
    assert gate.accept("hey luma", 100) == ""
    assert gate.accept("brightness fifty", 103) == "brightness fifty"
    assert gate.accept("good night", 104) is None
    assert gate.accept("hey luma good morning", 110) == "good morning"
    assert gate.accept("hey luma", 120) == ""
    assert gate.accept("good night", 128) is None


def test_dual_decoder_keeps_known_command_when_free_dictation_is_bad():
    assert choose_command("good morning", "hey luma blue marlin", "hey luma") == (
        "good morning", "constrained")
    assert choose_command("what time is it", "hey luma blue marlin", "hey luma") == (
        "what time is it", "constrained")
    assert choose_command("", "hey luma what's the time", "hey luma") == (
        "what's the time", "free")


def test_dual_decoder_never_guesses_conflicting_actions_or_negations():
    assert choose_command("set brightness to fifty", "hey luma set brightness to sixty", "hey luma") == (
        None, "conflict")
    assert choose_command("good morning", "hey luma good night", "hey luma") == (None, "conflict")
    assert choose_command("set brightness to fifty", "hey luma do not set brightness to fifty", "hey luma") == (
        None, "negated")
    assert choose_command("what is the weather today", "hey luma what's the weather tomorrow", "hey luma") == (
        "what's the weather tomorrow", "free_query")


def test_one_hundred_is_not_parsed_as_zero():
    assert parse_local_command("brightness one hundred").value == 100


def test_mute_cancels_calibration_and_rejects_late_voice_actions(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get("/api/v1/settings").json()["voice_enabled"] is True
    session = client.post("/api/v1/voice/calibration/start").json()["session"]
    client.post("/api/v1/voice/phase", json={"phase": "listening"})
    assert client.patch("/api/v1/settings", json={"voice_enabled": False}).status_code == 200
    assert not client.get("/api/v1/voice/calibration").json()["active"]
    assert client.post("/api/v1/voice/calibration/sample", json={
        "session": session, "text": "hey luma brightness fifty", "rms": .1, "peak": .6,
    }).status_code == 409
    assert not client.post("/api/v1/voice/command", json={"text": "brightness zero"}).json()["accepted"]
    assert not client.post("/api/v1/voice/phase", json={"phase": "speaking"}).json()["accepted"]
    state = client.get("/api/v1/state").json()
    assert state["settings"]["brightness"] == 70
    assert state["state"]["assistant_phase"] == "idle"
    assert client.patch("/api/v1/settings", json={"voice_enabled": True}).status_code == 200
    assert client.post("/api/v1/voice/command", json={"text": "brightness fifty"}).json()["accepted"]


def test_voice_morning_never_discloses_private_calendar(tmp_path):
    app = create_app(data_dir=tmp_path)
    now = datetime.now(UTC)
    app.state.luma.update_settings({"visible_calendar_ids": ["primary"]})
    app.state.luma.replace_events([CalendarEvent("1", "primary", "Secret meeting", now, now + timedelta(hours=1))])
    client = TestClient(app)
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" not in reply
    assert "private" in reply
    app.state.luma.phone_seen()
    reply = client.post("/api/v1/voice/command", json={"text": "good morning"}).json()["message"]
    assert "Secret meeting" in reply
