// Real browser against room_preview.py's temporary SQLite and fake VeSync HTTP.
// No real account, network appliance or physical device is touched.
const base='http://127.0.0.1:8750/',devtools='http://127.0.0.1:9224';
async function api(path,body){
  const response=await fetch(base+path,{method:body===undefined?'GET':'POST',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(`${path}: ${response.status} ${JSON.stringify(data)}`);return data;
}
async function browser(){
  const target=await (await fetch(`${devtools}/json/new?${encodeURIComponent(base+'?setup=extras')}`,{method:'PUT'})).json();
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  let sequence=0;const pending=new Map();
  socket.onmessage=event=>{const packet=JSON.parse(event.data),wait=pending.get(packet.id);if(!wait)return;pending.delete(packet.id);packet.error?wait.reject(Error(JSON.stringify(packet.error))):wait.resolve(packet.result);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.text);return result.result.value;};
  const until=async(expression,timeout=12000)=>{const start=Date.now();while(Date.now()-start<timeout){const value=await evaluate(expression);if(value)return value;await new Promise(resolve=>setTimeout(resolve,100));}throw Error(`Timeout: ${expression}`);};
  const tap=async expression=>{const point=await evaluate(`(()=>{const element=${expression};if(!element||element.disabled)return null;element.scrollIntoView({block:'center'});const rect=element.getBoundingClientRect();return{x:rect.x+rect.width/2,y:rect.y+rect.height/2}})()`);if(!point)throw Error(`Missing enabled target: ${expression}`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,x:point.x,y:point.y,button:'left',clickCount:1});};
  const click=async label=>{const expression=`[...document.querySelectorAll('button')].find(item=>item.textContent.trim().includes(${JSON.stringify(label)}))`;await until(`!!(${expression}&&!(${expression}).disabled)`);await tap(expression);};
  await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:base+'?setup=extras'});
  await until("document.querySelectorAll('.extras-choices button').length>=9");
  return{evaluate,until,tap,click,insert:async text=>send('Input.insertText',{text}),close:async()=>{socket.close();await fetch(`${devtools}/json/close/${target.id}`);}};
}

await api('_qa/control',{mode:'normal',reset_slots:true,locked:false,theme:'hearth'});
const setup=await browser();
try{
  await setup.click('Air purifier');await setup.click('Connect VeSync');
  await setup.tap("document.querySelector('.room-setup .extras-toggle input')");
  await setup.click('Continue to local sign-in');
  await setup.tap("document.querySelector('.room-setup input[type=text]')");await setup.insert('qa@example.invalid');
  await setup.tap("document.querySelector('.room-setup input[type=password]')");await setup.insert('synthetic-password-only');
  await setup.click('Connect account');
  await setup.until("document.querySelector('.room-setup')?.textContent.includes('VeSync session saved')");
  const paced=await setup.evaluate("(()=>{const button=[...document.querySelectorAll('.room-setup button')].find(item=>item.textContent.includes('Find my purifier'));return !!button?.disabled&&/in [1-6]s/.test(button.textContent)})()");
  if(!paced)throw Error('Purifier discovery was not held through the provider setup interval');
  await setup.click('Find my purifier');
  await setup.until("document.querySelector('.room-setup .room-options button')!==null");
  await setup.tap("document.querySelector('.room-setup .room-options button')");
  await setup.click('Select & check reported state');
  await setup.until("document.querySelector('.room-setup .room-controls button')!==null");
  const saved=await api('api/v1/room');
  if(!saved.connected||!saved.selected||JSON.stringify(saved).includes('synthetic-password-only'))throw Error('Fake account selection or credential privacy failed');
}finally{await setup.close();}

const checks=[{onboarding:{pacedDiscovery:true,accountAndSelectionSaved:true}}];
for(const theme of ['hearth','luma-glass','neon-grid']){
  await api('_qa/control',{mode:'normal',reset_slots:true,theme});
  const tab=await browser();
  try{
    await tab.click('Air purifier');
    await tab.until("document.querySelector('.room-setup .room-controls button')!==null");
    await api('_qa/control',{mode:'offline',reset_slots:true});
    await tab.click('Check reported state');
    await tab.until("document.querySelector('.room-setup')?.textContent.includes('VeSync is unavailable')");
    const offline=await tab.evaluate("(()=>({controls:!!document.querySelector('.room-setup .room-controls button'),saved:document.querySelector('.room-setup')?.textContent.includes('Last reading'),fit:document.body.scrollWidth<=innerWidth,leak:document.body.innerText.includes('QA_TOKEN_SENTINEL')}))()");
    if(offline.controls||!offline.saved||!offline.fit||offline.leak)throw Error(`${theme}: outage left unsafe controls, overflow or private provider text`);
    await api('_qa/control',{mode:'normal',reset_slots:true});
    await tab.click('Check reported state');
    await tab.until("document.querySelector('.room-setup .room-controls button')!==null");
    const recovered=await tab.evaluate("document.querySelector('.room-setup')?.textContent.includes('Reported state checked')");
    if(!recovered)throw Error(`${theme}: fresh provider recovery did not restore controls`);
    checks.push({theme,offline,recovered});
  }finally{await tab.close();}
}

await api('_qa/control',{mode:'normal',reset_slots:true,theme:'hearth'});
const privacy=await browser();
try{
  await privacy.click('Air purifier');await privacy.click('Reconnect VeSync');
  await privacy.tap("document.querySelector('.room-setup .extras-toggle input')");
  await privacy.click('Continue to local sign-in');
  await privacy.tap("document.querySelector('.room-setup input[type=text]')");await privacy.insert('private-draft@example.invalid');
  await api('_qa/control',{locked:true});
  await privacy.until("!document.querySelector('.room-setup')");
  const redacted=await privacy.evaluate("!document.body.innerText.includes('private-draft@example.invalid')&&!document.body.innerText.includes('QA purifier')");
  if(!redacted)throw Error('Private reconnect form remained visible during privacy lock');
  await api('_qa/control',{locked:false});
  const kept=await api('api/v1/room');
  if(!kept.connected||!kept.selected)throw Error('Privacy transition erased saved account/selection');
  if((await api('_qa/control',{})).commands!==0)throw Error('Setup or privacy checks sent an unintended purifier command');
  const reopened=await browser();
  try{
    await reopened.click('Air purifier');
    await reopened.until("document.querySelector('.room-setup .room-device-card')?.textContent.includes('QA purifier')");
    if(await reopened.evaluate("document.body.innerText.includes('private-draft@example.invalid')"))throw Error('Private reconnect draft leaked after unlock');
  }finally{await reopened.close();}
  checks.push({privacy:{redacted,savedSelectionRetained:true}});
}finally{await api('_qa/control',{locked:false});await privacy.close();}
console.log(JSON.stringify({checks},null,2));
