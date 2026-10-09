import test from 'node:test';
import assert from 'node:assert/strict';
import {configureSetupTransport,setupFetch,isRemoteSetup} from '../src/setupTransport.ts';
import {requestBytes} from '../src/companionProof.ts';

test('primary proof can sign only fixed bridge and fan paths, not arbitrary settings URLs',async()=>{
  const context={origin:'https://luma.example-tail.ts.net',identityDigest:'a'.repeat(64)},device='b'.repeat(43),nonce='c'.repeat(43);
  for(const [method,path] of [['POST','/remote/api/hub-settings'],['GET','/remote/api/device/fan'],['POST','/remote/api/device/fan']]){
    assert.ok(await requestBytes(device,nonce,context,method,path,new Uint8Array()));
  }
  await assert.rejects(requestBytes(device,nonce,context,'GET','/api/v1/settings',new Uint8Array()));
});
test('shared setup transport dispatches JSON without cookies/headers and respects abort',async()=>{
  let count=0;
  configureSetupTransport(async op=>{count++;assert.deepEqual(op,{method:'GET',path:'/api/v1/settings',body:{},confirmed:true});return {status:200,body:{theme:'hearth'}};});
  assert.equal(isRemoteSetup(),true);
  const response=await setupFetch('/api/v1/settings',{headers:{Cookie:'never forward this'}});
  assert.deepEqual(await response.json(),{theme:'hearth'});
  await assert.rejects(setupFetch('https://example.com/api/v1/settings'));
  const controller=new AbortController();controller.abort();
  await assert.rejects(setupFetch('/api/v1/settings',{signal:controller.signal}));
  assert.equal(count,1);
});
