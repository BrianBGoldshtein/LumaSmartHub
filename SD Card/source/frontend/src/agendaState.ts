import type {CalendarEvent,Snapshot} from './types';

export const HOUR=3600000;
const MINUTE=60000;
export type PlacedEvent={event:CalendarEvent;top:number;height:number;column:number;columns:number};
export type AgendaSection={start:number;end:number;items:PlacedEvent[];allDay:CalendarEvent[];dense:boolean};
export const calendarColor=(event:CalendarEvent)=>/^#[0-9a-f]{6}$/i.test(event.event_color||event.calendar_color||'')?event.event_color||event.calendar_color!:'var(--accent)';
export const eventKey=(event:CalendarEvent)=>`${event.calendar_id}:${event.id}`;

/** Clock-aligned windows grow around long events and tighten around brief ones. */
function timeWindows(events:CalendarEvent[],start:number,end:number,viewportHeight:number):{start:number;end:number}[]{
  const windows:{start:number;end:number}[]=[];
  const timed=events.filter(event=>!event.all_day).map(event=>({start:Date.parse(event.start),end:Date.parse(event.end)}))
    .filter(event=>Number.isFinite(event.start)&&Number.isFinite(event.end)&&event.end>event.start)
    .sort((a,b)=>a.start-b.start||a.end-b.end);
  const half=30*MINUTE,brief=new Set<number>();
  for(const event of timed){
    const length=event.end-event.start;
    if(length<=half){
      for(let tick=Math.floor(event.start/half)*half;tick<event.end;tick+=half)brief.add(tick);
    }
  }
  const briefTicks=[...brief].sort((a,b)=>a-b);
  // Wake/sleep can fall between ticks; frame the visible ruler on whole hours.
  const first=Math.floor(start/HOUR)*HOUR,last=Math.ceil(end/HOUR)*HOUR;
  const usableHeight=Math.max(220,viewportHeight*.55-(events.some(event=>event.all_day)?55:0));
  for(let cursor=first;cursor<last;){
    const nextBrief=briefTicks.find(tick=>tick>cursor)??last;
    if(brief.has(Math.floor(cursor/half)*half)){
      const next=Math.min(last,(Math.floor(cursor/half)+1)*half);
      windows.push({start:cursor,end:next});cursor=next;continue;
    }
    const active=timed.filter(event=>event.end>cursor&&Math.floor(event.start/HOUR)*HOUR<=cursor);
    if(!active.length){
      const nextStart=timed.filter(event=>event.end>cursor&&event.start>cursor)
        .reduce((nearest,event)=>Math.min(nearest,Math.floor(event.start/HOUR)*HOUR),last);
      const next=Math.min(last,nextBrief,Math.max(cursor+half,nextStart));
      windows.push({start:cursor,end:next});cursor=next;continue;
    }
    let target=Math.max(...active.map(event=>event.end));
    // Nearby appointments form one time block; short ones can still interrupt
    // it to claim their own readable half-hour scale.
    for(const event of timed){
      if(event.start<=target+half&&event.end>target)target=Math.max(target,event.end);
    }
    const relevant=timed.filter(event=>event.end>cursor&&event.start<Math.min(target,nextBrief));
    const shortest=Math.min(...relevant.map(event=>event.end-event.start));
    const span=Math.max(HOUR,Math.floor(usableHeight/52*shortest/HOUR)*HOUR);
    const next=Math.min(last,nextBrief,Math.ceil(target/HOUR)*HOUR,Math.ceil((cursor+span)/HOUR)*HOUR);
    windows.push({start:cursor,end:next});cursor=next;
  }
  return windows;
}

