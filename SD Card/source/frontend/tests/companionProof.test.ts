import test from 'node:test';
import assert from 'node:assert/strict';
import {createBrowserKey, enrollmentBytes, requestBytes, sha256, signProof} from '../src/companionProof.ts';

const context = {origin:'https://luma.example-tail.ts.net', identityDigest:'a'.repeat(64)};
const device = 'b'.repeat(43), nonce = 'c'.repeat(43), path = '/remote/api/preview';
const empty = new Uint8Array();

test('browser private key cannot be exported; public point and raw signatures match protocol sizes', async()=>{
  const key = await createBrowserKey();
  assert.equal(key.privateKey.extractable, false);
  assert.equal(key.publicKey.length, 87);
  await assert.rejects(crypto.subtle.exportKey('jwk',key.privateKey));
  assert.equal((await signProof(key,new TextEncoder().encode('example'))).length,86);
});

test('request signing binds canonical origin, identity, method, path and exact body bytes', async()=>{
  const bytes = await requestBytes(device,nonce,context,'GET',path,empty);
  assert.equal(new TextDecoder().decode(bytes),[
    'LUMA_REMOTE_V1',context.origin,context.identityDigest,device,nonce,'GET',path,
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
  ].join('\n'));
  const body = new TextEncoder().encode('{"name":"wake"}');
  const changed = await requestBytes(device,nonce,context,'POST','/remote/api/command',body);
  assert.ok(new TextDecoder().decode(changed).endsWith(await sha256(body)));
  assert.notDeepEqual(changed,bytes);
});

test('enrollment proof binds ticket and public point without disclosing private key',async()=>{
  const key = await createBrowserKey();
  const bytes = await enrollmentBytes(device,context,key.publicKey);
  const rows = new TextDecoder().decode(bytes).split('\n');
  assert.deepEqual(rows.slice(0,4),['LUMA_ENROLL_V1',device,context.origin,context.identityDigest]);
  assert.match(rows[4],/^[0-9a-f]{64}$/);
  assert.equal(rows.length,5);
});

test('own setup progression uses only fixed signed paths',async()=>{
  assert.ok(await requestBytes(device,nonce,context,'GET','/remote/api/setup',empty));
  assert.ok(await requestBytes(device,nonce,context,'POST','/remote/api/setup',new TextEncoder().encode('{"stage":"ready"}')));
  await assert.rejects(requestBytes(device,nonce,context,'PATCH','/remote/api/setup',empty));
  await assert.rejects(requestBytes(device,nonce,context,'GET','/remote/api/setup?profile_id=primary',empty));
});

test('rejects noncanonical origins, arbitrary paths, oversized and unexpected GET bodies',async()=>{
  for(const origin of ['http://luma.example-tail.ts.net','https://evil.test',context.origin+'/',context.origin+':443',context.origin+'\n']){
    await assert.rejects(requestBytes(device,nonce,{...context,origin},'GET',path,empty));
  }
  await assert.rejects(requestBytes(device,nonce,context,'GET','/api/v1/settings',empty));
  await assert.rejects(requestBytes(device,nonce,context,'GET',path+'?x=1',empty));
  await assert.rejects(requestBytes(device+'\n',nonce,context,'GET',path,empty));
  await assert.rejects(requestBytes(device,nonce,context,'GET',path,new Uint8Array([1])));
  await assert.rejects(requestBytes(device,nonce,context,'POST','/remote/api/command',new Uint8Array(65537)));
});
