import {useEffect,useRef,useState} from 'react';
import type {Snapshot} from './types';
import './voiceAccountChoice.css';

export function VoiceAccountChoice({choice}:{choice:Snapshot['voice_account_choice']}) {
  const [expired,setExpired]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const id=choice?.id,remaining=Math.min(30000,Math.max(0,choice?.remaining_ms??0));
  const liveId=useRef(id);liveId.current=id;
  useEffect(()=>{setError('');setBusy(false);},[id]);
  useEffect(()=>{
    if(!id||remaining<=0)return;
    const handle=window.setTimeout(()=>setExpired(id),remaining);
    return()=>window.clearTimeout(handle);
  },[id,remaining]);
  if(!choice||id===expired||remaining<=0||choice.users.length===0)return null;
  async function choose(profileId:string){
    if(!id||busy)return;
    setBusy(true);setError('');
    try{
      const response=await fetch('/api/v1/voice/account/choose',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({choice_id:id,profile_id:profileId})});
      const packet=await response.json();
      if(liveId.current!==id)return;
      if(response.ok&&packet.accepted===true)setExpired(id);
      else setError('That choice is no longer available. Ask Luma again.');
    }catch{if(liveId.current===id)setError('Luma is reconnecting. Please ask again.');}
    finally{if(liveId.current===id)setBusy(false);}
  }
  function cancel(){
    setExpired(id??null);
    void fetch('/api/v1/voice/account/cancel',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({choice_id:id})}).catch(()=>{});
  }
  return <aside className="voice-account-choice" role="dialog" aria-modal="false" aria-label="Choose whose information to use">
    <h2>Whose plans?</h2><p>Say a name after “Hey Luma” or choose.</p>
    <div>{choice.users.map(user=><button disabled={busy} key={user.profile_id} onClick={()=>void choose(user.profile_id)}>{user.nickname}</button>)}</div>
    {error&&<p role="status">{error}</p>}
    <button className="voice-account-close" disabled={busy} onClick={cancel}>Not now</button>
  </aside>;
}
