export type CountdownView={id:string;title:string;public:boolean;source:'manual'|'google';target:string;date:string;timed:boolean;label:string;value:number|null;unit:string|null;state:string;past:boolean;color?:string|null};
export type CountdownItem={id:string;revision:string;source:'manual'|'google';title:string;public:boolean;timezone:string;date?:string;time?:string|null;annual?:boolean;calendar_id?:string;event_id?:string;start?:string;all_day?:boolean;state?:string};
export type CountdownConfig={items:CountdownItem[];views:CountdownView[];limit:number;recovery_error:boolean};
export function visibleDates(items:CountdownView[]|undefined,privateMode:boolean){return (items||[]).filter(item=>!privateMode||item.public);}
export function disconnectedDates(items:CountdownView[]|undefined){return visibleDates(items,true).map(item=>item.source==='google'&&item.state==='ready'?{...item,state:'stale'}:item);}
export function dateCycle<T extends {page:string;seconds:number}>(cycle:T[],hasDates:boolean):Array<T|{page:'countdowns';seconds:number}>{const result=cycle.filter(item=>hasDates||item.page!=='countdowns');if(hasDates&&!result.some(item=>item.page==='countdowns'))return [...result,{page:'countdowns',seconds:25}];return result;}
export function datePages(items:CountdownView[],page:number){const count=Math.max(1,Math.ceil(items.length/3)),index=((page%count)+count)%count;return {count,index,items:items.slice(index*3,index*3+3)};}
export function dateColor(value:string|null|undefined){return value&&/^#[0-9a-f]{6}$/i.test(value)?value:'var(--accent)';}
export function dateCaption(item:CountdownView){
  if(item.state==='stale')return 'Saved date · awaiting sync';
  if(item.state==='deleted')return 'Removed from Google';
  if(item.state==='unavailable')return 'Check Google access';
  if(item.state==='unlinked')return 'Reconnect Google';
  const date=new Date(`${item.date}T12:00:00Z`);
  return Number.isNaN(date.getTime())?'':new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(date);
}
export const sampleDates:CountdownView[]=[
  {id:'sample-1',title:'Weekend away',public:false,source:'google',target:'2026-10-10T12:00:00-07:00',date:'2026-10-10',timed:false,label:'14 days',value:14,unit:'days',state:'ready',past:false,color:'#7986cb'},
  {id:'sample-2',title:'Autumn begins',public:true,source:'manual',target:'2026-10-01T00:00:00-07:00',date:'2026-10-01',timed:false,label:'Tomorrow',value:null,unit:null,state:'ready',past:false},
  {id:'sample-3',title:'Dinner together',public:false,source:'google',target:'2026-09-26T20:00:00-07:00',date:'2026-09-26',timed:true,label:'3 hours',value:3,unit:'hours',state:'stale',past:false,color:'#e67c73'},
];
