import {useEffect,useRef,useState} from 'react';
import {fanControls,type Cooling} from './fanControls';

type Request=<T>(method:string,path:string,body?:unknown)=>Promise<T>;
export function FanControlPanel({demo=false,request}:{demo?:boolean;request:Request}){
  const [status,setStatus]=useState<Cooling|null>(null),[busy,setBusy]=useState(false),[ack,setAck]=useState(false),[message,setMessage]=useState('');
  const [pollError,setPollError]=useState(false);
  const mutation=useRef({epoch:0,pending:false});
  useEffect(()=>{
    if(demo){setStatus({available:false,mode:'always_on',usb_power:'on',qualified:false,probe:'idle',reason:'Preview · no USB power is changed'});return;}
    let live=true,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      const epoch=mutation.current.epoch;
      if(document.visibilityState==='visible'&&!mutation.current.pending)try{const result=await request<Cooling>('GET','device/fan');if(live&&epoch===mutation.current.epoch&&!mutation.current.pending){setStatus(result);setPollError(false);}}
      catch{if(live&&epoch===mutation.current.epoch&&!mutation.current.pending){setStatus(null);setPollError(true);}}
      if(live)timer=setTimeout(()=>void poll(),2000);
    };
    void poll();return()=>{live=false;clearTimeout(timer);};
  },[demo,request]);
  async function action(action:string){
    if(mutation.current.pending)return;
    mutation.current.pending=true;mutation.current.epoch++;
    setBusy(true);setMessage('');
    try{setStatus(await request<Cooling>('POST','device/fan',{action,acknowledged:ack}));}
    catch(error){setMessage(error instanceof Error?error.message:'Cooling change failed. Keep USB powered.');}
    finally{mutation.current.pending=false;setAck(false);setBusy(false);}
  }
  const controls=fanControls(status,busy,demo,ack);
  return <section className="fan-control"><h2>USB fan cooling</h2>
    <p>On at {status?.on_celsius??70}°C · off at {status?.off_celsius??60}°C. No periodic USB discovery cycles.</p>
    <p role="status"><b>USB power: {status?.usb_power??'checking'}</b>{status&&<><br/>Mode: {status.mode==='automatic'?'Automatic cooling':'Keep USB on'}</>}<br/>{status?.reason}</p>
    <p className="setup-note">Standby keeps USB power on whenever no registered phone is connected, so the mouse stays available. Your saved cooling mode resumes when a verified phone returns. All four USB ports switch together. Use your phone remote’s Keep USB on control before using an unpowered mouse or plugging in a USB stick while a phone is connected. Detected storage and updates also keep power on.</p>
    <button disabled={busy||demo} onClick={()=>void action('always_on')}>Keep USB on · mouse & drives</button>
    <button disabled={controls.automaticDisabled} onClick={()=>void action('automatic')}>Automatic cooling</button>
    <details><summary>Verify physical fan switching</summary>
      <p>Remove USB drives first. Leave the fan’s physical switch on. This test cuts USB power for five seconds, then restores it. Watch the fan; reported power bits alone cannot prove it stopped.</p>
      <label><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>{status?.probe==='confirm'?'I saw the fan stop and restart.':'I understand the mouse will temporarily disconnect; USB drives are removed.'}</label>
      {status?.probe==='confirm'?<button disabled={controls.confirmDisabled} onClick={()=>void action('confirm')}>Confirm fan stopped and restarted</button>:
        <button disabled={controls.testDisabled} onClick={()=>void action('probe')}>{controls.testLabel}</button>}
      {status&&!status.available&&<p className="setup-note">USB is kept on after a fault. Check the acknowledgment, retry the physical test, then confirm only if you saw the fan stop and restart. Automatic cooling stays disabled until confirmation.</p>}
      <p className="setup-note">Connect a registered phone before testing; standby never interrupts mouse power. Automatic control stays disabled until this test is confirmed. Retest after changing hardware. No RPM sensor is installed.</p>
    </details>{pollError&&<p role="alert">Cooling status unavailable. Leave the fan powered continuously.</p>}{message&&<p role="alert">{message}</p>}
  </section>;
}
