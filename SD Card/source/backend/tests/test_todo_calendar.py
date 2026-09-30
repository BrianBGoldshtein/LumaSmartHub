import json
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from googleapiclient.errors import HttpError
import httplib2

from luma.api import create_app
from luma.calendar_logic import todo_events, todo_view
from luma.integrations.google_calendar import GoogleCalendarClient, parse_google_event, TaskConflict, TASK_WRITE_SCOPE, CALENDAR_SCOPE, TOKEN_KEY
from luma.models import CalendarEvent
from luma.storage import Storage

NOW=datetime(2026,9,26,20,tzinfo=UTC)
ZONE=ZoneInfo('America/Los_Angeles')


def raw_task(**extra):
    return {'id':'task1','summary':'Task title only','start':{'date':'2026-09-20'},'end':{'date':'2026-09-28'},
            'etag':'"version1"','description':'Do not show this','location':'Do not show this either',**extra}


def test_only_today_active_all_day_events_and_inclusive_visible_due_date():
    active=parse_google_event(raw_task(),'tasks','America/Los_Angeles')
    events=[active,replace(active,id='future',start=datetime(2026,9,27,tzinfo=ZONE)),
            replace(active,id='expired',end=datetime(2026,9,26,tzinfo=ZONE)),replace(active,id='cancelled',status='cancelled'),
            replace(active,id='other',calendar_id='other'),replace(active,id='timed',all_day=False)]
    assert todo_events(events,todo_calendar_id='tasks',now=NOW)==[active]
    assert todo_events([active],todo_calendar_id='tasks',now=datetime(2026,9,28,6,59,tzinfo=UTC))==[active]
    assert todo_events([active],todo_calendar_id='tasks',now=datetime(2026,9,28,7,tzinfo=UTC))==[]
    view=todo_view(active,'2')
    assert view['due_date']=='2026-09-27' and view['summary']=='Task title only'
    assert 'description' not in view and 'location' not in view


@pytest.mark.parametrize('color,completed',[(None,False),('0',False),('2',True),('5',False)])
def test_only_selected_color_means_completed(color,completed):
    raw=raw_task(**({'colorId':color} if color else {}))
    event=parse_google_event(raw,'tasks','UTC')
    assert todo_view(event,'2')['completed'] is completed
    assert todo_view(event,None)['completed'] is False


def test_calendar_default_rgb_does_not_define_completion():
    event=parse_google_event(raw_task(),'tasks','UTC')
    event.calendar_color='#7ae7bf'
    assert not todo_view(event,'2')['completed']


def test_one_day_and_dst_multi_day_ranges():
    event=parse_google_event(raw_task(start={'date':'2026-11-01'},end={'date':'2026-11-02'}),'tasks','America/Los_Angeles')
    assert (event.end.astimezone(UTC)-event.start.astimezone(UTC)).total_seconds()==25*3600
    for moment in (datetime(2026,11,1,8,30,tzinfo=UTC),datetime(2026,11,1,9,30,tzinfo=UTC)):
        assert todo_events([event],todo_calendar_id='tasks',now=moment)==[event]
    assert todo_view(event,'2')['due_date']=='2026-11-01'


def provider(tmp_path):
    client=GoogleCalendarClient(Storage(tmp_path/'luma.db'))
    client.storage.set_secret(TOKEN_KEY,json.dumps({'scopes':[CALENDAR_SCOPE,TASK_WRITE_SCOPE]}))
    service=MagicMock()
    service.events().get().execute.return_value=raw_task()
    service.events().patch().headers={}
    service.events().patch().execute.return_value=raw_task(colorId='2',etag='"version2"')
    service.colors().get().execute.return_value={'event':{'2':{'background':'#7ae7bf'}}}
    client._service=lambda:service
    return client,service


def recolor(client,**overrides):
    return client.recolor_task(**({'calendar_id':'tasks','event_id':'task1','expected_etag':'"version1"','color_id':'2','timezone':'America/Los_Angeles','now':NOW}|overrides))


