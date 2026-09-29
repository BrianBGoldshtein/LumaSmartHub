import {useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Fan,Radio} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {TouchField} from './TouchField';
import {scrollSetupToTop} from './setupScroll';
import {useConfirmKeyboard} from './useConfirmKeyboard';
import {emptyFans,demoAdapter,demoEligibility,fanButtons,fanStatus,fanOutcome,pendingObservation,type FanId,type FanConfig,type IrDevice} from './fanState';
import './room.css';

type Step='overview'|'prepare'|'output'|'buttons'|'learn'|'test'|'observe';
class FanError extends Error {status:number;constructor(message:string,status:number){super(message);this.status=status;}}

export function FanSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const activity=useContext(SetupActivity),alive=useRef(true),working=useRef(false),request=useRef<AbortController|null>(null),panel=useRef<HTMLDivElement>(null);
  const [config,setConfig]=useState<FanConfig>(emptyFans),[ready,setReady]=useState(demo),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [step,setStep]=useState<Step>('overview'),[fanId,setFanId]=useState<FanId>('fan_1'),[key,setKey]=useState('power_off');
  const [devices,setDevices]=useState<IrDevice[]>([]),[choice,setChoice]=useState(''),[name,setName]=useState(''),[emitter,setEmitter]=useState('1');
  const [receiver,setReceiver]=useState(''),[frequency,setFrequency]=useState(''),[ack,setAck]=useState(false);
  const [expected,setExpected]=useState<boolean|null>(null),[other,setOther]=useState<boolean|null>(null),[receipt,setReceipt]=useState('');
  const [repeated,setRepeated]=useState<boolean|null>(null);
  const [confirm,setConfirm]=useState<'discard'|'remove'|null>(null),[now,setNow]=useState(Date.now());
  const confirmPanel=useConfirmKeyboard(!!confirm,()=>{if(!busy)setConfirm(null);});
  const fan=config.fans.find(row=>row.id===fanId)!,button=fanButtons.find(row=>row.key===key)!;
  const selected=devices.find(row=>row.id===choice),input=devices.find(row=>row.id===receiver);
  const dirty=step==='output'&&!!choice||step==='observe';
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useLayoutEffect(()=>scrollSetupToTop(panel.current),[step,fanId]);
  useEffect(()=>{alive.current=true;if(!demo)void run(load);return()=>{alive.current=false;request.current?.abort();};},[demo]);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);

  async function call(path='',body?:unknown){
    const controller=new AbortController();request.current=controller;
    const deadline=setTimeout(()=>controller.abort(),35000);
    try{
      const response=await fetch(`/api/v1/fans${path}`,{method:body===undefined?'GET':'POST',cache:'no-store',signal:controller.signal,
        headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
      const value=await response.json();
      if(!alive.current)throw Error('Setup closed.');
      if(!response.ok)throw new FanError(typeof value.detail==='string'?value.detail:'Fan setup could not finish.',response.status);
      return value;
    }finally{clearTimeout(deadline);if(request.current===controller)request.current=null;}
  }
  async function load(){if(!demo)setConfig(await call());setReady(true);}
  async function run(action:()=>Promise<void>){
    if(working.current)return;working.current=true;setBusy(true);setMessage('');
    try{await action();}catch(error){if(alive.current){
      if(error instanceof FanError){
        if(error.status===403){setConfig(emptyFans());setReady(false);reset('overview');setMessage(error.message);}
        else{
          // The durable receipt may have changed before the IR error. Read only
          // local saved state; never replay the attempted send or learn.
          try{const latest:FanConfig=await call();if(alive.current){setConfig(latest);setReady(true);setMessage(error.message);}}
          catch{if(alive.current){setConfig(emptyFans());setReady(false);reset('overview');setMessage('Could not reload saved fan results. Check both fans before another command. Nothing was retried.');}}
        }
      }
      else{setConfig(emptyFans());setReady(false);reset('overview');setMessage('Connection stopped. No command will be retried. Reload saved setup and check both fans before trying again.');}
    }}finally{working.current=false;if(alive.current)setBusy(false);}
  }
  function reset(next:Step){setStep(next);setChoice('');setName('');setFrequency('');setAck(false);setExpected(null);setOther(null);setRepeated(null);setConfirm(null);}
  function back(){if(dirty)setConfirm('discard');else reset('overview');}
  function preview(change:(copy:FanConfig)=>void){const copy=structuredClone(config);change(copy);copy.revision=crypto.randomUUID();setConfig(demoEligibility(copy));onSaved?.();}
  function body(){return {revision:config.revision,fan:fanId};}
  async function discover(){
    const found=demo?[demoAdapter]:(await call('/discover',{revision:config.revision})).devices as IrDevice[];
    setDevices(found);return found;
  }
  async function output(){await discover();setName(fan.name||(fanId==='fan_1'?'Desk fan':'Bedside fan'));setEmitter(fanId==='fan_1'?'1':'2');setChoice('');setStep('output');}
  async function saveOutput(){
    if(!selected||!name.trim())return;
    if(demo)preview(copy=>{for(const item of copy.fans){item.buttons.forEach(b=>{b.checks=0;b.scene_eligible=false;});}const row=copy.fans.find(item=>item.id===fanId)!;row.name=name.trim();row.route={device:selected,emitter:selected.emitter_selection?Number(emitter):null};row.buttons=[];});
    else{setConfig(await call('/select',{...body(),device_id:choice,name,emitter:selected.emitter_selection?Number(emitter):null}));onSaved?.();}
    reset('overview');
  }
  async function startLearn(){const found=await discover();setReceiver(found.find(row=>row.receive)?.id||'');setAck(false);setFrequency('');setStep('learn');}
  async function record(){
    if(demo)preview(copy=>{const row=copy.fans.find(item=>item.id===fanId)!;row.buttons=[...row.buttons.filter(item=>item.key!==key),{...button,checks:0,scene_eligible:false}];});
    else{setConfig(await call('/learn',{...body(),button:key,receiver_id:receiver,carrier_hz:frequency?Number(frequency):null}));onSaved?.();}
    reset('buttons');setMessage(demo?'Sample button saved. No recording occurred.':'Button saved. Next, test what it does.');
  }
  async function send(test:boolean){
    if(demo){const id=crypto.randomUUID();preview(copy=>{copy.fans.find(row=>row.id===fanId)!.last_command={id,button:key,kind:test?'test':'manual',status:'sent_unconfirmed',at:new Date().toISOString(),observed:false};});setReceipt(id);}
    else{const value=await call(test?'/test':'/command',{...body(),button:key,confirmed:true});setConfig(value.configuration);setReceipt(value.result.id);
      if(value.result.status!=='sent_unconfirmed'){setMessage('Outcome unknown. Check both fans. This test cannot count as a completed check.');return;}}
    setNow(Date.now());
    if(test){setExpected(null);setOther(null);setRepeated(null);setStep('observe');}else{setMessage('Command sent · device state remains unconfirmed.');setAck(false);}
  }
  async function observe(){
    if(demo)preview(copy=>{if(expected&&other){const item=copy.fans.find(row=>row.id===fanId)!.buttons.find(item=>item.key===key)!;item.checks=Math.min(2,item.checks+1);}else for(const row of copy.fans)row.buttons.forEach(item=>item.checks=0);copy.fans.find(row=>row.id===fanId)!.last_command!.observed=true;});
    else{setConfig(await call('/observe',{...body(),command_id:receipt,expected_state:expected,other_unchanged:other,repeat_same_state:repeated===true}));onSaved?.();}
    reset('buttons');setMessage(expected&&other?'Observation saved. Absolute controls need two successful checks before scene eligibility.':'Checks cleared. Adjust the output or relearn the button before testing again.');
  }
  async function remove(){
    if(demo)preview(copy=>{const blank=emptyFans().fans.find(row=>row.id===fanId)!;copy.fans=copy.fans.map(row=>row.id===fanId?blank:{...row,buttons:row.buttons.map(item=>({...item,checks:0,scene_eligible:false}))});});
    else{setConfig(await call('/remove',body()));onSaved?.();}reset('overview');
  }
  async function forget(){if(demo)preview(copy=>{const row=copy.fans.find(item=>item.id===fanId)!;row.buttons=row.buttons.filter(item=>item.key!==key);});else{setConfig(await call('/forget',{...body(),button:key}));onSaved?.();}reset('buttons');}
  const allOutputs=config.fans.every(row=>row.route);
  const observing=pendingObservation(fan.last_command,now);
  const repeatCheck=button.kind==='absolute'&&(fan.buttons.find(item=>item.key===key)?.checks??0)>=1;
  const yesNo=(title:string,value:boolean|null,set:(value:boolean)=>void)=><fieldset className="room-controls"><legend>{title}</legend><div className="room-actions"><button disabled={busy} aria-pressed={value===true} onClick={()=>set(true)}>Yes</button><button disabled={busy} aria-pressed={value===false} onClick={()=>set(false)}>No</button></div></fieldset>;

  return <div ref={panel} className="room-setup fan-setup"><h2><Fan aria-hidden="true"/> Your two fans</h2>
    {demo&&<p className="setup-note">Sample preview only. No hardware is recorded or controlled.</p>}
    {!ready?<><p role="status">{message||'Loading saved fan setup…'}</p><button disabled={busy} onClick={()=>void run(load)}>Reload saved setup</button></>:config.recovery_error?<p role="alert">Saved fan settings need recovery. They have not been overwritten; commands are disabled.</p>:<>
      {step!=='overview'&&<button disabled={busy} onClick={back}>← Fan overview</button>}
      {step==='overview'?<><p>Choose both outputs, then learn and test one button at a time. All automations stay off.</p><div className="fan-cards">{config.fans.map(row=><section className="room-device-card" key={row.id}><h3>{row.name||(row.id==='fan_1'?'Fan 1':'Fan 2')}</h3><p>{fanStatus(row)}</p>{fanOutcome(row.last_command)&&<p role="status">{fanOutcome(row.last_command)}</p>}<button disabled={busy} onClick={()=>{setFanId(row.id);reset(row.route?'buttons':'prepare');}}>{row.route?'Buttons & controls':'Set up fan'}</button></section>)}</div><p className="setup-note">Two remotes can use identical signals. Independent control must be tested in both directions. Infrared does not report a fan’s current state.</p><button disabled={busy} onClick={()=>void run(load)}>Reload saved setup</button></>:null}
      {step==='prepare'&&<><h3>Connect the IR hardware</h3><ol className="room-prerequisites"><li>Use the verified USB infrared adapter; leave the microphone’s GPIO connections alone.</li><li>Position each chosen emitter so it reaches its fan. Identical remotes may need separately controlled, shielded emitters.</li><li>Keep both fans and their original remotes visible for the later checks.</li></ol><p className="setup-note">Have not received the hardware? Choose another extra and return here later. No special fan or network hardware is assumed.</p><button disabled={busy} onClick={()=>void run(output)}><Radio aria-hidden="true"/> Discover USB adapters</button></>}
      {step==='output'&&<><h3>Choose this fan’s output</h3><div className="room-options">{devices.filter(row=>row.send).map(row=><button key={row.id} disabled={busy} aria-pressed={choice===row.id} onClick={()=>{activity.edited();setChoice(row.id);}}><strong>{row.name}</strong><span>{row.emitter_selection?'Selectable emitter channels':'One shared output'} · {row.serial_present?'Device identity available':'Review after each restart'}</span></button>)}</div>{!devices.some(row=>row.send)&&<p>No compatible transmitter found. Attach one and rediscover; a receive-only dongle cannot control a fan.</p>}
        {selected&&<form onSubmit={event=>{event.preventDefault();void run(saveOutput);}}><TouchField label="Fan name" value={name} onChange={setName} maxLength={40} required disabled={busy}/>{selected.emitter_selection&&<TouchField label="Emitter channel · from adapter documentation" value={emitter} onChange={setEmitter} mode="digits" maxLength={2} required disabled={busy}/>}<p className="setup-note">Channel availability is checked when testing. Selecting an output never sends a command.</p><button disabled={busy||!name.trim()||(selected.emitter_selection&&(!/^\d+$/.test(emitter)||Number(emitter)<1||Number(emitter)>32))}>Save output</button></form>}<button disabled={busy} onClick={()=>void run(async()=>{await discover();setChoice('');})}>Rediscover</button></>}
      {step==='buttons'&&<><h3>{fan.name}</h3>{fanOutcome(fan.last_command)&&<p role="status">{fanOutcome(fan.last_command)}</p>}{!allOutputs&&<p className="setup-note">Choose both fan outputs before learning buttons, so checks can cover both directions.</p>}{fan.needs_output_review&&<div className="room-confirm"><p>This adapter has no serial identity. Check its USB port and emitter wiring after each restart.</p><button disabled={busy} onClick={()=>void run(async()=>{await discover();setMessage('Adapter list refreshed. Check the wiring, then confirm the output.');})}>Rediscover adapter</button><button disabled={busy||!devices.length} onClick={()=>void run(async()=>{if(demo)preview(copy=>{copy.fans.find(row=>row.id===fanId)!.needs_output_review=false;});else setConfig(await call('/review-output',body()));})}>I checked this output</button></div>}
        <div className="fan-buttons">{fan.buttons.map(item=><div className="room-device-card" key={item.key}><strong>{item.label}</strong><span>{item.kind==='absolute'?`${item.checks}/2 checks`:'Manual confirmation only'}{item.scene_eligible?' · scene-eligible, not enabled':''}</span><button disabled={busy} onClick={()=>{setKey(item.key);setAck(false);setStep('test');}}>Test / use</button></div>)}</div>
        {observing&&<button disabled={busy} onClick={()=>{setKey(fan.last_command!.button);setReceipt(fan.last_command!.id);setExpected(null);setOther(null);setStep('observe');}}>Finish last test observation</button>}
        <label className="fan-select">Button to learn<select value={key} disabled={busy||!allOutputs} onChange={event=>setKey(event.target.value)}>{fanButtons.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label><button disabled={busy||!allOutputs} onClick={()=>void run(startLearn)}>Learn this button</button><div className="room-actions"><button disabled={busy} onClick={()=>{setAck(false);setStep('prepare');}}>Change output</button><button disabled={busy} onClick={()=>setConfirm('remove')}>Remove fan</button></div></>}
      {step==='learn'&&<><h3>Learn “{button.label}”</h3><p>{button.kind==='absolute'?'Use a dedicated button that always selects this exact state. If one button switches on AND off, learn “Power toggle” instead.':'This relative/toggle control will require confirmation each time and cannot run in a scene.'}</p><label className="fan-select">Receiver<select disabled={busy} value={receiver} onChange={event=>setReceiver(event.target.value)}><option value="">Choose receiver</option>{devices.filter(row=>row.receive).map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label>{input&&!input.measure_carrier&&<TouchField label="Documented carrier frequency · Hz" value={frequency} onChange={setFrequency} mode="digits" maxLength={5} required disabled={busy}/>}
        <p>Point the original remote at the receiver. Start recording, then press the requested button once briefly. Recording ends within ten seconds.</p><label className="extras-toggle"><input type="checkbox" disabled={busy} checked={ack} onChange={event=>setAck(event.target.checked)}/><span>I have identified the correct remote button.</span></label>
        <button disabled={busy||!input||!ack||(!input.measure_carrier&&(!/^\d+$/.test(frequency)||Number(frequency)<20000||Number(frequency)>60000))} onClick={()=>void run(record)}>{busy?'Recording…':'Start recording'}</button>{busy&&<button onClick={()=>request.current?.abort()}>Cancel recording</button>}<p className="setup-note">Relearning replaces only this saved button and clears its checks. No remote recordings leave the hub.</p></>}
      {step==='test'&&<><h3>{fan.name} · {button.label}</h3><p>Observe both fans. For a dedicated-state button, check that the intended state is reached; for a toggle, check the expected change. The other fan must remain unaffected.</p><label className="extras-toggle"><input type="checkbox" disabled={busy} checked={ack} onChange={event=>setAck(event.target.checked)}/><span>I am ready for one command and can observe both fans.</span></label><div className="room-actions"><button disabled={busy||!ack} onClick={()=>void run(()=>send(true))}>Send one test</button><button disabled={busy||!ack||!fan.buttons.find(item=>item.key===key)?.checks} onClick={()=>void run(()=>send(false))}>Send once · no test</button><button disabled={busy} onClick={()=>void run(forget)}>Forget this button</button></div><p className="setup-note">Every send is unconfirmed until you look at the fan. Absolute buttons require two successful tests, including from the already-selected state, before scene eligibility. Test/manual commands pause that fan’s scene changes for one hour.</p></>}
      {step==='observe'&&<><h3>What happened?</h3>{observing?<>{yesNo(`${fan.name}: expected state or change?`,expected,setExpected)}{yesNo('Other fan stayed unchanged?',other,setOther)}{repeatCheck&&yesNo('Was this fan already in the requested state, and did it stay there?',repeated,setRepeated)}<button disabled={busy||expected===null||other===null||!!(repeatCheck&&expected&&other&&repeated!==true)} onClick={()=>void run(observe)}>Save observation</button><p className="setup-note">Answer within two minutes. A failed check clears independence checks so an unsafe setup cannot become automatic.</p></>:<><p>This observation window ended or the command outcome is unknown. Run a fresh test when ready.</p><button disabled={busy} onClick={()=>reset('buttons')}>Back to buttons</button></>}</>}
      {confirm&&<div ref={confirmPanel} className="room-confirm" role="alertdialog" aria-modal="true" tabIndex={-1} aria-label={confirm==='remove'?'Remove fan':'Discard unsaved setup'}><p>{confirm==='remove'?'Remove this fan’s learned buttons and reset both-direction checks? The physical fan is not changed.':'Leave without saving these edits or test observations? Previously saved buttons remain.'}</p><div className="room-actions"><button disabled={busy} onClick={()=>confirm==='remove'?void run(remove):reset('overview')}>{confirm==='remove'?'Remove fan':'Discard and leave'}</button><button disabled={busy} onClick={()=>setConfirm(null)}>Keep working</button></div></div>}
      {message&&<p className="setup-message" role="status">{message}</p>}
    </>}
  </div>;
}
