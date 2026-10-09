import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installIdleCursor} from '../src/idleCursor.ts';

test('wall cursor hides after 20s, returns on mouse movement, and cleans up',()=>{
  const surface=new EventTarget(),classes=new Set<string>();
  let pending:(()=>void)|undefined,delay=0,scheduled=0;
  const stop=installIdleCursor(surface,{classList:{add:name=>classes.add(name),remove:name=>classes.delete(name)}},20_000,
    ((fn:()=>void,ms:number)=>{pending=fn;delay=ms;scheduled++;return 1;}) as unknown as typeof setTimeout,
    (()=>{pending=undefined;}) as typeof clearTimeout);
  assert.equal(delay,20_000);pending!();assert.equal(classes.has('luma-cursor-idle'),true);
  const touch=new Event('pointermove');Object.assign(touch,{pointerType:'touch'});surface.dispatchEvent(touch);
  assert.equal(classes.has('luma-cursor-idle'),true);
  const mouse=new Event('pointermove');Object.assign(mouse,{pointerType:'mouse'});surface.dispatchEvent(mouse);
  assert.equal(classes.has('luma-cursor-idle'),false);assert.equal(scheduled,2);
  pending!();surface.dispatchEvent(new Event('wheel'));assert.equal(classes.size,0);
  stop();assert.equal(pending,undefined);surface.dispatchEvent(mouse);assert.equal(scheduled,3);
});
