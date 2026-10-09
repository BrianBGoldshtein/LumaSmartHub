// Actual wall approval, task and timer controllers. Synthetic phones/provider.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const initialized=await(await fetch(base+'/qa/voice-initialize',{method:'POST'})).json();
await fetch(base+'/qa/wall-tasks',{method:'POST'});
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/?page=todos'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let sequence=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);
  if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);
  const waiter=pending.get(row.id);if(!waiter)return;pending.delete(row.id);row.error?waiter.reject(Error(JSON.stringify(row.error))):waiter.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function waitFor(expression){const deadline=Date.now()+20000;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Timed out: '+expression);await new Promise(resolve=>setTimeout(resolve,60));}}
async function request(path,body){return value(`fetch(${JSON.stringify(path)},{method:'POST',headers:{'Content-Type':'application/json'},body:${JSON.stringify(JSON.stringify(body))}}).then(async r=>({status:r.status,body:await r.json()}))`);}
const uid=initialized.users[1].id,results=[];
try{
  await send('Page.enable');await send('Runtime.enable');await waitFor(`document.querySelector('.user-task-list')!==null`);
  assert.equal((await request('/api/v1/admin/unlock',{pin:'123456'})).status,200);
  for(const user of initialized.users)assert.equal((await request('/api/v1/users/manage',{action:'resume',profile_id:user.id})).status,200);
  await request('/api/v1/admin/lock',{});
  await waitFor(`document.querySelector('.user-task-status:not(:disabled)')!==null`);
  await value(`[...document.querySelectorAll('.user-panel')].find(p=>p.getAttribute('aria-label')==='Alex tasks').querySelector('.user-task-status').click()`);
  await waitFor(`[...document.querySelectorAll('.user-panel')].find(p=>p.getAttribute('aria-label')==='Alex tasks').querySelector('.user-task-status').getAttribute('aria-pressed')==='true'`);
  assert.equal(await value(`[...document.querySelectorAll('.user-panel')].find(p=>p.getAttribute('aria-label')==='Brian tasks').querySelector('.user-task-status').getAttribute('aria-pressed')`),'false');
  for(const theme of ['luma-glass','hearth','neon-grid'])for(const [width,height] of [[320,720],[390,844],[1024,768],[2048,1536]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await request('/qa/theme',{theme});
    await waitFor(`document.querySelector('.app').classList.contains('theme-${theme}')`);
    await value(`document.querySelector('[aria-label="Open Alex’s timer"]').click()`);
    await waitFor(`document.querySelector('[aria-label="Alex’s timer"] .timer-reading')!==null`);
    await value('document.fonts.ready');
    const bounds=await value(`(()=>{const r=document.querySelector('.feature-panel').getBoundingClientRect();return {x:r.x,right:r.right,y:r.y,bottom:r.bottom};})()`);
    assert.ok(bounds.x>=0&&bounds.right<=width&&bounds.y>=0&&bounds.bottom<=height);
    assert.equal(await value(`document.documentElement.scrollWidth<=innerWidth`),true);
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(`${process.env.USER_QA_OUTPUT}/${theme}-${width}-personal-timer.png`,Buffer.from(shot.data,'base64'));
    if(results.length===0){
      await value(`document.querySelector('.timer-presets button').click()`);
      await waitFor(`document.querySelector('.timer-reading span')?.textContent==='Focus'`);
      await value(`[...document.querySelectorAll('.feature-actions button')].find(b=>b.textContent==='Pause').click()`);
      await waitFor(`document.querySelector('.timer-reading span')?.textContent.includes('Paused')`);
      await value(`[...document.querySelectorAll('.feature-actions button')].find(b=>b.textContent==='Resume').click()`);
      await waitFor(`document.querySelector('.timer-reading span')?.textContent==='Focus'`);
      await value(`[...document.querySelectorAll('.feature-actions button')].find(b=>b.textContent==='Cancel timer').click()`);
      await waitFor(`document.querySelector('.timer-reading strong')?.textContent==='Ready'`);
      await value(`document.querySelector('.feature-panel details summary').click()`);
      await value(`(()=>{const fields=document.querySelectorAll('.feature-panel .touch-field input');
        const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
        set.call(fields[0],'45');fields[0].dispatchEvent(new Event('input',{bubbles:true}));
        set.call(fields[1],'Lab tea');fields[1].dispatchEvent(new Event('input',{bubbles:true}));
        const unit=document.querySelector('.timer-unit select');unit.value='seconds';unit.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      await value(`document.querySelector('.feature-panel details form').requestSubmit()`);
      await waitFor(`document.querySelector('.timer-reading span')?.textContent==='Lab tea'`);
      assert.equal(await value(`fetch('/api/v1/user-self/wall/preview?profile_id=${uid}').then(r=>r.json()).then(v=>v.timer.duration_seconds)`),45);
      await value(`[...document.querySelectorAll('.feature-actions button')].find(b=>b.textContent==='Cancel timer').click()`);
      await waitFor(`document.querySelector('.timer-reading strong')?.textContent==='Ready'`);
    }
    await value(`document.querySelector('[aria-label="Close timer"]').click()`);
    await waitFor(`document.querySelector('.feature-panel')===null`);
    results.push({theme,width,height,bounds});
  }
  await request('/qa/wall-complete',{profile_id:uid});
  await waitFor(`document.querySelector('.feature-notice span')?.textContent==='Alex · LAB alarm'`);
  await request('/qa/wall-greeting-after-alarm',{profile_id:uid});
  await waitFor(`document.querySelector('.presence-transition h1')?.textContent==='Alex'`);
  await waitFor(`document.querySelector('.presence-transition')===null`);
  assert.equal(await value(`document.querySelector('.feature-notice span')?.textContent`),'Alex · LAB alarm');
  await request('/qa/wall-notice-after-alarm',{});
  await waitFor(`document.querySelector('.phone-notice strong')?.textContent==='A later notification'`);
  assert.equal(await value(`document.querySelector('.feature-notice span')?.textContent`),'Alex · LAB alarm');
  await value(`document.querySelector('.feature-notice button').click()`);
  await waitFor(`document.querySelector('.timer-reading strong')?.textContent==='Time’s up'`);
  await value(`[...document.querySelectorAll('.feature-panel>button')].find(b=>b.textContent==='Dismiss').click()`);
  await waitFor(`document.querySelector('.timer-reading strong')?.textContent==='Ready'`);
  await value(`document.querySelector('[aria-label="Close timer"]').click()`);
  await waitFor(`document.querySelector('.feature-panel')===null`);
  await value(`document.querySelector('[aria-label="Open Alex’s timer"]').click()`);
  await waitFor(`document.querySelector('.timer-reading')!==null`);
  await request('/qa/voice-disconnect',{profile_id:uid});
  await waitFor(`document.querySelector('.feature-panel')===null`);
  assert.equal(await value(`document.querySelector('[aria-label="Open Alex’s timer"]')===null`),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({cases:results.length,actualApprovals:true,ownTaskOnly:true,timerLifecycle:true,customSeconds:true,greetingAfterAlarm:true,completionDismiss:true,disconnectClears:true,errors,results},null,2));
}finally{socket.close();}