def test_patch_changes_only_color_and_never_retries_or_changes_series(tmp_path):
    client,service=provider(tmp_path)
    updated=recolor(client)
    assert updated.event_color_id=='2' and updated.event_color=='#7ae7bf' and updated.etag=='"version2"'
    kwargs=service.events().patch.call_args.kwargs
    assert kwargs=={'calendarId':'tasks','eventId':'task1','body':{'colorId':'2'},'sendUpdates':'none'}
    assert service.events().patch().headers['If-Match']=='"version1"'
    service.events().patch().execute.assert_called_once_with(num_retries=0)
    service.events().patch().execute.return_value=raw_task(etag='"version3"')
    assert recolor(client,color_id=None).event_color_id is None
    assert service.events().patch.call_args.kwargs['body']=={'colorId':None}


@pytest.mark.parametrize('changes',[{'etag':'"changed"'},{'status':'cancelled'},{'recurrence':['RRULE:FREQ=DAILY']},
                                     {'start':{'dateTime':NOW.isoformat()},'end':{'dateTime':(NOW+timedelta(hours=1)).isoformat()}}])
def test_changed_cancelled_timed_or_series_never_patch(tmp_path,changes):
    client,service=provider(tmp_path)
    service.events().patch.reset_mock()
    service.events().get().execute.return_value=raw_task(**changes)
    with pytest.raises(ValueError):recolor(client)
    service.events().patch.assert_not_called()


def test_etag_race_conflict_and_no_false_confirmation(tmp_path):
    client,service=provider(tmp_path)
    service.events().patch().execute.side_effect=HttpError(httplib2.Response({'status':'412'}),b'{}')
    with pytest.raises(TaskConflict):recolor(client)
    service.events().patch().execute.assert_called_once_with(num_retries=0)
    service.events().patch().execute.side_effect=None
    service.events().patch().execute.return_value=raw_task()
    with pytest.raises(ValueError,match='confirm'):recolor(client)


def test_no_permission_and_unknown_palette_color_are_safe(tmp_path):
    client,service=provider(tmp_path)
    with pytest.raises(ValueError,match='unavailable'):recolor(client,color_id='99')
    client.storage.set_secret(TOKEN_KEY,json.dumps({'scopes':[CALENDAR_SCOPE]}))
    service.events.reset_mock()
    with pytest.raises(PermissionError):recolor(client)
    service.events.assert_not_called()


def active_app(tmp_path):
    app=create_app(data_dir=tmp_path)
    now=datetime.now(UTC)
    event=CalendarEvent('task1','tasks','Task',now-timedelta(days=2),now+timedelta(days=2),all_day=True,
                        etag='"version1"',calendar_color='#7986cb')
    app.state.luma.update_settings({'todo_calendar_id':'tasks','todo_completed_color_id':'2'})
    app.state.luma.replace_events([event])
    app.state.luma.unlock_with_pin()
    return app,event


def test_endpoint_accepts_only_selected_current_task_and_preserves_privacy(tmp_path):
    app,event=active_app(tmp_path)
    client=TestClient(app)
    body={'calendar_id':'tasks','event_id':'task1','etag':'"version1"','completed':True}
    updated=replace(event,event_color_id='2',event_color='#7ae7bf',etag='"version2"')
    with patch.object(app.state.google,'recolor_task',return_value=updated) as write:
        assert client.post('/api/v1/todos/complete',json={**body,'calendar_id':'not-tasks'}).status_code==422
        assert client.post('/api/v1/todos/complete',json={**body,'etag':'"old"'}).status_code==409
        assert client.post('/api/v1/todos/complete',json={**body,'completed':'yes'}).status_code==422
        assert client.post('/api/v1/todos/complete',json={**body,'title':'overwrite'}).status_code==422
        write.assert_not_called()
        result=client.post('/api/v1/todos/complete',json=body)
        assert result.status_code==200 and result.json()['todos'][0]['completed']
        assert result.json()['todos'][0]['calendar_color']=='#7986cb'
        assert client.post('/api/v1/todos/complete',json=body).status_code==409
        assert write.call_count==1
    restored=create_app(data_dir=tmp_path).state.luma
    assert restored.events[0].event_color_id=='2'
    restored.state.forced_private=True
    assert restored.snapshot()['todos']==[]


