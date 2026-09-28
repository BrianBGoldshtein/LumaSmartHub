import {useContext,useEffect,useRef,useState} from 'react';
import {TrainFront} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {TouchField} from './TouchField';
import {transitProvider,transitTerms,margueriteMap,sampleTransit,type TransitConfig,type TransitFavorite,type DirectoryEntry} from './transitState';
import './transit.css';

type Step='list'|'token'|'operator'|'route'|'stop'|'direction'|'review';
type Draft={title:string;operator:DirectoryEntry|null;route:DirectoryEntry|null;stop:DirectoryEntry|null;direction:string|null;public:boolean;item_id?:string;revision?:string};
const blank=():Draft=>({title:'',operator:null,route:null,stop:null,direction:null,public:false});
const empty:TransitConfig={items:[],views:[],token_configured:false,recovery_error:false};
async function api(path='',method='GET',body?:unknown){const response=await fetch(`/api/v1/transit${path}`,{method,cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not update transit. Please try again.');return data;}

export function TransitSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const activity=useContext(SetupActivity),alive=useRef(true);
  const [config,setConfig]=useState<TransitConfig>(empty),[ready,setReady]=useState(demo),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [step,setStep]=useState<Step>('list'),[draft,setDraft]=useState<Draft>(blank),[baseline,setBaseline]=useState('');
  const [token,setToken]=useState(''),[reviewed,setReviewed]=useState(false),[confirm,setConfirm]=useState<'discard'|'token'|TransitFavorite|null>(null);
  const [rows,setRows]=useState<DirectoryEntry[]>([]),[query,setQuery]=useState(''),[page,setPage]=useState(0),[total,setTotal]=useState(0),[more,setMore]=useState(false);
  const [directions,setDirections]=useState<string[]>([]),[previewNotice,setPreviewNotice]=useState('');
  const [directoryReady,setDirectoryReady]=useState(false);
  const dirty=!!token || (step!=='list'&&step!=='token'&&JSON.stringify(draft)!==baseline);
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useEffect(()=>{alive.current=true;if(!demo)void load();return()=>{alive.current=false;};},[demo]);
  async function run(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action();}catch(e){if(alive.current)setMessage((e as Error).message);}finally{if(alive.current)setBusy(false);}}
  async function load(){await run(async()=>{const value=await api();if(alive.current){setConfig(value);setReady(true);}});}
  function leave(){setToken('');setReviewed(false);setDraft(blank());setRows([]);setDirections([]);setStep('list');setConfirm(null);setMessage('');}
  function backToList(){if(dirty)setConfirm('discard');else leave();}
  const edit=<K extends keyof Draft>(key:K,value:Draft[K])=>{activity.edited();setDraft(current=>({...current,[key]:value}));};
  async function directory(next:'operator'|'route'|'stop',current=draft,search='',atPage=0){
    setStep(next);setRows([]);setTotal(0);setMore(false);setDirectoryReady(false);setQuery(search);setPage(atPage);
    await run(async()=>{
      let result:{items:DirectoryEntry[];total:number;has_more:boolean};
      if(demo){const options:DirectoryEntry[]=next==='operator'?[{id:'caltrain',name:'Caltrain',monitored:true},{id:'marguerite',name:'Marguerite · sample only',monitored:true},{id:'samtrans',name:'SamTrans',monitored:true}]:next==='route'?[{id:'local',name:'Local service'},{id:'express',name:'Express service'}]:[{id:'palo-alto',name:'Palo Alto',platform:'Northbound'},{id:'campus',name:'Campus Oval',platform:'1'},{id:'university',name:'University Avenue'}];const matches=options.filter(item=>item.name.toLowerCase().includes(search.toLowerCase()));result={items:matches,total:matches.length,has_more:false};}
      else result=await api('/directory','POST',{kind:next==='operator'?'operators':next==='route'?'lines':'stops',operator_id:current.operator?.id,line_id:current.route?.id,query:search,page:atPage});
      if(alive.current){setRows(result.items);setTotal(result.total);setMore(result.has_more);setDirectoryReady(true);}
    });
  }
  function choose(item:DirectoryEntry){
    activity.edited();setMessage('');
    if(step==='operator'){const value={...draft,operator:item,route:null,stop:null,direction:null};setDraft(value);void directory('route',value);}
    else if(step==='route'){const value={...draft,route:item,stop:null,direction:null};setDraft(value);void directory('stop',value);}
    else {setDraft({...draft,stop:item,title:draft.title||item.name.slice(0,100),direction:null});setDirections([]);setPreviewNotice('');setStep('direction');}
  }
  function begin(item?:TransitFavorite){
    const value=item?{title:item.title,operator:{id:item.operator_id,name:item.operator_name,monitored:item.monitored},route:item.route_id?{id:item.route_id,name:item.line||item.route_id}:null,stop:{id:item.stop_id,name:item.stop_name},direction:item.direction,public:item.public,item_id:item.id,revision:item.revision}:blank();
    setDraft(value);setBaseline(JSON.stringify(value));setDirections(item?.direction?[item.direction]:[]);setPreviewNotice('');
    if(item)setStep('review');else void directory('operator',value);
  }
  async function save(){await run(async()=>{
    if(!draft.operator||!draft.stop||!draft.title.trim())throw Error('Choose a boarding stop and a name first.');
    let saved:TransitConfig;
    if(demo){const item:TransitFavorite={id:draft.item_id||crypto.randomUUID(),revision:crypto.randomUUID(),title:draft.title.trim(),operator_id:draft.operator.id,operator_name:draft.operator.name,agency:draft.operator.id,stop_id:draft.stop.id,stop_name:draft.stop.name,route_id:draft.route?.id||null,line:draft.route?.id||null,direction:draft.direction,monitored:!!draft.operator.monitored,public:draft.public};saved={...config,items:[...config.items.filter(row=>row.id!==item.id),item],views:[...config.views.filter(row=>row.id!==item.id),{...sampleTransit()[0],id:item.id,title:item.title,public:item.public}]};}
    else saved=await api('/favorites','POST',{title:draft.title.trim(),operator_id:draft.operator.id,stop_id:draft.stop.id,route_id:draft.route?.id||null,direction:draft.direction,public:draft.public,item_id:draft.item_id,revision:draft.revision});
    if(alive.current){setConfig(saved);leave();setMessage(demo?'Sample stop saved in this preview only.':'Stop saved. Departure polling will use the shared request allowance.');onSaved?.();}
  });}
  async function saveToken(){const secret=token;setToken('');await run(async()=>{if(!reviewed)throw Error('Review the provider requirements first.');const saved=demo?{...config,token_configured:true}:await api('/token','POST',{token:secret});if(alive.current){setConfig(saved);leave();setMessage(demo?'Preview connection only; no token sent.':'Token saved privately. Choose Add stop to check provider access.');onSaved?.();}});}
  async function preview(){await run(async()=>{const value=demo?{directions:['N','S'],departures:[{}],notice:'Sample departures only; no provider was contacted.'}:await api('/preview','POST',{operator_id:draft.operator?.id,stop_id:draft.stop?.id,route_id:draft.route?.id||null});if(alive.current){setDirections(value.directions);setPreviewNotice(value.notice||`${value.departures.length} upcoming departures returned. Direction codes are supplied by the agency.`);}});}
  async function confirmAction(){const action=confirm;if(action==='discard'){leave();return;}await run(async()=>{let saved:TransitConfig;if(action==='token')saved=demo?{...config,token_configured:false,views:[]}:await api('/token','POST',{token:null});else if(action)saved=demo?{...config,items:config.items.filter(item=>item.id!==action.id),views:config.views.filter(item=>item.id!==action.id)}:await api(`/favorites/${action.id}`,'DELETE',{revision:action.revision});else return;if(alive.current){setConfig(saved);setConfirm(null);onSaved?.();}});}
  const external=(href:string,text:string)=><a href={href} target="_blank" rel="noreferrer">{text} ↗</a>;
  const order=['operator','route','stop','direction','review'];
  return <div className="transit-setup"><h2><TrainFront/> Your transit</h2>
    {!ready?<><p>Load your saved stops to begin.</p><button disabled={busy} onClick={()=>void load()}>Retry loading</button></>:<>
      {step!=='list'&&<button disabled={busy} onClick={backToList}>← Back to saved stops</button>}
      {config.recovery_error?<p role="alert">Saved stops need recovery. They have not been overwritten; transit changes are disabled.</p>:<>
      {step==='list'?<><p>Up to six stops. Private unless you choose otherwise.</p><div className="date-actions"><button disabled={busy} onClick={()=>{setStep('token');setReviewed(false);}}>{config.token_configured?'Replace token':'Connect transit'}</button><button disabled={busy||config.items.length>=6||(!demo&&!config.token_configured)} onClick={()=>begin()}>Add stop</button>{config.token_configured&&<button disabled={busy} onClick={()=>setConfirm('token')}>Remove token</button>}</div>
        <div className="date-editor-list">{config.items.map(item=><article key={item.id}><h3>{item.title}</h3><p>{item.operator_name} · {item.stop_name}{item.direction?` · ${item.direction}`:''}</p><p>{item.public?'Public in standby':'Private'}</p><div className="date-actions"><button disabled={busy} onClick={()=>begin(item)}>Edit stop</button><button disabled={busy} onClick={()=>setConfirm(item)}>Remove stop</button></div></article>)}</div>{!config.items.length&&<p className="setup-note">No saved stops yet. You can skip this optional extra.</p>}
      </>:step==='token'?<><h3>Connect your own provider token</h3><p>Obtain a token from 511 and review their agreement on the official site. Luma does not register or accept terms for you.</p><div className="transit-links">{external(transitProvider,'Get a token')}{external(transitTerms,'Read the agreement')}</div><p className="setup-note">The agreement includes documenting your application within 30 days of launch. Review the full requirements before using the feed. No registration or documentation is submitted by Luma.</p><form onSubmit={e=>{e.preventDefault();void saveToken();}}><TouchField label="511 API token" secret value={token} onChange={setToken} maxLength={256} minLength={16} required disabled={busy}/><label className="extras-toggle"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)} disabled={busy}/><span>I have obtained my token and reviewed the provider requirements.</span></label><button disabled={busy||!reviewed||token.length<16}>Save private token</button></form><p className="setup-note">The token stays on this hub and is never displayed again or included in portable settings backups. This step saves the token; the stop picker checks provider access.</p></>:<>
        <p className="transit-step">{order.indexOf(step)+1} / 5 · {({operator:'Agency',route:'Route',stop:'Boarding stop',direction:'Direction',review:'Review & save'} as Record<string,string>)[step]}</p>
        {(step==='operator'||step==='route'||step==='stop')?<><h3>{step==='operator'?'Choose an agency':step==='route'?'Choose a route':'Choose a stop or platform'}</h3>{draft.operator&&step!=='operator'&&<p>{draft.operator.name}{draft.route?` · ${draft.route.name}`:''}</p>}
          <form onSubmit={e=>{e.preventDefault();void directory(step,draft,query);}}><TouchField label="Search this directory" value={query} onChange={setQuery} disabled={busy} maxLength={100}/><button disabled={busy}>Search</button></form>
          {step==='route'&&<button disabled={busy} onClick={()=>{const value={...draft,route:null,stop:null,direction:null};setDraft(value);void directory('stop',value);}}>All routes at this stop</button>}
          <div className="transit-options">{rows.map(row=><button disabled={busy||row.station} key={row.id} onClick={()=>choose(row)}>{row.name}<span>{row.station?'Station group · choose a platform':row.platform?`Platform ${row.platform}`:row.id}</span></button>)}</div>
          {!busy&&!directoryReady&&<p>The directory could not be loaded. Use Search to try again.</p>}
          {directoryReady&&<>{!busy&&!rows.length&&<p>No matching entries. Try another search or agency.</p>}<div className="date-actions"><button disabled={busy||page===0} onClick={()=>void directory(step,draft,query,page-1)}>Previous results</button><span>{total} matches · page {page+1}</span><button disabled={busy||!more} onClick={()=>void directory(step,draft,query,page+1)}>More results</button></div></>}
          {step!=='operator'&&<button disabled={busy} onClick={()=>void directory(step==='stop'?'route':'operator',draft)}>← {step==='stop'?'Routes':'Agencies'}</button>}
        </>:step==='direction'?<><h3>Which way?</h3><p>{draft.stop?.name}</p><p className="setup-note">All directions is always available. Optionally check current departures to discover this agency’s direction codes; each check uses the shared request allowance.</p><button disabled={busy} onClick={()=>void preview()}>Check current departures</button>{previewNotice&&<p role="status">{previewNotice}</p>}<label className="extras-toggle"><input type="radio" name="transit-direction" checked={draft.direction===null} onChange={()=>edit('direction',null)} disabled={busy}/><span>All directions</span></label>{directions.map(direction=><label className="extras-toggle" key={direction}><input type="radio" name="transit-direction" checked={draft.direction===direction} onChange={()=>edit('direction',direction)} disabled={busy}/><span>{direction}</span></label>)}<div className="date-actions"><button disabled={busy} onClick={()=>void directory('stop',draft)}>← Stops</button><button disabled={busy} onClick={()=>setStep('review')}>Review stop →</button></div></>:<><h3>Make this stop yours</h3><form onSubmit={e=>{e.preventDefault();void save();}}><TouchField label="Name on the hub" value={draft.title} onChange={value=>edit('title',value)} required maxLength={100} disabled={busy}/><div className="transit-review"><p>{draft.operator?.name}</p><p>{draft.route?.name||'All routes'} · {draft.stop?.name}</p><p>{draft.direction||'All directions'}</p></div><label className="extras-toggle"><input type="checkbox" checked={draft.public} onChange={e=>edit('public',e.target.checked)} disabled={busy}/><span>Show this stop when my phone is away</span></label><p className="setup-note">Off by default. Public stops can reveal your commute to anyone in the room. No stops appear during night mode.</p><div className="date-actions"><button type="button" disabled={busy} onClick={()=>setStep('direction')}>← Direction</button><button type="button" disabled={busy} onClick={()=>void directory('operator',draft)}>Change agency or stop</button><button disabled={busy||!draft.title.trim()}>Save stop</button></div></form></>}
      </>}
      </>}
      <details><summary>Coverage & data</summary><p className="setup-note">Availability varies by agency. Marguerite may not have a compatible live feed here; its official map remains available. Luma never fabricates predictions or scrapes it. Scheduled and saved times are labeled; check the operator before traveling.</p><div className="transit-links">{external(margueriteMap,'Marguerite live map')}{external(transitProvider,'Provider information')}</div><p className="setup-note">data provided by <a href="https://511.org" target="_blank" rel="noreferrer">511.org</a>. {demo?'All entries here are synthetic preview data.':'Setup and live polling share a limited request allowance.'}</p></details>
    </>}
    {confirm&&<div className="date-confirm" role="alert"><p>{confirm==='discard'?'Discard unsaved transit choices?':confirm==='token'?'Remove the saved token? Stops stay saved, but cached departure times will be cleared and polling will stop.':`Remove “${confirm.title}” from Luma only?`}</p><div className="date-actions"><button disabled={busy} onClick={()=>void confirmAction()}>{confirm==='discard'?'Discard changes':'Confirm removal'}</button><button disabled={busy} onClick={()=>setConfirm(null)}>Keep editing</button></div></div>}
    {busy&&<p role="status">Working…</p>}{message&&<p role="status">{message}</p>}
  </div>;
}
