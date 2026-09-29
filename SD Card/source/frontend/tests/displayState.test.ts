import test from 'node:test';
import assert from 'node:assert/strict';
import {displayLevel,displayFilter,previewDisplay} from '../src/displayState.ts';

test('wake interpolation is bounded, smooth and exactly twenty seconds',()=>{
  const state=previewDisplay('waking');
  assert.equal(displayLevel(state),5);assert.equal(displayLevel(state,10000),37.5);
  assert.equal(displayLevel(state,20000),70);assert.equal(displayLevel(state,30000),70);
  assert.equal(displayLevel(state,-1000),5);
  const scheduled={...state,ramp:{...state.ramp!,duration_seconds:300,kind:'scheduled' as const}};
  assert.equal(displayLevel(scheduled,150000),37.5);assert.equal(displayLevel(scheduled,300000),70);
});
test('physical reference remains conservative and off is absolutely black',()=>{
  const state=previewDisplay('night-clock');
  assert.equal(displayFilter(state),.05);
  assert.equal(displayFilter({...state,handoff:{...state.handoff,reference_brightness:5}}),1);
  assert.equal(displayFilter({...state,handoff:{...state.handoff,reference_brightness:70}}),5/70);
  assert.equal(displayFilter({...state,handoff:{...state.handoff,reference_brightness:NaN}}),.05);
  assert.equal(displayFilter(previewDisplay('off')),0);
  assert.equal(displayFilter(null),1);
});
test('invalid ramp arithmetic never brightens a screen',()=>{
  const state=previewDisplay('waking');
  assert.equal(displayLevel({...state,ramp:{...state.ramp!,duration_seconds:0}}),0);
  assert.equal(displayLevel({...state,ramp:{...state.ramp!,from_brightness:NaN}}),0);
});
