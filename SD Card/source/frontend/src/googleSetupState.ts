export function googleCallbackMessage(flag:unknown):string {
  return flag==="1" ? "Sign-in didn’t finish. Try again. Your saved connection has not changed." : "";
}

export type GoogleStatus = {configured:boolean;authorized:boolean;task_updates:boolean;reconnect_required?:boolean};
export type GoogleCalendar = {id:string;summary:string;background_color?:string;selected?:boolean;primary?:boolean;access_role?:string};
export type GoogleEventColor = {id:string;background:string};
export type GoogleSettings = {visible_calendar_ids:string[];sleep_calendar_ids:string[];todo_calendar_id:string|null;todo_completed_color_id:string|null;sleep_event_title:string;theme:string};
type GoogleSetupReader = {
  status:()=>Promise<GoogleStatus>;
  settings:()=>Promise<GoogleSettings>;
  calendars:()=>Promise<GoogleCalendar[]>;
  colors:()=>Promise<GoogleEventColor[]>;
};
export const googleCatalogError = "Google calendars could not refresh. If authorization expired or was revoked, use Reconnect Google. Your saved selections and events have not been changed.";

// Local configuration must render before requesting protected Google data.
// A rejected refresh token must never hide the action needed to replace it.
export async function loadGoogleSetup(read:GoogleSetupReader,onCore:(status:GoogleStatus,settings:GoogleSettings)=>void) {
  const [status,settings] = await Promise.all([read.status(),read.settings()]);
  onCore(status,settings);
  if(!status.authorized)return {settings,catalog:null,error:""};
  try {
    const [calendars,colors] = await Promise.all([read.calendars(),read.colors()]);
    return {settings,catalog:{calendars,colors},error:""};
  } catch {
    // Do not surface arbitrary provider errors or substitute an empty catalog
    // that could subsequently overwrite the owner's saved calendar choices.
    return {settings,catalog:null,error:googleCatalogError};
  }
}

export function calendarSelection(ids:string[],calendars:GoogleCalendar[]):string[] {
  return Array.from(new Set(ids.map(id=>id==="primary" ? calendars.find(c=>c.primary)?.id || id : id)));
}

export function canEditGoogleCalendars(status:GoogleStatus,catalogReady:boolean):boolean {
  return status.authorized && catalogReady;
}
