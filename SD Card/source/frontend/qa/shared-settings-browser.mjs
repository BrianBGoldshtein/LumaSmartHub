// Disposable TLS browser fixture. No owner data, hardware or real providers.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const debug='http://127.0.0.1:19226',base='https://luma.example-tail.ts.net';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/remote/'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let id=0;const pending=new Map(),errors=[],reports=[];
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);
  if(data.method==='Page.javascriptDialogOpening')void send('Page.handleJavaScriptDialog',{accept:true});
  const task=pending.get(data.id);if(task){pending.delete(data.id);data.error?task.reject(Error(JSON.stringify(data.error))):task.resolve(data.result);}};
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+25000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression);await new Promise(r=>setTimeout(r,80));}}
const child="document.querySelector('.all-settings iframe')?.contentDocument";
async function click(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await send('Page.navigate',{url:await value("fetch('/qa/ticket').then(r=>r.json()).then(v=>v.url)")});
  await click('Enroll this browser');await until("document.body.innerText.includes('Approval code:')");
  await value("fetch('/qa/approve').then(r=>r.json())");await until("document.querySelector('.hero')!==null");
  await click('Settings');await until("document.querySelector('input[type=password]')!==null");
  await value("(()=>{const f=document.querySelector('input[type=password]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(f,'123456');f.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await click('Unlock primary settings');await until(`!!(${child}?.querySelector('.setup-content'))`);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await until(`document.querySelector('.theme-${theme}')!==null&&!!(${child}?.querySelector('.theme-${theme}'))`);
    for(const width of [320,390])for(const [step,selector] of [['device','.device-setup'],['onboarding','.onboarding-main'],['extras','.extras-choices'],['users','.user-setup']]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      await value(`document.querySelector('.all-settings iframe').contentWindow.location.hash=${JSON.stringify(step)}`);
      await until(`!!(${child}?.querySelector(${JSON.stringify(selector)}))&&${child}?.fonts.status==='loaded'`);
      await until(`!!(${child}?.querySelector('.theme-${theme}'))&&${child}?.querySelector('h1')!==null&&!/Loading (saved settings|your saved progress)/.test(${child}?.body.innerText??'')`);
      if(step==='users')await until(`(${child}?.querySelectorAll('.user-list article').length??0)>=2`);
      if(step==='device')await until(`${child}?.body.innerText.includes('Location & display')`);
      if(step==='onboarding')await until(`${child}?.querySelector('.onboarding-themes')!==null`);
      const report=await value(`(()=>{const d=${child},w=d.defaultView;return {width:w.innerWidth,scroll:d.documentElement.scrollWidth,heading:d.querySelector('h1')?.textContent,keyboards:d.querySelectorAll('.keyboard-toggle').length};})()`);
      assert.ok(report.scroll<=report.width+1,`${theme}/${width}/${step}: horizontal overflow`);assert.equal(report.keyboards,0);
      reports.push({theme,step,...report});
      if(width===390){await value("document.querySelector('.all-settings').scrollIntoView({block:'start'})");const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/shared-${theme}-${step}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await value("fetch('/qa/disconnect').then(r=>r.json())");await until("document.querySelector('.all-settings iframe')===null");
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Synthetic primary phone and real signed browser transport, not Safari/Pi acceptance',reports,disconnectClearsFrame:true,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
