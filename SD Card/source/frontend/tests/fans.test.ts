import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyFans,demoAdapter,demoEligibility,fanButtons,fanStatus,pendingObservation} from '../src/fanState.ts';

test('two independent empty fan slots never imply connected hardware',()=>{
  const config=emptyFans();assert.equal(config.fans.length,2);assert.equal(config.independent,false);
  assert.equal(config.remote_control,false);assert.ok(config.fans.every(row=>!row.route&&!row.buttons.length));
  assert.equal(fanStatus(config.fans[0]),'Choose an output');
});
test('all toggle and relative keys remain ineligible even with two successful checks',()=>{
  const config=emptyFans();
  for(const row of config.fans){row.route={device:demoAdapter,emitter:1};row.buttons=fanButtons.map(button=>({...button,checks:2,scene_eligible:false}));}
  demoEligibility(config);assert.equal(config.independent,true);
  for(const row of config.fans)for(const button of row.buttons)assert.equal(button.scene_eligible,button.kind==='absolute');
  config.fans[1].buttons=[];demoEligibility(config);assert.ok(config.fans[0].buttons.every(button=>!button.scene_eligible));
});
test('observation is only available for recent completed test sends',()=>{
  const now=Date.now(),receipt={id:'test',button:'power_off',kind:'test' as const,status:'sent_unconfirmed' as const,at:new Date(now).toISOString(),observed:false};
  assert.ok(pendingObservation(receipt,now));assert.ok(!pendingObservation(receipt,now+120001));
  assert.ok(!pendingObservation(receipt,now-1));assert.ok(!pendingObservation({...receipt,observed:true},now));
  assert.ok(!pendingObservation({...receipt,status:'unknown'},now));assert.ok(!pendingObservation({...receipt,kind:'manual'},now));
  assert.ok(!pendingObservation({...receipt,at:'bad'},now));
});
test('no-serial review status takes precedence over saved button checks',()=>{
  const row=emptyFans().fans[0];row.route={device:demoAdapter,emitter:1};row.needs_output_review=true;
  assert.equal(fanStatus(row),'Review USB output after restart');
});
