// Headless, disposable browser and loopback-only synthetic API. Never connects
// to an owner's browser/Pi/Google account and never runs an actual installer.
import assert from 'node:assert/strict';
const base='http://127.0.0.1:18874',debug='http://127.0.0.1:19224';
async function control(body){const r=await fetch(base+'/_qa/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});assert.equal(r.status,200);}
const target=await (await fetch(debug+'/json/new?'+encodeURIComponent(base+'/?setup=google'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map();let sequence=0;
socket.onmessage=event=>{const packet=JSON.parse(event.data),wait=pending.get(packet.id);if(!wait)return;pending.delete(packet.id);packet.error?wait.reject(Error(JSON.stringify(packet.error))):wait.resolve(packet.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+15000;while(Date.now()<end){if(await value(expression))return;await new Promise(resolve=>setTimeout(resolve,100));}throw Error('UI condition timed out: '+expression);}
async function go(query){await send('Page.navigate',{url:base+'/?'+query});}
async function click(label){const expression=`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)})`;await until(`!!(${expression})&&!(${expression}).disabled`);await value(`(${expression}).click()`);}
const checks=[];
try{
  await send('Page.enable');await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  for(const theme of ['hearth','luma-glass','neon-grid']){
    await control({settings_failed:false});await go(`setup=google&theme=${theme}`);
    await until("document.body.innerText.includes('Calendar editing is paused')");
    assert.ok(await value("[...document.querySelectorAll('button')].some(b=>b.textContent==='Reconnect Google'&&!b.disabled)"));
    assert.ok(await value("![...document.querySelectorAll('button')].some(b=>b.textContent==='Save calendars')"));
    await click('Reconnect Google');await until("document.body.innerText.includes('Synthetic Google consent reached')");
    await control({settings_failed:true});await go(`setup=google&theme=${theme}`);
    await until("document.body.innerText.includes('Could not load saved Google settings')");
    assert.ok(await value(`!!document.querySelector('.app.theme-${theme} .setup-content')`));
    assert.ok(await value("document.body.scrollWidth<=innerWidth"));
    await control({settings_failed:false});await click('Reload Google setup');
    await until("new URL(location.href).searchParams.has('ui_refresh')&&document.body.innerText.includes('Reconnect Google')");
    checks.push({theme,reconnect_after_rejection:true,themed_local_error:true,fresh_reload:true});
  }
  for(const failed of [true,false]){
    await control({settings_failed:false,state:'idle',version:'0.2.10',update_failed:failed});
    await go('setup=device&section=connect');
    await until("document.body.innerText.includes('Luma software')");
    await click('Check for updates');await click('Review complete · Install update');
    if(failed){await until("document.body.innerText.includes('The update failed')");assert.equal(await value("new URL(location.href).searchParams.has('ui_release')"),false);}
    else{await until("new URL(location.href).searchParams.get('ui_release')==='0.2.11'");assert.equal(await value("new URL(location.href).searchParams.get('setup')"),'device');assert.ok(await value("new URL(location.href).searchParams.has('ui_refresh')"));}
    checks.push({update_failed:failed,navigation_verified:true});
  }
  console.log(JSON.stringify({scope:'Disposable desktop browser, synthetic loopback API; not owner Pi acceptance',checks},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
