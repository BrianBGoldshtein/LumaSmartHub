// Synthetic local storage/PIN only. No owner browser, Pi, broker or account.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18832',debug='http://127.0.0.1:19227';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/?setup=device'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let id=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);
  if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);
  const wait=pending.get(row.id);if(!wait)return;pending.delete(row.id);row.error?wait.reject(Error(JSON.stringify(row.error))):wait.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const seq=++id;pending.set(seq,{resolve,reject});socket.send(JSON.stringify({id:seq,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const deadline=Date.now()+20000;
  while(!(await value(expression))){if(Date.now()>=deadline)throw Error('Timed out: '+expression+' '+await value('document.body.innerText'));
    await new Promise(resolve=>setTimeout(resolve,100));}}
const click=text=>value(`(()=>{const button=[...document.querySelectorAll('button')].find(row=>row.textContent.trim()===${JSON.stringify(text)});if(!button)throw Error('Missing button');button.click();})()`);
try{
  await send('Page.enable');await send('Runtime.enable');await send('Page.bringToFront');
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await until(`document.body.innerText.includes('Primary settings')&&!document.querySelector('.primary-admin-prompt button')?.disabled`);
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
    await send('Page.navigate',{url:base+'/?setup=device'});
    await until(`document.querySelector('.theme-${theme} .primary-admin-prompt')!==null`);
    for(const width of [1024,2048]){
      await send('Emulation.setDeviceMetricsOverride',{width,height:width===1024?768:1536,deviceScaleFactor:1,mobile:false});
      assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`));
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await fs.writeFile(`${process.env.WALL_QA_OUTPUT}/${theme}-${width}-locked.png`,Buffer.from(shot.data,'base64'));
    }
  }
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await click('Type on screen');await until(`document.querySelector('.touch-keyboard')!==null`);
  for(const digit of ['1','2','3','4','5','6'])await click(digit);
  await click('Unlock settings');await until(`document.body.innerText.includes('Your space.')`);
  const keyStorage=await value(`({local:Object.keys(localStorage),session:Object.keys(sessionStorage),cookie:document.cookie})`);
  assert.ok(!keyStorage.cookie.includes('luma_primary_admin'),'Admin cookie must be HttpOnly');
  assert.ok(!JSON.stringify(keyStorage).includes('123456'),'No PIN in browser storage');
  await click('Confirm PIN');await until(`document.querySelector('[role="dialog"]')!==null`);
  await click('Cancel');await until(`document.querySelector('[role="dialog"]')===null`);
  assert.ok((await value('document.body.innerText')).includes('Your space.'));
  await value(`fetch('/qa/expire',{method:'POST'}).then(r=>r.json())`);
  await until(`document.querySelector('.primary-admin-prompt')!==null&&!document.body.innerText.includes('Your space.')`);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Disposable Chromium/storage/PIN; no Pi workers or accounts',themes:3,sizes:[1024,2048],touchKeypadUnlock:true,httponlyCookie:true,pinNotStored:true,confirmationPreservesPanel:true,expiryLocksPanel:true,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
