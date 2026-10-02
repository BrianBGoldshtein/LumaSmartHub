"""Notification cue claims are local, private, bounded, and never replayed."""
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from luma.api import create_app
from luma.device_agent import apply_notification_chime
from luma.models import CalendarEvent, PhoneNotification
from luma.voice_speech import VoicePlaybackError, notification_cue_pcm
from luma import voice_speech


def notice(now, key='one'):
    return PhoneNotification(key, 'net.whatsapp.WhatsApp', 'WhatsApp',
                             'A new message', 'Hello', now)


def test_new_phone_notice_claimed_once_and_not_replayed_on_refresh_or_restart(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    now = datetime.now(UTC)
    service.phone_seen(now)
    service.receive_notification(notice(now))
    client = TestClient(app)
    claim = lambda: client.post('/api/v1/device/notification-chime').json()
    assert claim() == {'play': True, 'volume': 35}
    assert service.snapshot(now)['notifications'][0]['id'] == 'one'
    assert claim()['play'] is False
    service.receive_notification(notice(now))  # ANCS update with the same UID.
    assert claim()['play'] is False
    assert create_app(data_dir=tmp_path).state.luma.claim_notification_chime(now)['play'] is False


def test_privacy_mute_and_expired_phone_notices_are_consumed(tmp_path):
    service = create_app(data_dir=tmp_path).state.luma
    now = datetime.now(UTC)
    service.receive_notification(notice(now))
    assert service.claim_notification_chime(now)['play'] is False
    service.phone_seen(now)
    assert service.claim_notification_chime(now)['play'] is False
    service.receive_notification(notice(now, 'two'))
    service.update_settings({'notification_chime_enabled': False}, now)
    assert service.claim_notification_chime(now)['play'] is False
    service.update_settings({'notification_chime_enabled': True}, now)
    assert service.claim_notification_chime(now)['play'] is False
    service.receive_notification(notice(now-timedelta(minutes=1), 'old'))
    assert service.claim_notification_chime(now)['play'] is False
    service.receive_notification(notice(now, 'three'))
    service.update_settings({'volume': 0}, now)
    assert service.claim_notification_chime(now)['play'] is False
    service.update_settings({'volume': 55}, now)
    assert service.claim_notification_chime(now)['play'] is False


def test_departure_cue_survives_restart_without_replay(tmp_path):
    app = create_app(data_dir=tmp_path)
    service = app.state.luma
    now = datetime.now(UTC)
    service.update_settings({'departure_enabled': True,
                             'departure_calendar_ids': ['personal']}, now)
    service.phone_seen(now)
    event = CalendarEvent('meeting', 'personal', 'Meeting',
                          now+timedelta(minutes=25), now+timedelta(hours=1))
    service.replace_events([event], now)
    service.calendar_synced_at = now
    assert service.claim_notification_chime(now)['play'] is True
    assert service.claim_notification_chime(now)['play'] is False
    restored = create_app(data_dir=tmp_path).state.luma
    restored.phone_seen(now)
    restored.calendar_synced_at = now
    assert restored.claim_notification_chime(now)['play'] is False


def test_departure_during_private_standby_is_not_replayed_when_phone_returns(tmp_path):
    service = create_app(data_dir=tmp_path).state.luma
    now = datetime.now(UTC)
    service.update_settings({'departure_enabled': True,
                             'departure_calendar_ids': ['personal']}, now)
    event = CalendarEvent('meeting', 'personal', 'Meeting',
                          now+timedelta(minutes=25), now+timedelta(hours=1))
    service.replace_events([event], now)
    service.calendar_synced_at = now
    assert service.claim_notification_chime(now)['play'] is False
    service.phone_seen(now)
    assert service.claim_notification_chime(now)['play'] is False


def test_sleep_and_screen_off_silence_new_alerts_without_later_replay(tmp_path):
    service = create_app(data_dir=tmp_path).state.luma
    now = datetime.now(UTC)
    service.update_settings({'departure_enabled': True,
                             'departure_calendar_ids': ['personal'],
                             'sleep_calendar_ids': ['sleep']}, now)
    service.phone_seen(now)
    meeting = CalendarEvent('meeting', 'personal', 'Meeting',
                            now+timedelta(minutes=25), now+timedelta(hours=1))
    sleep = CalendarEvent('night', 'sleep', 'Sleep',
                          now-timedelta(minutes=5), now+timedelta(minutes=10))
    service.replace_events([meeting, sleep], now)
    service.calendar_synced_at = now
    service.receive_notification(notice(now))
    assert service.snapshot(now)['state']['display_power'] == 'off'
    assert service.claim_notification_chime(now)['play'] is False
    service.replace_events([meeting], now+timedelta(minutes=11))
    assert service.claim_notification_chime(now+timedelta(minutes=11))['play'] is False


def test_notification_settings_and_claim_are_local_only(tmp_path):
    app = create_app(data_dir=tmp_path)
    local = TestClient(app)
    remote = TestClient(app, client=('192.0.2.20', 5000))
    token = app.state.security.get_or_create_lan_token()
    assert remote.post('/api/v1/device/notification-chime',
                       headers={'X-Luma-Token': token}).status_code == 403
    assert remote.patch('/api/v1/settings', json={'notification_chime_enabled': False},
                        headers={'X-Luma-Token': token}).status_code == 403
    for invalid in ({'notification_chime_enabled': 'yes'},
                    {'notification_chime_volume': -1},
                    {'notification_chime_volume': True},
                    {'notification_chime_volume': 101}):
        assert local.patch('/api/v1/settings', json=invalid).status_code == 422
    assert local.patch('/api/v1/settings', json={
        'notification_chime_enabled': False,
        'notification_chime_volume': 25}).status_code == 200
    restored = create_app(data_dir=tmp_path).state.luma.settings
    assert restored.notification_chime_enabled is False
    assert restored.notification_chime_volume == 25


def test_notification_cue_is_short_bounded_and_scales_with_volume():
    low = notification_cue_pcm(20)
    high = notification_cue_pcm(80)
    assert len(low) == len(high)
    assert 15000 < len(low) < 25000  # Under half a second at 22.05 kHz/16-bit.
    assert max(abs(int.from_bytes(low[i:i+2], 'little', signed=True)) for i in range(0, len(low), 2)) < \
           max(abs(int.from_bytes(high[i:i+2], 'little', signed=True)) for i in range(0, len(high), 2))
    for invalid in (-1, True, 101):
        with pytest.raises(ValueError):
            notification_cue_pcm(invalid)


def test_notification_cue_uses_the_same_explicit_local_route_as_voice(monkeypatch):
    played = []
    monkeypatch.setattr(voice_speech, 'pulse_playback_environment', lambda: {'PULSE_SERVER': 'local'})
    monkeypatch.setattr(voice_speech, '_play_pcm',
                        lambda pcm, env: played.append((pcm, env)) or 'system_speaker')
    assert voice_speech.play_notification_cue(35) == 'system_speaker'
    assert played[0][1] == {'PULSE_SERVER': 'local'}
    assert played[0][0] == notification_cue_pcm(35)


def test_device_bridge_never_replays_failed_notification_audio():
    claim = Mock(return_value={'play': True, 'volume': 35})
    play = Mock(side_effect=VoicePlaybackError('speaker_route_unavailable'))
    assert apply_notification_chime(claim, play) == 'unavailable; not replayed'
    play.assert_called_once_with(35)
    claim.return_value = {'play': False, 'volume': 35}
    assert apply_notification_chime(claim, play) is None
    play.assert_called_once()


def test_device_report_accepts_only_fixed_chime_status(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.post('/api/v1/device/report', json={
        'controls': {'notification_chime': 'unavailable; not replayed'}}).status_code == 200
    assert client.post('/api/v1/device/report', json={
        'controls': {'notification_chime': 'private message'}}).status_code == 422
