// Disposable wall fixture, synthetic CPU sensor, never the owner's Pi.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/?setup=device'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let id=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);const wait=pending.get(row.id);if(!wait)return;pending.delete(row.id);row.error?wait.reject(Error(JSON.stringify(row.error))):wait.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const seq=++id;pending.set(seq,{resolve,reject});socket.send(JSON.stringify({id:seq,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const deadline=Date.now()+20000;while(!await value(expression)){if(Date.now()>deadline)throw Error('Timed out '+expression+' '+await value('document.body.innerText'));await new Promise(r=>setTimeout(r,100));}}
async function click(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
try{
  await send('Page.enable');await send('Runtime.enable');await send('Page.bringToFront');
  await send('Emulation.setDeviceMetricsOverride',{width:1024,height:768,deviceScaleFactor:1,mobile:false});
  await until(`document.body.innerText.includes('Primary settings')`);await click('Type on screen');
  for(const digit of ['1','2','3','4','5','6'])await click(digit);
  await click('Unlock settings');await until(`document.querySelector('.temperature-readout')?.textContent.includes('56.5°C')`);
  const states=[];
  for(const [state,text] of [['warm','74.0°C'],['hot','82.0°C'],['unavailable','Sensor unavailable'],['normal','56.5°C']]){
    await value(`fetch('/qa/temperature',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state:${JSON.stringify(state)}})})`);
    await until(`document.querySelector('.temperature-readout')?.textContent.includes(${JSON.stringify(text)})`);
    assert.equal(await value(`document.querySelector('.temperature-readout').classList.contains('temperature-${state}')`),true);states.push(state);
  }
  const layouts=[];
  for(const theme of ['luma-glass','hearth','neon-grid']){
    await send('Page.navigate',{url:base+'/?setup=device&demo=1&theme='+theme});
    await until(`document.querySelector('.temperature-readout')?.textContent.includes('56.5°C')`);
    assert.ok(await value(`document.querySelector('.temperature-readout').textContent.includes('Example')`));
    assert.ok(await value(`document.documentElement.scrollWidth<=innerWidth`),'Wall overflow');
    const metrics=await value(`(()=>{const e=document.querySelector('.temperature-readout'),r=e.getBoundingClientRect();return {left:r.left,right:r.right,font:getComputedStyle(e.querySelector('strong')).fontFamily};})()`);
    assert.ok(metrics.left>=0&&metrics.right<=1024);layouts.push({theme,...metrics});
    await value(`document.querySelector('.temperature-readout').scrollIntoView({block:'center'})`);
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.USER_QA_OUTPUT}/temperature-${theme}.png`,Buffer.from(shot.data,'base64'));
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Synthetic sensor, Chromium not Pi hardware',states,layouts,exampleLabeled:true,errors},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
