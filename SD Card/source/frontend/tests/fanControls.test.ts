import test from 'node:test';
import assert from 'node:assert/strict';
import {fanControls,type Cooling} from '../src/fanControls.ts';
const fault:Cooling={available:false,mode:'always_on',usb_power:'on',qualified:false,
  probe:'idle',reason:'Switching failed',standby_override:false,fault:true};

test('latched-fault recovery is enabled only after acknowledgment, not blocked by unavailable',()=>{
  assert.equal(fanControls(fault,false,false,false).testDisabled,true);
  const retry=fanControls(fault,false,false,true);
  assert.equal(retry.testDisabled,false);assert.equal(retry.testLabel,'Retry physical fan test');
  assert.equal(retry.automaticDisabled,true);assert.equal(retry.confirmDisabled,true);
});
test('standby, busy, preview, missing status and an active probe still block interruption',()=>{
  for(const result of [fanControls({...fault,standby_override:true},false,false,true),
    fanControls(fault,true,false,true),fanControls(fault,false,true,true),fanControls(null,false,false,true),
    fanControls({...fault,probe:'running'},false,false,true)])assert.equal(result.testDisabled,true);
});
test('independent restoration must reach confirm state and observation must be acknowledged',()=>{
  const returned={...fault,available:true,fault:false,probe:'confirm'};
  assert.equal(fanControls(returned,false,false,false).confirmDisabled,true);
  assert.equal(fanControls(returned,false,false,true).confirmDisabled,false);
  assert.equal(fanControls({...returned,standby_override:true},false,false,true).confirmDisabled,true);
  assert.equal(fanControls(returned,false,false,true).automaticDisabled,true);
  assert.equal(fanControls({...returned,probe:'idle',qualified:true},false,false,false).automaticDisabled,false);
});
