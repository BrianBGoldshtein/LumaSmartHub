import {useEffect,useState} from 'react';

type Cooling={available:boolean;mode:string;usb_power:string;qualified:boolean;probe:string;reason:string;on_celsius?:number;off_celsius?:number;standby_override?:boolean};
type Request=<T>(method:string,path:string,body?:unknown)=>Promise<T>;
export function FanControlPanel({demo=false,request}:{demo?:boolean;request:Request}){
  const [status,setStatus]=useState<Cooling|null>(null),[busy,setBusy]=useState(false),[ack,setAck]=useState(false),[message,setMessage]=useState('');
  const [pollError,setPollError]=useState(false);
  useEffect(()=>{
    if(demo){setStatus({available:false,mode:'always_on',usb_power:'on',qualified:false,probe:'idle',reason:'Preview · no USB power is changed'});return;}
    let live=true,timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{
      if(document.visibilityState==='visible')try{const result=await request<Cooling>('GET','device/fan');if(live){setStatus(result);setPollError(false);}}
      catch{if(live){setStatus(null);setPollError(true);}}
      if(live)timer=setTimeout(()=>void poll(),2000);
    };
    void poll();return()=>{live=false;clearTimeout(timer);};
  },[demo,request]);
  async function action(action:string){
    setBusy(true);setMessage('');
    try{setStatus(await request<Cooling>('POST','device/fan',{action,acknowledged:ack}));setAck(false);}
    catch(error){setMessage(error instanceof Error?error.message:'Cooling change failed. Keep USB powered.');}
    finally{setBusy(false);}
  }
  return <section className="fan-control"><h2>USB fan cooling</h2>
    <p>On at {status?.on_celsius??70}°C · off at {status?.off_celsius??60}°C. No periodic USB discovery cycles.</p>
    <p role="status"><b>USB power: {status?.usb_power??'checking'}</b>{status&&<><br/>Mode: {status.mode==='automatic'?'Automatic cooling':'Keep USB on'}</>}<br/>{status?.reason}</p>
    <p className="setup-note">Standby keeps USB power on whenever no registered phone is connected, so the mouse stays available. Your saved cooling mode resumes when a verified phone returns. All four USB ports switch together. Use your phone remote’s Keep USB on control before using an unpowered mouse or plugging in a USB stick while a phone is connected. Detected storage and updates also keep power on.</p>
    <button disabled={busy||demo} onClick={()=>void action('always_on')}>Keep USB on · mouse & drives</button>
    <button disabled={busy||demo||!status?.available||!status.qualified||status.probe==='running'} onClick={()=>void action('automatic')}>Automatic cooling</button>
    <details><summary>Verify physical fan switching</summary>
      <p>Remove USB drives first. Leave the fan’s physical switch on. This test cuts USB power for five seconds, then restores it. Watch the fan; reported power bits alone cannot prove it stopped.</p>
      <label><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>{status?.probe==='confirm'?'I saw the fan stop and restart.':'I understand the mouse will temporarily disconnect; USB drives are removed.'}</label>
      {status?.probe==='confirm'?<button disabled={busy||demo||!ack||status.standby_override} onClick={()=>void action('confirm')}>Confirm fan stopped and restarted</button>:
        <button disabled={busy||demo||!ack||!status?.available||status.standby_override||status.probe==='running'} onClick={()=>void action('probe')}>Test five-second USB interruption</button>}
      <p className="setup-note">Connect a registered phone before testing; standby never interrupts mouse power. Automatic control stays disabled until this test is confirmed. Retest after changing hardware. No RPM sensor is installed.</p>
    </details>{pollError&&<p role="alert">Cooling status unavailable. Leave the fan powered continuously.</p>}{message&&<p role="alert">{message}</p>}
  </section>;
}
