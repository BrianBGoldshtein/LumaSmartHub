import {useEffect,useRef,useState} from 'react';
import {fanControls,type Cooling} from './fanControls';

type Request=<T>(method:string,path:string,body?:unknown)=>Promise<T>;
export function FanControlPanel({demo=false,request}:{demo?:boolean;request:Request}){
  const [status,setStatus]=useState<Cooling|null>(null),[busy,setBusy]=useState(false),[ack,setAck]=useState(false),[message,setMessage]=useState('');
  const [pollError,setPollError]=useState(false);
  const [connection,setConnection]=useState<'usb'|'gpio12'|null>(null),[wiringAck,setWiringAck]=useState(false);
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
  async function action(action:string,wiring=false){
    if(mutation.current.pending)return;
    mutation.current.pending=true;mutation.current.epoch++;
    setBusy(true);setMessage('');
    try{setStatus(await request<Cooling>('POST','device/fan',{action,acknowledged:wiring?wiringAck:ack}));setConnection(null);}
    catch(error){setMessage(error instanceof Error?error.message:'Cooling change failed. Keep USB powered.');}
    finally{mutation.current.pending=false;setAck(false);setWiringAck(false);setBusy(false);}
  }
  const controls=fanControls(status,busy,demo,ack);
  const gpio=status?.backend==='gpio12',selected=connection??status?.backend??'usb';
  return <section className="fan-control"><h2>Fan cooling</h2>
    <p>On at {status?.on_celsius??70}°C · off at {status?.off_celsius??60}°C. No periodic USB discovery cycles.</p>
    <p role="status"><b>{gpio?'Fan power':'USB power'}: {(gpio?status?.fan_power:status?.usb_power)??'checking'}</b>{status&&<><br/>Mode: {status.mode==='automatic'?'Automatic cooling':gpio?'Keep fan on':'Keep USB on'}</>}{gpio&&<><br/>BCM12 switch · USB power: {status?.usb_power}</>}<br/>{status?.reason}</p>
    {gpio?<p className="setup-note">Only the inline fan switch changes. USB Wi-Fi, mouse and drives stay powered. Automatic cooling continues in standby; a software update, missing temperature or lost controller heartbeat keeps the fan on. The switch defaults off before the service starts and is not a hardware thermostat.</p>:<>
    <p className="setup-note">Standby keeps USB power on whenever no registered phone is connected, so the mouse stays available. Your saved cooling mode resumes when a verified phone returns. All four USB ports switch together. Use your phone remote’s Keep USB on control before using an unpowered mouse or plugging in a USB stick while a phone is connected. Detected storage and updates also keep power on.</p>
    <p className="setup-note">A connected USB Wi-Fi or Ethernet adapter keeps all USB power on, even when idle, so cooling cannot interrupt its network. The USB fan therefore runs continuously while that adapter is attached. Select Keep USB on before plugging one in.</p>
    </>}
    <button disabled={busy||demo} onClick={()=>void action('always_on')}>{gpio?'Keep fan on':'Keep USB on · mouse & drives'}</button>
    <button disabled={controls.automaticDisabled} onClick={()=>void action('automatic')}>Automatic cooling</button>
    <details><summary>Verify physical fan switching</summary>
      <p>{gpio?'Leave the fan’s physical switch on. Only the fan pauses for five seconds; USB Wi-Fi, mouse and drives remain powered.':'Remove USB drives first. Leave the fan’s physical switch on. This test cuts USB power for five seconds, then restores it.'} Watch the fan; reported control bits alone cannot prove it stopped.</p>
      <label><input type="checkbox" checked={ack} disabled={busy} onChange={event=>setAck(event.target.checked)}/>{status?.probe==='confirm'?'I saw the fan stop and restart.':gpio?'I will watch the fan stop and restart; it is wired to the BCM12 switch.':'I understand the mouse will temporarily disconnect; USB drives are removed.'}</label>
      {status?.probe==='confirm'?<button disabled={controls.confirmDisabled} onClick={()=>void action('confirm')}>Confirm fan stopped and restarted</button>:
        <button disabled={controls.testDisabled} onClick={()=>void action('probe')}>{controls.testLabel}</button>}
      {status&&!status.available&&<p className="setup-note">{gpio?'If the fan is not running, connect it directly to powered USB.':'USB is kept on after a fault.'} Check the acknowledgment, retry the physical test, then confirm only if you saw the fan stop and restart. Automatic cooling stays disabled until confirmation.</p>}
      <p className="setup-note">Connect a registered phone before testing. Automatic control stays disabled until this test is confirmed. Retest after changing hardware. No RPM sensor is installed.</p>
    </details>
    <details className="fan-connection"><summary>Move fan to a GPIO switch</summary>
      <ol><li>Use the 8086 USB2 Power Switch, 5V supply and a fan within its current rating. Shut down and remove Pi power before wiring.</li>
      <li>Pi USB → switch’s micro-USB input. Fan → switch’s USB-A output. Leave the fan’s own switch on.</li>
      <li>BCM12 (header pin 32, or ReSpeaker V1 digital Grove GPIO12) → EN. Ground → GND. Leave the board’s 5V header pin unconnected. Never connect 5V to a GPIO signal.</li>
      <li>Boot, select the connection below, acknowledge the wiring, then run and confirm the physical fan test above. USB Wi-Fi stays powered in GPIO mode.</li></ol>
      <label>Fan connection<select value={selected} disabled={busy||demo} onChange={event=>{setConnection(event.target.value as 'usb'|'gpio12');setWiringAck(false);}}><option value="usb">Existing USB hub switching</option><option value="gpio12">BCM12 · inline USB switch</option></select></label>
      <label><input type="checkbox" checked={wiringAck} disabled={busy||demo} onChange={event=>setWiringAck(event.target.checked)}/>I have wired the fan for this connection; the switch uses a 3.3V active-high EN input.</label>
      <button disabled={busy||demo||!status||!wiringAck||selected===(status.backend??'usb')||status.probe==='running'} onClick={()=>void action(selected==='gpio12'?'select_gpio':'select_usb',true)}>Use this fan connection</button>
      <p className="setup-note">Changing connection clears its test approval and starts in Keep on mode. Return the fan plug directly to Pi USB before selecting the existing USB connection. The microphone can stay installed; GPIO12 must be unused by any other device.</p>
    </details>{pollError&&<p role="alert">Cooling status unavailable. Leave the fan powered continuously.</p>}{message&&<p role="alert">{message}</p>}
  </section>;
}
