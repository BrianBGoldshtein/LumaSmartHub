import {useEffect,useRef} from 'react';
import type {SetupOperation,SetupResult} from '../setupTransport';
import type {Theme} from '../types';

type Request=<T>(method:string,path:string,body?:unknown)=>Promise<T>;
type Pending={id:string;operation:SetupOperation};
const google:Record<string,string>={'google/status':'status','google/calendars':'calendars','google/event-colors':'colors','google/sync':'sync','google/config':'web-client'};
export function SettingsFrame({request,theme,onError,onClose}:{request:Request;theme:Theme;onError:(error:unknown)=>void;onClose:()=>void}){
  const frame=useRef<HTMLIFrameElement>(null),current=useRef({request,onError,onClose});current.current={request,onError,onClose};
  useEffect(()=>{
    let live=true,reads:Pending[]=[];const ids=new Set<string>();
    const reply=(id:string,result:SetupResult)=>{ids.delete(id);if(live)frame.current?.contentWindow?.postMessage({kind:'luma-settings-response',id,result},location.origin);};
    async function bridge(items:Pending[]){
      try{
        const value=await current.current.request<{results:SetupResult[]}>('POST','/remote/api/hub-settings',{operations:items.map(item=>item.operation)});
        if(!Array.isArray(value.results)||value.results.length!==items.length)throw Error('Invalid settings response.');
        items.forEach((item,i)=>reply(item.id,value.results[i]));
      }catch(error){items.forEach(item=>reply(item.id,{status:503,body:{detail:'Luma is unavailable. Review device status before retrying.'}}));if(live)current.current.onError(error);}
    }
    // Align independently started panel polls on one clock. Even an active
    // voice check makes at most one signed read batch per second, not one
    // challenge per meter/model/status resource.
    const timer=setInterval(()=>{const group=reads.splice(0,12);if(group.length)void bridge(group);},1000);
    async function direct(item:Pending){
      const route=item.operation.path.slice(8),op=item.operation;
      try{
        let result:unknown;
        if(route==='google/authorize'||route==='google/authorize-tasks')result=await current.current.request('POST','/remote/api/google/authorize',{task_updates:route.endsWith('-tasks')});
        else result=await current.current.request(op.method,'/remote/api/google/'+google[route],op.body);
        if(route==='google/status'){
          const status=result as Record<string,unknown>;
          result={...status,configured:status.web_configured===true};
        }
        reply(item.id,{status:200,body:result});
      }catch(error){reply(item.id,{status:503,body:{detail:'Google setup could not finish. Check the Web OAuth client and private connection.'}});if(live)current.current.onError(error);}
    }
    const listener=(event:MessageEvent)=>{
      if(event.origin!==location.origin||event.source!==frame.current?.contentWindow)return;
      const data=event.data;
      if(data?.kind==='luma-settings-close'){current.current.onClose();return;}
      if(data?.kind==='luma-settings-navigate'){
        try{const url=new URL(data.url);if(url.protocol==='https:'&&url.hostname==='accounts.google.com'&&!url.username&&!url.password)location.assign(url.href);}catch{/* Invalid URLs never navigate. */}return;
      }
      if(data?.kind!=='luma-settings-request'||typeof data.id!=='string'||!/^[a-zA-Z0-9-]{1,64}$/.test(data.id)||ids.has(data.id)||ids.size>=64)return;
      const op=data.operation as SetupOperation;
      if(!op||typeof op.path!=='string'||!/^\/api\/v1\/[a-z0-9/-]+$/.test(op.path)||!['GET','POST','PATCH','PUT','DELETE'].includes(op.method)
        ||typeof op.confirmed!=='boolean'||!op.body||Array.isArray(op.body)||typeof op.body!=='object')return;
      if(JSON.stringify(op).length>60000)return;
      ids.add(data.id);const item={id:data.id,operation:op};const route=op.path.slice(8);
      if(route in google||route==='google/authorize'||route==='google/authorize-tasks'){void direct(item);return;}
      if(op.method==='GET')reads.push(item);else void bridge([item]);
    };
    window.addEventListener('message',listener);
    return()=>{live=false;reads=[];ids.clear();clearInterval(timer);window.removeEventListener('message',listener);};
  },[]);
  return <section className="all-settings"><h2>All hub settings</h2><p>The same guided setup and controls as your wall screen. Changes apply to the Pi, not this phone.</p>
    <iframe ref={frame} src={`/remote/settings.html#device/${theme}`} title="Luma hub settings"/></section>;
}
