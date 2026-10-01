import type {CalendarEvent} from './types';

export function taskPages(tasks:CalendarEvent[],page:number){
  // Completion remains in the provider snapshot for sync/voice, but never
  // consumes a slot or a rotation page on the wall-facing to-do slide.
  const outstanding=tasks.filter(task=>!task.completed);
  const count=Math.max(1,Math.ceil(outstanding.length/3));
  const index=((page%count)+count)%count;
  return {index,count,total:outstanding.length,items:outstanding.slice(index*3,index*3+3)};
}
export function taskDueLabel(date:string|undefined,today:string){
  if(!date || !/^\d{4}-\d{2}-\d{2}$/.test(date))return '';
  if(date===today)return 'Due today';
  const parsed=new Date(`${date}T12:00:00Z`);
  return Number.isNaN(parsed.getTime())?'':`Due ${new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(parsed)}`;
}
