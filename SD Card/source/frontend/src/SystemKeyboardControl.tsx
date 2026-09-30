import {useState} from "react";

/** Native Wayland keyboard: no credentials or keystrokes pass through Luma. */
export function SystemKeyboardControl({demo}:{demo:boolean}) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState("");
  async function request(visible:boolean){
    setBusy(true);
    try{
      if(demo){setMessage("Preview only — the system keyboard opens on the Pi.");return;}
      const response=await fetch("/api/v1/device/keyboard",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({visible})});
      const result=await response.json();
      if(!response.ok)throw Error(result.detail || "Keyboard unavailable");
      setMessage(visible?"Keyboard requested. Wait for it to appear, then open sign-in. It closes after 15 minutes or when the screen sleeps.":"Keyboard close requested.");
    }catch(error){setMessage(error instanceof Error?error.message:"Keyboard unavailable");}
    finally{setBusy(false);}
  }
  return <div className="system-keyboard-control">
    <p className="setup-note">Need to type on an external sign-in page? Open the system keyboard first. Close it here when finished.</p>
    <button disabled={busy} onClick={()=>void request(true)}>Open system keyboard</button>
    <button disabled={busy} onClick={()=>void request(false)}>Close system keyboard</button>
    {message && <p className="setup-message" role="status">{message}</p>}
  </div>;
}
