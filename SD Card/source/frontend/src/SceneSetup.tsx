import {useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Sunrise,Moon,Home,DoorOpen} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {scrollSetupToTop} from './setupScroll';
import {useConfirmKeyboard} from './useConfirmKeyboard';
import {emptyScenes,sampleScenes,sceneDraft,sceneKeys,sceneLabels,automaticLabels,actionLabel,resultLabel,remoteReauthorizationReady,type SceneKey,type SceneConfig,type SceneDefinition} from './sceneState';
import './room.css';

export function SceneSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const activity=useContext(SetupActivity),alive=useRef(true),working=useRef(false),request=useRef<AbortController|null>(null),panel=useRef<HTMLDivElement>(null);
  const [config,setConfig]=useState<SceneConfig>(()=>demo?sampleScenes():emptyScenes()),[ready,setReady]=useState(demo),[busy,setBusy]=useState(false);
  const [runningScene,setRunningScene]=useState(false),[stopping,setStopping]=useState(false);
  const [selected,setSelected]=useState<SceneKey|null>(null),[step,setStep]=useState<'actions'|'review'>('actions'),[message,setMessage]=useState('');
  const [remoteDraft,setRemoteDraft]=useState<SceneKey[]>([]);
  const [draft,setDraft]=useState<SceneDefinition>({enabled:false,automatic:false,actions:[]}),[baseline,setBaseline]=useState(''),[revision,setRevision]=useState('');
  const [choice,setChoice]=useState(''),[confirm,setConfirm]=useState<'discard'|'run'|'remote-reset'|null>(null);
  const confirmPanel=useConfirmKeyboard(!!confirm,()=>{if(!busy)setConfirm(null);});
  const sceneDirty=!!selected&&JSON.stringify(draft)!==baseline;
  const remoteSaved=sceneKeys.filter(key=>config.remote.scenes[key].allowed||config.remote.scenes[key].needs_review);
  const remoteDirty=JSON.stringify([...remoteDraft].sort())!==JSON.stringify([...remoteSaved].sort());
  const remoteNeedsReview=remoteReauthorizationReady(config,remoteDraft);
  const dirty=sceneDirty||remoteDirty;
  const choices=config.devices.flatMap(device=>device.actions.map(item=>({item,label:`${device.name} · ${item.label}`})));
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useLayoutEffect(()=>scrollSetupToTop(panel.current),[selected,step]);
  useEffect(()=>{alive.current=true;if(!demo)void run(load);return()=>{alive.current=false;request.current?.abort();};},[demo]);
  useEffect(()=>{setRemoteDraft(sceneKeys.filter(key=>config.remote.scenes[key].allowed||config.remote.scenes[key].needs_review));},[config.remote.revision]);
  async function call(path='',method='GET',body?:unknown){
    const controller=new AbortController();request.current=controller;
    const timeout=setTimeout(()=>controller.abort(),130000);
    try{
      const response=await fetch(`/api/v1/scenes${path}`,{method,cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
      const value=await response.json();if(!alive.current)throw Error('Setup closed.');
      if(response.status===403){setConfig(emptyScenes());setSelected(null);setReady(false);throw Error('Unlock Luma before configuring scenes.');}
      if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Scene operation could not finish.');
      return value;
    }finally{clearTimeout(timeout);if(request.current===controller)request.current=null;}
  }
  async function load(){const value=demo?config:await call();setConfig(value);setRemoteDraft(sceneKeys.filter(key=>value.remote.scenes[key].allowed||value.remote.scenes[key].needs_review));setReady(true);}
  async function run(action:()=>Promise<void>,refreshAfterFailure=false){
    if(working.current)return;working.current=true;setBusy(true);setMessage('');
    try{await action();}catch(error){if(alive.current){
      // A scene may have sent one or more actions before an interruption. Read
      // only durable local results; never resubmit its run request.
      if(refreshAfterFailure&&!demo){
        try{setConfig(await call());setReady(true);}catch{setConfig(emptyScenes());setReady(false);}
      }
      if(alive.current)setMessage(error instanceof Error&&error.name!=='AbortError'?error.message:'Connection stopped. Review saved results; no scene will be retried automatically.');
    }}
    finally{working.current=false;if(alive.current)setBusy(false);}
  }
  function choose(key:SceneKey){
    if(remoteDirty){setMessage('Save or discard your private iPhone permission edits before opening a scene.');return;}
    const value=sceneDraft(config.definitions[key]);setSelected(key);setDraft(value);setBaseline(JSON.stringify(value));setRevision(config.revision);setStep('actions');setChoice('');setMessage('');
  }
  function edit(change:Partial<SceneDefinition>){activity?.edited();setDraft(value=>({...value,...change,...(change.actions?.length===0?{enabled:false,automatic:false}:{})}));setMessage('');}
  async function stop(){
    if(stopping)return;
    setStopping(true);
    const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),15000);
    try{
      if(!demo){
        // Independent request: replacing/aborting the in-flight run connection
        // before the broker acknowledges cancellation can lose its result.
        const response=await fetch('/api/v1/scenes/cancel',{method:'POST',cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error();
        const value=await response.json();
        if(alive.current)setConfig(value);
      }
      if(alive.current)setMessage('Stop requested. Check the last-run results; already-sent actions may have taken effect.');
    }catch{if(alive.current)setMessage('Could not confirm cancellation. Refresh results and check the devices.');}
    finally{clearTimeout(deadline);if(alive.current)setStopping(false);}
  }
  function back(){if(sceneDirty)setConfirm('discard');else setSelected(null);}
  async function saveRemote(){
    if(demo){setMessage('Preview only. Remote access is not enabled in this sample.');return;}
    const value=await call('/remote','PUT',{revision:config.remote.revision,enabled:remoteDraft.length>0,scenes:remoteDraft});
    setConfig(value);setMessage(remoteDraft.length?'Remote permission saved for the exact reviewed scenes and actions.':'Remote appliance actions are off.');
  }
  async function resetRemote(){
    const value=await call('/remote/reset','POST',{revision:config.remote.revision,confirmed:true});
    setConfig(value);setRemoteDraft([]);setConfirm(null);setMessage('Corrupt remote permissions were discarded. Remote appliance actions are off.');
  }
  async function save(){
    if(!selected)return;
    if(demo){const next=structuredClone(config);next.definitions[selected]=sceneDraft(draft);next.revision=crypto.randomUUID();setConfig(next);}
    else setConfig(await call(`/${selected}`,'PUT',{revision,...draft}));
    setSelected(null);setConfirm(null);setMessage(demo?'Sample scene saved in this preview only.':'Scene saved. No command was sent.');onSaved?.();
  }
  async function execute(){
    if(!selected)return;
    setRunningScene(true);
    try{
      if(demo){const next=structuredClone(config);next.runs.push({id:crypto.randomUUID(),scene:selected,source:'manual',at:new Date().toISOString(),finished:true,interrupted:false,steps:draft.actions.map(action=>({action,status:'unconfirmed'}))});setConfig(next);setMessage('Sample result only. No device was contacted.');}
      else{const result=await call(`/${selected}/run`,'POST',{revision:config.revision});setConfig(result.configuration);setMessage('Scene finished. Review each device result below.');}
    }finally{if(alive.current)setRunningScene(false);}
    setConfirm(null);setSelected(null);
  }
  const icons={morning:Sunrise,night:Moon,arrive:Home,away:DoorOpen};
  const last=config.runs.at(-1);
  return <div ref={panel} className="room-setup">
    <h2>Room scenes</h2><p>{demo?'Sample preview · no device commands or saved account changes.':'A few deliberate actions, together. Start with one scene; everything is optional.'}</p>
    {!ready?<button disabled={busy} onClick={()=>void run(load)}>Load saved scenes</button>:<>
      {config.recovery_error?<p role="alert">Saved scenes need recovery. Nothing has been overwritten; actions are disabled.</p>:!selected?<>
        {remoteDirty&&<p role="status" className="setup-note">Save or discard your private iPhone permission edits before opening another scene or refreshing results.</p>}
        <div className="scene-cards">{sceneKeys.map(key=>{const Icon=icons[key],row=config.definitions[key];return <button key={key} disabled={busy||remoteDirty} onClick={()=>choose(key)}><Icon aria-hidden="true"/><strong>{sceneLabels[key]}</strong><span>{row.needs_review?'Device review needed':!row.enabled?'Off':row.automatic?'Manual + automatic':'Manual only'} · {row.actions.length} {row.actions.length===1?'action':'actions'}</span></button>;})}</div>
        <section className="private-scene-policy" aria-labelledby="remote-scene-heading">
          <h3 id="remote-scene-heading">Private iPhone actions</h3>
          <p>Separate opt-in. Choose scenes to run from your authenticated Shortcut. This grants only the exact saved devices/actions below—not calendar access, nearby-phone status, scene editing, or automatic triggers.</p>
          {config.remote.recovery_error&&<><p role="alert">Remote permissions are damaged, so remote commands are blocked. Local scenes and settings are unchanged.</p><button disabled={busy||demo} onClick={()=>setConfirm('remote-reset')}>Reset remote permissions…</button></>}
          {sceneKeys.map(key=>{const row=config.definitions[key],permission=config.remote.scenes[key],selectedRemote=remoteDraft.includes(key),selectable=row.enabled&&row.actions.length>0&&!row.needs_review;return <label className="extras-toggle" key={key}>
            <input type="checkbox" disabled={busy||demo||config.remote.recovery_error||!selectable&&!selectedRemote} checked={selectedRemote} onChange={event=>{activity?.edited();setRemoteDraft(current=>event.target.checked?[...current,key]:current.filter(value=>value!==key));}}/>
            <span>{sceneLabels[key]} · {row.actions.length?row.actions.map(action=>actionLabel(action,config.devices)).join('; '):'no saved actions'}{permission.needs_review?' · local review required':!selectable?' · configure and review locally first':''}</span>
          </label>;})}
          {(remoteDirty||remoteNeedsReview)&&<button disabled={busy||demo||config.remote.recovery_error} onClick={()=>void run(saveRemote)}>{remoteNeedsReview&&!remoteDirty?'Reauthorize reviewed remote scenes':remoteDraft.length?'Save separate remote permission':'Turn off remote appliance actions'}</button>}
          {remoteDirty&&<button disabled={busy} onClick={()=>{setRemoteDraft(remoteSaved);setMessage('Unsaved private iPhone permission edits discarded.');}}>Discard permission edits</button>}
          {config.remote.enabled&&<p className="setup-note">Remote scene commands are enabled only for the exact reviewed actions above. They never unlock private calendar data. A scene edit or device relink makes its prior permission ineffective until reviewed again.</p>}
          {config.remote.recovery_error&&<p className="setup-note">Resetting discards only the unreadable remote allowlist and leaves all remote control off. You can grant scenes again after review.</p>}
        </section>
        <button disabled={busy||remoteDirty} onClick={()=>void run(load)}>Refresh devices & results</button>
        {!config.devices.length&&<p className="setup-note">Connect and select the air purifier first. You can leave scenes off and continue setup.</p>}
      </>:<>
        <button disabled={busy} onClick={back}>← All scenes</button><h3>{sceneLabels[selected]} · {step==='actions'?'Choose actions':'Review & enable'}</h3>
        {step==='actions'?<>
          <p>Add only the changes you want. They run in the order below.</p>
          <label className="scene-choice">Device action<select value={choice} disabled={busy} onChange={event=>setChoice(event.target.value)}><option value="">Choose an available action…</option>{choices.map((row,index)=><option key={index} value={index}>{row.label}</option>)}</select></label>
          <button disabled={busy||choice===''||draft.actions.length>=8} onClick={()=>{const {label:_,...item}=choices[Number(choice)].item;edit({actions:[...draft.actions,item]});setChoice('');}}>Add action</button>
          <ol className="scene-actions">{draft.actions.map((item,index)=><li key={index}><span>{actionLabel(item,config.devices)}</span><div><button disabled={busy||index===0} aria-label={`Move action ${index+1} earlier`} onClick={()=>{const next=[...draft.actions];[next[index-1],next[index]]=[next[index],next[index-1]];edit({actions:next});}}>↑</button><button disabled={busy} aria-label={`Remove action ${index+1}`} onClick={()=>edit({actions:draft.actions.filter((_,i)=>i!==index)})}>Remove</button></div></li>)}</ol>
          {!draft.actions.length&&<p className="setup-note">No actions yet. Empty scenes stay off.</p>}
          <p className="setup-note">Only fresh purifier capabilities are offered. If an action is missing, return to device setup.</p>
          <button disabled={busy} onClick={()=>setStep('review')}>Review scene</button>
        </>:<>
          <ol className="scene-actions">{draft.actions.map((item,index)=><li key={index}>{actionLabel(item,config.devices)}</li>)}</ol>
          <label className="extras-toggle"><input type="checkbox" checked={draft.enabled} disabled={busy||!draft.actions.length} onChange={event=>edit({enabled:event.target.checked,automatic:event.target.checked?draft.automatic:false})}/><span>Enable this scene for explicit use</span></label>
          <label className="extras-toggle"><input type="checkbox" checked={draft.automatic} disabled={busy||!draft.enabled} onChange={event=>edit({automatic:event.target.checked})}/><span>{automaticLabels[selected]}</span></label>
          <p className="setup-note">{selected==='morning'||selected==='night'?'Uses only the Sleep calendars selected in Night & wake. Screen commands alone do not enable this calendar trigger.':'Uses the selected phone’s authenticated Bluetooth connection, not PIN unlock or Tailscale. Radio uncertainty does not count as leaving.'}</p>
          {(selected==='morning'||selected==='night')&&!config.calendar_ready&&<p className="setup-note">Fresh Sleep calendar data is not available yet. You may save the preference; no missed trigger will replay when it connects.</p>}
          {(selected==='arrive'||selected==='away')&&!config.phone_configured&&<p className="setup-note">Pair your phone before automatic presence scenes can work.</p>}
          <p className="setup-note">Manual device control takes priority for one hour. Scenes have a five-minute cooldown. Purifier speed/mode may turn it on. No remote appliance access is enabled here.</p>
          <div className="room-actions"><button disabled={busy} onClick={()=>setStep('actions')}>Edit actions</button><button disabled={busy} onClick={()=>void run(save)}>Save scene</button></div>
        </>}
        <button disabled={busy||dirty||!config.definitions[selected].enabled||config.definitions[selected].needs_review||!config.clock_trusted} onClick={()=>setConfirm('run')}>Run saved scene once…</button>
        {!config.clock_trusted&&<p className="setup-note">Scene execution waits for a verified system clock.</p>}
      </>}
      {last&&<section className="scene-result"><h3>{sceneLabels[last.scene]} · last run</h3><p>{last.interrupted?'Interrupted · never resumed':last.finished?'Finished — see each result':'In progress · refresh for results'}</p><ul>{last.steps.map((item,index)=><li key={index}><span>{actionLabel(item.action,config.devices)}</span><strong>{resultLabel(item.status)}</strong></li>)}</ul></section>}
      {(runningScene||config.busy)&&<button disabled={stopping} onClick={()=>void stop()}>{stopping?'Stopping…':'Stop scene'}</button>}
    </>}
    {confirm&&<div ref={confirmPanel} className="room-confirm" role="alertdialog" aria-modal="true" tabIndex={-1} aria-label={confirm==='discard'?'Discard scene edits':confirm==='remote-reset'?'Reset remote permissions':'Run scene confirmation'}><p>{confirm==='discard'?'Discard these unsaved edits?':confirm==='remote-reset'?'Discard the unreadable remote allowlist? This turns remote appliance actions off. Local scene settings and saved accounts are not changed.':'Run the saved actions now? Some actions may turn devices on. Already-sent actions cannot be undone by cancelling.'}</p><button disabled={busy} onClick={()=>{if(confirm==='discard'){setSelected(null);setConfirm(null);}else if(confirm==='remote-reset')void run(resetRemote);else void run(execute,true);}}>{confirm==='discard'?'Discard edits':confirm==='remote-reset'?'Reset and turn remote actions off':'Run once'}</button><button disabled={busy} onClick={()=>setConfirm(null)}>Keep reviewing</button></div>}
    {message&&<p role="status" className="setup-message">{message}</p>}
  </div>;
}
