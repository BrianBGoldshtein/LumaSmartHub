// Real Luma HTTP/browser flow with fan_preview.py's temporary store and fake IR.
// No USB radio, fan, appliance, or owner account is accessed.
const base='http://127.0.0.1:8752/',devtools='http://127.0.0.1:9224';
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
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
  const until=async(expression,timeout=12000)=>{const start=Date.now();while(Date.now()-start<timeout){const value=await evaluate(expression);if(value)return value;await pause(100);}throw Error(`Timeout: ${expression}`);};
  const tap=async expression=>{const point=await evaluate(`(()=>{const element=${expression};if(!element||element.disabled)return null;element.scrollIntoView({block:'center'});const rect=element.getBoundingClientRect();return{x:rect.x+rect.width/2,y:rect.y+rect.height/2}})()`);if(!point)throw Error(`Missing enabled target: ${expression}`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,x:point.x,y:point.y,button:'left',clickCount:1});};
  const click=async label=>{const expression=`[...document.querySelectorAll('button')].find(item=>item.textContent.trim().includes(${JSON.stringify(label)}))`;await until(`!!(${expression}&&!(${expression}).disabled)`);await tap(expression);};
  await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:base+'?setup=extras'});
  await until("document.querySelectorAll('.extras-choices button').length>=9");
  return{evaluate,until,tap,click,close:async()=>{socket.close();await fetch(`${devtools}/json/close/${target.id}`);}};
}

await api('_qa/control',{mode:'normal',locked:false,theme:'hearth'});
let config=await api('api/v1/fans');
const device=(await api('api/v1/fans/discover',{revision:config.revision})).devices[0];
if(!device?.send||!device.receive)throw Error('Fake USB IR endpoint missing');
for(const [fan,emitter,name] of [['fan_1',1,'Bedroom Woozoo fan with a long name'],['fan_2',2,'Second Woozoo']]){
  await pause(1100);
  config=await api('api/v1/fans/select',{revision:config.revision,fan,device_id:device.id,emitter,name});
}
await pause(1100);
config=await api('api/v1/fans/learn',{revision:config.revision,fan:'fan_1',button:'power_off',receiver_id:device.id,carrier_hz:null});
if(!config.fans.find(row=>row.id==='fan_1')?.buttons.some(item=>item.key==='power_off'))throw Error('Fake button setup failed');

const checks=[];
for(const theme of ['hearth','luma-glass','neon-grid']){
  await pause(1100);
  await api('_qa/control',{mode:'unavailable',theme});
  const tab=await browser();
  try{
    await tab.click('Two fans');await tab.click('Buttons & controls');
    await tab.until("document.querySelector('.fan-setup .fan-buttons button')!==null");
    await tab.click('Test / use');
    await tab.tap("document.querySelector('.fan-setup .extras-toggle input')");
    await tab.click('Send one test');
    await tab.until("document.querySelector('.fan-setup')?.textContent.includes('Last send outcome unknown')");
    const result=await api('api/v1/fans');
    const receipt=result.fans.find(row=>row.id==='fan_1')?.last_command;
    const fit=await tab.evaluate('document.body.scrollWidth<=innerWidth');
    const leak=await tab.evaluate("document.body.innerText.includes('QA USB unavailable sentinel')||document.body.innerText.includes('QA_SECRET_SENTINEL')");
    const repeatBlocked=await tab.evaluate("[...document.querySelectorAll('.fan-setup button')].find(item=>item.textContent.includes('Send one test'))?.disabled===true");
    if(receipt?.status!=='unknown'||!fit||leak||!repeatBlocked)throw Error(`${theme}: IR uncertainty, fresh acknowledgement, narrow layout or error redaction failed`);
    checks.push({theme,unknown:receipt.status==='unknown',repeatBlocked,fit,noLeak:!leak});
  }finally{await tab.close();}
}

await pause(1100);
await api('_qa/control',{mode:'block_learn',theme:'hearth'});
const before=await api('api/v1/fans');
const tab=await browser();
try{
  await tab.click('Two fans');await tab.click('Buttons & controls');
  await tab.click('Learn this button');
  await tab.until("document.querySelector('.fan-setup')?.textContent.includes('Learn “Off”')");
  await tab.tap("document.querySelector('.fan-setup .extras-toggle input')");
  // Reading the instruction also lets the runtime's one-second IR pacing
  // interval expire after receiver discovery.
  await pause(1100);
  await tab.click('Start recording');
  const started=Date.now();while(!(await api('_qa/status')).learn_started&&Date.now()-started<12000)await pause(100);
  if(!(await api('_qa/status')).learn_started)throw Error('Blocked fake learn never started');
  await api('_qa/control',{mode:'block_learn',locked:true});
  await tab.until("!document.querySelector('.fan-setup')");
  const redacted=await tab.evaluate("!document.body.innerText.includes('Bedroom Woozoo fan with a long name')");
  if(!redacted)throw Error('Private fan details remained visible after lock');
  const wait=Date.now();while((await api('_qa/status')).cancellations<1&&Date.now()-wait<12000)await pause(100);
  if((await api('_qa/status')).cancellations<1)throw Error('Privacy unmount did not cancel the held IR learn');
  await api('_qa/control',{mode:'normal',locked:false,release:true});
  const after=await api('api/v1/fans');
  const buttons=after.fans.find(row=>row.id==='fan_1')?.buttons.map(item=>item.key);
  if(after.revision!==before.revision||buttons.includes('power_on'))throw Error('Cancelled IR learn modified the durable fan setup');
  checks.push({privacy:{redacted,cancelled:true,noLateButton:true}});
}finally{await api('_qa/control',{mode:'normal',locked:false,release:true});await tab.close();}
console.log(JSON.stringify({checks},null,2));
