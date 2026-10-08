import test from 'node:test';
import assert from 'node:assert/strict';
import {RemoteClient, bootstrapRemote, RemoteError} from '../src/companionClient.ts';
import {createBrowserKey} from '../src/companionProof.ts';

const context={origin:'https://luma.example-tail.ts.net',identityDigest:'a'.repeat(64)};
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}});
async function credential(){return {...await createBrowserKey(),deviceId:'b'.repeat(43)};}

test('bootstrap rejects a different origin and omits cached/cookie access',async()=>{
  const fetcher=(async(_url,options)=>{
    assert.equal(options?.credentials,'omit');assert.equal(options?.cache,'no-store');assert.equal(options?.redirect,'error');
    return response(context);
  }) as typeof fetch;
  assert.deepEqual(await bootstrapRemote(context.origin,fetcher),context);
  await assert.rejects(bootstrapRemote('https://other.example-tail.ts.net',fetcher));
});

test('signed mutation uses one challenge and exactly the submitted UTF-8 body',async()=>{
  const calls:{path:string;options:RequestInit|undefined}[]=[];
  const fetcher=(async(url,options)=>{
    calls.push({path:String(url),options});
    return response(String(url).endsWith('/challenge')?{nonce:'c'.repeat(43),expires_in_seconds:30}:{brightness:34});
  }) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  assert.deepEqual(await client.request('PATCH','/remote/api/settings',{brightness:34}),{brightness:34});
  assert.equal(calls.length,2);
  const challenge=JSON.parse(calls[0].options!.body as string);
  assert.equal(challenge.method,'PATCH');assert.equal(challenge.path,'/remote/api/settings');
  assert.match(challenge.body_digest,/^[0-9a-f]{64}$/);
  assert.equal(calls[1].options!.body,'{"brightness":34}');
  assert.equal((calls[1].options!.headers as Record<string,string>)['X-Luma-Proof'].length,86);
});

test('private reads fail while hidden; invalid paths do not make a network request',async()=>{
  let calls=0;
  const fetcher=(async()=>{calls++;return response({});}) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>false);
  await assert.rejects(client.request('GET','/remote/api/preview'));assert.equal(calls,0);
  const visible=new RemoteClient(await credential(),context,fetcher,()=>true);
  await assert.rejects(visible.request('GET','/api/v1/settings'));assert.equal(calls,0);
});

test('suspend invalidates queued work and does not retry uncertain mutations',async()=>{
  let calls=0;let release:()=>void=()=>{};
  const waiting=new Promise<void>(resolve=>{release=resolve;});
  const fetcher=(async()=>{calls++;await waiting;return response({nonce:'c'.repeat(43),expires_in_seconds:30});}) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  const first=client.request('POST','/remote/api/command',{name:'wake'});
  const second=client.request('GET','/remote/api/preview');
  // Catch both immediately so the deliberate cancellation is not unhandled.
  const checked=[assert.rejects(first),assert.rejects(second)];
  while(calls===0)await new Promise(resolve=>setTimeout(resolve,1));
  client.suspend();release();await Promise.all(checked);assert.equal(calls,1);
});

test('provider error inputs are replaced with fixed local copy',async()=>{
  const fetcher=(async()=>response({detail:'PRIVATE_PROVIDER_DATA'},403)) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  await assert.rejects(client.request('GET','/remote/api/preview'),error=>{
    assert.ok(error instanceof RemoteError);assert.equal(error.kind,'connection');
    assert.ok(!error.message.includes('PRIVATE_PROVIDER_DATA'));return true;
  });
});

test('fixed administrator denial requests PIN renewal without reflecting provider text',async()=>{
  let calls=0;
  const fetcher=(async()=>{calls++;return calls===1?response({nonce:'c'.repeat(43),expires_in_seconds:30}):
    response({code:'admin_required',fresh:true,detail:'PRIVATE_PROVIDER_DATA'},403);}) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  await assert.rejects(client.request('PATCH','/remote/api/settings',{brightness:20}),error=>{
    assert.ok(error instanceof RemoteError);assert.equal(error.kind,'admin');
    assert.ok(!error.message.includes('PRIVATE_PROVIDER_DATA'));return true;
  });
  assert.equal(calls,2);
});

test('browser fetch is not called with the remote object as its receiver',async()=>{
  const fetcher=function(this:unknown,url:RequestInfo|URL){
    assert.equal(this,undefined);
    return Promise.resolve(response(String(url).endsWith('/challenge')?{nonce:'c'.repeat(43),expires_in_seconds:30}:{ok:true}));
  } as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  assert.deepEqual(await client.request('GET','/remote/api/preview'),{ok:true});
});

test('serialized operations are paced below the gateway burst budget without replay',async()=>{
  const starts:number[]=[];let calls=0;
  const fetcher=(async(url)=>{calls++;
    if(String(url).endsWith('/challenge')){starts.push(performance.now());return response({nonce:'c'.repeat(43),expires_in_seconds:30});}
    return response({ok:true});
  }) as typeof fetch;
  const client=new RemoteClient(await credential(),context,fetcher,()=>true);
  await Promise.all([client.request('GET','/remote/api/preview'),client.request('GET','/remote/api/settings'),client.request('GET','/remote/api/preview')]);
  assert.equal(calls,6);assert.equal(starts.length,3);
  for(let i=1;i<starts.length;i++)assert.ok(starts[i]-starts[i-1]>=100);
});
