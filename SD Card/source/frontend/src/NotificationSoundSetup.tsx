import {useEffect,useState} from 'react';

export function NotificationSoundSetup({demo}:{demo:boolean}){
  const [enabled,setEnabled]=useState(true),[volume,setVolume]=useState(35);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{
    if(demo)return;
    const controller=new AbortController();
    fetch('/api/v1/settings',{signal:controller.signal}).then(async response=>{
      if(!response.ok)throw new Error('Notification sound settings are unavailable.');
      return response.json();
    }).then(settings=>{
      setEnabled(settings.notification_chime_enabled!==false);
      setVolume(Number.isInteger(settings.notification_chime_volume)?settings.notification_chime_volume:35);
    }).catch(error=>{if(!controller.signal.aborted)setMessage(error.message);});
    return()=>controller.abort();
  },[demo]);
  async function save(){
    if(demo){setMessage('Preview only. No sound setting was saved.');return;}
    setBusy(true);setMessage('');
    try{
      const response=await fetch('/api/v1/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({notification_chime_enabled:enabled,notification_chime_volume:volume})});
      if(!response.ok)throw new Error('Could not save notification sound settings.');
      setMessage('Notification sound saved. Timer alarms are separate.');
    }catch(error){setMessage(error instanceof Error?error.message:'Could not save notification sound settings.');}
    finally{setBusy(false);}
  }
  return <section><h2>Notification sound</h2>
    <p>One soft Luma bell for a new iPhone notification or time-to-leave reminder. Silent during Sleep, screen-off and privacy standby; timer alarms remain separate.</p>
    <label><input type="checkbox" checked={enabled} onChange={event=>setEnabled(event.target.checked)} disabled={busy}/> Play notification bell</label>
    <label>Chime volume · {volume}%<input type="range" min="0" max="100" step="5" value={volume} onChange={event=>setVolume(Number(event.target.value))} disabled={busy||!enabled}/></label>
    <button type="button" disabled={busy} onClick={()=>void save()}>Save notification sound</button>
    {message&&<p className="setup-message" role="status">{message}</p>}
  </section>;
}
