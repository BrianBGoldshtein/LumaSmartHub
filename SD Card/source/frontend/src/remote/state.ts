import type {CalendarEvent,Weather,Theme} from '../types';
import type {TimerState} from '../timerState';
import type {Departure} from '../departureState';
import type {DeviceTemperature} from '../temperatureState';
export type Preview={profile_id:string;role:'primary'|'secondary';nickname:string;server_time:string;privacy_redacted:boolean;weather:Weather|null;timer:TimerState;
  device_temperature?:DeviceTemperature;departure:Departure|null;todo_controls:{can_update:boolean;stale?:boolean};calendar:CalendarEvent[];ongoing:CalendarEvent[];todos:CalendarEvent[];
  settings:{theme:Theme;timezone:string;weather_location_label:string};state:{active_page:string;display_power:string;phone_connected:boolean}};
export type RemoteSettings={theme:Theme;brightness:number;volume:number;timezone:string;latitude:number|null;longitude:number|null;
  weather_location_label:string;orientation:string;voice_enabled:boolean;night_clock_enabled:boolean;night_brightness:number;
  notification_chime_enabled:boolean;notification_chime_volume:number;visible_calendar_ids:string[];todo_calendar_id:string|null;
  todo_completed_color_id:string|null;sleep_calendar_ids:string[];sleep_event_title:string;departure_calendar_ids:string[];
  departure_enabled:boolean;departure_include_virtual:boolean;departure_prep_minutes:number;departure_travel_minutes:number;
  timer_focus_minutes:number;timer_break_minutes:number;weather_nudges_enabled:boolean;
  weather_rain_percent:number;weather_gust_mph:number;weather_hot_f:number;weather_cold_f:number;
  cycle:{page:string;seconds:number}[]};
export type PersonalSettings=Pick<RemoteSettings,'theme'|'timezone'|'weather_location_label'|'visible_calendar_ids'|'todo_calendar_id'|'todo_completed_color_id'|'departure_calendar_ids'|'departure_enabled'|'departure_include_virtual'|'departure_prep_minutes'|'departure_travel_minutes'>;
export const personalSteps=['remote','google','calendars','ready'] as const;
export type PersonalSetup={profile_id:string;nickname:string;setup_stage:typeof personalSteps[number];wall_share_approved:boolean};
export function primaryRemote(value:unknown):boolean{
  return !!value&&typeof value==='object'&&(value as Partial<Preview>).profile_id==='primary'&&(value as Partial<Preview>).role==='primary';
}
export type UpdateStatus={current_version:string;state?:string;phase?:string;message?:string;target_version?:string;elapsed_seconds?:number};
export type Candidate={state:string;current_version:string;version?:string;release_notes?:string;candidate_id?:string;expires_in_seconds?:number};
export function updateOutcome(status:UpdateStatus,target:string):string|null{
  if(status.target_version!==target)return null;
  if(status.state==='installed'&&status.current_version===target)return `Luma ${target} is installed.`;
  if(status.state==='failed')return `Update ${target} did not finish. Luma reports version ${status.current_version}; check Software before retrying.`;
  return null; // Accepted, reconnecting and old progress are not success.
}
export function safeColor(color:unknown):string{return typeof color==='string'&&/^#[0-9a-f]{6}$/i.test(color)?color:'#b4e1d7';}
export function enrollTicket(value:string,origin:string):string|null{
  try{const url=new URL(value);if(url.origin!==origin||url.pathname!=='/remote/'||url.search)return null;
    const ticket=new URLSearchParams(url.hash.slice(1)).get('enroll');return ticket&&/^[A-Za-z0-9_-]{43}$/.test(ticket)?ticket:null;
  }catch{return null;}
}
export function clockText(date:string,zone:string):string{
  return new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit',timeZone:zone}).format(new Date(date));
}
export function upcoming(events:CalendarEvent[],now:string){
  const timestamp=Date.parse(now);return events.filter(event=>Date.parse(event.end)>timestamp)
    .sort((a,b)=>Date.parse(a.start)-Date.parse(b.start));
}
