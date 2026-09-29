// Manual synthetic browser acceptance. Requires scene_preview.py on :8751 and
// disposable Chrome CDP on :9224. Never contacts physical devices.
const base='http://127.0.0.1:8751/',devtools='http://127.0.0.1:9224';
async function api(path,method='GET',body){
  const response=await fetch(base+path,{method,headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw Error(`${path}: ${response.status} ${JSON.stringify(value)}`);return value;
}
async function browser(query='?setup=extras'){
  const target=await (await fetch(`${devtools}/json/new?${encodeURIComponent(base+query)}`,{method:'PUT'})).json();
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let sequence=0;const pending=new Map();
  socket.onmessage=event=>{const packet=JSON.parse(event.data),wait=pending.get(packet.id);if(!wait)return;pending.delete(packet.id);packet.error?wait.reject(Error(JSON.stringify(packet.error))):wait.resolve(packet.result);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;};
  const until=async(expression,timeout=12000)=>{const start=Date.now();while(Date.now()-start<timeout){const value=await evaluate(expression);if(value)return value;await new Promise(resolve=>setTimeout(resolve,100));}throw Error(`Timeout: ${expression}`);};
  const tap=async expression=>{const point=await evaluate(`(()=>{const element=${expression};if(!element||element.disabled)return null;element.scrollIntoView({block:'center'});const rect=element.getBoundingClientRect();return{x:rect.x+rect.width/2,y:rect.y+rect.height/2}})()`);if(!point)throw Error(`Missing enabled target: ${expression}`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,x:point.x,y:point.y,button:'left',clickCount:1});};
  const click=label=>tap(`[...document.querySelectorAll('button')].find(item=>item.textContent.trim().includes(${JSON.stringify(label)}))`);
  const key=async(value,shift=false)=>{const code=value==='Tab'?'Tab':'Escape',number=value==='Tab'?9:27,params={key:value,code,windowsVirtualKeyCode:number,nativeVirtualKeyCode:number,modifiers:shift?8:0};await send('Input.dispatchKeyEvent',{type:'rawKeyDown',...params});await send('Input.dispatchKeyEvent',{type:'keyUp',...params});};
  const insert=async text=>send('Input.insertText',{text});
  await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:base+query});
  await until("document.querySelectorAll('.extras-choices button').length>=9");
  return{evaluate,until,tap,click,key,insert,close:async()=>{socket.close();await fetch(`${devtools}/json/close/${target.id}`);}};
}

const initial=await api('api/v1/scenes');
const action=initial.devices.find(device=>device.id==='fan_1')?.actions.find(item=>item.action==='power_on');
if(!action)throw Error('Synthetic fan capability is missing');
const {label:_,...savedAction}=action;
await api('api/v1/scenes/night','PUT',{revision:initial.revision,enabled:true,automatic:false,actions:[savedAction]});
const checks=[];
for(const theme of ['hearth','luma-glass','neon-grid']){
  await api('api/v1/settings','PATCH',{theme});const tab=await browser();
  try{
    await tab.click('Room scenes');await tab.until("document.querySelector('.private-scene-policy')?.innerText.includes('Night')");
    await tab.tap("[...document.querySelectorAll('.private-scene-policy label')].find(item=>item.textContent.includes('Night'))?.querySelector('input')");
    await tab.until("document.querySelector('.private-scene-policy')?.innerText.includes('Discard permission edits')");
    const protectedEdits=await tab.evaluate("(()=>({note:document.querySelector('.room-setup [role=status]')?.textContent.includes('Save or discard'),night:[...document.querySelectorAll('.scene-cards button')].find(item=>item.textContent.includes('Night'))?.disabled,refresh:[...document.querySelectorAll('.room-setup button')].find(item=>item.textContent.includes('Refresh devices'))?.disabled}))()");
    if(!protectedEdits.note||!protectedEdits.night||!protectedEdits.refresh)throw Error(`${theme}: remote edits can be lost`);
    await tab.click('Discard permission edits');await tab.click('Night');
    await tab.until("document.querySelector('.scene-actions')?.textContent.includes('On')");
    await tab.tap("document.querySelector('[aria-label=\"Remove action 1\"]')");await tab.click('All scenes');
    await tab.until("document.querySelector('[role=alertdialog]')?.textContent.includes('Discard these unsaved edits')");
    const safeFocus=await tab.evaluate("document.activeElement?.textContent.includes('Keep reviewing')");
    await tab.key('Tab');
    const wrappedForward=await tab.evaluate("document.activeElement?.textContent.includes('Discard edits')");
    await tab.key('Tab',true);
    const wrappedBack=await tab.evaluate("document.activeElement?.textContent.includes('Keep reviewing')");
    if(!safeFocus||!wrappedForward||!wrappedBack)throw Error(`${theme}: confirmation keyboard focus escaped or defaulted to destructive action`);
    await tab.key('Escape');
    await tab.until("!document.querySelector('[role=alertdialog]')");
    await tab.click('All scenes');
    await tab.click('Keep reviewing');
    if(!await tab.evaluate("document.querySelector('.room-setup')?.textContent.includes('Choose actions')"))throw Error(`${theme}: scene draft was lost`);
    await tab.click('All scenes');await tab.click('Discard edits');await tab.until("!!document.querySelector('.scene-cards')");
    const fit=await tab.evaluate("({body:document.body.scrollWidth,viewport:innerWidth})");
    if(fit.body>fit.viewport)throw Error(`${theme}: horizontal overflow`);
    checks.push({theme,protectedEdits,keyboard:{safeFocus,wrappedForward,wrappedBack,escape:true},fit});
  }finally{await tab.close();}
}

