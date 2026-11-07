// Actual signed remotes, synthetic live phone authority; never an owner's Pi.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='https://luma.example-tail.ts.net',debug='http://127.0.0.1:19226';
const target=await(await fetch(debug+'/json/new?'+encodeURIComponent(base+'/remote/'),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
let id=0;const pending=new Map(),errors=[],reports=[];
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
socket.onmessage=e=>{const v=JSON.parse(e.data);if(v.method==='Runtime.exceptionThrown')errors.push(v.params.exceptionDetails.text);
  const p=pending.get(v.id);if(p){pending.delete(v.id);v.error?p.reject(Error(JSON.stringify(v.error))):p.resolve(v.result);}};
async function value(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description??r.exceptionDetails.text);return r.result.value;}
async function until(expression){const end=Date.now()+25000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression+'\n'+await value('document.body.innerText'));await new Promise(r=>setTimeout(r,80));}}
async function click(text){await until(`[...document.querySelectorAll('button')].some(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled)`);
  await value(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)}&&!b.disabled).click()`);}
async function roster(count){await value(`fetch('/qa/roster',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({count:${count}})}).then(r=>r.json())`);}
try{
  await send('Page.enable');await send('Runtime.enable');
  for(const role of ['primary','secondary']){
    const ticket=role==='primary'?'/qa/ticket':'/qa/guest-ticket';
    const url=await value(`fetch('${ticket}').then(r=>r.json()).then(v=>v.url)`);
    // Another phone/Serve identity starts a fresh document, not the old
    // identity digest retained by a same-document enrollment fragment.
    await send('Page.navigate',{url:'about:blank'});
    await send('Page.navigate',{url});
    await click('Enroll this browser');await until("document.body.innerText.includes('Approval code:')");
    await value("fetch('/qa/approve').then(r=>r.json())");await until("document.querySelector('.hero')!==null");
    await roster(4);await until("document.querySelectorAll('.connected-users li').length===5");
    for(const theme of ['luma-glass','hearth','neon-grid']){
      await value(`fetch('/qa/theme',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({theme:${JSON.stringify(theme)}})}).then(r=>r.json())`);
      await until(`document.querySelector('.theme-${theme}')!==null`);
      for(const width of [320,390,1024]){
        await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:width<700});
        await value('document.fonts.ready');await value('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
        const layout=await value(`(()=>{const box=document.querySelector('.connected-users'),r=box.getBoundingClientRect();return {width:innerWidth,scroll:document.documentElement.scrollWidth,count:box.querySelectorAll('li').length,text:box.innerText,cards:[...box.querySelectorAll('li')].map(n=>{const b=n.getBoundingClientRect();return {left:b.left,right:b.right};}),left:r.left,right:r.right};})()`);
        assert.equal(layout.count,5);assert.ok(layout.scroll<=width+1&&layout.left>=0&&layout.right<=width);
        assert.ok(layout.cards.every(c=>c.left>=0&&c.right<=width));
        assert.ok(layout.text.includes('Alexandria Bell-Robinson')&&layout.text.includes('Renée')&&layout.text.includes('You'));
        if(width===390){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/roster-${role}-${theme}.png`,Buffer.from(shot.data,'base64'));}
        reports.push({role,theme,...layout});
      }
    }
    for(const page of role==='primary'?['My calendars','Settings','Software','Hub']:['My calendars','Hub']){
      await click(page);assert.equal(await value("document.querySelectorAll('.connected-users li').length"),5);
    }
    await roster(1);await until("document.querySelectorAll('.connected-users li').length===2");
    assert.equal(await value("document.querySelector('.connected-users').innerText.includes('Renée')"),false);
    if(role==='primary'){
      await value("fetch('/qa/disconnect').then(r=>r.json())");await until("document.querySelector('.connected-users')===null");
      await value("fetch('/qa/reconnect').then(r=>r.json())");await until("document.querySelector('.hero')!==null");
    }else{
      await value("fetch('/qa/disconnect').then(r=>r.json())");await until("document.querySelectorAll('.connected-users li').length===1");
      assert.ok(!(await value("document.querySelector('.connected-users').innerText")).includes('Primary'));
    }
  }
  await value("fetch('/qa/revoke').then(r=>r.json())");await until("document.querySelector('.connected-users')===null");
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Synthetic phones, actual signed primary/secondary remote UI',reports,liveDisconnect:true,secondaryOnly:true,allPages:true,revocationClears:true,errors},null,2));
}catch(e){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.REMOTE_QA_OUTPUT}/roster-failure.png`,Buffer.from(shot.data,'base64'));throw e;}
finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
