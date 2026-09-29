export interface DisplayState {
  mode:'day'|'night-clock'|'off'|'waking'; brightness:number; day_brightness:number; night_brightness:number;
  awaiting_clock:boolean; quiet:boolean; note?:string;
  ramp:{id:string;kind:'scheduled'|'morning'|'temporary';duration_seconds:number;elapsed_seconds:number;from_brightness:number;to_brightness:number}|null;
  handoff:{revision:string|null;needs_frame:boolean;reference_brightness:number;physical_brightness:number|null;physical_power:boolean|null;status:string};
}
export function displayLevel(display:DisplayState,elapsedMs=0){
  if(display.mode==='off')return 0;
  const ramp=display.mode==='waking'?display.ramp:null;
  let level=display.brightness;
  if(ramp){
    if(!Number.isFinite(ramp.duration_seconds) || ramp.duration_seconds<=0)return 0;
    const t=Math.min(1,Math.max(0,(ramp.elapsed_seconds+Math.max(0,elapsedMs)/1000)/ramp.duration_seconds));
    level=ramp.from_brightness+(ramp.to_brightness-ramp.from_brightness)*t*t*(3-2*t);
  }
  return Number.isFinite(level)?Math.min(100,Math.max(0,level)):0;
}
export function displayFilter(display:DisplayState|undefined|null,elapsedMs=0){
  if(!display)return 1;
  const reference=display.handoff.reference_brightness;
  const denominator=Number.isFinite(reference)&&reference>=1&&reference<=100?reference:100;
  return Math.min(1,displayLevel(display,elapsedMs)/denominator);
}
export function previewDisplay(mode:DisplayState['mode'],brightness=70):DisplayState{
  return {mode,brightness:mode==='day'?brightness:mode==='off'?0:5,day_brightness:brightness,night_brightness:5,awaiting_clock:false,quiet:mode!=='day',
    ramp:mode==='waking'?{id:'preview',kind:'morning',duration_seconds:20,elapsed_seconds:0,from_brightness:5,to_brightness:brightness}:null,
    handoff:{revision:null,needs_frame:false,reference_brightness:100,physical_brightness:null,physical_power:true,status:'preview'}};
}
