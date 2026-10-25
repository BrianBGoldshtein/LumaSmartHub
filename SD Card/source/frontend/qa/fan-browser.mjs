// Actual wall/primary-remote controls and protected API; fake USB hardware only.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='https://luma.example-tail.ts.net',wall='http://127.0.0.1:18835',debug='http://127.0.0.1:19226';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/remote/'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let id=0,mode='remote';const pending=new Map(),errors=[],reports=[];
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);
  if(data.method==='Page.javascriptDialogOpening')void send('Page.handleJavaScriptDialog',{accept:true});
  const item=pending.get(data.id);if(item){pending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result);}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description??result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+25000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression+'\n'+await value('document.body.innerText'));await new Promise(r=>setTimeout(r,80));}}
const doc=()=>mode==='remote'?"document.querySelector('.all-settings iframe')?.contentDocument":'document';
const scoped=body=>`(()=>{const d=${doc()};${body}})()`;
async function inside(predicate){await until(scoped(`return !!d&&(${predicate});`));}
async function click(text){await inside(`[...d.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(scoped(`[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click();`));}
async function outerClick(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
async function acknowledge(){await value(scoped(`d.querySelector('.fan-control input[type=checkbox]').click();`));}
async function reset(permanent=false){await value(`fetch('/qa/fan/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({permanent:${permanent}})}).then(r=>r.json())`);}
async function audit(){return value("fetch('/qa/fan').then(r=>r.json())");}
async function exercise(theme,width){
  await inside(`d.fonts.status==='loaded'&&d.querySelector('.theme-${theme}')!==null`);
  await reset();
  await inside(`d.querySelector('.fan-control')?.textContent.includes('Switching fault')`);
  await value(scoped(`const v=d.querySelector('.fan-control details');if(!v.open)v.querySelector('summary').click();`));
  const before=(await audit()).calls.filter(v=>v===false).length;
  assert.equal(await value(scoped(`return [...d.querySelectorAll('.fan-control button')].find(b=>b.textContent==='Retry physical fan test').disabled;`)),true);
  await acknowledge();await click('Retry physical fan test');
  await inside(`d.querySelector('.fan-control')?.textContent.includes('Testing · USB power returns')`);
  assert.equal((await audit()).status.probe,'running');
  await inside(`[...d.querySelectorAll('.fan-control button')].some(b=>b.textContent==='Confirm fan stopped and restarted')`);
  let row=await audit();assert.equal(row.status.usb_power,'on');assert.equal(row.status.qualified,false);
  assert.equal(row.calls.filter(v=>v===false).length,before+1);
  assert.equal(await value(scoped(`return d.querySelector('.fan-control input[type=checkbox]').checked;`)),false);
  await acknowledge();await click('Confirm fan stopped and restarted');
  await inside(`d.querySelector('.fan-control')&&[...d.querySelectorAll('.fan-control button')].some(b=>b.textContent==='Automatic cooling'&&!b.disabled)`);
  await click('Automatic cooling');await inside(`d.querySelector('.fan-control')?.textContent.includes('Mode: Automatic cooling')`);
  row=await audit();assert.equal(row.status.qualified,true);assert.equal(row.status.mode,'automatic');
  await value(scoped(`d.querySelector('.fan-control').scrollIntoView({block:'start'});return new Promise(resolve=>d.defaultView.requestAnimationFrame(()=>d.defaultView.requestAnimationFrame(resolve)));`));
  const layout=await value(scoped(`return {width:d.defaultView.innerWidth,scroll:d.documentElement.scrollWidth};`));
  assert.ok(layout.scroll<=layout.width+1,`${mode}/${theme}/${width}: overflow`);
  if(width===390||mode==='wall'){
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/fan-${mode}-${theme}.png`,Buffer.from(shot.data,'base64'));
  }
  await click('Keep USB on · mouse & drives');assert.equal((await audit()).status.usb_power,'on');
  reports.push({mode,theme,requestedWidth:width,...layout,ackRequired:true,independentRestoration:true,explicitConfirmation:true,automaticRecovered:true});
}
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Page.navigate',{url:await value("fetch('/qa/ticket').then(r=>r.json()).then(v=>v.url)")});
  await outerClick('Enroll this browser');await until("document.body.innerText.includes('Approval code:')");
  await value("fetch('/qa/approve').then(r=>r.json())");await until("document.querySelector('.hero')!==null");
  await outerClick('Settings');await until("document.querySelector('input[type=password]')!==null");
  await value("(()=>{const f=document.querySelector('input[type=password]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(f,'123456');f.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await outerClick('Unlock primary settings');await inside("d.querySelector('.device-setup')!==null");
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='users'");await inside("d.querySelector('.user-setup')!==null");
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='device'");await inside("d.querySelector('.device-setup')!==null");
    await inside("[...d.querySelectorAll('summary')].some(s=>s.textContent.trim()==='USB cooling')");
    await value(scoped("[...d.querySelectorAll('summary')].find(s=>s.textContent.trim()==='USB cooling').click();"));
    for(const width of [320,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});await exercise(theme,width);}
  }
  // A persistently failing simulated switch must not silently requalify.
  await reset(true);await inside(`d.querySelector('.fan-control')?.textContent.includes('Switching fault')`);
  await acknowledge();await click('Retry physical fan test');
  await inside(`d.querySelector('.fan-control [role=alert]')!==null`);
  assert.equal(await value(scoped(`return d.querySelector('.fan-control input[type=checkbox]').checked;`)),false);
  const failed=await audit();assert.equal(failed.status.qualified,false);assert.equal(failed.status.usb_power,'on');
  await click('Keep USB on · mouse & drives');
  mode='wall';await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:wall+'/?setup=device'});await until("document.querySelector('.app')!==null");
  assert.equal(await value("fetch('/api/v1/admin/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'123456'})}).then(r=>r.status)"),200);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await send('Page.navigate',{url:wall+'/?setup=device'});await inside("d.querySelector('.device-setup')!==null");
    await exercise(theme,1024);
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Simulated USB hub, actual signed primary/wall UI; not physical fan verification',reports,persistentFailureStaysUnqualified:true,errors},null,2));
}catch(error){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/fan-failure.png`,Buffer.from(shot.data,'base64'));throw error;}
finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
