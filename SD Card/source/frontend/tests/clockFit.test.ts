import test from 'node:test';
import assert from 'node:assert/strict';
import {fitClockFont} from '../src/clockFit.ts';
test('clock keeps the theme size when its actual digits fit',()=>{
  assert.equal(fitClockFont(200,550,600),200);
});
test('long clock digits shrink only enough and arcade fit stays on its pixel unit',()=>{
  assert.equal(fitClockFont(156,400,300,3),117);
  for(const available of [100,200,320,500]){
    const result=fitClockFont(200,600,available,4);
    assert.ok(result/200*600<=available);assert.equal(result%4,0);
  }
});
test('hidden or invalid measurement cannot erase the clock',()=>{
  assert.equal(fitClockFont(150,0,300),150);
  assert.equal(fitClockFont(150,400,0),150);
});
