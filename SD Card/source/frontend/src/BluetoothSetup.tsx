import {useEffect,useState,type FormEvent} from "react";
import {useSetupActivity} from "./setupActivity";
import {Bluetooth,Check,Smartphone} from "lucide-react";
import {TouchField} from "./TouchField";
import {forgetBluetoothPhone} from "./bluetoothForget";

type Phone={path:string;name:string;address:string;paired:boolean;trusted:boolean};
type Pairing={session:string|null;phase:string;devices:Phone[];selected:Phone|null;challenge:string|null;passkey:string|null;message:string;phone_address?:string|null;connection_status?:string;last_reconnect_at?:string|null;reconnect_attempts?:number};
const initial:Pairing={session:null,phase:"idle",devices:[],selected:null,challenge:null,passkey:null,message:""};
const previewPhone:Phone={path:"preview-phone",name:"Your iPhone",address:"Preview device",paired:false,trusted:false};
const active=(phase:string)=>["scanning","pairing","confirming"].includes(phase);

export function BluetoothSetup({demo,pinConfigured}:{demo:boolean;pinConfigured:boolean}){
  const [state,setState]=useState<Pairing>(initial),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState(""),[forgetMode,setForgetMode]=useState(false),[forgetPin,setForgetPin]=useState(""),[forgetError,setForgetError]=useState("");
  useSetupActivity(busy || active(state.phase));
  useEffect(()=>{
    if(demo)return;
    let stopped=false,timer:ReturnType<typeof setTimeout>;
    const controller=new AbortController();
    async function poll(){
      try{
        const response=await fetch("/api/v1/bluetooth/pairing",{signal:controller.signal});
        if(!response.ok)throw Error();
        const data=await response.json();if(!stopped){setState(data);setError("");}
      }catch{if(!stopped)setError("Bluetooth setup is unavailable. Check the local service.");}
      if(!stopped)timer=setTimeout(()=>void poll(),1500);
    }
    void poll();return ()=>{stopped=true;clearTimeout(timer);controller.abort();};
  },[demo]);
  async function action(name:string,body?:unknown){
    setBusy(true);setError("");
    try{
      if(demo){
        if(name==="start")setState({...initial,session:"demo",phase:"scanning",devices:[previewPhone],message:"Preview scan — no Bluetooth radio is used."});
        if(name==="select")setState(s=>({...s,phase:"confirming",selected:previewPhone,challenge:"demo-code",passkey:"042817",message:"Preview code only. On your Pi, confirm only if both screens show the same digits."}));
        if(name==="confirm"){
          const accepted=(body as {accepted:boolean}).accepted;
          setState(s=>({...s,phase:accepted?"complete":"cancelled",passkey:null,challenge:null,phone_address:accepted?previewPhone.address:null,message:accepted?"Preview complete — no device was paired or trusted.":"Preview pairing rejected."}));
        }
        if(name==="cancel")setState(s=>({...s,phase:"cancelled",passkey:null,challenge:null,message:"Preview pairing cancelled."}));
        return;
      }
      const response=await fetch(`/api/v1/bluetooth/pairing/${name}`,{method:"POST",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
      const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Please try again.");
      if(data.phase)setState(s=>({...s,...data}));
      else if(name==="confirm")setState(s=>({...s,phase:"pairing",passkey:null,challenge:null,message:"Waiting for the iPhone…"}));
    }catch(error){setError(error instanceof Error?error.message:"Pairing failed");}finally{setBusy(false);}
  }
  async function forgetPhone(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);setForgetError("");
    try{
      const result=await forgetBluetoothPhone(demo,forgetPin);
      setForgetPin("");setForgetMode(false);
      if(result.preview){setState({...initial,message:"Preview only — no Bluetooth pairing or saved phone was changed."});setNotice("Preview only — no Bluetooth pairing or saved phone was changed.");}
      else{setState(s=>({...s,phone_address:null,connection_status:"Not configured"}));setNotice(result.bond_removed?"The old pairing was removed. Find and pair your iPhone again when ready.":"The saved phone selection was cleared; no old bond was present.");}
    }catch(error){setForgetError(error instanceof Error?error.message:"Luma could not remove the phone pairing.");setForgetPin("");}finally{setBusy(false);}
  }
  return <section className="bluetooth-setup"><h2><Bluetooth/> Your iPhone</h2>
    <p className="setup-note">Open Settings → Bluetooth on your iPhone and keep it nearby. Select it below, then compare the pairing code on both screens. Pairing lets this phone become your privacy key; it does not route calls or music through Luma.</p>
    {state.phone_address && <><p className="setup-note">Selected phone: {state.phone_address}<br/>{state.connection_status || "Notification authorization is still required."}<br/>Luma checks this bonded iPhone and retries the connection automatically{state.last_reconnect_at?` · Last attempt ${new Date(state.last_reconnect_at).toLocaleTimeString()}`:''}.</p>
      {!forgetMode?<button disabled={busy} onClick={()=>{setError("");setNotice("");setForgetError("");setForgetMode(true);}}>Forget this iPhone…</button>:<form className="bluetooth-forget" onSubmit={forgetPhone}>
        <p>This removes only the selected iPhone’s Bluetooth pairing and clears it as Luma’s nearby-phone key. Other saved settings stay unchanged. Pair it again afterward.</p>
        {pinConfigured?<><TouchField label="Luma PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={forgetPin} onChange={setForgetPin} autoComplete="current-password" disabled={busy}/><button disabled={busy||forgetPin.length<4}>Confirm · forget iPhone</button></>:<p role="status">Set a Luma PIN in <strong>Privacy PIN</strong> above before you can forget a paired phone.</p>}
        {forgetError&&<p className="setup-message" role="alert">{forgetError}</p>}<button type="button" disabled={busy} onClick={()=>{setForgetPin("");setForgetError("");setForgetMode(false);}}>Cancel</button>
      </form>}
    </>}
    {!forgetMode && !active(state.phase) && <button disabled={busy} onClick={()=>void action("start")}><Smartphone/>{state.phone_address?"Choose another phone":"Find my iPhone"}</button>}
    {state.phase==="scanning" && <><p role="status">Looking for nearby devices…</p><div className="network-list">{state.devices.map(phone=><button key={phone.path} disabled={busy} onClick={()=>void action("select",{session:state.session,device:phone.path})}><Smartphone/><span>{phone.name}<small>{phone.address} · {phone.paired?(phone.trusted?"Previously paired":"Unfinished bond"):"Compare code to pair"}</small></span></button>)}</div><p className="setup-note">Discovery stops after 45 seconds. Device names are not proof of identity; check the matching code on your phone.</p></>}
    {state.phase==="confirming" && <div className="pairing-confirmation"><p>{state.selected?.name}</p><output aria-label="Pairing code">{state.passkey}</output><p>Does this code match your iPhone?</p><button disabled={busy} onClick={()=>void action("confirm",{session:state.session,challenge:state.challenge,accepted:true})}><Check/>Codes match — pair</button><button disabled={busy} onClick={()=>void action("confirm",{session:state.session,challenge:state.challenge,accepted:false})}>Doesn’t match — reject</button></div>}
    {active(state.phase) && <button disabled={busy} onClick={()=>void action("cancel",{session:state.session})}>Cancel pairing</button>}
    {state.message && <p className="setup-note" role="status">{state.message}</p>}
    {notice && <p className="setup-note" role="status">{notice}</p>}
    {error && <p className="setup-message" role="alert">{error}</p>}
    <p className="setup-note">After pairing, enable Share System Notifications for Luma on your iPhone if offered. Your calendar stays private until Luma verifies authorized notification access. No code confirmation is needed when selecting an already bonded, trusted phone.</p>
  </section>;
}
