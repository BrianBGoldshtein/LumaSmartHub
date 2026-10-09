// Real Chromium/controllers; synthetic Bluetooth and Google, never owner devices.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/?setup=users'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let id=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);
  if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);
  const wait=pending.get(row.id);if(!wait)return;pending.delete(row.id);row.error?wait.reject(Error(JSON.stringify(row.error))):wait.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const seq=++id;pending.set(seq,{resolve,reject});socket.send(JSON.stringify({id:seq,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const deadline=Date.now()+20000;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Timed out: '+expression+' '+await value('document.body.innerText'));
  await new Promise(resolve=>setTimeout(resolve,100));}}
async function click(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  return value(`(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled);b.click();})()`);}
async function fixture(path){return value(`fetch(${JSON.stringify('/qa/'+path)},{method:'POST'}).then(r=>r.json())`);}
async function screenshot(label){
  assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`),'Horizontal overflow: '+label);
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await fs.writeFile(`${process.env.USER_QA_OUTPUT}/${label}.png`,Buffer.from(shot.data,'base64'));
}
try{
  await send('Page.enable');await send('Runtime.enable');await send('Page.bringToFront');
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await until(`document.body.innerText.includes('Primary settings')`);
  await click('Type on screen');
  for(const digit of ['1','2','3','4','5','6'])await click(digit);
  await click('Unlock settings');await until(`document.body.innerText.includes('Your people.')`);
  await value(`(()=>{const input=document.querySelector('input[placeholder="e.g. Alex"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,'Alex');input.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click('Approve & begin guided setup');await until(`location.search==='?setup=personal'&&document.body.innerText.includes('Alex’s space.')`);
  await screenshot('phone');
  assert.ok(!(await value('document.cookie')).includes('luma_personal_setup'),'Personal cookie must be HttpOnly');
  await fixture('expire-primary');
  assert.equal(await value(`fetch('/api/v1/settings').then(r=>r.status)`),403);
  await click('Find my iPhone');await until(`document.querySelector('.network-list button')!==null`);
  await value(`document.querySelector('.network-list button').click()`);
  await until(`document.querySelector('[aria-label="Pairing code"]')?.textContent==='042817'`);
  await screenshot('pairing-confirmation');
  await click('Codes match · pair');
  await until(`document.body.innerText.includes('Personal setup paused')`);
  await fixture('authorize');await until(`document.body.innerText.includes('Take Luma with you')`);
  await screenshot('remote');
  await click('Continue →');await until(`document.body.innerText.includes('Your Google account')`);
  await fixture('google-linked');await until(`document.body.innerText.includes('Google account linked.')`);
  await screenshot('google');
  await click('Continue →');await until(`document.body.innerText.includes('Alex classes')`);
  await screenshot('calendar-choices');
  await value(`document.querySelector('input[name="agenda"][value="alex-events"]').click()`);
  await value(`(()=>{const field=document.querySelector('select[name="todo"]');field.value='alex-tasks';field.dispatchEvent(new Event('change',{bubbles:true}));const color=document.querySelector('select[name="color"]');color.value='2';color.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await click('Save my calendars & continue');await until(`document.body.innerText.includes('Make yourself at home')`);
  await value(`document.querySelector('.user-check input').click()`);await click('Save my sharing choice');
  await until(`document.body.innerText.includes('Personal setup saved.')`);
  let saved=await value(`fetch('/api/v1/user-self/status').then(r=>r.json())`);
  assert.equal(saved.wall_share_approved,true);assert.deepEqual(saved.personal.visible_calendar_ids,['alex-events']);assert.equal(saved.personal.todo_calendar_id,'alex-tasks');
  const layouts=[];
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await send('Page.navigate',{url:base+'/?setup=personal'});await until(`document.querySelector('.theme-${theme} .user-setup')!==null&&document.body.innerText.includes('Make yourself at home')`);
    for(const width of [320,390,1024,2048]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:width<680?844:width===1024?768:1536,deviceScaleFactor:1,mobile:width<680});
      assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`),'Horizontal overflow');
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await fs.writeFile(`${process.env.USER_QA_OUTPUT}/${theme}-${width}-personal.png`,Buffer.from(shot.data,'base64'));
      layouts.push({theme,width});
    }
  }
  await fixture('disconnect');await until(`document.body.innerText.includes('Personal setup paused')&&!document.body.innerText.includes('Alex’s space.')`);
  await fixture('authorize');await until(`document.body.innerText.includes('Alex’s space.')&&document.body.innerText.includes('Make yourself at home')`);
  await click('Lock personal setup');await until(`document.body.innerText.includes('Personal setup paused')`);
  assert.equal(await value(`fetch('/api/v1/user-self/status').then(r=>r.status)`),403);
  await fixture('more-users');
  await send('Page.navigate',{url:base+'/?setup=users'});await until(`document.body.innerText.includes('Primary settings')`);
  await click('Type on screen');for(const digit of ['1','2','3','4','5','6'])await click(digit);
  await click('Unlock settings');await until(`document.body.innerText.includes('Registered users · 5/5')`);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await send('Page.navigate',{url:base+'/?setup=users'});await until(`document.querySelector('.theme-${theme}')!==null&&document.body.innerText.includes('Registered users · 5/5')`);
    for(const width of [320,390,1024,2048]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:width<680?844:width===1024?768:1536,deviceScaleFactor:1,mobile:width<680});
      await screenshot(`${theme}-${width}-users`);
      assert.ok(await value(`document.querySelector('input[placeholder="e.g. Alex"]').disabled`),'Capacity must disable Add user');
    }
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Disposable Chromium/controllers; synthetic phones/provider only',primaryApprovalOnce:true,
    continuedAfterPrimaryExpiry:true,pairingCodeCompared:true,bondAloneNotPresence:true,ownCalendarChoicesSaved:true,
    wallSharingConsent:true,resumableWithoutPrimary:true,disconnectClearsPrivate:true,personalLockRevokes:true,layouts,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
