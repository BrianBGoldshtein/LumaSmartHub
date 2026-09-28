import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreSetup,demoTransition,setupSteps,setupCopy} from '../src/onboardingState.ts';
import {setupLink} from '../src/setupTheme.ts';

test('restore saves only known navigation states, never credentials',()=>{
  assert.deepEqual(restoreSetup({step:'calendar',password:'discard',statuses:{phone:'later',voice:'passed',unknown:'reviewed'}}),{version:1,step:'calendar',statuses:{phone:'later'}});
  for(const raw of [null,[],42,{step:[],statuses:[]}])assert.deepEqual(restoreSetup(raw),{version:1,step:'welcome',statuses:{}});
});
test('essentials lead into optional setup, explicit review and finish',()=>{
  let state=restoreSetup(null);
  for(const step of setupSteps.slice(0,4))state=demoTransition(state,'continue',step);
  assert.equal(state.step,'extras');
  state=demoTransition(state,'skip_optional');
  assert.equal(state.step,'review');assert.equal(state.statuses.voice,'later');
  assert.equal(state.statuses.review,undefined);
  state=demoTransition(state,'finish');assert.equal(state.statuses.review,'reviewed');
});
test('back, reload and revisit preserve reviewed/later but not hardware passes',()=>{
  let state=demoTransition(restoreSetup(null),'visit','calendar');
  state=demoTransition(state,'later','calendar');
  state=demoTransition(restoreSetup(JSON.parse(JSON.stringify(state))),'visit','calendar');
  assert.equal(state.statuses.calendar,'later');
  state=demoTransition(state,'continue','calendar');assert.equal(state.statuses.calendar,'reviewed');
  assert.equal(demoTransition(state,'skip_optional').step,'review');
});
test('stale step and early finish are rejected',()=>{
  const initial=restoreSetup(null);
  for(const action of ['finish','skip_optional','unknown'])assert.throws(()=>demoTransition(initial,action));
  assert.throws(()=>demoTransition(initial,'later','welcome'));
  assert.throws(()=>demoTransition(initial,'continue','space'));
});
test('every step has copy and every theme can reopen guided setup',()=>{
  for(const step of setupSteps)assert.ok(setupCopy[step].title && setupCopy[step].description);
  for(const theme of ['luma-glass','hearth','neon-grid'] as const){
    assert.match(setupLink(true,theme,'onboarding'),/setup=onboarding/);
    assert.match(setupLink(true,theme,'onboarding'),new RegExp(theme));
  }
});
