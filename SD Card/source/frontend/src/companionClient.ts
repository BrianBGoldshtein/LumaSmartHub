import {enrollmentBytes, requestBytes, sha256, signProof} from './companionProof.ts';
import type {BrowserCredential, BrowserKey, RemoteContext} from './companionProof.ts';
import {isAdminNeeded} from './adminState.ts';

export class RemoteError extends Error {
  readonly kind:'connection'|'conflict'|'expired'|'invalid'|'unavailable'|'admin';
  constructor(kind:RemoteError['kind'],message:string){super(message);this.kind=kind;}
}
type Fetcher = typeof fetch;
function failure(status:number): RemoteError {
  if(status===403)return new RemoteError('connection','Connect your selected iPhone to Luma and check enrollment.');
  if(status===409)return new RemoteError('conflict','Hub state changed. Refresh before trying again.');
  if(status===410)return new RemoteError('expired','The review expired. Check again.');
  if(status===422||status===413||status===415)return new RemoteError('invalid','Luma could not accept this change. Check the values.');
  return new RemoteError('unavailable','Luma is unavailable or restarting. Reconnect and refresh.');
}

async function jsonResponse(response:Response):Promise<unknown>{
  if(response.headers.get('Content-Type')?.split(';')[0]!=='application/json')throw failure(response.ok?503:response.status);
  const reader=response.body?.getReader();
  if(!reader)throw failure(503);
  const chunks:Uint8Array[]=[];let size=0;
  try{
    while(true){const next=await reader.read();if(next.done)break;
      size+=next.value.length;
      if(size>1024*1024){await reader.cancel();throw failure(503);}
      chunks.push(next.value);
    }
    const bytes=new Uint8Array(size);let offset=0;
    for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
    let value:unknown;
    try{value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));}
    catch{throw failure(response.ok?503:response.status);}
    if(!response.ok){
      if(response.status===403&&isAdminNeeded(value))throw new RemoteError('admin','Confirm your primary hub PIN, then review and try again.');
      throw failure(response.status);
    }
    return value;
  }finally{reader.releaseLock();}
}

export async function bootstrapRemote(origin:string,fetcher:Fetcher=fetch,signal?:AbortSignal):Promise<RemoteContext>{
  if(!/^https:\/\/[^/]+\.ts\.net$/.test(origin))throw failure(403);
  const value=await jsonResponse(await fetcher('/remote/api/bootstrap',{cache:'no-store',credentials:'omit',redirect:'error',signal}));
  const context=value as RemoteContext;
  if(!context||context.origin!==origin||typeof context.identityDigest!=='string'||!/^[0-9a-f]{64}$/.test(context.identityDigest))throw failure(403);
  return context;
}

export async function enrollRemote(ticket:string,key:BrowserKey,context:RemoteContext,
  fetcher:Fetcher=fetch,signal?:AbortSignal):Promise<{device_id:string;comparison_code:string}>{
  const message=await enrollmentBytes(ticket,context,key.publicKey);
  const value=await jsonResponse(await fetcher('/remote/api/enroll',{
    method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',credentials:'omit',redirect:'error',signal,
    body:JSON.stringify({ticket,public_key:key.publicKey,signature:await signProof(key,message)}),
  })) as {device_id:string;comparison_code:string};
  if(!value||typeof value.device_id!=='string'||value.device_id.length!==43||!/^[A-Za-z0-9_-]{43}$/.test(value.device_id)
    ||typeof value.comparison_code!=='string'||value.comparison_code.length!==6||!/^\d{6}$/.test(value.comparison_code))throw failure(503);
  return value;
}

export class RemoteClient {
  private pending:Promise<void>=Promise.resolve();
  private active:AbortController|null=null;
  private epoch=0;
  private lastStarted=0;
  private key:BrowserCredential;
  private context:RemoteContext;
  private fetcher:Fetcher;
  private visible:()=>boolean;
  constructor(key:BrowserCredential,context:RemoteContext,fetcher:Fetcher=fetch,
    visible:()=>boolean=()=>document.visibilityState==='visible'){
    this.key=key;this.context=context;
    // Native Safari/Chromium fetch is a Window operation. Calling it as
    // this.fetcher() with a RemoteClient receiver can throw Illegal invocation;
    // Node's fetch/mocks are more permissive, so browser qualification matters.
    this.fetcher=(input,init)=>fetcher(input,init);this.visible=visible;
  }

  // Called on hide/pagehide/offline. Neither replies nor actions are cached or
  // retried. A command already accepted by the hub may finish; review before
  // attempting it again rather than blindly replaying an uncertain mutation.
  suspend(){this.epoch++;this.active?.abort();}

  request<T>(method:string,path:string,payload?:unknown):Promise<T>{
    const epoch=this.epoch;
    const task=this.pending.then(async()=>{
      if(epoch!==this.epoch||!this.visible())throw failure(403);
      const controller=new AbortController();this.active=controller;
      const timer=setTimeout(()=>controller.abort(),path.includes('/updates/')?50000:20000);
      const ensureVisible=()=>{if(controller.signal.aborted||epoch!==this.epoch||!this.visible())throw failure(403);};
      try{
        // Each operation makes two authenticated HTTP calls. Pace a fast
        // calendar load plus taps below the gateway's 24-call/second burst
        // limit; never retry a throttled or uncertain mutation.
        const wait=Math.min(125,Math.max(0,125-(performance.now()-this.lastStarted)));
        if(wait)await new Promise(resolve=>setTimeout(resolve,wait));
        ensureVisible();this.lastStarted=performance.now();
        const body=method==='GET'?'':JSON.stringify(payload??{});
        const bytes=new TextEncoder().encode(body);
        // Validate action/origin/body BEFORE requesting any challenge.
        await requestBytes(this.key.deviceId,'a'.repeat(43),this.context,method,path,bytes);
        ensureVisible();
        const challenge=await jsonResponse(await this.fetcher('/remote/api/challenge',{
          method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',credentials:'omit',redirect:'error',signal:controller.signal,
          body:JSON.stringify({device_id:this.key.deviceId,method,path,body_digest:await sha256(bytes)}),
        })) as {nonce:string;expires_in_seconds:number};
        if(!challenge||typeof challenge.nonce!=='string'||challenge.nonce.length!==43
          ||!/^[A-Za-z0-9_-]{43}$/.test(challenge.nonce)||challenge.expires_in_seconds!==30)throw failure(503);
        ensureVisible();
        const message=await requestBytes(this.key.deviceId,challenge.nonce,this.context,method,path,bytes);
        const signature=await signProof(this.key,message);
        ensureVisible();
        const response=await this.fetcher(path,{
          method,headers:{'X-Luma-Device':this.key.deviceId,'X-Luma-Nonce':challenge.nonce,'X-Luma-Proof':signature,
            ...(method==='GET'?{}:{'Content-Type':'application/json'})},
          body:method==='GET'?undefined:body,cache:'no-store',credentials:'omit',redirect:'error',signal:controller.signal,
        });
        const value=await jsonResponse(response);ensureVisible();return value as T;
      }catch(error){
        if(error instanceof RemoteError)throw error;
        throw failure(503);
      }finally{clearTimeout(timer);if(this.active===controller)this.active=null;}
    });
    // This tail deliberately holds no resolved private response value.
    this.pending=task.then(()=>{},()=>{});
    return task;
  }
}
