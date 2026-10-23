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
  const mouse=new Event('pointermove');Object.assign(mouse,{pointerType:'mouse',screenX:100,screenY:200,movementX:1,movementY:0});surface.dispatchEvent(mouse);
  assert.equal(classes.has('luma-cursor-idle'),false);assert.equal(scheduled,2);
  pending!();surface.dispatchEvent(new Event('wheel'));assert.equal(classes.size,0);
  stop();assert.equal(pending,undefined);surface.dispatchEvent(mouse);assert.equal(scheduled,3);
});

test('unchanged coordinates never restart idle time or reveal the hidden cursor',()=>{
  const surface=new EventTarget(),classes=new Set<string>();
  let pending:(()=>void)|undefined,scheduled=0;
  const stop=installIdleCursor(surface,{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}},20_000,
    ((fn:()=>void)=>{pending=fn;scheduled++;return 1;}) as unknown as typeof setTimeout,(()=>{}) as typeof clearTimeout);
  const move=(x:number,y:number,movementX=0)=>{
    const event=new Event('pointermove');Object.assign(event,{pointerType:'mouse',screenX:x,screenY:y,movementX});surface.dispatchEvent(event);
  };
  move(500,300,1);
  for(let i=0;i<1000;i++)move(500,300,1); // Ignore misleading relative deltas too.
  assert.equal(scheduled,2);
  pending!();assert.ok(classes.has('luma-cursor-idle'));
  for(let i=0;i<1000;i++)move(500,300);
  assert.ok(classes.has('luma-cursor-idle'));assert.equal(scheduled,2);
  move(501,300);assert.equal(classes.has('luma-cursor-idle'),false);assert.equal(scheduled,3);
  stop();
});

test('first stationary hover event does not delay the startup deadline',()=>{
  const surface=new EventTarget(),classes=new Set<string>();
  let pending:(()=>void)|undefined,scheduled=0;
  const stop=installIdleCursor(surface,{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}},20_000,
    ((fn:()=>void)=>{pending=fn;scheduled++;return 1;}) as unknown as typeof setTimeout,(()=>{}) as typeof clearTimeout);
  const event=new Event('pointermove');Object.assign(event,{pointerType:'mouse',screenX:500,screenY:300,movementX:0,movementY:0});
  surface.dispatchEvent(event);assert.equal(scheduled,1);
  pending!();surface.dispatchEvent(event);assert.ok(classes.has('luma-cursor-idle'));assert.equal(scheduled,1);
  stop();
});

test('native refresh never reactivates the cursor or creates a feedback loop',()=>{
  const surface=new EventTarget(),classes=new Set<string>(),changes:boolean[]=[];
  let pending:(()=>void)|undefined;
  const stop=installIdleCursor(surface,{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}},20_000,
    ((fn:()=>void)=>{pending=fn;return 1;}) as unknown as typeof setTimeout,(()=>{}) as typeof clearTimeout,
    idle=>changes.push(idle));
  function motion(x:number){const e=new Event('pointermove');Object.assign(e,{pointerType:'mouse',screenX:x,screenY:300,movementX:1,movementY:0});surface.dispatchEvent(e);}
  motion(640);pending!();assert.deepEqual(changes,[true]);
  motion(640+1/256);motion(640);assert.ok(classes.has('luma-cursor-idle'));assert.deepEqual(changes,[true]);
  motion(650);assert.equal(classes.has('luma-cursor-idle'),false);assert.deepEqual(changes,[true,false]);
  motion(650+1/256);motion(650);assert.deepEqual(changes,[true,false]);
  stop();
});

test('the first ever subpixel refresh after startup does not reveal the idle cursor',()=>{
  const surface=new EventTarget(),classes=new Set<string>(),changes:boolean[]=[];
  let pending:(()=>void)|undefined;
  const stop=installIdleCursor(surface,{classList:{add:n=>classes.add(n),remove:n=>classes.delete(n)}},20_000,
    ((fn:()=>void)=>{pending=fn;return 1;}) as unknown as typeof setTimeout,(()=>{}) as typeof clearTimeout,
    idle=>changes.push(idle));
  pending!();
  const event=new Event('pointermove');
  Object.assign(event,{pointerType:'mouse',screenX:1279.99609375,screenY:719,movementX:-1/256,movementY:0});
  surface.dispatchEvent(event);
  assert.ok(classes.has('luma-cursor-idle'));assert.deepEqual(changes,[true]);
  stop();
});
