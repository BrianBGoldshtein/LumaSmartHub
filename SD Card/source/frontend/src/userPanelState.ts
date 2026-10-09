import type {UserPanel} from './types';
import {upcomingAgendaSections,placeAgendaWindow,HOUR} from './agendaState.ts';

// The corner roster already identifies a sole viewer. Retain attribution
// when several people are present, even if only one configured calendars.
export function showPanelIdentity(panelCount:number,presentCount:number){
  return panelCount>1||presentCount>1;
}

/** Every present configured user stays visible; never silently rotate pairs. */
export function userGrid(count:number){
  if(!Number.isInteger(count)||count<1||count>5)throw Error('Invalid user panel count');
  const columns=count===5?6:count===4?2:count;
  const spans=Array.from({length:count},(_,index)=>count===5?(index<3?2:3):1);
  return {columns,rows:count>=4?2:1,spans};
}

export function synchronizedUserSections(panels:UserPanel[],now:number,height=600){
  if(!panels.length||!Number.isFinite(now))return [];
  // Choosing windows independently creates different truths for the same
  // screen. Choose them once from the union, then place each account in them.
  const events=panels.flatMap(panel=>panel.agenda.events.map(event=>({...event,profile_id:panel.profile_id})));
  const agenda={...panels[0].agenda,start:new Date(Math.floor(now/HOUR)*HOUR).toISOString(),
    end:new Date(now+14*HOUR).toISOString(),events};
  return upcomingAgendaSections(agenda,now,2,height).map(section=>({
    start:section.start,end:section.end,
    panels:panels.map(panel=>{
      const own=events.filter(event=>event.profile_id===panel.profile_id);
      const placed=placeAgendaWindow(own,section.start,section.end,1);
      const allDay=own.filter(event=>event.all_day&&Date.parse(event.start)<section.end&&Date.parse(event.end)>section.start);
      return {profile_id:panel.profile_id,nickname:panel.nickname,
        section:{...placed,items:section.items.length?placed.items:[],allDay:section.allDay.length?allDay:[]}};
    }),
  }));
}
