import {useEffect,useState} from 'react';
import type {Snapshot} from './types';
import {voiceNoticeDuration} from './voiceNoticeState';

/** Fixed, non-private feedback; no transcript, sound or full-screen takeover. */
export function VoiceNotice({notice}:{notice:Snapshot['voice_notice']}) {
  const [expired,setExpired]=useState<number|null>(null);
  const id=notice?.id;
  const remaining=voiceNoticeDuration(notice,expired);
  useEffect(()=>{
    if(id===undefined||remaining<=0)return;
    const timer=window.setTimeout(()=>setExpired(id),remaining);
    return ()=>window.clearTimeout(timer);
  },[id,remaining]);
  if(id===undefined||remaining<=0)return null;
  return <aside className="voice-notice" role="status">Unknown command</aside>;
}
