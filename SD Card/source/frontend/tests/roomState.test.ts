import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleRoom,emptyRoom,purifierFresh,purifierStatus,supportsPurifier,commandStatus,type PurifierReceipt} from '../src/roomState.ts';

test('room starts disconnected, unselected, without scenes or remote control',()=>{
  const value=emptyRoom();assert.equal(value.connected,false);assert.equal(value.selected,null);assert.equal(value.purifier,null);assert.equal(value.remote_control,false);
});
test('controls expire locally even if no replacement snapshot arrives',()=>{
  const view=sampleRoom().purifier!,now=Date.parse(view.reported_at!);
  assert.ok(purifierFresh(view,now));assert.ok(supportsPurifier(view,'power',false,now+300000));
  for(const time of [now-1,now+300001]){assert.equal(purifierFresh(view,time),false);assert.equal(supportsPurifier(view,'power',true,time),false);}
  assert.equal(purifierFresh({...view,reported_at:'bad'},now),false);
  assert.equal(purifierFresh({...view,health:'unconfirmed'},now),false);
});
test('only fresh discovered capabilities expose strict absolute controls',()=>{
  const view=sampleRoom().purifier!,now=Date.parse(view.reported_at!);
  assert.ok(supportsPurifier(view,'speed',3,now));assert.equal(supportsPurifier(view,'speed','3',now),false);
  assert.equal(supportsPurifier(view,'speed',4,now),false);assert.equal(supportsPurifier(view,'power',1,now),false);
  assert.equal(supportsPurifier({...view,capabilities:{...view.capabilities!,display:false}},'display',true,now),false);
  assert.equal(supportsPurifier({...view,capabilities:null},'power',true,now),false);
  assert.equal(supportsPurifier(view,'mode','unsupported',now),false);
});
test('unconfirmed, rejected and not-sent outcomes remain distinct',()=>{
  const receipt={status:'unconfirmed'} as PurifierReceipt;
  assert.match(commandStatus(receipt),/unconfirmed/);
  assert.match(commandStatus({...receipt,status:'rejected'}),/not accepted/);
  assert.match(commandStatus({...receipt,status:'not_sent'}),/not sent/);
  assert.match(commandStatus({...receipt,status:'confirmed'}),/readback/);
  assert.match(purifierStatus({...sampleRoom().purifier!,health:'needs_reconnect'}),/Reconnect/);
});
