"""Crowded scans must not silently discard a phone or weaken pairing checks."""
from unittest.mock import Mock

import pytest
from dbus_next import Variant

from luma.pairing import BlueZPairing, PairingFlow, device_choices, readable_name
from test_pairing import ADAPTER, ADDRESS, DEVICE, FakeDriver, until


def inventory(count=180):
    rows={}
    for index in range(count):
        address=f'AA:BB:CC:DD:{index//256:02X}:{index%256:02X}'
        path=ADAPTER+'/dev_'+address.replace(':','_')
        rows[path]={'org.bluez.Device1':dict(Adapter=ADAPTER,Address=address,
            Alias=f'Device {index:04}',RSSI=-30-index%70,Paired=False,Bonded=False,Trusted=False)}
    return rows


def props(name,rssi=None,**extra):
    return dict(Adapter=ADAPTER,Address=ADDRESS,Alias=name,RSSI=rssi,**extra)


@pytest.mark.parametrize('value',['AA:BB:CC:DD:EE:FF','aabbccddeeff','aabbccdd-eeff-1234-5678-123456789abc',
    '794139537','F3A9B5','X9Y1Z8Q7W6S5D4G3','Bluetooth device','Unknown','',None,False])
def test_identifier_labels_are_demoted_not_named(value):
    assert not readable_name(value)[1]


@pytest.mark.parametrize('value',["Brian’s iPhone",'Brian iPhone 17 Pro Max','iPhone','Émilie’s Phone',
    'WH-1000XM4','Pixel 9','MacBook','Office Phone','Cafe'])
def test_human_and_product_names_remain_named(value):
    assert readable_name(value)[1]


def test_readable_names_then_stronger_signals_not_alphabet_or_stale_bonds():
    rows=inventory(4)
    for row,values in zip(rows.values(),[
        props('AAA stale paired phone',None,Paired=True,Bonded=True,Trusted=True),
        props('Zoe iPhone',-35),props('Aardvark Phone',-80),props('AABBCCDDEEFF',-10)]):
        row['org.bluez.Device1'].update(values)
    choices=device_choices(rows,ADAPTER)
    assert [c['name'] for c in choices]==['Zoe iPhone','Aardvark Phone','AAA stale paired phone','AABBCCDDEEFF']
    assert [c['rssi'] for c in choices]==[-35,-80,None,-10]


@pytest.mark.parametrize('invalid',[None,True,False,'-30',127,200,-128,float('nan')])
def test_invalid_or_missing_signal_is_unknown_not_strong(invalid):
    rows=inventory(2)
    first,second=list(rows.values())
    first['org.bluez.Device1'].update(Alias='Zoe Phone',RSSI=-80)
    second['org.bluez.Device1'].update(Alias='AAA Phone',RSSI=invalid)
    choices=device_choices(rows,ADAPTER)
    assert [c['rssi'] for c in choices]==[-80,None]


def test_alias_identifier_falls_back_to_remote_name_and_zero_rssi_is_valid():
    choices=device_choices({DEVICE:{'org.bluez.Device1':props('AA-BB-CC-DD-EE-FF',0,Name='My iPhone')}},ADAPTER)
    assert choices[0]['name']=='My iPhone' and choices[0]['named']
    assert choices[0]['rssi']==0
    choices=device_choices({DEVICE:{'org.bluez.Device1':props('Bedroom Phone',-45,Name='iPhone')}},ADAPTER)
    assert choices[0]['name']=='Bedroom Phone'


def test_all_1200_results_remain_searchable_and_order_is_deterministic():
    rows=inventory(1200)
    rows[DEVICE]={'org.bluez.Device1':props('Zoe target phone',-120)}
    choices=device_choices(rows,ADAPTER)
    assert len(choices)==1201 and choices[-1]['path']==DEVICE
    assert choices==device_choices(dict(reversed(list(rows.items()))),ADAPTER)
    assert {c['path'] for c in choices}==set(rows)


@pytest.mark.asyncio
async def test_choice_beyond_old_cutoff_still_requires_exact_code_before_trust():
    driver,save=FakeDriver(),Mock()
    rows=inventory()
    driver.props.update(Alias='Zoe target phone',RSSI=-120)
    rows[DEVICE]={'org.bluez.Device1':driver.props}
    async def objects():return rows
    driver.objects=objects
    flow=PairingFlow(save,lambda:driver)
    try:
        flow.start()
        await until(lambda:len(flow.devices)==181)
        assert flow.devices.index(next(c for c in flow.devices if c['path']==DEVICE))>40
        flow.select(flow.session,DEVICE)
        await until(lambda:flow.phase=='confirming')
        assert driver.trust_calls==0 and flow.passkey=='042817'
        save.assert_not_called()
        flow.confirm(flow.session,flow.challenge,True)
        await flow.task
        assert flow.phase=='complete'
        save.assert_called_once_with(ADDRESS)
        assert driver.trust_calls==1
    finally:
        await flow.close()


@pytest.mark.asyncio
async def test_bluez_variant_rssi_and_alias_reach_choices_without_content(tmp_path):
    driver=BlueZPairing();driver.adapter=ADAPTER
    class Manager:
        async def call_get_managed_objects(self):
            return {DEVICE:{'org.bluez.Device1':{'Adapter':Variant('o',ADAPTER),
                'Address':Variant('s',ADDRESS),'Alias':Variant('s','My iPhone'),'RSSI':Variant('n',-37)}}}
    async def interface(*args):return Manager()
    driver.interface=interface
    choice=device_choices(await driver.objects(),ADAPTER)[0]
    assert choice['rssi']==-37 and choice['name']=='My iPhone'


def test_secondary_crowded_snapshot_reads_registry_once_and_keeps_other_bonds_hidden(tmp_path):
    from luma.api import create_app
    app=create_app(data_dir=tmp_path)
    setup=app.state.user_setup
    guest=app.state.profiles.create_secondary('Alex')
    app.state.profiles.bind_phone('primary',ADDRESS)
    setup.pairing_owner=('synthetic-token',None,guest.id)
    rows=inventory(1200);rows[DEVICE]={'org.bluez.Device1':props('Other registered phone',-30)}
    setup.pairing.devices=device_choices(rows,ADAPTER)
    original=app.state.profiles.list
    app.state.profiles.list=Mock(wraps=original)
    app.state.profiles.by_phone=Mock(side_effect=AssertionError('Per-device SQLite lookup'))
    result=setup.pairing_snapshot(guest.id)
    assert len(result['devices'])==1200
    assert not any(row['address']==ADDRESS for row in result['devices'])
    app.state.profiles.list.assert_called_once()
