import assert from 'node:assert/strict';
import test from 'node:test';
import { STANDBY_CYCLE, standbyPage } from '../src/standbyCycle.ts';

test('private standby rotates clock, weather and ambient without a private page',()=>{
  assert.deepEqual(STANDBY_CYCLE.map(item=>item.page),['home','weather','ambient']);
  assert.ok(STANDBY_CYCLE.every(item=>item.seconds>=10));
  for(const page of ['agenda','todos','countdowns','transit'] as const){
    assert.equal(standbyPage(page),'home');
  }
  assert.equal(standbyPage('weather'),'weather');
  assert.equal(standbyPage('ambient'),'ambient');
});
