// Disposable browser only. Inject non-secret update states, never install.
import assert from 'node:assert/strict';
const debug='http://127.0.0.1:19228',base='http://127.0.0.1:18833';
const target=await(await fetch(debug+'/json/new?about:blank',{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let id=0;const pending=new Map();
socket.onmessage=event=>{const data=JSON.parse(event.data),item=pending.get(data.id);if(!item)return;pending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+20000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression);await new Promise(r=>setTimeout(r,80));}}
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`{
    const original=window.fetch;
    window.syntheticUpdate={current_version:'0.3.1',state:'idle'};
    window.fetch=(input,init)=>String(input)==='/api/v1/updates/status'
      ?Promise.resolve(new Response(JSON.stringify(window.syntheticUpdate),{headers:{'Content-Type':'application/json'}}))
      :original(input,init);
  }`});
  for(const mode of ['day','night-clock','off']){
    await fetch(base+'/qa/display-mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})});
    await send('Page.navigate',{url:base+'/'});
    await until(mode==='night-clock'?`document.querySelector('.night-clock')!==null`:mode==='off'?`document.querySelector('.sleep-screen')!==null`:`document.querySelector('.home-page,.privacy-page')!==null`);
    await value(`window.syntheticUpdate={current_version:'0.3.1',state:'installing',phase:'copying',target_version:'0.3.2'}`);
    await until(`document.querySelector('.wall-update-progress')!==null`);
    assert.equal(await value(`getComputedStyle(document.body).opacity`),'1',mode+': update must remain readable');
    await value(`window.syntheticUpdate={current_version:'0.3.1',state:'failed'}`);
    await until(`document.querySelector('.wall-update-progress')===null`);
    if(mode!=='day')assert.ok(Number(await value(`getComputedStyle(document.body).opacity`))<.05,'Night dimming must return');
  }
  await fetch(base+'/qa/display-mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'day'})});
  // No demo parameter: exercise the always-mounted production observer while
  // the disposable server supplies synthetic onboarding/settings state.
  await send('Page.navigate',{url:base+'/?setup=onboarding'});
  await until(`document.querySelector('.app')!==null`);
  await value(`window.syntheticUpdate={current_version:'0.3.1',state:'installing',phase:'copying',target_version:'0.3.2',elapsed_seconds:12}`);
  await until(`document.querySelector('[aria-label="Software update in progress"]')!==null`);
  assert.match(await value(`document.querySelector('[aria-label="Software update in progress"]').textContent`),/Updating to 0.3.2/);
  // Temporary API loss must retain the last valid progress, not reveal UI.
  await value(`window.syntheticUpdate=null`);
  await new Promise(r=>setTimeout(r,1700));
  assert.ok(await value(`document.querySelector('[aria-label="Software update in progress"]')!==null`));
  await value(`window.syntheticUpdate={current_version:'0.3.1',state:'failed',message:'Previous release restored'}`);
  await until(`document.querySelector('[aria-label="Software update in progress"]')===null`);
  await value(`window.syntheticUpdate={current_version:'0.3.1',state:'installing',phase:'checking',target_version:'0.3.2'}`);
  await until(`document.querySelector('[aria-label="Software update in progress"]')!==null`);
  await value(`window.syntheticUpdate={current_version:'0.3.2',state:'installed',phase:'complete',target_version:'0.3.2'}`);
  await until(`document.querySelector('[aria-label="Software update in progress"]').textContent.includes('Update verified')`);
  await until(`new URL(location.href).searchParams.get('ui_release')==='0.3.2'`);
  console.log(JSON.stringify({passed:true,scope:'Mocked progress only; no install or hardware reboot',checks:['external update during normal, night-clock, display-off and setup views','night progress stays readable','progress retained through outage or malformed status','failure dismissal restores the prior view','verified completion','cache-busting dashboard navigation']}));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
