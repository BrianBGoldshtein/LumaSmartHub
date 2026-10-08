import test from 'node:test';
import assert from 'node:assert/strict';
import {loadGoogleSetup,calendarSelection,canEditGoogleCalendars,googleCatalogError,googleCallbackMessage,type GoogleSettings} from '../src/googleSetupState.ts';

const status={configured:true,authorized:true,task_updates:true};
const settings:GoogleSettings={visible_calendar_ids:['primary','work','temporarily-missing'],sleep_calendar_ids:['sleep'],todo_calendar_id:'tasks',todo_completed_color_id:'2',sleep_event_title:'Sleep',theme:'hearth'};
const calendars=[{id:'owner',summary:'Personal',primary:true},{id:'work',summary:'Work'}];
const colors=[{id:'2',background:'#7ae7bf'}];
const reader=()=>({status:async()=>status,settings:async()=>structuredClone(settings),calendars:async()=>calendars,colors:async()=>colors});

test('Google reconnect metadata renders before a blocked calendar request completes',async()=>{
  let release!:()=>void;
  const wait=new Promise<void>(resolve=>{release=resolve;});
  let core=false;
  const read=reader();
  read.calendars=async()=>{assert.equal(core,true);await wait;return calendars;};
  const job=loadGoogleSetup(read,(state,saved)=>{core=true;assert.equal(state.configured,true);assert.deepEqual(saved,settings);});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(core,true);
  release();
  assert.deepEqual((await job).catalog,{calendars,colors});
});

for(const failing of ['calendars','colors'] as const){
  test(`failed Google ${failing} preserves local setup and disables editing`,async()=>{
    const read=reader();
    read[failing]=async()=>{throw Error('invalid_grant PRIVATE_PROVIDER_TEXT');};
    let configured=false;
    const result=await loadGoogleSetup(read,state=>{configured=state.configured;});
    assert.equal(configured,true);
    assert.deepEqual(result.settings,settings);
    assert.equal(result.catalog,null);
    assert.equal(result.error,googleCatalogError);
    assert.doesNotMatch(result.error,/PRIVATE_PROVIDER_TEXT/);
    assert.equal(canEditGoogleCalendars(status,result.catalog!==null),false);
  });
}

test('unlinked Google does not request protected data but still exposes local configuration',async()=>{
  const read=reader();read.status=async()=>({...status,authorized:false});
  read.calendars=async()=>{assert.fail('must not request calendars');};
  read.colors=async()=>{assert.fail('must not request colors');};
  const result=await loadGoogleSetup(read,state=>assert.equal(state.configured,true));
  assert.equal(result.catalog,null);assert.equal(result.error,'');
});

test('missing local settings never initializes writable empty calendar choices',async()=>{
  const read=reader();read.settings=async()=>{throw Error('settings unavailable');};
  await assert.rejects(loadGoogleSetup(read,()=>assert.fail('cannot initialize unsaved defaults')));
});

test('primary aliases normalize without discarding saved unavailable calendars',()=>{
  assert.deepEqual(calendarSelection(settings.visible_calendar_ids,calendars),['owner','work','temporarily-missing']);
  assert.deepEqual(calendarSelection(['primary'],[]),['primary']);
  assert.deepEqual(calendarSelection(['primary','owner'],calendars),['owner']);
});

test('retry after refresh rejection permits editing only after a complete catalog',async()=>{
  const read=reader();let failed=true;
  read.calendars=async()=>{if(failed)throw Error('expired');return calendars;};
  const first=await loadGoogleSetup(read,()=>{});
  assert.equal(canEditGoogleCalendars(status,first.catalog!==null),false);
  failed=false;
  const second=await loadGoogleSetup(read,()=>{});
  assert.equal(canEditGoogleCalendars(status,second.catalog!==null),true);
  assert.deepEqual(second.settings,settings);
  assert.deepEqual(settings.visible_calendar_ids,['primary','work','temporarily-missing']);
});

test('unfinished OAuth callback never claims saved credentials changed',()=>{
  assert.match(googleCallbackMessage('1'),/saved connection has not changed/);
  assert.equal(googleCallbackMessage(null),'');
});

test('renewal-required Google still exposes reconnect core and preserves chosen calendars',async()=>{
  const read={...reader(),status:async()=>({...status,reconnect_required:true})};
  read.calendars=async()=>{throw Error('expired');};
  const result=await loadGoogleSetup(read,(state,saved)=>{
    assert.equal(state.reconnect_required,true);
    assert.equal(state.configured,true);
    assert.deepEqual(saved.visible_calendar_ids,settings.visible_calendar_ids);
  });
  assert.equal(result.catalog,null);
  assert.equal(canEditGoogleCalendars(status,false),false);
});
