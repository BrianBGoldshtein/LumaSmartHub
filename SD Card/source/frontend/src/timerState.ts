export type TimerState={id:string|null;status:'idle'|'running'|'paused'|'awaiting_time'|'complete';label:string;duration_seconds:number;remaining_seconds:number;note:string};
export const idleTimer:TimerState={id:null,status:'idle',label:'Timer',duration_seconds:0,remaining_seconds:0,note:''};
export function timerRemaining(timer:TimerState,elapsedSeconds:number){
  return Math.max(0,timer.remaining_seconds-(timer.status==='running'?Math.max(0,elapsedSeconds):0));
}
export function timerText(seconds:number){
  const total=Math.max(0,Math.ceil(seconds));
  return `${Math.floor(total/60)}:${String(total%60).padStart(2,'0')}`;
}
export function previewTimerCommand(timer:TimerState,name:string,value:unknown,remaining:number,id:string):TimerState{
  if(name==='start_timer'){
    const request=value as {minutes:number;label?:string;replace_id?:string};
    if(!request || !Number.isInteger(request.minutes) || request.minutes<1 || request.minutes>240)throw Error('Choose 1–240 whole minutes.');
    if(['running','paused','awaiting_time'].includes(timer.status) && request.replace_id!==timer.id)throw Error('Confirm replacement of the current timer.');
    return {id,status:'running',label:request.label?.trim() || 'Timer',duration_seconds:request.minutes*60,remaining_seconds:request.minutes*60,note:''};
  }
  if(name==='pause_timer' && ['running','awaiting_time'].includes(timer.status))return {...timer,status:'paused',remaining_seconds:remaining};
  if(name==='resume_timer' && timer.status==='paused')return {...timer,status:'running'};
  if(name==='cancel_timer' || name==='dismiss_timer')return {...idleTimer};
  throw Error('This timer action is not available.');
}
