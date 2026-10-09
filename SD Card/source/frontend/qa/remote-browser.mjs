// Disposable Chromium/TLS and synthetic ANCS only. No owner browser/Pi access.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='https://luma.example-tail.ts.net',debug='http://127.0.0.1:19226';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/remote/'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map();let id=0;const errors=[],responses=[];
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);
  if(data.method==='Page.javascriptDialogOpening')void send('Page.handleJavaScriptDialog',{accept:true});
  if(data.method==='Network.responseReceived')responses.push({path:new URL(data.params.response.url).pathname,status:data.params.response.status});
  const wait=pending.get(data.id);if(!wait)return;pending.delete(data.id);data.error?wait.reject(Error(JSON.stringify(data.error))):wait.resolve(data.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const seq=++id;pending.set(seq,{resolve,reject});socket.send(JSON.stringify({id:seq,method,params}));});
let wallSocket,wallId=0;const wallPending=new Map();let wallTarget;
async function wallValue(expression){
  const result=await new Promise((resolve,reject)=>{const seq=++wallId;wallPending.set(seq,{resolve,reject});wallSocket.send(JSON.stringify({id:seq,method:'Runtime.evaluate',params:{expression,returnByValue:true,awaitPromise:true}}));});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;
}
async function wallUntil(expression){const end=Date.now()+15000;while(!await wallValue(expression)){if(Date.now()>end)throw Error('Wall timed out: '+expression);await new Promise(r=>setTimeout(r,100));}}
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression,timeout=18000){const deadline=Date.now()+timeout;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Condition timed out: '+expression+'\n'+JSON.stringify({page:await value('({text:document.body.innerText,visibility:document.visibilityState,online:navigator.onLine})'),errors,responses}));
  await new Promise(resolve=>setTimeout(resolve,100));}}
