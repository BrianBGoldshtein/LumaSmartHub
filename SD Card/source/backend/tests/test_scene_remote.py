from copy import deepcopy

import pytest

from luma.scene_remote import RemoteScenePolicy
from luma.storage import Storage


ACTION={'device':'fan_1','action':'oscillate_off','value':None,'binding':'a'*64}


class Devices:
    def __init__(self): self.calls=0
    def bind(self, actions):
        self.calls+=1
        if any(item['binding'] != 'a'*64 for item in actions):
            raise ValueError('review required')
        return deepcopy(actions)


def definitions():
    return {key:{'enabled':False,'automatic':False,'actions':[]} for key in ('morning','night','arrive','away')}


def test_remote_permissions_are_separate_default_off_and_bound_to_exact_actions(tmp_path):
    storage=Storage(tmp_path/'luma.db');policy=RemoteScenePolicy(storage);rows=definitions();devices=Devices()
    rows['morning']={'enabled':True,'automatic':False,'actions':[ACTION]}
    assert not policy.effective('morning',rows['morning'])
    policy.save(True,['morning'],revision=policy.revision,definitions=rows,devices=devices)
    assert policy.effective('morning',rows['morning']) and devices.calls==1
    changed=deepcopy(rows);changed['morning']['actions'][0]['action']='power'
    status=policy.configuration(changed)
    assert not policy.effective('morning',changed['morning'])
    assert status['scenes']['morning']=={'allowed':False,'needs_review':True}
    reopened=RemoteScenePolicy(storage)
    assert reopened.effective('morning',rows['morning']) and not reopened.effective('morning',changed['morning'])


def test_remote_permission_save_is_revisioned_and_requires_live_enabled_review(tmp_path):
    policy=RemoteScenePolicy(Storage(tmp_path/'luma.db'));rows=definitions();devices=Devices()
    with pytest.raises(ValueError): policy.save(True,['morning'],revision=policy.revision,definitions=rows,devices=devices)
    rows['morning']={'enabled':True,'automatic':False,'actions':[ACTION]}
    with pytest.raises(ValueError): policy.save(True,['morning','morning'],revision=policy.revision,definitions=rows,devices=devices)
    with pytest.raises(ValueError): policy.save(True,['morning'],revision='stale',definitions=rows,devices=devices)
    policy.save(False,[],revision=policy.revision,definitions=rows,devices=devices)
    assert not policy.enabled and policy.grants=={}


def test_remote_permission_corruption_fails_closed_and_preserves_record(tmp_path):
    storage=Storage(tmp_path/'luma.db')
    corrupt={'version':1,'revision':'bad','enabled':True,'grants':{'morning':'f'*64}}
    storage.set_cache('room','scene_remote_policy',corrupt)
    policy=RemoteScenePolicy(storage)
    assert policy.recovery_error and not policy.enabled and not policy.effective('morning',{'enabled':True,'actions':[ACTION]})
    before=storage.get_cache('room','scene_remote_policy')
    with pytest.raises(ValueError): policy.save(False,[],revision=policy.revision,definitions=definitions(),devices=Devices())
    assert storage.get_cache('room','scene_remote_policy')==before


def test_explicit_remote_recovery_discards_only_the_corrupt_allowlist_and_defaults_off(tmp_path):
    storage=Storage(tmp_path/'luma.db')
    storage.set_cache('room','scene_remote_policy',{'version':1,'revision':'bad','enabled':True,'grants':{'night':'x'}})
    policy=RemoteScenePolicy(storage)
    storage.set_cache('room','scenes',{'unrelated':'scene definitions'})
    scenes_before=storage.get_cache('room','scenes')
    with pytest.raises(ValueError): policy.reset_corrupt(revision=policy.revision,confirmed=False)
    policy.reset_corrupt(revision=policy.revision,confirmed=True)
    assert not policy.recovery_error and not policy.enabled and policy.grants=={}
    assert storage.get_cache('room','scenes')==scenes_before