// A card's height is its real time interval. Even a one-minute event must not
// manufacture a collision with a later appointment just to gain visual space.
export function agendaSections(agenda:NonNullable<Snapshot['agenda']>,maxColumns=2,viewportHeight=600):AgendaSection[]{
  maxColumns=Math.max(1,Math.floor(maxColumns));
  const start=Date.parse(agenda.start),end=Date.parse(agenda.end);
  if(!Number.isFinite(start)||!Number.isFinite(end)||end<=start)return [];
  const sections:AgendaSection[]=[];
  const allDay=agenda.events.filter(e=>e.all_day);
  // A lone all-day item does not deserve an otherwise empty full-screen slide.
  // Pair it with the first populated time window, keeping its full-detail tap.
  if(allDay.length>1)sections.push({start,end,items:[],allDay,dense:allDay.length>3});
  for(const window of timeWindows(agenda.events,start,end,viewportHeight)){
    const from=window.start,to=window.end,duration=to-from;
    const items=agenda.events.filter(e=>!e.all_day && Date.parse(e.end)>Date.parse(e.start) && Date.parse(e.start)<to && Date.parse(e.end)>from)
      .map(event=>{
        // Never pull an event upward to make its card fit: its top edge is the
        // exact start time (or the section boundary for an ongoing event).
        const top=Math.max(0,Math.min(Date.parse(event.start)-from,duration));
        const bottom=Math.min(duration,Date.parse(event.end)-from);
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
    // Every adaptive interval is one complete schedule. Dense overlaps stay
    // on the same time axis, with horizontal scrolling for extra lanes.
    sections.push({start:from,end:to,allDay:[],items,
      dense:items.some(item=>item.columns>maxColumns)});
  }
  if(allDay.length===1){
    const firstPopulated=sections.find(section=>section.items.length>0);
    if(firstPopulated)firstPopulated.allDay=[allDay[0]];
    else sections.unshift({start,end,items:[],allDay,dense:false});
  }
  return sections;
}

/** Automatic rotation skips past appointments and empty time windows. */
export function upcomingAgendaSections(agenda:NonNullable<Snapshot['agenda']>,now:number,maxColumns=2,viewportHeight=600):AgendaSection[]{
  if(!Number.isFinite(now))return [];
  const horizon=now+14*HOUR;
  const events=agenda.events.filter(event=>Date.parse(event.end)>now && Date.parse(event.start)<horizon);
  const rolling={...agenda,start:new Date(Math.floor(now/HOUR)*HOUR).toISOString(),end:new Date(horizon).toISOString(),events};
  return agendaSections(rolling,maxColumns,viewportHeight).filter(section=>section.items.length>0 || section.allDay.length>0);
}

export function agendaDemo(events:CalendarEvent[],packed=false,crowded=false,short=false,long=false):NonNullable<Snapshot['agenda']>{
  const now=new Date(),at=(hour:number)=>{const day=new Date(now);day.setHours(hour,0,0,0);return day.toISOString();};
  const names=['Morning run','Research seminar','Project studio','Lunch with Maya','Office hours','Design review','Dinner with friends','Evening reading'];
  const samples=names.map((summary,i)=>({id:`packed-${i}`,calendar_id:['work','personal','school'][i%3],calendar_name:['Work','Personal','School'][i%3],calendar_color:['#7986cb','#33b679','#f6bf26'][i%3],summary,start:at([7,9,10,12,14,15,18,21][i]),end:at([8,11,11,13,15,16,19,22][i]),all_day:false}));
  const extra=crowded?Array.from({length:12},(_,i)=>({...samples[1],id:`overlap-${i}`,summary:`Concurrent appointment ${i+1}`,calendar_id:`calendar-${i}`,start:at(9),end:at(10)})):[];
  const brief=short?[{...samples[0],id:'short-1',summary:'CS 279: Prof. Dmor Office Hours',start:at(9),end:new Date(Date.parse(at(9))+25*60000).toISOString()},
    {...samples[2],id:'short-overlap',summary:'Team check-in',start:new Date(Date.parse(at(9))+15*MINUTE).toISOString(),end:new Date(Date.parse(at(9))+40*MINUTE).toISOString()},
    {...samples[1],id:'short-2',summary:'A longer departmental planning session with everyone',start:new Date(Date.parse(at(9))+30*60000).toISOString(),end:new Date(Date.parse(at(9))+50*60000).toISOString()},
    ...[20,25,30].map((minute,i)=>({...samples[i],id:`five-minute-${i}`,summary:['Quick check-in','Call Maya','Next appointment'][i],start:new Date(Date.parse(at(10))+minute*MINUTE).toISOString(),end:new Date(Date.parse(at(10))+(minute+5)*MINUTE).toISOString()}))]:[];
  const longSamples=[{...samples[0],id:'long-studio',summary:'Design studio',start:at(9),end:at(15)},
    {...samples[1],id:'long-lab',summary:'Research lab',start:at(12),end:at(17)}];
  const chosen=long?longSamples:packed?[...(short?brief:samples),...extra,{...samples[0],id:'all-day',summary:'Campus open day',start:at(0),end:at(24),all_day:true}]:events.filter(e=>Date.parse(e.start)<Date.parse(at(24)) && Date.parse(e.end)>Date.parse(at(0)));
  return {date:new Intl.DateTimeFormat('en-CA').format(now),start:at(7),end:at(23),wake:at(7),sleep:at(23),stale:false,events:chosen};
}
