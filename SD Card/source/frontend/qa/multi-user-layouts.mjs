// Synthetic public demo fixtures; no owner accounts, radio or device writes.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const base='http://127.0.0.1:18833',debug='http://127.0.0.1:19228';
const target=await(await fetch(debug+'/json/new?about:blank',{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map(),errors=[],reports=[];let id=0;
socket.onmessage=event=>{const data=JSON.parse(event.data);
  if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails.text);
  const item=pending.get(data.id);if(!item)return;pending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result);};
const send=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});
async function value(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;}
async function until(expression){const end=Date.now()+15000;while(!(await value(expression))){if(Date.now()>end)throw Error('Timed out: '+expression);await new Promise(r=>setTimeout(r,40));}}
try{
  await send('Page.enable');await send('Runtime.enable');
  // Daytime fixtures must contain actual timed appointments even when this
  // lab runs at night. This changes only the disposable demo document clock.
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`{const OriginalDate=Date,now=Date.parse('2026-10-08T16:10:00Z');window.Date=class extends OriginalDate{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};}`});
  for(const [width,height] of [[1024,768],[2048,1536]])for(const theme of ['luma-glass','hearth','neon-grid'])for(let count=1;count<=5;count++)for(const [page,fixture] of [['home','long'],['agenda','short'],['agenda','crowded'],['todos','many-todos'],['agenda','empty']]){
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
    await send('Page.navigate',{url:`${base}/?demo=1&hold=1&theme=${theme}&users=${count}&page=${page}&fixture=${fixture}`});
    await until(`document.querySelectorAll('.user-panel').length===${count}&&document.fonts.status==='loaded'`);
    await value('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    if(page==='agenda'&&fixture!=='empty'){
      // An explicit all-day overview is allowed to precede timed sections.
      // Qualify an actual timed section rather than declaring that overview
      // to be coverage of short appointments or crowded overlap columns.
      for(let section=0;section<20&&!await value(`document.querySelector('.user-appointment')!==null`);section++){
        if(!await value(`document.querySelector('[aria-label="Next shared section"]')!==null`))break;
        await value(`document.querySelector('[aria-label="Next shared section"]').click()`);
        await new Promise(r=>setTimeout(r,70));
      }
    }
    const report=await value(`(()=>({overflow:document.documentElement.scrollWidth>innerWidth,
      panels:[...document.querySelectorAll('.user-panel')].map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};}),
      appointments:[...document.querySelectorAll('.user-appointment')].map(e=>{const r=e.getBoundingClientRect(),s=e.querySelector('strong');return {height:r.height,titleHeight:s.getBoundingClientRect().height,font:parseFloat(getComputedStyle(s).fontSize)};}),
      tracks:[...document.querySelectorAll('.user-appointments')].map(e=>({width:e.clientWidth,scroll:e.scrollWidth})),
      font:getComputedStyle(document.querySelector('.user-panel h2')).fontFamily}))()`);
    assert.equal(report.overflow,false,`${theme}/${count}/${page}/${width}: page overflow`);
    if(page==='agenda'&&fixture!=='empty')assert.ok(report.appointments.length>0,`${fixture}: timed appointments must be exercised`);
    assert.ok(report.tracks.every(t=>t.scroll<=t.width+1),`${theme}/${count}/${fixture}: overlapping events require scrolling ${JSON.stringify(report.tracks)}`);
    assert.ok(report.panels.every(r=>r.x>=-1&&r.right<=width+1&&r.y>=-1&&r.bottom<=height+1),`${theme}/${count}/${page}/${width}: panel beyond screen`);
    reports.push({width,theme,count,page,fixture,...report});
    if(count===5&&width===2048&&fixture!=='empty'){
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
      await fs.writeFile(`${process.env.USER_QA_OUTPUT}/multi-${theme}-${page}-${fixture}.png`,Buffer.from(shot.data,'base64'));
    }
    if(page==='home'&&count===5){
      await value(`document.querySelector('.user-next-event')?.click()`);
      if(await value(`document.querySelector('.agenda-detail')!==null`)){
        const box=await value(`(()=>{const r=document.querySelector('.agenda-detail').getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom};})()`);
        assert.ok(box.x>=0&&box.y>=0&&box.right<=width&&box.bottom<=height,'Event dialog overflow');
        await value(`document.querySelector('[aria-label="Close event details"]').click()`);
      }
    }
  }
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`{const OriginalDate=Date,now=Date.parse('2026-10-08T18:59:00Z');window.Date=class extends OriginalDate{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}};}`});
  for(const theme of ['luma-glass','hearth','neon-grid'])for(const width of [320,390])for(const privacy of [false,true]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:844,deviceScaleFactor:1,mobile:true});
    await send('Page.navigate',{url:`${base}/?demo=1&hold=1&theme=${theme}&page=home${privacy?'&privacy=1':''}`});
    await until(`document.querySelector('.clock-time')!==null&&document.fonts.status==='loaded'`);
    await value('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
    const clock=await value(`(()=>{const row=document.querySelector('.clock-time'),r=row.parentElement.getBoundingClientRect(),period=row.querySelector('small').getBoundingClientRect(),digits=row.querySelector('span').getBoundingClientRect();return {available:r.right,right:Math.max(period.right,digits.right),font:parseFloat(getComputedStyle(row).fontSize)};})()`);
    assert.ok(clock.right<=clock.available+1&&clock.right<=width,`${theme}/${width}: clipped mobile clock`);
    reports.push({theme,width,privacy,clock});
    if(theme==='neon-grid'&&width===390&&!privacy){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(`${process.env.USER_QA_OUTPUT}/neon-mobile-clock.png`,Buffer.from(shot.data,'base64'));}
  }
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Synthetic demo layout QA, not hardware acceptance',cases:reports.length,errors,reports},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
