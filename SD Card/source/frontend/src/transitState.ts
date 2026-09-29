export type TransitDeparture={route:string;direction:string;destination:string;at:string;minutes:number;kind:'predicted'|'scheduled';stale:boolean;updated_at:string|null;scheduled_at?:string|null;prediction_until?:string|null};
export type TransitView={id:string;title:string;operator:string;stop:string;direction:string|null;public:boolean;departures:TransitDeparture[];state:'ready'|'stale'|'empty'|'unavailable';checked_at:string|null;offline?:boolean};
export type TransitFavorite={id:string;revision:string;title:string;operator_id:string;operator_name:string;agency:string;stop_id:string;stop_name:string;route_id:string|null;line:string|null;direction:string|null;monitored:boolean;public:boolean};
export type TransitConfig={items:TransitFavorite[];views:TransitView[];token_configured:boolean;recovery_error:boolean};
export type DirectoryEntry={id:string;name:string;monitored?:boolean;station?:boolean;platform?:string};
export const transitProvider='https://511.org/open-data/transit';
export const transitTerms='https://511.org/sites/default/files/2026-04/511_Data_Agreement_Final_2026.pdf';
export const margueriteMap='https://transportation.stanford.edu/getting-stanford/marguerite/marguerite-live-map';
export const visibleTransit=(items:TransitView[]|undefined,privateMode:boolean)=>(items||[]).filter(item=>!privateMode||item.public);
export const disconnectedTransit=(items:TransitView[]|undefined)=>visibleTransit(items,true).map(item=>({...item,offline:true,state:'stale' as const}));
export function ageTransit(item:TransitView,now:number):TransitView{
  if(!Number.isFinite(now))return {...item,departures:[],state:'unavailable'};
  const checked=Date.parse(item.checked_at||''),fresh=Number.isFinite(checked)&&now>=checked&&now-checked<=300000&&!item.offline;
  const departures=item.departures.flatMap(row=>{
    const original=Date.parse(row.at);
    if(!Number.isFinite(original)||original<now||now<checked)return [];
    const live=row.kind==='predicted'&&fresh&&Number.isFinite(Date.parse(row.prediction_until||''))&&now<=Date.parse(row.prediction_until!);
    const at=row.kind==='predicted'&&!live?Date.parse(row.scheduled_at||''):original;
    if(!Number.isFinite(at)||at<now||at-now>86400000)return [];
    return [{...row,at:new Date(at).toISOString(),minutes:Math.ceil((at-now)/60000),kind:live?'predicted' as const:'scheduled' as const,stale:row.stale||!fresh}];
  }).sort((a,b)=>Date.parse(a.at)-Date.parse(b.at)).slice(0,3);
  return {...item,departures,state:departures.length?fresh&&item.state!=='stale'?'ready':'stale':fresh&&item.state==='empty'?'empty':'unavailable'};
}
export function transitCycle<T extends {page:string;seconds:number}>(cycle:T[],hasTransit:boolean):Array<T|{page:'transit';seconds:number}>{const result=cycle.filter(item=>hasTransit||item.page!=='transit');return hasTransit&&!result.some(item=>item.page==='transit')?[...result,{page:'transit',seconds:25}]:result;}
export function transitStress(now:number):TransitView[]{return Array.from({length:6},(_,index)=>({...sampleTransit(now)[index%3],id:`stress-${index}`,title:`Long-distance afternoon connection ${index+1}`,operator:'An agency with a longer display name',stop:'University Avenue · Northern boarding platform',departures:sampleTransit(now)[0].departures.map((row,i)=>({...row,route:'Regional express service',destination:'A long destination name across the peninsula',kind:'scheduled',at:new Date(now+[108,780,1440][i]*60000).toISOString(),minutes:[108,780,1440][i]}))}));}
export function sampleTransit(now=Date.now()):TransitView[]{return ['To the city','Back to campus','Across town'].map((title,index)=>({id:`transit-${index}`,title,operator:['Caltrain','Marguerite · sample','SamTrans'][index],stop:['Palo Alto','Campus Oval','University Avenue'][index],direction:null,public:index===0,state:'ready',checked_at:new Date(now).toISOString(),departures:[5,18,34].map((minutes,i)=>({route:['Local','Express','Local'][i],direction:'N',destination:index===0?'San Francisco':index===1?'Campus loop':'Redwood City',at:new Date(now+minutes*60000).toISOString(),minutes,kind:i===2?'scheduled':'predicted',stale:false,updated_at:new Date(now).toISOString(),scheduled_at:new Date(now+(minutes+2)*60000).toISOString(),prediction_until:new Date(now+300000).toISOString()}))}));}
