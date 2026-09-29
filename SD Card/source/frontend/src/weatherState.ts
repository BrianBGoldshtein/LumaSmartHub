export function precipitationLabel(value:number|null|undefined){
  return typeof value==='number' && Number.isFinite(value) && value>=0 && value<=100 ? `${Math.round(value)}%` : '—';
}

export interface ExtraPreferences {
  timer_focus_minutes:string;
  timer_break_minutes:string;
  weather_nudges_enabled:boolean;
  weather_rain_percent:string;
  weather_gust_mph:string;
  weather_hot_f:string;
  weather_cold_f:string;
}
export type ExtraTask='timer'|'weather';
export function extraPreferences(data:Record<string,unknown>={}):ExtraPreferences{
  return {
    timer_focus_minutes:String(data.timer_focus_minutes ?? 25),timer_break_minutes:String(data.timer_break_minutes ?? 5),
    weather_nudges_enabled:data.weather_nudges_enabled===true,weather_rain_percent:String(data.weather_rain_percent ?? 50),
    weather_gust_mph:String(data.weather_gust_mph ?? 25),weather_hot_f:String(data.weather_hot_f ?? 90),weather_cold_f:String(data.weather_cold_f ?? 45),
  };
}
export function extraPatch(task:ExtraTask,values:ExtraPreferences):Record<string,number|boolean>{
  const whole=(key:keyof ExtraPreferences,low:number,high:number,label:string)=>{
    const raw=String(values[key]);const number=Number(raw);
    if(!/^-?\d+$/.test(raw) || !Number.isInteger(number) || number<low || number>high)throw Error(`${label}: choose a whole number from ${low} to ${high}.`);
    return number;
  };
  if(task==='timer')return {timer_focus_minutes:whole('timer_focus_minutes',1,240,'Focus minutes'),timer_break_minutes:whole('timer_break_minutes',1,240,'Break minutes')};
  const hot=whole('weather_hot_f',-50,130,'Hot threshold'),cold=whole('weather_cold_f',-50,130,'Cool threshold');
  if(cold>=hot)throw Error('The cool threshold must be below the hot threshold.');
  return {weather_nudges_enabled:values.weather_nudges_enabled,weather_rain_percent:whole('weather_rain_percent',1,100,'Precipitation chance'),
    weather_gust_mph:whole('weather_gust_mph',5,100,'Wind gusts'),weather_hot_f:hot,weather_cold_f:cold};
}
