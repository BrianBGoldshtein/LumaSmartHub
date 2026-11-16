import {useEffect,useState} from 'react';
import {announceAdminNeeded} from './adminState';
import {useSetupActivity} from './setupActivity';
import {setupFetch} from './setupTransport';
import {setupTheme} from './setupTheme';
import type {Theme} from './types';

const themes = [
  { id: 'luma-glass', name: 'Luma Glass' },
  { id: 'hearth', name: 'Hearth' },
  { id: 'neon-grid', name: 'Neon Grid' },
] as const;

type Appearance = {theme: Theme; brightness: number};

export function AppearanceSetup({demo,theme,onSaved}: {demo:boolean;theme:Theme;onSaved:(theme:Theme)=>void}) {
  const [saved,setSaved] = useState<Appearance|null>(demo?{theme,brightness:70}:null);
  const [chosen,setChosen] = useState<Appearance>({theme,brightness:70});
  const [busy,setBusy] = useState(false);
  const [message,setMessage] = useState('');
  const [retry,setRetry] = useState(0);
  useSetupActivity(busy);

  useEffect(()=>{
    if(demo)return;
    const controller = new AbortController();
    setupFetch('/api/v1/settings',{signal:controller.signal,cache:'no-store'}).then(async response=>{
      const data = await response.json();
      if(!response.ok){announceAdminNeeded(data);throw Error('Could not load display settings.');}
      const appearance = {theme:setupTheme(data.theme),brightness:data.brightness as number};
      setSaved(appearance);
      setChosen(appearance);
    }).catch(()=>{if(!controller.signal.aborted)setMessage('Could not load display settings.');});
    return ()=>controller.abort();
  },[demo,retry]);

  async function save() {
    if(!saved)return;
    const patch: Partial<Appearance> = {};
    if(chosen.theme!==saved.theme)patch.theme=chosen.theme;
    if(chosen.brightness!==saved.brightness)patch.brightness=chosen.brightness;
    setBusy(true);setMessage('');
    try {
      if(!demo){
        const response=await setupFetch('/api/v1/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});
        if(!response.ok){announceAdminNeeded(await response.json());throw Error('Could not save display settings.');}
      }
      setSaved(chosen);
      onSaved(chosen.theme);
      setMessage(demo?'Preview only.':'Display settings saved.');
    } catch {setMessage('Could not save display settings. Try again.');}
    finally {setBusy(false);}
  }

  if(!saved)return <><p role="status">{message||'Loading display settings…'}</p>
    {message&&<button onClick={()=>{setMessage('');setRetry(value=>value+1);}}>Retry settings</button>}</>;

  return <form className="settings-appearance" onSubmit={event=>{event.preventDefault();void save();}}>
    <fieldset>
      <legend>Theme</legend>
      <div className="settings-theme-options">
        {themes.map(({id,name})=><label key={id} className={`theme-choice choice-${id}`}>
          <input type="radio" name="luma-theme" checked={chosen.theme===id} disabled={busy} onChange={()=>setChosen({...chosen,theme:id})}/>
          <span>{name}</span>
          <strong aria-hidden="true">12:48</strong>
        </label>)}
      </div>
    </fieldset>
    <label>Daytime brightness <output>{chosen.brightness}%</output>
      <input type="range" min="0" max="100" value={chosen.brightness} disabled={busy} onChange={event=>setChosen({...chosen,brightness:Number(event.target.value)})}/>
    </label>
    <button disabled={busy||chosen.theme===saved.theme&&chosen.brightness===saved.brightness}>{busy?'Saving…':'Save display settings'}</button>
    {message&&<p role="status" className="setup-message">{message}</p>}
  </form>;
}
