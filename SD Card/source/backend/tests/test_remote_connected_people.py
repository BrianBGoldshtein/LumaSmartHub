"""Real signed primary/secondary preview; no live phones or private accounts."""
from itertools import product
import pytest
from test_multiuser_app import app_rig
from test_companion_multiuser_api import browser
from test_companion_api import dispatch,envelope,client


@pytest.mark.asyncio
@pytest.mark.parametrize('viewer',[0,1])
@pytest.mark.parametrize('others',list(product([False,True],repeat=4)))
async def test_roster_includes_all_verified_phones_and_only_names_roles_self(app_rig,viewer,others):
    app,users,link,_=app_rig;rig=browser(app_rig,viewer)
    active={users[viewer].id}
    for user,present in zip([u for n,u in enumerate(users) if n!=viewer],others):
        if present:link(user.id);active.add(user.id)
    result=await dispatch(rig,'GET','/remote/api/preview')
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    rows=result.json()['connected_users']
    assert rows==[{'nickname':u.nickname,'role':u.role,'self':u.id==users[viewer].id}
                  for u in users if u.id in active]
    assert all(set(row)=={'nickname','role','self'} for row in rows)
    assert all(u.nickname+' PRIVATE' not in result.text for n,u in enumerate(users) if n!=viewer)
    assert 'phone_address' not in result.text and 'notifications' not in result.text


@pytest.mark.asyncio
async def test_guest_no_calendars_or_wall_sharing_still_appears_but_lost_link_disappears(app_rig):
    app,users,link,_=app_rig;rig=browser(app_rig,0);other=users[1]
    app.state.profiles.update_personal(other.id,{'visible_calendar_ids':[],'todo_calendar_id':None})
    app.state.profiles.set_setup(other.id,'ready',wall_share_approved=False)
    link(other.id)
    async def names():return [r['nickname'] for r in (await dispatch(rig,'GET','/remote/api/preview')).json()['connected_users']]
    assert other.nickname in await names()
    child=app.state.bluetooth.runtime(other.id);child.remote_authorized.clear()
    child.service.state.phone_connected=True  # Stale UI/pairing is not live authority.
    assert other.nickname not in await names()
    link(other.id);assert other.nickname in await names()
    child.remote_authorized.last_checked-=16
    assert other.nickname not in await names()
    pending=envelope(rig,'GET','/remote/api/preview')
    app.state.bluetooth.runtime('primary').remote_authorized.clear()
    async with client(app) as caller:result=await caller.post('/api/v1/companion/dispatch',json=pending)
    assert result.status_code==403 and 'connected_users' not in result.text


@pytest.mark.asyncio
@pytest.mark.parametrize('viewer',[0,1])
async def test_timer_action_preview_also_keeps_current_roster(app_rig,viewer):
    app,users,link,_=app_rig;rig=browser(app_rig,viewer)
    for user in users:link(user.id)
    result=await dispatch(rig,'POST','/remote/api/command',{'name':'start_timer','value':5})
    assert result.status_code==200 and len(result.json()['preview']['connected_users'])==5
