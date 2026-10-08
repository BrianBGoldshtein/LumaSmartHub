// Disposable localhost Chromium only. Tests crypto/IndexedDB, not an iPhone,
// Bluetooth presence, real account or public network. Output uses fake IDs.
import assert from 'node:assert/strict';
const base='http://127.0.0.1:18875', debug='http://127.0.0.1:19225';
const target=await (await fetch(debug+'/json/new?'+encodeURIComponent(base),{method:'PUT'})).json();
const socket=new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
const pending=new Map();let sequence=0;
socket.onmessage=event=>{
  const packet=JSON.parse(event.data), wait=pending.get(packet.id);
  if(!wait)return;
  pending.delete(packet.id);
  packet.error?wait.reject(Error(JSON.stringify(packet.error))):wait.resolve(packet.result);
};
const send=(method,params={})=>new Promise((resolve,reject)=>{
  const id=++sequence;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));
});
async function value(expression){
  const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text);
  return result.result.value;
}
async function go(query){
  await send('Page.navigate',{url:base+'/?'+query});
  const deadline=Date.now()+5000;
  while(!(await value(`location.origin===${JSON.stringify(base)}&&location.search===${JSON.stringify('?'+query)}&&document.readyState==='complete'`))){
    assert.ok(Date.now()<deadline,'Disposable browser did not finish navigation.');
    await new Promise(resolve=>setTimeout(resolve,50));
  }
}
try{
  await send('Page.enable');await send('Runtime.enable');
  await go('round=1');
  const first=await value(`(async()=>{
    const p=await import('/companionProof.js');
    const key=await p.createBrowserKey();
    let exportRejected=false;
    try{await crypto.subtle.exportKey('jwk',key.privateKey);}catch{exportRejected=true;}
    const deviceId='b'.repeat(43),nonce='c'.repeat(43);
    const identityDigest=await p.sha256(new TextEncoder().encode('owner@example.test'));
    const connection={origin:'https://luma.example-tail.ts.net',identityDigest};
    const message=await p.requestBytes(deviceId,nonce,connection,'GET','/remote/api/preview',new Uint8Array());
    const signature=await p.signProof(key,message);
    const enrollment=await p.enrollmentBytes('a'.repeat(43),connection,key.publicKey);
    const enrollmentSignature=await p.signProof(key,enrollment);
    await p.saveCredential({...key,deviceId,previewData:'Must never persist'});
    window.__qaOldContext=true;
    return {public_key:key.publicKey,signature,message:new TextDecoder().decode(message),
      extractable:key.privateKey.extractable,exportRejected,deviceId,
      enrollment_message:new TextDecoder().decode(enrollment),enrollment_signature:enrollmentSignature};
  })()`);
  assert.equal(first.extractable,false);assert.equal(first.exportRejected,true);
  await go('round=2');
  assert.equal(await value('window.__qaOldContext===undefined'),true);
  const second=await value(`(async()=>{
    const p=await import('/companionProof.js');
    const key=await p.loadCredential();
    const message=await p.requestBytes('b'.repeat(43),'d'.repeat(43),{
      origin:'https://luma.example-tail.ts.net',
      identityDigest:await p.sha256(new TextEncoder().encode('owner@example.test')),
    },'GET','/remote/api/preview',new Uint8Array());
    return {public_key:key.publicKey,signature:await p.signProof(key,message),
      message:new TextDecoder().decode(message),extractable:key.privateKey.extractable,deviceId:key.deviceId,
      persisted_fields:Object.keys(key).sort()};
  })()`);
  assert.equal(second.public_key,first.public_key);assert.equal(second.extractable,false);
  assert.equal(second.deviceId,first.deviceId);
  assert.deepEqual(second.persisted_fields,['deviceId','privateKey','publicKey']);
  assert.notEqual(second.message,first.message);
  console.log(JSON.stringify({scope:'Disposable Chromium crypto and IndexedDB; not Safari/iPhone acceptance',first,second},null,2));
}finally{socket.close();await fetch(debug+'/json/close/'+target.id);}
