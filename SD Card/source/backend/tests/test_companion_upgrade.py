"""First-install handoff preserves the existing owner opt-in boundary."""
from types import SimpleNamespace
import pytest
from luma.update_broker import refresh_gateway_after_030_upgrade,ProgressStore


@pytest.mark.parametrize('enabled',['enabled','disabled','static','enabled-runtime','masked'])
def test_first_remote_handoff_restarts_only_persistently_owner_enabled_gateway(tmp_path,enabled):
    root=tmp_path/'releases';current=root/'0.3.0';current.mkdir(parents=True)
    (current/'.luma-release.json').write_text('{"version":"0.3.0"}')
    app=tmp_path/'luma';app.symlink_to(current,target_is_directory=True)
    status=root/'.luma-update-status.json'
    ProgressStore(status).write({'state':'installed','phase':'complete','target_version':'0.3.0','started_epoch':1,'message':'Installed'})
    calls=[]
    def runner(command,**kwargs):
        calls.append(command);return SimpleNamespace(returncode=0 if enabled=='enabled' else 1,stdout=enabled+'\n')
    kwargs=dict(status_path=status,app_root=app,releases_root=root,runner=runner)
    assert refresh_gateway_after_030_upgrade(**kwargs)==(enabled=='enabled')
    assert all('enable' not in call and 'tailscale' not in call for call in calls)
    if enabled=='enabled':
        assert calls[-1]==['/usr/bin/systemctl','--no-block','restart','luma-shortcut-gateway.service']
        assert refresh_gateway_after_030_upgrade(**kwargs) is False
        assert len(calls)==2
    else:assert len(calls)==1


@pytest.mark.parametrize('version,state',[('0.2.11','installed'),('0.3.0','failed'),('0.3.1','installed')])
def test_handoff_does_not_run_after_failure_or_other_versions(tmp_path,version,state):
    status=tmp_path/'status'
    ProgressStore(status).write({'state':state,'phase':'complete' if state=='installed' else 'failed','target_version':version,'started_epoch':1,'message':'Status'})
    def runner(*_,**__):raise AssertionError('Must not touch any service')
    assert not refresh_gateway_after_030_upgrade(status_path=status,app_root=tmp_path/'missing',releases_root=tmp_path,runner=runner)
