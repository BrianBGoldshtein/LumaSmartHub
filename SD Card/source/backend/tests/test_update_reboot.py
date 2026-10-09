import json
import subprocess
import pytest
from luma.update_broker import ProgressStore,reboot_after_verified_upgrade


@pytest.fixture
def committed(tmp_path):
    releases=tmp_path/'releases';releases.mkdir()
    current=releases/'0.3.2';current.mkdir()
    (current/'.luma-release.json').write_text(json.dumps({'version':'0.3.2'}))
    app=tmp_path/'app';app.symlink_to(current,target_is_directory=True)
    status=releases/'.status.json'
    ProgressStore(status).write({'state':'installed','phase':'complete','target_version':'0.3.2',
                                 'started_epoch':1,'message':'Passed health check'})
    return dict(status_path=status,app_root=app,releases_root=releases)


def test_success_reboots_once_and_never_on_subsequent_boot(committed):
    calls=[]
    assert reboot_after_verified_upgrade(**committed,runner=lambda command,**kwargs:calls.append(command))
    assert calls==[['/usr/bin/systemctl','--no-block','reboot']]
    assert not reboot_after_verified_upgrade(**committed,runner=lambda *args,**kwargs:pytest.fail('Reboot loop'))


@pytest.mark.parametrize('state',['failed','installing','idle'])
def test_uncommitted_updates_never_reboot(committed,state):
    ProgressStore(committed['status_path']).write({'state':state,'phase':'checking','target_version':'0.3.2',
                                                 'started_epoch':1,'message':'Not committed'})
    assert not reboot_after_verified_upgrade(**committed,runner=lambda *args,**kwargs:pytest.fail('Premature reboot'))


def test_active_release_must_match_success_record(committed):
    (committed['app_root']/'.luma-release.json').write_text(json.dumps({'version':'0.3.1'}))
    assert not reboot_after_verified_upgrade(**committed,runner=lambda *args,**kwargs:pytest.fail('Wrong release'))


def test_denied_reboot_does_not_rollback_or_retry_forever(committed):
    def denied(*args,**kwargs):raise subprocess.CalledProcessError(1,args[0])
    assert not reboot_after_verified_upgrade(**committed,runner=denied)
    assert ProgressStore(committed['status_path']).read()['state']=='installed'
    assert not reboot_after_verified_upgrade(**committed,runner=lambda *args,**kwargs:pytest.fail('Retry loop'))
