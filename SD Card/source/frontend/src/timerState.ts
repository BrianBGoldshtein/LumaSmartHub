export type TimerState={id:string|null;status:'idle'|'running'|'paused'|'awaiting_time'|'complete';label:string;duration_seconds:number;remaining_seconds:number;note:string};
export type TimerStartRequest={minutes?:number;seconds?:number;label?:string;replace_id?:string};
export const idleTimer:TimerState={id:null,status:'idle',label:'Timer',duration_seconds:0,remaining_seconds:0,note:''};
export function timerRemaining(timer:TimerState,elapsedSeconds:number){
  return Math.max(0,timer.remaining_seconds-(timer.status==='running'?Math.max(0,elapsedSeconds):0));
}
export function timerText(seconds:number){
  const total=Math.max(0,Math.ceil(seconds));
  if(total>=3600)return `${Math.floor(total/3600)}:${String(Math.floor(total%3600/60)).padStart(2,'0')}:${String(total%60).padStart(2,'0')}`;
  return `${Math.floor(total/60)}:${String(total%60).padStart(2,'0')}`;
}
export function timerDurationSeconds(value:unknown){
  if(!value||typeof value!=='object'||Array.isArray(value))throw Error('Choose a timer from 1 second to 4 hours.');
  const request=value as TimerStartRequest;
  if(Object.keys(request).some(key=>!['minutes','seconds','label','replace_id'].includes(key))||
    ('minutes' in request)===('seconds' in request))throw Error('Choose seconds or minutes for the timer.');
  if('minutes' in request&&!Number.isInteger(request.minutes))throw Error('Choose whole minutes for the timer.');
  const seconds='seconds' in request?request.seconds:request.minutes===undefined?undefined:request.minutes*60;
  if(!Number.isInteger(seconds)||seconds===undefined||seconds<1||seconds>14400)throw Error('Choose a timer from 1 second to 4 hours.');
  if(request.label!==undefined && (typeof request.label!=='string'||request.label.trim().length<1||request.label.trim().length>40||/[\x00-\x1f]/.test(request.label)))throw Error('Use a timer label of 1 to 40 characters.');
  return seconds;
}
export function previewTimerCommand(timer:TimerState,name:string,value:unknown,remaining:number,id:string):TimerState{
  if(name==='start_timer'){
    const seconds=timerDurationSeconds(value),request=value as TimerStartRequest;
    if(['running','paused','awaiting_time'].includes(timer.status) && request.replace_id!==timer.id)throw Error('Confirm replacement of the current timer.');
    if(request.replace_id && request.replace_id!==timer.id)throw Error('The timer changed. Review it before starting again.');
    return {id,status:'running',label:request.label?.trim() || 'Timer',duration_seconds:seconds,remaining_seconds:seconds,note:''};
  }
  if(name==='pause_timer' && ['running','awaiting_time'].includes(timer.status))return {...timer,status:'paused',remaining_seconds:remaining};
  if(name==='resume_timer' && timer.status==='paused')return {...timer,status:'running'};
  if(name==='cancel_timer' || name==='dismiss_timer')return {...idleTimer};
  throw Error('This timer action is not available.');
}
