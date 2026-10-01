import type {CalendarEvent,Theme} from './types';

const DAY_MS=86_400_000;
const DEADLINE_PALETTE:Record<Theme,{lightness:number;chroma:number;redHue:number;greenHue:number}>={
  'luma-glass':{lightness:76,chroma:.16,redHue:24,greenHue:153},
  hearth:{lightness:79,chroma:.14,redHue:30,greenHue:145},
  'neon-grid':{lightness:78,chroma:.18,redHue:18,greenHue:158},
};

function dayNumber(value:string):number|null{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const [year,month,day]=value.split('-').map(Number);
  const millis=Date.UTC(year,month-1,day);
  return new Date(millis).toISOString().slice(0,10)===value?millis/DAY_MS:null;
}

export function deadlineStatus(dueDate:string|undefined,today:string,theme:Theme){
  const due=dayNumber(dueDate || ''),current=dayNumber(today);
  if(due===null || current===null)return {daysUntil:null,color:'var(--muted)',label:'Deadline unavailable',kind:'unknown' as const};
  const daysUntil=due-current;
  const palette=DEADLINE_PALETTE[theme];
  // Red through tomorrow, yellow around days 3–4, green by day 7.
  // OKLCH keeps the interpolation bright on every dark theme.
  const progress=Math.min(1,Math.max(0,(daysUntil-1)/6));
  const hue=Math.round(palette.redHue+(palette.greenHue-palette.redHue)*progress);
  const color=`oklch(${palette.lightness}% ${palette.chroma} ${hue})`;
  const label=daysUntil<0?`Overdue by ${-daysUntil} ${daysUntil===-1?'day':'days'}`
    :daysUntil===0?'Deadline today'
    :daysUntil===1?'Deadline tomorrow'
    :`Due in ${daysUntil} days`;
  const kind=daysUntil<0?'overdue':daysUntil<=1?'urgent':daysUntil>7?'distant':'approaching';
  return {daysUntil,color,label,kind};
}

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
