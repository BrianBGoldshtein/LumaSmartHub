// Public demo fixtures only; no owner data, device control or real accounts.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const target=await(await fetch(debug+'/json/new?about:blank',{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let id=0;const pending=new Map(),errors=[],reports=[];
socket.onmessage=event=>{const data=JSON.parse(event.data);if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);const item=pending.get(data.id);if(!item)return;pending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+12000;while(!await value(expression)){if(Date.now()>end)throw Error('Timed out: '+expression);await new Promise(r=>setTimeout(r,40));}}
const cases=[['weather','&fixture=weather-hint'],['countdowns','&fixture=long-dates'],['transit','&fixture=long-transit'],
  ['home','&privacy=1'],['home','&fixture=night'],['home','&arrival=mixed'],['home','&arrival=all'],['home','&voice=choose'],
  ['home','&voice=listening'],...['blocks','snake','rally','breaker','invaders','pendulums','gears','balls','stars','glow','sunset'].map(scene=>['ambient','&scene='+scene])];
try{
  await send('Page.enable');await send('Runtime.enable');
  for(const [width,height] of [[1024,768],[2048,1536]])for(const theme of ['hearth','luma-glass','neon-grid'])for(const [page,extra] of cases){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:`${base}/?demo=1&hold=1&theme=${theme}&page=${page}${extra}`});
    await until(`document.querySelector('.app')!==null&&document.fonts.status==='loaded'`);
    await value('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    const report=await value(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
      heading:getComputedStyle(document.querySelector('.app')).getPropertyValue('--heading'),
      islands:[...document.querySelectorAll('.presence-transition,.voice-account-choice,.island-panel,.timer-panel')].map(e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};}),
      game:document.querySelector('.game-field')?(()=>{const r=document.querySelector('.game-field').getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};})():null}))()`);
    assert.equal(report.overflow,false,`${theme}/${page}/${extra}: horizontal overflow`);
    if(page==='ambient')assert.equal(await value(`document.querySelector('.ambient-visual').dataset.scene`),extra.split('=')[1],'Must audit the requested scene, not a fallback');
    assert.ok(report.islands.every(r=>r.left>=-1&&r.right<=width+1&&r.top>=-1&&r.bottom<=height+1),'Overlay outside screen');
    if(report.game)assert.ok(report.game.left>=-1&&report.game.right<=width+1&&report.game.top>=-1&&report.game.bottom<=height+1,'Game field outside screen');
    reports.push({width,theme,page,extra,...report});
    if(width===1024){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.USER_QA_OUTPUT}/audit-${theme}-${page}-${extra.replaceAll(/[^a-z0-9]/gi,'-')}.png`,Buffer.from(shot.data,'base64'));}
    if(page==='home'&&extra==='&privacy=1'){
      await value(`document.querySelector('.island-handle')?.click()`);
      const panel=await value(`(()=>{const e=document.querySelector('.island-panel');if(!e)return null;const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom};})()`);
      assert.ok(panel&&panel.left>=0&&panel.right<=width&&panel.top>=0&&panel.bottom<=height,'Controls must fit');
      if(width===1024){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.USER_QA_OUTPUT}/audit-${theme}-controls.png`,Buffer.from(shot.data,'base64'));}
    }
  }
  assert.deepEqual(errors,[]);console.log(JSON.stringify({scope:'Rendered synthetic themes, not hardware acceptance',cases:reports.length,errors,reports},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
