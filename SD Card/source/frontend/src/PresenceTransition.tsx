import {useEffect,useState} from 'react';
import type {CSSProperties} from 'react';
import {LogIn,LogOut} from 'lucide-react';
import type {Snapshot} from './types';
import './presenceTransition.css';

/** Expire locally as well as on the server; a frozen connection cannot stick. */
export function PresenceTransition({transition}: {transition:Snapshot['presence_transition']}) {
  const [expired,setExpired]=useState<number|null>(null);
  const id=transition?.id;
  const remaining=Math.min(5000,Math.max(0,transition?.remaining_ms??0));
  useEffect(()=>{
    if(id===undefined||remaining<=0)return;
    const timer=window.setTimeout(()=>setExpired(id),remaining);
    return()=>window.clearTimeout(timer);
  },[id,remaining]);
  if(!transition||expired===id||remaining<=0)return null;
  const groups=[{names:transition.arriving,verb:transition.arriving.length===1?'is arriving':'are arriving',Icon:LogIn},
                {names:transition.leaving,verb:transition.leaving.length===1?'has left':'have left',Icon:LogOut}];
  return <section className="presence-transition" role="status" aria-live="polite" data-transition-id={id}>
    <div className="presence-transition-light" aria-hidden="true"/>
    <div className="presence-transition-groups">{groups.filter(group=>group.names.length).map(({names,verb,Icon})=>
      <div className="presence-transition-group" key={verb}><Icon aria-hidden="true"/>
        <h1 style={{'--name-scale':Math.max(1,names.join(' & ').length/100)} as CSSProperties}>{names.join(' & ')}</h1><p>{verb}</p></div>)}</div>
    <div className="presence-transition-progress" aria-hidden="true" key={id} style={{animationDuration:`${remaining}ms`}}/>
  </section>;
}
