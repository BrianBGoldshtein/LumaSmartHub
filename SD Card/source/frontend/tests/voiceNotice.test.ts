import test from 'node:test';
import assert from 'node:assert/strict';
import {voiceNoticeDuration} from '../src/voiceNoticeState.ts';

test('unknown-command feedback is brief and cannot reappear from a stale snapshot',()=>{
  assert.equal(voiceNoticeDuration({id:1,remaining_ms:3000},null),3000);
  assert.equal(voiceNoticeDuration({id:1,remaining_ms:3000},1),0);
  assert.equal(voiceNoticeDuration({id:2,remaining_ms:600},1),600);
  assert.equal(voiceNoticeDuration({id:2,remaining_ms:90000},1),3000);
});

test('missing, expired or malformed feedback never appears',()=>{
  assert.equal(voiceNoticeDuration(undefined,null),0);
  for(const notice of [{id:0,remaining_ms:3000},{id:1,remaining_ms:0},
                      {id:1,remaining_ms:-1},{id:NaN,remaining_ms:3000},
                      {id:1,remaining_ms:Infinity}]){
    assert.equal(voiceNoticeDuration(notice,null),0);
  }
});
