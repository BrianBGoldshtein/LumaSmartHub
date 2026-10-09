// Explicit setup-only transport. The wall keeps native fetch; the companion
// settings entry delegates bounded JSON operations to its authenticated parent.
export type SetupOperation={method:string;path:string;body:Record<string,unknown>;confirmed:boolean};
export type SetupResult={status:number;body:unknown};
let transport:((operation:SetupOperation)=>Promise<SetupResult>)|null=null;
export function configureSetupTransport(value:NonNullable<typeof transport>){transport=value;}
export function isRemoteSetup(){return transport!==null;}
const disruptive=new Set(['security/pin','security/lan-token/rotate','users/manage','network','network/hotspot',
  'tailscale','bluetooth/forget','backups/export','backups/apply','updates/install']);
export async function setupFetch(input:RequestInfo|URL,init?:RequestInit):Promise<Response>{
  if(!transport)return fetch(input,init);
  if(typeof input!=='string'||!/^\/api\/v1\/[a-z0-9/-]+$/.test(input))throw Error('This setup operation is unavailable.');
  const method=init?.method??'GET';
  if(init?.signal?.aborted)throw new DOMException('Aborted','AbortError');
  let body:Record<string,unknown>={};
  if(init?.body!==undefined){if(typeof init.body!=='string')throw Error('Use a JSON setup request.');body=JSON.parse(init.body);}
  if(!body||Array.isArray(body)||typeof body!=='object')throw Error('Setup request is invalid.');
  const route=input.slice(8),readAction=route==='tailscale'&&body.action==='status'||route==='network'&&['scan','check'].includes(String(body.action));
  const confirmed=method==='GET'||readAction||!disruptive.has(route)||confirm('Apply this protected change to Luma? Network, phone, PIN or update changes may disconnect this remote. Review the values before continuing.');
  if(!confirmed)return new Response(JSON.stringify({detail:'Cancelled. Nothing was sent.'}),{status:409,headers:{'Content-Type':'application/json'}});
  const result=await transport({method,path:input,body,confirmed});
  if(init?.signal?.aborted)throw new DOMException('Aborted','AbortError');
  return new Response(JSON.stringify(result.body),{status:result.status,headers:{'Content-Type':'application/json','Cache-Control':'no-store'}});
}
export function setupNavigate(url:string){
  if(!transport){location.assign(url);return;}
  const target=new URL(url,location.href);
  if(target.protocol==='https:'&&target.hostname==='accounts.google.com'&&!target.username&&!target.password){
    parent.postMessage({kind:'luma-settings-navigate',url:target.href},location.origin);return;
  }
  if(target.origin!==location.origin)throw Error('Setup navigation is invalid.');
  const step=target.searchParams.get('setup');
  location.hash=step&&['device','onboarding','google','extras','users','personal'].includes(step)?step:'close';
}