def test_endpoint_failure_keeps_prior_state_and_remote_cannot_write(tmp_path):
    app,event=active_app(tmp_path)
    body={'calendar_id':'tasks','event_id':'task1','etag':'"version1"','completed':True}
    client=TestClient(app)
    with patch.object(app.state.google,'recolor_task',side_effect=TimeoutError('private provider detail')) as write:
        assert client.post('/api/v1/todos/complete',json=body).status_code==502
        assert app.state.luma.events==[event]
        token=app.state.security.get_or_create_lan_token()
        remote=TestClient(app,client=('192.0.2.20',5000))
        assert remote.post('/api/v1/todos/complete',json=body,headers={'X-Luma-Token':token}).status_code==403
        assert client.post('/api/v1/todos/complete',json=body,headers={'Origin':'https://evil.example'}).status_code==403
        app.state.luma.state.forced_private=True
        assert client.post('/api/v1/todos/complete',json=body).status_code==403
        assert write.call_count==1


def test_more_than_three_tasks_and_manual_recolor_refresh_are_not_truncated(tmp_path):
    app,event=active_app(tmp_path)
    app.state.luma.replace_events([replace(event,id=f'task{i}',event_color_id='2' if i==3 else None) for i in range(12)])
    todos=app.state.luma.snapshot()['todos']
    assert len(todos)==12 and todos[-1]['completed']
    app.state.luma.replace_events([replace(e,event_color_id=None) for e in app.state.luma.events])
    assert not any(item['completed'] for item in app.state.luma.snapshot()['todos'])


def test_explicit_scope_upgrade_is_local_and_does_not_unlock(tmp_path):
    from test_google_oauth import CONFIG
    app=create_app(data_dir=tmp_path)
    app.state.google.set_client_config(CONFIG)
    client=TestClient(app)
    scopes=parse_qs(urlsplit(client.post('/api/v1/google/authorize-tasks').json()['url']).query)['scope'][0].split()
    assert set(scopes)=={CALENDAR_SCOPE,TASK_WRITE_SCOPE}
    assert client.get('/api/v1/state').json()['privacy_redacted']
    assert not client.get('/api/v1/google/status').json()['task_updates']
    token=app.state.security.get_or_create_lan_token()
    remote=TestClient(app,client=('192.0.2.20',5000))
    assert remote.post('/api/v1/google/authorize-tasks',headers={'X-Luma-Token':token}).status_code==403


@pytest.mark.parametrize('granted',[True,False])
def test_real_sdk_upgrade_persists_only_granted_permissions(tmp_path,granted):
    import requests
    from urllib.parse import urlencode
    from test_google_oauth import CONFIG
    client=GoogleCalendarClient(Storage(tmp_path/'luma.db'))
    client.set_client_config(CONFIG)
    original=json.dumps({'scopes':[CALENDAR_SCOPE], 'refresh_token':'existing-synthetic'})
    client.storage.set_secret(TOKEN_KEY,original)
    query=parse_qs(urlsplit(client.begin_authorization(task_updates=True)).query)
    state=query['state'][0]
    def exchange(session,request,**kwargs):
        response=requests.Response();response.request=request;response.status_code=200
        response._content=json.dumps({'access_token':'synthetic', 'refresh_token':'synthetic-refresh','token_type':'Bearer','expires_in':3600,
                                     'scope':' '.join([CALENDAR_SCOPE,TASK_WRITE_SCOPE] if granted else [CALENDAR_SCOPE])}).encode()
        return response
    callback=client.redirect_uri+'?'+urlencode({'state':state,'code':'synthetic'})
    with patch.object(requests.Session,'send',exchange):
        if granted:client.finish_authorization(callback,state)
        else:
            with pytest.raises((Warning,ValueError)):client.finish_authorization(callback,state)
    assert client.task_write_authorized() is granted
    if not granted:assert client.storage.get_secret(TOKEN_KEY)==original
    else:
        restored=GoogleCalendarClient(Storage(tmp_path/'luma.db'))
        assert TASK_WRITE_SCOPE in restored._credentials().scopes
        assert TASK_WRITE_SCOPE in parse_qs(urlsplit(restored.begin_authorization()).query)['scope'][0]


def test_write_capability_requires_both_scope_and_calendar_role(tmp_path):
    app,event=active_app(tmp_path)
    app.state.luma.todo_write_authorized=True
    assert not app.state.luma.snapshot()['todo_controls']['can_update']
    app.state.luma.replace_events([replace(event,calendar_writable=True)])
    assert app.state.luma.snapshot()['todo_controls']['can_update']
    app.state.luma.todo_write_authorized=False
    assert not app.state.luma.snapshot()['todo_controls']['can_update']
