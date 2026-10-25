from unittest.mock import Mock

import httpx
import pytest

from luma import api,startup_diagnostics as diagnostic


@pytest.fixture
def timer(monkeypatch):
    monkeypatch.setattr(diagnostic,'_armed',False)
    start=Mock();cancel=Mock()
    monkeypatch.setattr(diagnostic.faulthandler,'dump_traceback_later',start)
    monkeypatch.setattr(diagnostic.faulthandler,'cancel_dump_traceback_later',cancel)
    return start,cancel


def test_startup_dump_is_one_shot_and_never_exits(timer):
    start,cancel=timer
    diagnostic.arm();diagnostic.arm()
    start.assert_called_once_with(30,repeat=False,file=diagnostic.sys.stderr,exit=False)
    diagnostic.healthy();diagnostic.healthy()
    cancel.assert_called_once()


def test_failed_watchdog_setup_cannot_prevent_api_startup(timer):
    timer[0].side_effect=OSError('synthetic stderr failure')
    diagnostic.arm();diagnostic.healthy()
    assert not diagnostic._armed
    timer[1].assert_not_called()


@pytest.mark.parametrize('production',[False,True])
def test_main_arms_only_on_the_appliance_and_always_cancels(monkeypatch,timer,production):
    monkeypatch.setattr(api.sys,'platform','linux')
    monkeypatch.setenv('LUMA_DATA_DIR','/var/lib/luma' if production else '/tmp/fake-luma')
    monkeypatch.setattr(api,'create_app',Mock(return_value=object()))
    monkeypatch.setattr(api.uvicorn,'run',Mock(side_effect=RuntimeError('synthetic exit')))
    with pytest.raises(RuntimeError,match='synthetic exit'):
        api.main()
    assert timer[0].call_count==int(production)
    assert timer[1].call_count==int(production)


@pytest.mark.asyncio
@pytest.mark.parametrize('database_ok',[False,True])
async def test_only_actual_database_health_cancels_startup_dump(tmp_path,monkeypatch,timer,database_ok):
    app=api.create_app(data_dir=tmp_path)
    diagnostic.arm()
    # Find the actual storage used by the production route without replacing
    # the route with a synthetic health endpoint.
    monkeypatch.setattr(app.state.luma.storage,'integrity_check',lambda:database_ok)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:8742') as client:
        response=await client.get('/api/v1/health')
    assert response.status_code==200
    assert response.json()['database']==('ok' if database_ok else 'error')
    assert timer[1].call_count==int(database_ok)
