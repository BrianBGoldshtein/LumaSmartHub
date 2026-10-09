// Render the real wall app; this is not an actual phone/radio/speaker test.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const target=await(await fetch(debug+'/json/new?about:blank',{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[];let id=0;
socket.onmessage=event=>{const row=JSON.parse(event.data);
  if(row.method==='Runtime.exceptionThrown')errors.push(row.params.exceptionDetails.text);
  const wait=pending.get(row.id);if(!wait)return;pending.delete(row.id);row.error?wait.reject(Error(JSON.stringify(row.error))):wait.resolve(row.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const seq=++id;pending.set(seq,{resolve,reject});socket.send(JSON.stringify({id:seq,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function waitFor(expression){const deadline=Date.now()+10000;while(!(await value(expression))){
  if(Date.now()>=deadline)throw Error('Timed out: '+expression);
  await new Promise(resolve=>setTimeout(resolve,40));}}
const reports=[];
try{
  await send('Page.enable');await send('Runtime.enable');
  for(const theme of ['luma-glass','hearth','neon-grid'])for(const [width,height] of [[390,844],[1024,768],[2048,1536]])for(const arrival of ['Brian','mixed','leave','all','A very long forty-character user name']){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:base+'/?'+new URLSearchParams({demo:'1',theme,arrival,privacy:'1',hold:'1'})});
    await waitFor(`document.querySelector('.presence-transition')!==null`);
    await value('document.fonts.ready');
    const layout=await value(`(()=>{const box=document.querySelector('.presence-transition').getBoundingClientRect();
      const texts=[...document.querySelectorAll('.presence-transition-group h1,.presence-transition-group p')].map(node=>{
        const rect=node.getBoundingClientRect();return {text:node.textContent,x:rect.x,y:rect.y,right:rect.right,bottom:rect.bottom,font:getComputedStyle(node).fontFamily,color:getComputedStyle(node).color};});
      return {width:box.width,height:box.height,texts,overflow:document.documentElement.scrollWidth>innerWidth};})()`);
    assert.equal(layout.width,width);assert.equal(layout.height,height);assert.equal(layout.overflow,false);
    for(const row of layout.texts){assert.ok(row.x>=0&&row.right<=width&&row.y>=0&&row.bottom<=height,JSON.stringify({theme,width,arrival,row}));
      if(theme==='hearth'&&row.text.includes('Brian'))assert.ok(row.font.includes('Newsreader'));
      if(theme==='neon-grid')assert.ok(row.font.includes('Pixelify'));}
    const label=`${theme}-${width}-${['mixed','leave','all'].includes(arrival)?arrival:arrival==='Brian'?'arrival':'long'}`;
    const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await fs.writeFile(`${process.env.USER_QA_OUTPUT}/${label}.png`,Buffer.from(shot.data,'base64'));
    reports.push({label,...layout});
  }
  await waitFor(`document.querySelector('.presence-transition')===null`);
  await new Promise(resolve=>setTimeout(resolve,1000));
  assert.equal(await value(`document.querySelector('.presence-transition')===null`),true);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({cases:reports.length,localExpiryPassed:true,errors,reports},null,2));
}finally{socket.close();}
