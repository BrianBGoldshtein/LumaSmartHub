// Real wall and signed-primary settings; simulated GPIO/USB/temperature only.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='https://luma.example-tail.ts.net',wall='http://127.0.0.1:18835',debug='http://127.0.0.1:19226';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/remote/'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
let id=0,mode='remote';const pending=new Map(),errors=[],reports=[];
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
socket.onmessage=e=>{const v=JSON.parse(e.data);if(v.method==='Runtime.exceptionThrown')errors.push(v.params.exceptionDetails.text);
  const p=pending.get(v.id);if(p){pending.delete(v.id);v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);}};
async function value(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);return r.result.value;}
async function until(expression){const end=Date.now()+25000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression+'\n'+await value('document.body.innerText'));await new Promise(r=>setTimeout(r,80));}}
const doc=()=>mode==='remote'?"document.querySelector('.all-settings iframe')?.contentDocument":'document';
const scoped=body=>`(()=>{const d=${doc()};${body}})()`;
async function inside(test){await until(scoped(`return !!d&&(${test});`));}
async function click(text){await inside(`[...d.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(scoped(`[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click();`));}
async function outer(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
async function post(path,body={}){return value(`fetch(${JSON.stringify(path)},{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(body)})}).then(r=>r.json())`);}
async function audit(){return value("fetch('/qa/gpio').then(r=>r.json())");}
async function select(backend){await value(scoped(`const n=d.querySelector('.fan-connection select');n.value=${JSON.stringify(backend)};n.dispatchEvent(new d.defaultView.Event('change',{bubbles:true}));`));}
async function exercise(theme,width){
  await post('/qa/gpio/reset');
  await inside(`d.querySelector('.fan-control')?.textContent.includes('USB power: on')&&!d.querySelector('.fan-control')?.textContent.includes('BCM12 switch')`);
  await value(scoped(`const n=d.querySelector('.fan-connection');if(!n.open)n.querySelector('summary').click();`));
  await select('gpio12');
  assert.equal(await value(scoped(`return [...d.querySelectorAll('button')].find(b=>b.textContent==='Use this fan connection').disabled;`)),true);
  assert.equal((await audit()).fan_calls.length,0);
  await value(scoped(`d.querySelector('.fan-connection input').click();`));await click('Use this fan connection');
  await inside(`d.querySelector('.fan-control')?.textContent.includes('BCM12 switch · USB power: on')`);
  let row=await audit();assert.equal(row.status.backend,'gpio12');assert.equal(row.status.qualified,false);assert.equal(row.fan_on,true);
  assert.equal(await value(scoped(`return [...d.querySelectorAll('button')].find(b=>b.textContent==='Automatic cooling').disabled;`)),true);
  await value(scoped(`const n=d.querySelector('.fan-control details:not(.fan-connection)');if(!n.open)n.querySelector('summary').click();d.querySelector('.fan-control input[type=checkbox]').click();`));
  await click('Test five-second fan interruption');
  await inside(`d.querySelector('.fan-control')?.textContent.includes('Testing · fan power returns')`);
  row=await audit();assert.equal(row.fan_on,false);assert.equal(row.usb_on,true);
  await post('/qa/gpio/advance',{seconds:6});
  await inside(`[...d.querySelectorAll('button')].some(b=>b.textContent==='Confirm fan stopped and restarted')`);
  assert.equal(await value(scoped(`return d.querySelector('.fan-control input[type=checkbox]').checked;`)),false);
  await value(scoped(`d.querySelector('.fan-control input[type=checkbox]').click();`));
  await click('Confirm fan stopped and restarted');await post('/qa/gpio/advance',{seconds:61,heartbeat:true});
  await click('Automatic cooling');await inside(`d.querySelector('.fan-control')?.textContent.includes('Mode: Automatic cooling')`);
  row=await audit();assert.equal(row.fan_on,false);assert.equal(row.status.mode,'automatic');
  row=await post('/qa/gpio/advance',{temperature:70});assert.equal(row.fan_on,true);
  row=await post('/qa/gpio/advance',{temperature:60,seconds:61,heartbeat:true});
  assert.equal(row.fan_on,false);
  await inside(`d.querySelector('.fan-control')?.textContent.includes('Mode: Automatic cooling')`);
  assert.equal(row.usb_on,true);assert.ok(row.usb_calls.every(Boolean));
  await value(scoped(`d.querySelector('.fan-connection').scrollIntoView({block:'center'});return d.fonts.ready;`));
  const layout=await value(scoped(`const n=d.querySelector('.fan-connection').getBoundingClientRect();return {width:d.defaultView.innerWidth,scroll:d.documentElement.scrollWidth,left:n.left,right:n.right};`));
  assert.ok(layout.scroll<=layout.width+1&&layout.left>=0&&layout.right<=layout.width+1,JSON.stringify({mode,theme,width,layout}));
  if(width===390||mode==='wall'){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/gpio-${mode}-${theme}.png`,Buffer.from(shot.data,'base64'));}
  await click('Keep fan on');await inside(`d.querySelector('.fan-control')?.textContent.includes('Mode: Keep fan on')`);
  assert.equal((await audit()).fan_on,true);
  await select('usb');await value(scoped(`d.querySelector('.fan-connection input').click();`));await click('Use this fan connection');
  await inside(`d.querySelector('.fan-control')?.textContent.includes('USB power: on')&&!d.querySelector('.fan-control')?.textContent.includes('BCM12 switch')`);
  row=await audit();assert.equal(row.status.backend,'usb');assert.equal(row.status.qualified,false);assert.equal(row.usb_on,true);
  reports.push({mode,theme,requestedWidth:width,...layout,wiringAck:true,fanOnlyProbe:true,observation:true,thermal70_60:true,usbNeverCut:true,returnClearsApproval:true});
}
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Page.navigate',{url:await value("fetch('/qa/ticket').then(r=>r.json()).then(v=>v.url)")});
  await outer('Enroll this browser');await until("document.body.innerText.includes('Approval code:')");
  await value("fetch('/qa/approve').then(r=>r.json())");await until("document.querySelector('.hero')!==null");
  await outer('Settings');await until("document.querySelector('input[type=password]')!==null");
  await value("(()=>{const n=document.querySelector('input[type=password]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(n,'123456');n.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await outer('Unlock primary settings');await inside("d.querySelector('.device-setup')!==null");
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await post('/qa/theme',{theme});
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='users'");await inside("d.querySelector('.user-setup')!==null");
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='device'");await inside("d.querySelector('.device-setup')!==null");
    await inside("[...d.querySelectorAll('summary')].some(n=>n.textContent.trim()==='Fan cooling')");
    await value(scoped(`[...d.querySelectorAll('summary')].find(n=>n.textContent.trim()==='Fan cooling').click();`));
    for(const width of [320,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});await exercise(theme,width);}
  }
  mode='wall';await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:wall+'/?setup=device'});await until("document.querySelector('.app')!==null");
  assert.equal(await value("fetch('/api/v1/admin/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'123456'})}).then(r=>r.status)"),200);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await post('/qa/theme',{theme});await send('Page.navigate',{url:wall+'/?setup=device'});
    // The wall renders the controls directly; only the compact phone view
    // wraps each section in an outer accordion.
    await inside("d.querySelector('.fan-control')!==null");
    await exercise(theme,1024);
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Synthetic GPIO/USB, actual signed shared settings; not physical fan acceptance',reports,errors},null,2));
}catch(e){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/gpio-failure.png`,Buffer.from(shot.data,'base64'));throw e;}
finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