await api('_qa/control','POST',{mode:'hold'});const tab=await browser();
try{
  await tab.click('Room scenes');await tab.until("[...document.querySelectorAll('.scene-cards button')].some(item=>item.textContent.includes('Night')&&!item.disabled)");
  await tab.click('Night');await tab.click('Run saved scene once');await tab.click('Run once');
  const start=Date.now();while((await api('_qa/status')).dispatches<1&&Date.now()-start<12000)await new Promise(resolve=>setTimeout(resolve,100));
  if((await api('_qa/status')).dispatches!==1)throw Error('Synthetic scene never dispatched');
  await tab.until("[...document.querySelectorAll('.room-setup button')].some(item=>item.textContent.includes('Stop scene'))");
  await tab.click('Stop scene');await tab.until("document.querySelector('.scene-result')?.textContent.includes('Interrupted')");
  const durable=await api('_qa/reopen'),view=await api('api/v1/scenes'),status=await api('_qa/status');
  if(status.dispatches!==1||durable.runs.at(-1)?.finished!==false||view.runs.at(-1)?.interrupted!==true)throw Error('Stopped scene replayed or lacked durable interrupted result');
  checks.push({cancellation:{dispatches:status.dispatches,durableUnfinished:!durable.runs.at(-1).finished,interrupted:view.runs.at(-1).interrupted,ui:await tab.evaluate("document.querySelector('.scene-result')?.textContent.includes('Interrupted')")}});
}finally{await api('_qa/control','POST',{mode:'release'});await tab.close();}

const beforeLock=await api('api/v1/scenes');
await api('api/v1/scenes/morning','PUT',{revision:beforeLock.revision,enabled:true,automatic:false,actions:[savedAction]});
await api('_qa/control','POST',{mode:'hold'});
const privacyTab=await browser();
try{
  await privacyTab.click('Room scenes');
  await privacyTab.until("[...document.querySelectorAll('.scene-cards button')].some(item=>item.textContent.includes('Morning')&&!item.disabled)");
  await privacyTab.click('Morning');await privacyTab.click('Run saved scene once');await privacyTab.click('Run once');
  const started=Date.now();while((await api('_qa/status')).dispatches<2&&Date.now()-started<12000)await new Promise(resolve=>setTimeout(resolve,100));
  if((await api('_qa/status')).dispatches!==2)throw Error('Privacy test did not reach its held dispatch');
  const locked=await api('_qa/control','POST',{locked:true});
  if(!locked.privacy_redacted)throw Error('Synthetic lock did not redact privacy');
  await privacyTab.until("document.body.innerText.includes('Unlock with your nearby phone or PIN to configure scenes')");
  const redacted=await privacyTab.evaluate("!document.querySelector('.room-setup')&&!document.body.innerText.includes('Private iPhone actions')");
  if(!redacted)throw Error('Private scene editor remained visible after lock');
  const wait=Date.now();let lockedRun;
  while(Date.now()-wait<12000){lockedRun=(await api('_qa/reopen')).runs.at(-1);if(lockedRun?.scene==='morning'&&!lockedRun.finished)break;await new Promise(resolve=>setTimeout(resolve,100));}
  if(lockedRun?.scene!=='morning'||lockedRun.finished)throw Error('Privacy lock did not interrupt the durable scene run');
  await api('_qa/control','POST',{mode:'release'});
  await api('_qa/control','POST',{locked:false});
  await privacyTab.until("document.querySelector('.scene-result')?.textContent.includes('Interrupted')");
  const final=await api('_qa/status');
  if(final.dispatches!==2)throw Error('Privacy unlock replayed a scene action');
  checks.push({privacy:{redacted,interrupted:!lockedRun.finished,dispatches:final.dispatches}});
}finally{await api('_qa/control','POST',{mode:'release'});await privacyTab.close();}