async function click(text){
  await until(`[...document.querySelectorAll('button')].some(button=>button.textContent.trim()===${JSON.stringify(text)}&&!button.disabled)`);
  return value(`(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled);if(!button)throw Error('Button unavailable');button.click();})()`);
}
try{
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  // Install before the authenticated client captures its fetch transport.
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{const nativeFetch=window.fetch.bind(window);window.fetch=async(...args)=>{const response=await nativeFetch(...args);if(String(args[0]).endsWith('/remote/api/settings')&&args[1]?.method==='PATCH'){window.qaSaveResponsePending=true;await new Promise(r=>setTimeout(r,1500));window.qaSaveResponsePending=false;}return response;};})()`});
  // Enrollment changes only a hash, so explicitly reload the empty lab page
  // once to run the fixture before its new authenticated client is created.
  await send('Page.reload');
  wallTarget=await(await fetch(debug+'/json/new?'+encodeURIComponent('http://127.0.0.1:18835/'),{method:'PUT'})).json();
  wallSocket=new WebSocket(wallTarget.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{wallSocket.onopen=resolve;wallSocket.onerror=reject;});
  wallSocket.onmessage=event=>{const data=JSON.parse(event.data),item=wallPending.get(data.id);if(!item)return;wallPending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result);};
  await wallUntil(`document.querySelector('.app')!==null`);
  await send('Page.bringToFront');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await until(`document.querySelector('.locked')!==null`);
  const url=await value(`fetch('/qa/ticket').then(r=>r.json()).then(v=>v.url)`);
  await send('Page.navigate',{url});await until(`document.readyState==='complete'&&location.hash===''&&[...document.querySelectorAll('button')].some(b=>b.textContent==='Enroll this browser')`);
  await click('Enroll this browser');await until(`document.body.innerText.includes('Approval code:')`);
  await value(`fetch('/qa/approve').then(r=>r.json())`);await until(`document.querySelector('.hero')!==null`);
  assert.ok((await value('document.body.innerText')).includes('A very long lecture title'));
  await until(`document.querySelector('.temperature-readout')?.textContent.includes('56.5°C')`);
  const credentialFields=await value(`new Promise((resolve,reject)=>{const r=indexedDB.open('luma-remote-key-v1',1);r.onsuccess=()=>{const db=r.result;const tx=db.transaction('credentials');const q=tx.objectStore('credentials').get('selected');q.onsuccess=()=>{resolve(Object.keys(q.result).sort());db.close();};};r.onerror=reject;})`);
  assert.deepEqual(credentialFields,['deviceId','privateKey','publicKey']);
  const layouts=[];
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await until(`document.querySelector('.theme-${theme}')!==null`);
    for(const width of [320,390]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      const layout=await value(`({width:innerWidth,scroll:document.documentElement.scrollWidth,theme:getComputedStyle(document.querySelector('h1')).fontFamily})`);
      assert.ok(layout.scroll<=width,'Horizontal overflow');layouts.push({...layout,id:theme});
      assert.equal(await value(`(()=>{const r=document.querySelector('.temperature-readout').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth;})()`),true,'Temperature fits mobile width');
      if(width===390){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/${theme}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await click('Settings');await until(`document.body.innerText.includes('Primary settings')`);
  await value(`(()=>{const field=document.querySelector('input[type="password"]');const native=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;native.call(field,'123456');field.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click('Unlock primary settings');await until(`document.querySelector('.themes')!==null`);
  await until(`document.querySelector('.all-settings iframe')?.contentDocument?.body.innerText.includes('Your space.')`);
  await value(`document.querySelector('.quick-settings').open=true`);
  assert.equal(await value(`(()=>{const d=document.querySelector('.all-settings iframe').contentDocument;return d.querySelector('.keyboard-toggle')===null&&d.documentElement.scrollWidth<=d.defaultView.innerWidth;})()`),true,'Shared settings fit phone and use native keyboard');
  await value(`document.querySelector('.all-settings iframe').contentWindow.location.hash='users'`);
  await until(`document.querySelector('.all-settings iframe')?.contentDocument?.body.innerText.includes('Your people.')`);
  await value(`(()=>{const d=document.querySelector('.all-settings iframe').contentDocument;const field=d.querySelector('input');const native=Object.getOwnPropertyDescriptor(d.defaultView.HTMLInputElement.prototype,'value').set;native.call(field,'Casey');field.dispatchEvent(new d.defaultView.Event('input',{bubbles:true}));})()`);
  await value(`document.querySelector('.all-settings iframe').contentDocument.querySelector('form').requestSubmit()`);
  await until(`document.querySelector('.all-settings iframe')?.contentDocument?.body.innerText.includes('Casey')&&document.querySelector('.all-settings iframe')?.contentDocument?.body.innerText.includes('Pair your iPhone')`);
  await value(`document.querySelector('.all-settings iframe').contentWindow.location.hash='device'`);
  await until(`document.querySelector('.all-settings iframe')?.contentDocument?.body.innerText.includes('Your space.')`);
  for(const panel of ['USB cooling','Wi-Fi & appliance network','Raspberry Pi Connect','Signed software updates','Private Tailscale connection','iPhone remotes','Bluetooth pairing & forgetting','Notification sounds','Hey Luma & voice calibration']){
    assert.equal(await value(`(()=>{const d=document.querySelector('.all-settings iframe').contentDocument;return [...d.querySelectorAll('summary')].some(e=>e.textContent===${JSON.stringify(panel)});})()`),true,'All advanced controls available');
  }
  assert.equal(await value(`document.querySelector('.all-settings iframe').contentDocument.querySelectorAll('.remote-settings-disclosure[open]').length`),0,'Closed advanced panels do not poll');
  // The wall receives a published snapshot before the phone's save response.
  // Hold only that synthetic response to exercise tab clicks during this gap.
  for(const [name,theme] of [['Glass','luma-glass'],['Hearth','hearth'],['Neon','neon-grid']]){
    await click(name);await until(`window.qaSaveResponsePending===true`);
    assert.equal(await value(`[...document.querySelectorAll('.segmented button')].every(button=>button.disabled)`),true,'Settings tabs must wait for the save response, not just the wall snapshot');
    await wallUntil(`document.querySelector('.theme-${theme}')!==null`);
  }
  await click('Calendars');await until(`document.body.innerText.includes('Agenda · select all that apply')`);
  await click('Save calendar choices');await until(`document.querySelector('.themes')!==null`);
  await click('Hub');await until(`document.querySelector('.hero')!==null`);
  await value(`document.querySelector('.task button').click()`);
  await until(`document.querySelector('.task.completed')!==null`);
  await value(`(()=>{const field=document.querySelector('input[name="label"]');const native=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;native.call(field,'QA tea');field.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await click('Start timer');await until(`document.querySelector('.timer')!==null&&document.body.innerText.includes('QA tea')`);
  await click('Pause');await until(`document.querySelector('.timer')?.textContent.includes('paused')`);
  await click('Resume');await until(`document.querySelector('.timer')?.textContent.includes('running')`);
  await click('Cancel');await until(`document.querySelector('.timer')===null`);
  await click('Software');await until(`document.body.innerText.includes('Current version')&&document.body.innerText.includes('0.2.11')`);
  await click('Check for updates');await until(`document.querySelector('.release')!==null`);
  await click('Review complete · Install');await until(`document.body.innerText.includes('Synthetic services restarting')`);
  await wallUntil(`document.querySelector('.wall-update-progress')?.textContent.includes('Updating to 0.3.0')`);
  const accepted=await value(`fetch('/qa/actions').then(r=>r.json())`);
  assert.deepEqual(accepted.actions,['task','update']);
  await value(`fetch('/qa/update-complete').then(r=>r.json())`);
  await until(`document.querySelector('.software')?.textContent.includes('Current version 0.3.0')`);
  await click('Hub');await until(`document.querySelector('.hero')!==null`);
  await value(`fetch('/qa/disconnect').then(r=>r.json())`);await until(`document.querySelector('.locked')!==null`);
  assert.ok(!(await value('document.body.innerText')).includes('A very long lecture title'));
  await value(`fetch('/qa/reconnect').then(r=>r.json())`);await click('Check connection');await until(`document.querySelector('.hero')!==null`);
  await send('Page.navigate',{url:base+'/remote/'});await until(`document.querySelector('.hero')!==null`);
  const other=await(await fetch(debug+'/json/new?about:blank',{method:'PUT'})).json();
  try{
    await send('Target.activateTarget',{targetId:other.id});
    await until(`document.visibilityState==='hidden'&&document.querySelector('.hero')===null`);
    const before=responses.filter(row=>row.path.startsWith('/remote/api/')).length;
    await new Promise(resolve=>setTimeout(resolve,5500));
    assert.equal(responses.filter(row=>row.path.startsWith('/remote/api/')).length,before,'Hidden window must not poll');
    await send('Page.bringToFront');await until(`document.querySelector('.hero')!==null`);
  }finally{await fetch(debug+'/json/close/'+other.id);}
  await send('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await until(`document.querySelector('.hero')===null&&document.body.innerText.includes('Offline.')`);
  assert.ok(!(await value('document.body.innerText')).includes('A very long lecture title'));
  await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  await until(`document.querySelector('.hero')!==null`);
  await value(`fetch('/qa/revoke').then(r=>r.json())`);await until(`document.querySelector('.locked')!==null`);
  assert.ok(!(await value('document.body.innerText')).includes('A very long lecture title'));
  const guestUrl=await value(`fetch('/qa/guest-ticket').then(r=>r.json()).then(v=>v.url)`);
  // A different user's iPhone starts a fresh document/Serve identity context.
  // A same-document fragment keeps the old bootstrap digest and must fail.
  await send('Page.navigate',{url:'about:blank'});
  await send('Page.navigate',{url:guestUrl});
  await until(`[...document.querySelectorAll('button')].some(b=>b.textContent==='Enroll this browser')`);
  await click('Enroll this browser');await until(`document.body.innerText.includes('Approval code:')`);
  await value(`fetch('/qa/approve').then(r=>r.json())`);await until(`document.querySelector('.hero')!==null`);
  assert.ok((await value('document.body.innerText')).includes('Alex PRIVATE seminar'));
  await until(`document.querySelector('.temperature-readout')?.textContent.includes('56.5°C')`);
  assert.ok(!(await value('document.body.innerText')).includes('A very long lecture title'));
  assert.equal(await value(`[...document.querySelectorAll('nav button')].map(button=>button.textContent).join(',')`),'Hub,My calendars');
  assert.ok(!(await value('document.body.innerText')).includes('Wall controls'));
  await click('My calendars');await until(`document.body.innerText.includes('Agenda · select all that apply')`);
  assert.ok(!(await value('document.body.innerText')).includes('Sleep calendars'));
  assert.equal(await value(`document.querySelector('input[type="file"]')===null`),true);
  await click('Save calendar choices');await until(`document.body.innerText.includes('Alex’s calendars')`);
  await until(`document.querySelector('[aria-label="Your personal setup"]')?.innerText.includes('Ready when you are')`);
  for(const title of ['Choose your calendars','Connect your Google account','Your private phone link']){
    await click('Back');await until(`document.querySelector('[aria-label="Your personal setup"]')?.innerText.includes(${JSON.stringify(title)})`);
  }
  await click('Continue setup');await until(`document.body.innerText.includes('Connect your Google account')`);
  await click('Continue · Google is optional');await until(`document.body.innerText.includes('Choose your calendars')`);
  await click('Continue to sharing');await until(`document.body.innerText.includes('Ready when you are')`);
  await until(`!document.querySelector('[aria-label="Your personal setup"] input').disabled`);
  await value(`document.querySelector('[aria-label="Your personal setup"] input').click()`);
  await until(`document.body.innerText.includes('Setup saved · Wall sharing off')`);
  // Reload consumes a new signed request using the saved browser key. No
  // primary PIN or pairing request is needed to resume this user's progress.
  await send('Page.navigate',{url:base+'/remote/'});await until(`document.querySelector('.hero')!==null`);
  await click('My calendars');await until(`document.body.innerText.includes('Setup saved · Wall sharing off')`);
  assert.equal(await value(`document.querySelector('[aria-label="Your personal setup"] input').checked`),false);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await until(`document.querySelector('.theme-${theme}')!==null`);
    for(const width of [320,390]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`),'Personal guide horizontal overflow');
      if(width===390){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/guest-setup-${theme}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await click('Hub');await until(`document.querySelector('.hero')!==null`);
  assert.ok((await value('document.body.innerText')).includes('Alex PRIVATE seminar'),'Own preview survives turning wall sharing off');
  await click('Start timer');await until(`document.querySelector('.timer')!==null`);
  await click('Pause');await until(`document.querySelector('.timer')?.textContent.includes('paused')`);
  await click('Cancel');await until(`document.querySelector('.timer')===null`);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await until(`document.querySelector('.theme-${theme}')!==null`);
    for(const width of [320,390]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`),'Guest horizontal overflow');
      if(width===390){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/guest-${theme}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await value(`fetch('/qa/revoke').then(r=>r.json())`);await until(`document.querySelector('.locked')!==null`);
  assert.ok(!(await value('document.body.innerText')).includes('Alex PRIVATE seminar'));
  assert.equal(await value(`document.querySelector('.temperature-readout')===null`),true,'Revocation clears the sensor with the authorized preview');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Disposable Chromium; synthetic ANCS/provider/update broker, no Safari/Pi/live acceptance',layouts,credentialFields,enrollment:true,calendarSave:true,taskCompletion:true,timerLifecycle:true,remoteThemesAppliedToWall:true,remoteUpdateVisibleOnWall:true,updateReviewAcceptedOnce:true,updateStatusComplete:true,disconnectCleared:true,newSession:true,keyReload:true,backgroundCleared:true,backgroundPollingStopped:true,offlineCleared:true,revocationCleared:true,guestOwnCalendars:true,guestOwnTimer:true,guestNoAdminControls:true,guestNoOverflow:true,guestSetupResume:true,guestOwnSharingConsent:true,guestRevocationCleared:true,errors},null,2));
}finally{wallSocket?.close();if(wallTarget)await fetch(debug+'/json/close/'+wallTarget.id);socket.close();await fetch(debug+'/json/close/'+target.id);}
