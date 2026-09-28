import type {CalendarEvent} from './types';

export function taskPages(tasks:CalendarEvent[],page:number){
  const count=Math.max(1,Math.ceil(tasks.length/3));
  const index=((page%count)+count)%count;
  return {index,count,items:tasks.slice(index*3,index*3+3)};
}
export function taskDueLabel(date:string|undefined,today:string){
  if(!date || !/^\d{4}-\d{2}-\d{2}$/.test(date))return '';
  if(date===today)return 'Due today';
  const parsed=new Date(`${date}T12:00:00Z`);
  return Number.isNaN(parsed.getTime())?'':`Due ${new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(parsed)}`;
}
