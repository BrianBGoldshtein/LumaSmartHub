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
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression,timeout=18000){const deadline=Date.now()+timeout;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Condition timed out: '+expression+'\n'+JSON.stringify({page:await value('({text:document.body.innerText,visibility:document.visibilityState,online:navigator.onLine})'),errors,responses}));
  await new Promise(resolve=>setTimeout(resolve,100));}}
const click=text=>value(`(()=>{const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!button)throw Error('Button unavailable');button.click();})()`);
try{
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Page.bringToFront');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await until(`document.querySelector('.locked')!==null`);
  const url=await value(`fetch('/qa/ticket').then(r=>r.json()).then(v=>v.url)`);
  await send('Page.navigate',{url});await until(`document.readyState==='complete'&&location.hash===''&&[...document.querySelectorAll('button')].some(b=>b.textContent==='Enroll this browser')`);
  await click('Enroll this browser');await until(`document.body.innerText.includes('Approval code:')`);
  await value(`fetch('/qa/approve').then(r=>r.json())`);await until(`document.querySelector('.hero')!==null`);
  assert.ok((await value('document.body.innerText')).includes('A very long lecture title'));
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
      if(width===390){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/${theme}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await click('Settings');await until(`document.querySelector('.themes')!==null`);
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
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Disposable Chromium; synthetic ANCS/provider/update broker, no Safari/Pi/live acceptance',layouts,credentialFields,enrollment:true,calendarSave:true,taskCompletion:true,timerLifecycle:true,updateReviewAcceptedOnce:true,updateStatusComplete:true,disconnectCleared:true,newSession:true,keyReload:true,backgroundCleared:true,backgroundPollingStopped:true,offlineCleared:true,revocationCleared:true,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
