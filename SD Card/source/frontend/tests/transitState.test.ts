import test from 'node:test';
import assert from 'node:assert/strict';
import {ageTransit,disconnectedTransit,sampleTransit,transitCycle,visibleTransit} from '../src/transitState.ts';
const now=Date.parse('2026-09-26T20:00:00Z');
test('private stops never survive disconnect or privacy standby',()=>{
  const samples=sampleTransit(now);
  assert.equal(visibleTransit(samples,true).length,1);
  const offline=disconnectedTransit(samples);assert.equal(offline.length,1);assert.ok(offline[0].offline);
  const view=ageTransit(offline[0],now);
  assert.ok(view.departures.every(row=>row.kind==='scheduled'&&row.stale));
});
test('predictions expire against their actual expiry without waiting for another snapshot',()=>{
  const item=sampleTransit(now)[0];
  assert.equal(ageTransit(item,now+60000).departures[0].minutes,4);
  const later=ageTransit(item,now+6*60000);
  assert.equal(later.departures[0].minutes,14);assert.equal(later.departures[0].kind,'scheduled');
  assert.equal(later.state,'stale'); // the already departed5min prediction never reappears at7min.
  assert.equal(ageTransit(item,now-1000).departures.length,0);
});
test('missing schedule fallback becomes unavailable rather than an immortal live countdown',()=>{
  const item=sampleTransit(now)[0];item.departures=[{...item.departures[1],scheduled_at:null}];
  assert.equal(ageTransit(item,now+301000).state,'unavailable');
  assert.equal(ageTransit(item,now+301000).departures.length,0);
});
test('configured transit joins the cycle once without changing other durations',()=>{
  const base=[{page:'home',seconds:45},{page:'countdowns',seconds:25}];
  const cycle=transitCycle(base,true);assert.deepEqual(cycle.slice(0,2),base);
  assert.equal(transitCycle(cycle,true).length,3);
  assert.deepEqual(transitCycle(cycle,false),base);
});
