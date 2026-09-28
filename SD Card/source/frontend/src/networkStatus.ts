export type NetworkStatus={state:"unknown"|"unavailable"|"offline"|"portal"|"limited"|"online";stale:boolean;checking_enabled:boolean;checked_at:string|null};
export function networkNotice(status?:NetworkStatus):string|null{
  if(!status || status.stale)return null;
  if(status.state==="portal")return "Network sign-in";
  if(status.state==="offline")return "Offline · Saved view";
  if(status.state==="limited")return "Limited internet";
  return null;
}
export function networkDescription(status?:NetworkStatus):string{
  if(!status || status.stale)return "Checking connection…";
  if(status.state==="online")return "Internet available";
  if(status.state==="portal")return "Network sign-in may be required. Open sign-in, review the terms, then check again.";
  if(status.state==="offline")return "No network connection. Your dashboard settings and saved information remain on this Pi.";
  if(status.state==="limited")return "Connected, but internet access is limited. You may need to sign in again.";
  if(status.state==="unavailable")return "Network status is unavailable. Check the local network service.";
  return "Internet access has not been verified.";
}
