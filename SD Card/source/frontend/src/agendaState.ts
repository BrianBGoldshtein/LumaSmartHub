import type {CalendarEvent,Snapshot} from './types';

export const HOUR=3600000;
export type PlacedEvent={event:CalendarEvent;top:number;height:number;column:number;columns:number};
export type AgendaSection={start:number;end:number;items:PlacedEvent[];allDay:CalendarEvent[];lane:number;lanes:number};
export const calendarColor=(event:CalendarEvent)=>/^#[0-9a-f]{6}$/i.test(event.event_color||event.calendar_color||'')?event.event_color||event.calendar_color!:'var(--accent)';
export const eventKey=(event:CalendarEvent)=>`${event.calendar_id}:${event.id}`;

// Minimum visual duration keeps short events legible. Column packing uses that
// same visual extent, so adjacent five-minute appointments never paint over one another.
export function agendaSections(agenda:NonNullable<Snapshot['agenda']>,maxColumns=2):AgendaSection[]{
  maxColumns=Math.max(1,Math.floor(maxColumns));
  const start=Date.parse(agenda.start),end=Date.parse(agenda.end);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return [];
  const sections:AgendaSection[]=[];
  const allDay=agenda.events.filter(e=>e.all_day);
  // A lone all-day item does not deserve an otherwise empty full-screen slide.
  // Pair it with the first populated time window, keeping its full-detail tap.
  if(allDay.length!==1)for(let i=0;i<allDay.length;i+=3)sections.push({start,end,items:[],allDay:allDay.slice(i,i+3),lane:0,lanes:1});
  for(let from=start;from<end;from+=4*HOUR){
    const to=Math.min(end,from+4*HOUR),duration=to-from,minHeight=Math.min(80*60000,duration);
    const items=agenda.events.filter(e=>!e.all_day && Date.parse(e.start)<to && Date.parse(e.end)>from)
      .map(event=>{
        const top=Math.max(0,Math.min(Date.parse(event.start)-from,duration-minHeight));
        const bottom=Math.min(duration,Math.max(Date.parse(event.end)-from,top+minHeight));
        return {event,top:top/duration*100,height:(bottom-top)/duration*100,column:0,columns:1};
      }).sort((a,b)=>a.top-b.top||b.height-a.height||eventKey(a.event).localeCompare(eventKey(b.event)));
    let group:PlacedEvent[]=[],groupEnd=0,ends:number[]=[];
    const finish=()=>{for(const item of group)item.columns=ends.length;};
    for(const item of items){
      if(group.length && item.top>=groupEnd-.00001){finish();group=[];ends=[];groupEnd=0;}
      let column=ends.findIndex(value=>value<=item.top+.00001);
      if(column<0)column=ends.length;
      item.column=column;ends[column]=item.top+item.height;group.push(item);groupEnd=Math.max(groupEnd,ends[column]);
    }
    finish();
    const lanes=Math.max(1,...items.map(item=>Math.ceil(item.columns/maxColumns)));
    for(let lane=0;lane<lanes;lane++){
      sections.push({start:from,end:to,allDay:[],lane,lanes,items:items.filter(item=>Math.floor(item.column/maxColumns)===lane).map(item=>({...item,column:item.column%maxColumns,columns:Math.min(maxColumns,item.columns-lane*maxColumns)}))});
    }
  }
  if(allDay.length===1){
    const firstPopulated=sections.find(section=>section.items.length>0);
    if(firstPopulated)firstPopulated.allDay=[allDay[0]];
    else sections.unshift({start,end,items:[],allDay,lane:0,lanes:1});
  }
  return sections;
}

/** Automatic rotation skips past appointments and empty time windows. */
export function upcomingAgendaSections(agenda:NonNullable<Snapshot['agenda']>,now:number,maxColumns=2):AgendaSection[]{
  if(!Number.isFinite(now))return [];
  const horizon=now+14*HOUR;
  const events=agenda.events.filter(event=>Date.parse(event.end)>now && Date.parse(event.start)<horizon);
  const rolling={...agenda,start:new Date(Math.floor(now/HOUR)*HOUR).toISOString(),end:new Date(horizon).toISOString(),events};
  return agendaSections(rolling,maxColumns).filter(section=>section.items.length>0 || section.allDay.length>0);
}

export function agendaDemo(events:CalendarEvent[],packed=false,crowded=false,short=false):NonNullable<Snapshot['agenda']>{
  const now=new Date(),at=(hour:number)=>{const day=new Date(now);day.setHours(hour,0,0,0);return day.toISOString();};
  const names=['Morning run','Research seminar','Project studio','Lunch with Maya','Office hours','Design review','Dinner with friends','Evening reading'];
  const samples=names.map((summary,i)=>({id:`packed-${i}`,calendar_id:['work','personal','school'][i%3],calendar_name:['Work','Personal','School'][i%3],calendar_color:['#7986cb','#33b679','#f6bf26'][i%3],summary,start:at([7,9,10,12,14,15,18,21][i]),end:at([8,11,11,13,15,16,19,22][i]),all_day:false}));
  const extra=crowded?Array.from({length:12},(_,i)=>({...samples[1],id:`overlap-${i}`,summary:`Concurrent appointment ${i+1}`,calendar_id:`calendar-${i}`,start:at(9),end:at(10)})):[];
  const brief=short?[{...samples[0],id:'short-1',summary:'CS 279: Prof. Dmor Office Hours',start:at(9),end:new Date(Date.parse(at(9))+25*60000).toISOString()},
    {...samples[1],id:'short-2',summary:'A longer departmental planning session with everyone',start:new Date(Date.parse(at(9))+30*60000).toISOString(),end:new Date(Date.parse(at(9))+50*60000).toISOString()}]:[];
  const chosen=packed?[...(short?brief:samples),...extra,{...samples[0],id:'all-day',summary:'Campus open day',start:at(0),end:at(24),all_day:true}]:events.filter(e=>Date.parse(e.start)<Date.parse(at(24)) && Date.parse(e.end)>Date.parse(at(0)));
  return {date:new Intl.DateTimeFormat('en-CA').format(now),start:at(7),end:at(23),wake:at(7),sleep:at(23),stale:false,events:chosen};
}
