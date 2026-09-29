export interface Departure {
  key:string; title:string; start:string; depart_at:string;
  prep_minutes:number; travel_minutes:number; color?:string|null;
}
export function departureText(reminder:Departure,serverTime:string,elapsedMs=0){
  const now=Date.parse(serverTime)+Math.max(0,elapsedMs);
  if(!Number.isFinite(now) || now>=Date.parse(reminder.start))return null;
  const minutes=Math.ceil((Date.parse(reminder.depart_at)-now)/60000);
  return Number.isFinite(minutes)?minutes>0?`Leave in ${minutes} min`:'Time to leave':null;
}
export function departureMinutes(value:string){
  if(!/^\d{1,3}$/.test(value) || Number(value)>240)throw Error('Choose whole minutes from 0 to 240.');
  return Number(value);
}
export interface DeparturePreferences {
  departure_enabled:boolean; departure_calendar_ids:string[]; departure_include_virtual:boolean;
  departure_prep_minutes:string; departure_travel_minutes:string;
}
export function departurePreferences(raw:Record<string,unknown>={}):DeparturePreferences{
  return {departure_enabled:raw.departure_enabled===true,departure_calendar_ids:Array.isArray(raw.departure_calendar_ids)?raw.departure_calendar_ids.filter((id):id is string=>typeof id==='string'):[],
    departure_include_virtual:raw.departure_include_virtual===true,departure_prep_minutes:String(raw.departure_prep_minutes??5),departure_travel_minutes:String(raw.departure_travel_minutes??10)};
}
export function departurePatch(values:DeparturePreferences){
  if(values.departure_enabled && !values.departure_calendar_ids.length)throw Error('Choose at least one calendar, or leave reminders off.');
  return {...values,departure_prep_minutes:departureMinutes(values.departure_prep_minutes),departure_travel_minutes:departureMinutes(values.departure_travel_minutes)};
}
