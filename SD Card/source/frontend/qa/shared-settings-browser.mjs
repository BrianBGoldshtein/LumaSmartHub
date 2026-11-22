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
  await click('Unlock primary settings');await until(`!!(${child}?.querySelector('.settings-groups'))`);
  const navigate=section=>value(`[...${child}.querySelectorAll('.settings-groups a,.settings-options a,.settings-path a')].find(a=>a.hash.endsWith(${JSON.stringify(section)})).click()`);
  await navigate('/networking');
  await until(`${child}?.querySelector('h1')?.textContent==='Network & remote'`);
  await navigate('/wifi');
  await until(`!!${child}?.querySelector('.network-setup')`);
  assert.equal(await value(`${child}.activeElement.id`),'settings-page-title');
  await navigate('/networking');
  await until(`!!${child}?.querySelector('.settings-options')`);
  await navigate('/luma-glass');
  await until(`!!${child}?.querySelector('.settings-groups')`);
  await navigate('/display');
  await until(`${child}?.querySelector('h1')?.textContent==='Display & weather'`);
  await navigate('/appearance');
  await until(`!!${child}?.querySelector('.settings-appearance input[type="range"]')`);
  await value(`(()=>{const d=${child},slider=d.querySelector('.settings-appearance input[type="range"]'),w=d.defaultView;Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(slider,slider.value==='68'?'69':'68');slider.dispatchEvent(new w.Event('input',{bubbles:true}));})()`);
  await until(`${child}?.querySelector('.settings-appearance button')?.disabled===false`);
  await value(`${child}.querySelector('.settings-appearance button').click()`);
  await until(`${child}?.querySelector('.settings-appearance [role=status]')?.textContent==='Display settings saved.'`);
  const wall='http://127.0.0.1:18835';
  await send('Page.navigate',{url:wall+'/?setup=device'});
  await until(`document.querySelector('.app')!==null`);
  assert.ok(await value(`fetch('/api/v1/admin/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'123456'})}).then(r=>r.ok)`));
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await send('Emulation.setDeviceMetricsOverride',{width:1024,height:600,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:wall+'/?setup=device&demo=1&theme='+theme});
    await until(`document.querySelector('.settings-hub.theme-${theme} .settings-groups')?.children.length===8`);
    await value(`(async()=>{await document.fonts.ready;await new Promise(r=>requestAnimationFrame(r));})()`);
    assert.ok(await value(`document.querySelector('.settings-hub').scrollHeight<=innerHeight+1`));
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/wall-settings-${theme}.png`,Buffer.from(shot.data,'base64'));
    const links=await value(`[...document.querySelectorAll('.settings-groups a')].filter(a=>a.href.includes('section=')).map(a=>a.href)`);
    if(theme==='luma-glass'){
      const sections=[];
      for(const link of links){
        await send('Page.navigate',{url:link});await until(`!!document.querySelector('.settings-options')`);
        sections.push(...await value(`[...document.querySelectorAll('.settings-options a')].map(a=>a.href)`));
      }
      assert.equal(new Set(sections).size,sections.length);
      assert.equal(sections.length,26);
      for(const link of sections){
        const panel=new URL(link).searchParams.get('section');
        await send('Page.navigate',{url:link});
        await until(`!!document.querySelector('.settings-controls[data-panel="${panel}"]')`);
        assert.ok(await value(`document.querySelector('.settings-controls').textContent.trim().length>0`),panel+' has no controls');
      }
    }
  }
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  // The already-enrolled browser retains its key across this tab navigation.
  await send('Page.navigate',{url:base+'/remote/'});
  await until(`!!document.querySelector('.hero')`);
  await click('Settings');
  await until(`!!document.querySelector('input[type=password]')`);
  await value("(()=>{const f=document.querySelector('input[type=password]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(f,'123456');f.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await click('Unlock primary settings');await until(`!!(${child}?.querySelector('.settings-groups'))`);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await until(`document.querySelector('.theme-${theme}')!==null&&!!(${child}?.querySelector('.theme-${theme}'))`);
    for(const width of [320,390])for(const [step,selector,section=''] of [['device','.settings-groups'],['device','.settings-options','system'],['device','.fan-control','cooling'],['onboarding','.onboarding-main'],['extras','.extras-choices'],['users','.user-setup']]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      await value(`document.querySelector('.all-settings iframe').contentWindow.location.hash=${JSON.stringify([step,theme,section].filter(Boolean).join('/'))}`);
      await until(`!!(${child}?.querySelector(${JSON.stringify(selector)}))&&${child}?.fonts.status==='loaded'`);
      await until(`!!(${child}?.querySelector('.theme-${theme}'))&&${child}?.querySelector('h1')!==null&&!/Loading (saved settings|your saved progress)/.test(${child}?.body.innerText??'')`);
      if(step==='users')await until(`(${child}?.querySelectorAll('.user-list article').length??0)>=2`);
      if(section==='cooling'){
        await until(`${child}?.querySelector('.fan-control')?.textContent.includes('On at 70°C')`);
        const cooling=await value(`${child}.querySelector('.fan-control').textContent`);
        assert.ok(cooling.includes('On at 70°C · off at 60°C'));
        assert.ok(cooling.includes('No periodic USB discovery cycles.'));
        assert.ok(cooling.includes('Use your phone remote’s Keep USB on control'));
        assert.ok(!cooling.includes('discovery window returns'));
      }
      if(step==='onboarding')await until(`${child}?.querySelector('.onboarding-themes')!==null`);
      // Measure once after font/layout frames settle, not during the hash
      // transition. Do not retry or weaken the actual overflow assertion.
      await value(`(async()=>{const d=${child};await d.fonts.ready;await new Promise(resolve=>d.defaultView.requestAnimationFrame(()=>d.defaultView.requestAnimationFrame(resolve)));})()`);
      const report=await value(`(()=>{const d=${child},w=d.defaultView;return {width:w.innerWidth,scroll:d.documentElement.scrollWidth,heading:d.querySelector('h1')?.textContent,keyboards:d.querySelectorAll('.keyboard-toggle').length};})()`);
      assert.ok(report.scroll<=report.width+1,`${theme}/${width}/${step}: horizontal overflow`);assert.equal(report.keyboards,0);
      reports.push({theme,step,section,...report});
      if(width===390){await value("document.querySelector('.all-settings').scrollIntoView({block:'start'})");const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/shared-${theme}-${section||step}.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  await value("fetch('/qa/disconnect').then(r=>r.json())");await until("document.querySelectorAll('.connected-users li').length===0");
  assert.ok(await value("document.querySelector('.all-settings iframe')!==null"));
  await value("fetch('/qa/revoke').then(r=>r.json())");await until("document.querySelector('.all-settings iframe')===null");
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Synthetic primary phone and real signed browser transport, not Safari/Pi acceptance',reports,awaySettingsAvailable:true,revocationClearsFrame:true,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