for(const theme of ['hearth','luma-glass','neon-grid']){
  const fanTab=await browser(`?demo=1&setup=extras&theme=${theme}`);
  try{
    await fanTab.click('Two fans');await fanTab.click('Set up fan');await fanTab.click('Discover USB adapters');
    await fanTab.until("document.querySelector('.fan-setup .room-options')?.textContent.includes('Sample USB IR adapter')");
    await fanTab.tap("document.querySelector('.fan-setup .room-options button')");await fanTab.click('Fan overview');
    await fanTab.until("!!document.querySelector('.fan-setup [role=alertdialog]')");
    const safe=await fanTab.evaluate("document.activeElement?.textContent.includes('Keep working')");
    await fanTab.key('Tab');const forward=await fanTab.evaluate("document.activeElement?.textContent.includes('Discard and leave')");
    await fanTab.key('Tab',true);const back=await fanTab.evaluate("document.activeElement?.textContent.includes('Keep working')");
    await fanTab.key('Escape');await fanTab.until("!document.querySelector('.fan-setup [role=alertdialog]')");
    const retained=await fanTab.evaluate("document.querySelector('.fan-setup .room-options button[aria-pressed=true]')!==null");
    await fanTab.click('Fan overview');await fanTab.click('Discard and leave');
    await fanTab.until("!!document.querySelector('.fan-setup .fan-cards')");
    const fit=await fanTab.evaluate('document.body.scrollWidth<=innerWidth');
    if(!safe||!forward||!back||!retained||!fit)throw Error(`${theme}: fan draft, keyboard or narrow layout failed`);
    checks.push({fanKeyboard:{theme,safeFocus:safe,forward,back,escape:true,retained,fit}});
  }finally{await fanTab.close();}

  const roomTab=await browser(`?demo=1&setup=extras&theme=${theme}`);
  try{
    await roomTab.click('Air purifier');await roomTab.click('Connect VeSync');
    await roomTab.tap("document.querySelector('.room-setup .extras-toggle input')");
    await roomTab.click('Continue to local sign-in');
    await roomTab.tap("document.querySelector('.room-setup input[type=text]')");await roomTab.insert('qa@example.invalid');
    await roomTab.click('Back to room devices');
    await roomTab.until("!!document.querySelector('.room-setup [role=alertdialog]')");
    const safe=await roomTab.evaluate("document.activeElement?.textContent.includes('Keep current settings')");
    await roomTab.key('Tab');const forward=await roomTab.evaluate("document.activeElement?.textContent.includes('Discard changes')");
    await roomTab.key('Tab',true);const back=await roomTab.evaluate("document.activeElement?.textContent.includes('Keep current settings')");
    await roomTab.key('Escape');await roomTab.until("!document.querySelector('.room-setup [role=alertdialog]')");
    const retained=await roomTab.evaluate("[...document.querySelectorAll('.room-setup input[type=text]')].some(item=>item.value==='qa@example.invalid')");
    await roomTab.click('Back to room devices');await roomTab.click('Discard changes');
    await roomTab.until("document.querySelector('.room-setup .room-device-card')!==null");
    const fit=await roomTab.evaluate('document.body.scrollWidth<=innerWidth');
    if(!safe||!forward||!back||!retained||!fit)throw Error(`${theme}: purifier draft, keyboard or narrow layout failed`);
    checks.push({purifierKeyboard:{theme,safeFocus:safe,forward,back,escape:true,retained,fit}});
  }finally{await roomTab.close();}
}
console.log(JSON.stringify({checks},null,2));
