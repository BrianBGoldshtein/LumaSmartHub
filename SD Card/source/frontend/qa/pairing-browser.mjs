// Synthetic crowded BlueZ driver, real primary/secondary controllers and UI.
// Never installed or run against the owner's Pi, browser or Bluetooth radio.
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
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+25000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression+'\n'+await value('document.body.innerText'));await new Promise(r=>setTimeout(r,80));}}
const doc=()=>mode==='remote'?"document.querySelector('.all-settings iframe')?.contentDocument":'document';
const scoped=body=>`(()=>{const d=${doc()};${body}})()`;
async function inside(predicate){await until(scoped(`return !!d&&(${predicate});`));}
async function click(text){await inside(`[...d.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(scoped(`[...d.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click();`));}
async function outerClick(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
async function query(text){await value(scoped(`const f=d.querySelector('.phone-picker input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(f,${JSON.stringify(text)});f.dispatchEvent(new Event('input',{bubbles:true}));`));}
async function shot(name){await value(scoped(`d.querySelector('.phone-picker').scrollIntoView({block:'start'});`));
  const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/${name}.png`,Buffer.from(result.data,'base64'));}
async function exercise(theme,width,role){
  await inside(`d.fonts.status==='loaded'&&d.querySelector('.theme-${theme}')!==null`);
  await click(role==='secondary'?'Find my iPhone':'Choose another phone');
  await inside(`d.querySelector('.phone-picker-count')?.textContent.includes('of 251 devices')`);
  assert.equal(await value(scoped(`return d.querySelectorAll('.phone-picker-results button').length;`)),6);
  assert.equal(await value(scoped(`return d.querySelector('.phone-picker-results strong').textContent;`)),'Campus device 000');
  assert.ok((await value(scoped(`return d.querySelector('.phone-picker-results button').textContent;`))).includes('-25 dBm'));
  await click('Next');await inside(`d.querySelector('.phone-picker-count')?.textContent.startsWith('7–12')`);
  await click('Previous');await inside(`d.querySelector('.phone-picker-count')?.textContent.startsWith('1–6')`);
  await query('no such device');await inside(`d.querySelectorAll('.phone-picker-results button').length===0&&d.querySelector('.phone-picker-count')?.textContent.includes('No matches')`);
  await click('Clear search');await inside(`d.querySelectorAll('.phone-picker-results button').length===6`);
  await query('cc dd ee 00 00 f9');await inside(`d.querySelectorAll('.phone-picker-results button').length===1`);
  assert.ok((await value(scoped(`return d.querySelector('.phone-picker-results button').textContent;`))).includes('CC:DD:EE:00:00:F9'));
  await click('Clear search');await query('ZOE');await inside(`d.querySelectorAll('.phone-picker-results button').length===1&&d.querySelector('.phone-picker-results strong')?.textContent==='Zoë’s iPhone'`);
  // Measure after settled frames; never turn an overflow assertion into a retry.
  await value(scoped(`return new Promise(resolve=>d.defaultView.requestAnimationFrame(()=>d.defaultView.requestAnimationFrame(resolve)));`));
  const layout=await value(scoped(`return {width:d.defaultView.innerWidth,scroll:d.documentElement.scrollWidth,buttons:d.querySelectorAll('.phone-picker-results button').length};`));
  assert.ok(layout.scroll<=layout.width+1,`${mode}/${role}/${theme}/${width}: overflow`);
  if(mode==='remote')assert.equal(await value(scoped(`return d.querySelectorAll('.phone-picker .keyboard-toggle').length;`)),0);
  else{
    assert.equal(await value(scoped(`return d.querySelectorAll('.phone-picker .keyboard-toggle').length;`)),1);
    await value(scoped(`d.querySelector('.phone-picker .keyboard-toggle').click();`));
    await inside(`d.querySelector('.phone-picker .touch-keyboard')!==null`);
    await value(scoped(`d.querySelector('.phone-picker .keyboard-toggle').click();`));
    await inside(`d.querySelector('.phone-picker .touch-keyboard')===null`);
  }
  if(width===390||mode==='wall')await shot(`pairing-${mode}-${role}-${theme}`);
  await value(scoped(`d.querySelector('.phone-picker-results button').click();`));
  await inside(`d.querySelector('[aria-label="Pairing code"]')?.textContent==='042817'`);
  const audit=await value(`fetch('/qa/pairing-audit').then(r=>r.json())`),last=audit.drivers.at(-1);
  assert.equal(last.selected,'/org/bluez/hci0/dev_CC_DD_EE_00_FF_01');assert.equal(last.trust_calls,0);
  await click('Cancel pairing');await inside(`d.querySelector('.phone-picker')===null`);
  await until(`fetch('/qa/pairing-audit').then(r=>r.json()).then(r=>r.drivers.at(-1).closed)`);
  reports.push({mode,role,theme,requestedWidth:width,...layout,exactSelection:true,noTrustBeforeConfirmation:true,cancelClosed:true});
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
    // Shared settings fetch their theme on mount.
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='users'");await inside("d.querySelector('.user-setup')!==null");
    await value("document.querySelector('.all-settings iframe').contentWindow.location.hash='device'");await inside("d.querySelector('.device-setup')!==null");
    await value(scoped("[...d.querySelectorAll('summary')].find(s=>s.textContent.trim()==='Bluetooth pairing & forgetting').click();"));
    for(const width of [320,390]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
      await exercise(theme,width,'primary');
    }
  }
  mode='wall';
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:wall+'/?setup=device'});await until("document.querySelector('.app')!==null");
  assert.equal(await value("fetch('/api/v1/admin/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:'123456'})}).then(r=>r.status)"),200);
  let secondary=null;
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await send('Page.navigate',{url:wall+'/?setup=device'});await inside("d.querySelector('.device-setup')!==null");
    await exercise(theme,1024,'primary');
    const action=secondary?{action:'resume',profile_id:secondary}:{action:'create',nickname:'Casey'};
    const user=await value(`fetch('/api/v1/users/manage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(${JSON.stringify(action)})}).then(async r=>({status:r.status,...await r.json()}))`);
    assert.equal(user.status,200);secondary=user.profile_id;
    await send('Page.navigate',{url:wall+'/?setup=personal'});await inside("d.querySelector('.user-setup')!==null");
    await exercise(theme,1024,'secondary');
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Synthetic crowded radio; real UI and pairing controllers, not physical iPhone discovery',reports,errors},null,2));
}catch(error){
  const screenshot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/pairing-failure.png`,Buffer.from(screenshot.data,'base64'));throw error;
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
