// Real wall/controller/chooser; synthetic phones/provider, no microphone/audio.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const initialized=await(await fetch(base+'/qa/voice-initialize',{method:'POST'})).json();
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let sequence=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);
  if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);
  const waiter=pending.get(row.id);if(!waiter)return;pending.delete(row.id);row.error?waiter.reject(Error(JSON.stringify(row.error))):waiter.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function waitFor(expression){const deadline=Date.now()+15000;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Timed out: '+expression);
  await new Promise(resolve=>setTimeout(resolve,50));}}
async function request(path,body={}){return value(`fetch(${JSON.stringify(path)},{method:'POST',headers:{'Content-Type':'application/json'},body:${JSON.stringify(JSON.stringify(body))}}).then(r=>r.json())`);}
async function question(){const result=await request('/api/v1/voice/command',{text:'when is my next event'});assert.equal(result.accepted,false);await waitFor(`document.querySelector('.voice-account-choice')!==null`);}
const reports=[];
try{
  await send('Page.enable');await send('Runtime.enable');
  await waitFor(`document.querySelector('.app')!==null`);
  for(const theme of ['luma-glass','hearth','neon-grid'])for(const [width,height] of [[320,720],[390,844],[1024,768],[2048,1536]]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await request('/qa/theme',{theme});
    await question();await value('document.fonts.ready');
    await waitFor(`document.querySelector('.app').classList.contains('theme-${theme}')`);
    assert.equal(await value(`document.documentElement.scrollWidth<=innerWidth`),true);
    const labels=await value(`[...document.querySelectorAll('.voice-account-choice>div button')].map(b=>b.textContent)`);
    assert.deepEqual(labels,['Brian','Alex','Sam','Casey','Robin']);
    const bounds=await value(`(()=>{const r=document.querySelector('.voice-account-choice').getBoundingClientRect();return {x:r.x,right:r.right,y:r.y,bottom:r.bottom};})()`);
    assert.ok(bounds.x>=0&&bounds.right<=width&&bounds.y>=0&&bounds.bottom<=height);
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(`${process.env.USER_QA_OUTPUT}/${theme}-${width}-voice-choice.png`,Buffer.from(shot.data,'base64'));
    await value(`[...document.querySelectorAll('.voice-account-choice button')].find(b=>b.textContent==='Alex').click()`);
    await waitFor(`document.querySelector('.voice-account-choice')===null`);
    const reply=await request('/api/v1/voice/account/reply');
    assert.equal(reply.play,true);assert.ok(reply.message.includes('Alex PRIVATE EVENT'));assert.ok(!reply.message.includes('Brian PRIVATE'));
    assert.deepEqual(await request('/api/v1/voice/account/reply'),{play:false});
    reports.push({theme,width,height,bounds});
  }
  await question();await value(`document.querySelector('.voice-account-close').click()`);
  await waitFor(`document.querySelector('.voice-account-choice')===null`);
  assert.equal(await value(`fetch('/api/v1/state').then(r=>r.json()).then(s=>s.voice_account_choice===null)`),true);
  await question();await request('/qa/voice-expire');
  await waitFor(`document.querySelector('.voice-account-choice')===null`);
  await question();await request('/qa/voice-disconnect',{profile_id:initialized.users[1].id});
  await waitFor(`![...document.querySelectorAll('.voice-account-choice>div button')].some(b=>b.textContent==='Alex')`);
  assert.equal(await value(`fetch('/api/v1/state').then(r=>r.json()).then(s=>s.user_panels.some(u=>u.nickname==='Alex'))`),false);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({cases:reports.length,touchReplies:true,oneUse:true,cancel:true,expiry:true,disconnectClearing:true,errors,reports},null,2));
}finally{socket.close();}
