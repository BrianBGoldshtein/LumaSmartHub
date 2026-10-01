import type {CalendarEvent} from './types';

export function taskPages(tasks:CalendarEvent[],page:number){
  const byDue=(a:CalendarEvent,b:CalendarEvent)=>(a.due_date || '').localeCompare(b.due_date || '')
    || (a.summary || '').localeCompare(b.summary || '') || a.id.localeCompare(b.id);
  const outstanding=tasks.filter(task=>!task.completed).sort(byDue);
  const completed=tasks.filter(task=>task.completed).sort(byDue);
  // Keep complete-only pages separate so they can rotate more quickly.
  const groups=[...Array.from({length:Math.ceil(outstanding.length/3)},(_,i)=>outstanding.slice(i*3,i*3+3)),
    ...Array.from({length:Math.ceil(completed.length/3)},(_,i)=>completed.slice(i*3,i*3+3))];
  const count=Math.max(1,groups.length);
  const index=((page%count)+count)%count;
  const items=groups[index] || [];
  return {index,count,total:tasks.length,items,completedOnly:items.length>0 && items.every(task=>task.completed)};
}
export function taskDueLabel(date:string|undefined,today:string){
  if(!date || !/^\d{4}-\d{2}-\d{2}$/.test(date))return '';
  if(date===today)return 'Due today';
  const parsed=new Date(`${date}T12:00:00Z`);
  return Number.isNaN(parsed.getTime())?'':`Due ${new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(parsed)}`;
}
