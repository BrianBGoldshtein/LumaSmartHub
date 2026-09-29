import {useEffect,useState} from "react";
import {WifiOff,Wifi} from "lucide-react";
import {networkNotice,type NetworkStatus} from "./networkStatus";
import {setupLink} from "./setupTheme";
import type {Theme} from "./types";

export function NetworkNotice({demo,theme}:{demo:boolean;theme:Theme}){
  const [status,setStatus]=useState<NetworkStatus>();
  useEffect(()=>{
    if(demo){
      const fixture=new URLSearchParams(location.search).get("network");
      if(fixture && ["portal","offline","limited"].includes(fixture))setStatus({state:fixture as NetworkStatus["state"],stale:false,checking_enabled:true,checked_at:null});
      return;
    }
    let stopped=false;
    const controller=new AbortController();
    async function poll(){
      try{
        const response=await fetch("/api/v1/network/status",{signal:controller.signal});
        if(!response.ok)throw Error();
        const next=await response.json();if(!stopped)setStatus(next);
      }catch{if(!stopped)setStatus(undefined);}
    }
    void poll();const timer=setInterval(()=>void poll(),30000);
    return ()=>{stopped=true;controller.abort();clearInterval(timer);};
  },[demo]);
  const label=networkNotice(status);
  if(!label)return null;
  return <a className="network-notice" href={`${setupLink(demo,theme,"device")}#network`} aria-label={`${label}. Open Wi-Fi settings.`}>
    {status?.state==="offline"?<WifiOff/>:<Wifi/>}<span>{label}</span>
  </a>;
}
