import pytest
from fastapi.testclient import TestClient
from luma.api import create_app
from luma.onboarding import STEPS, load_progress, transition
from luma.storage import Storage


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path))


def test_fresh_setup_is_private_and_secret_free(client):
    response = client.get('/api/v1/onboarding')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    data = response.json()
    assert data['step'] == 'welcome' and not data['completed']
    assert data['statuses'] == {}
    assert data['summary'] == dict(weather=False, pin=False, google=False, phone_selected=False, voice_enabled=True,
                                  weather_nudges_enabled=False, timer_focus_minutes=25, timer_break_minutes=5,
                                  departure_enabled=False, departure_calendars=0, night_clock_enabled=True, night_brightness=5, countdowns=0, public_countdowns=0,
                                  transit_stops=0, public_transit_stops=0, transit_token=False,
                                  purifier_session=False, purifier_selected=False, room_recovery=False,
                                  scenes_enabled=0, scenes_automatic=0, scenes_recovery=False)
    assert client.get('/api/v1/state').json()['privacy_redacted']


def test_progress_survives_restart_and_finish_is_explicit(tmp_path):
    client = TestClient(create_app(data_dir=tmp_path))
    for step in STEPS[:4]:
        assert client.post('/api/v1/onboarding', json={'action':'continue','step':step}).status_code == 200
    client = TestClient(create_app(data_dir=tmp_path))
    assert client.get('/api/v1/onboarding').json()['step'] == 'extras'
    result = client.post('/api/v1/onboarding', json={'action':'skip_optional'}).json()
    assert result['step'] == 'review' and not result['completed']
    assert result['statuses']['voice'] == 'later'
    assert result['summary']['voice_enabled']  # Skipping a check is not muting.
    result = client.post('/api/v1/onboarding', json={'action':'finish'}).json()
    assert result['completed']
    assert client.get('/api/v1/state').json()['privacy_redacted']
    assert client.post('/api/v1/onboarding', json={'action':'finish'}).json()['completed']
    assert TestClient(create_app(data_dir=tmp_path)).get('/api/v1/onboarding').json()['completed']


@pytest.mark.parametrize('payload', [None, [], {'action':'finish'}, {'action':'later','step':'welcome'},
    {'action':'continue','step':'space'}, {'action':'visit','step':['review']}, {'action':{}},
    {'action':'continue','step':'welcome','password':'must-not-save'}, {'action':'skip_optional'},
    {'action':'unknown'}, {'action':'visit','step':'unknown'}])
def test_invalid_requests_do_not_mutate(client, payload):
    before = client.get('/api/v1/onboarding').json()
    assert client.post('/api/v1/onboarding', json=payload).status_code == 422
    assert client.get('/api/v1/onboarding').json() == before


def test_bounded_input_and_local_only(client):
    assert client.post('/api/v1/onboarding', content='x'*1025).status_code == 413
    assert client.post('/api/v1/onboarding', content='not JSON').status_code == 422
    token = client.get('/api/v1/security/lan-token').json()['token']
    remote = TestClient(client.app, client=('100.101.102.103', 5000))
    for verb in ('get','post'):
        assert getattr(remote,verb)('/api/v1/onboarding', headers={'X-Luma-Token':token}).status_code == 403
        assert getattr(client,verb)('/api/v1/onboarding', headers={'Origin':'https://attacker.example'}).status_code == 403


def test_summary_uses_actual_settings_not_review_flags(client):
    client.patch('/api/v1/settings', json={'voice_enabled':False, 'latitude':37.4, 'longitude':-122.1,
                                         'weather_nudges_enabled':True, 'timer_focus_minutes':35})
    client.post('/api/v1/security/pin', json={'pin':'0427'})
    result = client.post('/api/v1/onboarding', json={'action':'visit','step':'review'}).json()
    assert result['summary']['weather'] and result['summary']['pin']
    assert not result['summary']['voice_enabled']
    assert result['summary']['weather_nudges_enabled'] and result['summary']['timer_focus_minutes']==35
    assert result['statuses'] == {} and not result['completed']
    client.post('/api/v1/onboarding', json={'action':'finish'})
    assert not client.get('/api/v1/settings').json()['voice_enabled']


def test_restoration_discards_unknown_fields(tmp_path):
    storage = Storage(tmp_path/'luma.db')
    storage.set_cache('onboarding','progress',{'step':'bogus','password':'discard','statuses':{'phone':'later','secret':'anything','voice':'passed'}})
    assert load_progress(storage) == {'version':1,'step':'welcome','statuses':{'phone':'later'}}
    for value in (None, [], 'invalid', {'step':[], 'statuses':[]}):
        storage.set_cache('onboarding','progress',value)
        assert load_progress(storage) == {'version':1,'step':'welcome','statuses':{}}


def test_skipping_retains_previous_reviews():
    state = {'version':1,'step':'calendar','statuses':{'phone':'reviewed'}}
    result = transition(state,{'action':'skip_optional'})
    assert result['statuses']['phone'] == 'reviewed'
    assert state['step'] == 'calendar'
