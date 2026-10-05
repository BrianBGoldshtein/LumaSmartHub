import test from 'node:test';
import assert from 'node:assert/strict';
import {wakeDetectorCopy} from '../src/wakeDetectorState.ts';

test('selected, installed and running are different readiness states',()=>{
  assert.match(wakeDetectorCopy('acoustic'),/waiting for the voice service/);
  assert.match(wakeDetectorCopy('acoustic',{mode:'dual_decoder',phase:'ready',error:null}),/waiting/);
  for(const phase of ['waiting_asset','preparing_asset'] as const){
    assert.match(wakeDetectorCopy('acoustic',{mode:'acoustic',phase,error:null}),/commands wait.*no more-sensitive fallback/);
  }
  assert.match(wakeDetectorCopy('acoustic',{mode:'acoustic',phase:'ready',error:null}),/listener running/);
});

test('runtime errors use fixed copy, never arbitrary upstream text',()=>{
  const copy=wakeDetectorCopy('acoustic',{mode:'acoustic',phase:'failed',error:'secret /path'});
  assert.ok(!copy.includes('secret')&&!copy.includes('/path'));
  assert.match(copy,/will not switch/);
  assert.match(wakeDetectorCopy('acoustic',{mode:'acoustic',phase:'failed',error:'keyword_alignment_unavailable'}),/discarded the phrase/);
  assert.match(wakeDetectorCopy('standard'),/Ordinary conversation/);
  assert.match(wakeDetectorCopy('dual_decoder'),/both speech decoders/);
});
