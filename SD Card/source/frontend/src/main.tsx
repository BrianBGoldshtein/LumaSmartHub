import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/newsreader/latin-400.css";
import "@fontsource/newsreader/latin-700.css";
import "@fontsource/space-grotesk/latin-500.css";
import "@fontsource/space-grotesk/latin-700.css";
import "@fontsource/pixelify-sans/latin-400.css";
import "@fontsource/pixelify-sans/latin-700.css";
import { Sun, CloudSun, Cloud, CloudFog, CloudRain, CloudSnow, CloudLightning, Droplets, CalendarDays, ListChecks, LockKeyhole, Volume2, SlidersHorizontal } from "lucide-react";
import { AmbientVisual, LumaGlow } from "./Interludes";
import { GoogleSetup } from "./GoogleSetup";
import { DeviceSetup } from "./DeviceSetup";
import { Onboarding } from "./Onboarding";
import { NetworkNotice } from "./NetworkNotice";
import {TimerBadge,TimerPanel,TimerComplete} from './FocusTimer';
import {ExtrasSetup} from './ExtrasSetup';
import {TodosPage} from './TodosPage';
import {DepartureNotice,DeparturePanel} from './DepartureNotice';
import {NightDisplay,useDisplayFilter} from './NightDisplay';
import {previewDisplay} from './displayState';
import {CountdownsPage} from './CountdownsPage';
import {AgendaPage} from './AgendaPage';
import {TransitPage} from './TransitPage';
import {visibleTransit,disconnectedTransit,transitCycle,sampleTransit,transitStress} from './transitState';
import {agendaDemo} from './agendaState';
import {visibleDates,disconnectedDates,sampleDates,dateCycle} from './countdownState';
import {precipitationLabel} from './weatherState';
import {STANDBY_CYCLE,standbyPage} from './standbyCycle';
import {setupLink} from "./setupTheme";
import { fetchSnapshot, sendCommand, watchSnapshots } from "./api";
import { demoSnapshot } from "./demo";
import type { CalendarEvent, Page, Snapshot, Theme, Weather } from "./types";
import "./styles.css";

const demoMode = new URLSearchParams(location.search).has("demo");
const demoParameters = new URLSearchParams(location.search);

function initialDemoSnapshot(): Snapshot {
  const theme = demoParameters.get("theme") as Theme | null;
  const privateMode = demoParameters.has("privacy");
  const result:Snapshot = {
    ...demoSnapshot,
    transit:demoParameters.get('page')==='transit'?visibleTransit((demoParameters.get('fixture')==='long-transit'?transitStress:sampleTransit)(Date.parse(demoSnapshot.server_time)),privateMode):[],
    countdowns:demoParameters.get('page')==='countdowns'||demoParameters.get('fixture')==='countdowns'?visibleDates(demoParameters.get('fixture')==='many-dates'?Array.from({length:12},(_,i)=>({...sampleDates[i%3],id:`date-${i}`,title:`${sampleDates[i%3].title} ${i+1}`})):demoParameters.get('fixture')==='long-dates'?sampleDates.map(item=>({...item,title:'A long-awaited celebration with family and friends across the country',value:item.value===null?null:12345})):sampleDates,privateMode):[],
    display:demoParameters.get('fixture')==='night'?previewDisplay('night-clock'):demoParameters.get('fixture')==='waking'?previewDisplay('waking'):null,
    departure:!privateMode && demoParameters.get('fixture')==='departure'?{key:'sample',title:'Design studio',start:new Date(Date.now()+23*60000).toISOString(),depart_at:new Date(Date.now()+8*60000).toISOString(),prep_minutes:5,travel_minutes:10,color:'#7986cb'}:null,
    weather: demoParameters.get('fixture')==='weather-hint' && demoSnapshot.weather ? {...demoSnapshot.weather,nudge:{kind:'precipitation',title:'Wet weather possible',detail:'Up to 60% chance',window:'Next 6h'}} : demoSnapshot.weather,
    calendar: demoParameters.get("fixture") === "empty" ? [] : demoParameters.get("fixture") === "long" ? demoSnapshot.calendar.map((event, index) => ({...event, summary:["Research planning and quarterly project review", "Dinner with friends at the neighborhood restaurant", "Prepare tomorrow’s presentation and travel checklist"][index]})) : demoSnapshot.calendar,
    todos: demoParameters.get("fixture") === "empty" ? [] : demoParameters.get('fixture')==='many-todos'?Array.from({length:14},(_,index)=>({...demoSnapshot.todos[index%3],id:`task-${index}`,summary:`${demoSnapshot.todos[index%3].summary} ${index+1}`})):demoSnapshot.todos,
    settings: { ...demoSnapshot.settings, theme: theme || demoSnapshot.settings.theme },
    state: {
      ...demoSnapshot.state,
      privacy: privateMode ? "private" : "full",
      phone_connected: !privateMode,
      assistant_phase: demoParameters.get('voice') === 'listening' ? 'listening' : demoSnapshot.state.assistant_phase,
    },
    privacy_redacted: privateMode,
  };
  result.agenda=privateMode?null:agendaDemo(result.calendar,['packed','crowded','short'].includes(demoParameters.get('fixture')||''),demoParameters.get('fixture')==='crowded',demoParameters.get('fixture')==='short');
  if(['packed','crowded','short'].includes(demoParameters.get('fixture')||''))result.calendar=result.agenda?.events.filter(event=>Date.parse(event.end)>Date.now())||[];
  return result;
}

function formatTime(value: Date | string, timezone?: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  }).format(typeof value === "string" ? new Date(value) : value);
}

function formatDay(value: Date, timezone?: string) {
  return new Intl.DateTimeFormat("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: timezone,
  }).format(value);
}

function WeatherIcon({ code = 0 }: {code?: number}) {
  const Icon = code <= 1 ? Sun : code === 2 ? CloudSun : code === 3 ? Cloud : code < 50 ? CloudFog : code >= 95 ? CloudLightning : (code >= 71 && code <= 77) || code === 85 || code === 86 ? CloudSnow : CloudRain;
  const pixels = Array.from({length:256},(_,i)=>{const x=i%16,y=Math.floor(i/16),r=Math.hypot(x-7.5,y-7.5);
    if(code<=1) return (r>=3 && r<=4.4) || ((x===7 || x===8) && (y<2 || y>13)) || ((y===7 || y===8) && (x<2 || x>13)) || ((x===y || x+y===15) && (x===2 || x===3 || x===12 || x===13));
    const cloud=(y>=5 && y<=10 && x>=2 && x<=13) || (y>=3 && y<=6 && x>=5 && x<=10);
    return cloud || (code>=51 && y>=12 && y<=14 && (x===4 || x===8 || x===12));
  });
  return <span className="weather-icon" aria-hidden="true"><Icon className="weather-vector" strokeWidth={1.7}/><svg className="pixel-weather" viewBox="0 0 16 16">{pixels.map((on,i)=>on && <rect key={i} x={i%16} y={Math.floor(i/16)} width="1" height="1"/>)}</svg></span>;
}

function weatherLabel(code = 0) {
  if (code <= 1) return "Clear skies";
  if (code === 2) return "Partly cloudy";
  if (code === 3) return "Overcast";
  if (code < 50) return "Foggy";
  if (code >= 95) return "Thunderstorms";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "Snow";
  return "Rain";
}

function StatusBar({ snapshot, page, onTimer }: { snapshot: Snapshot; page: Page; onTimer:()=>void }) {
  return (
    <header className="status-bar">
      <div className="wordmark"><LumaGlow />luma</div>
      <div className="status-items">
        <NetworkNotice demo={demoMode} theme={snapshot.settings.theme}/>
        {snapshot.privacy_redacted && <span className="privacy-chip">Private</span>}
        <span className={`phone-dot ${snapshot.state.phone_connected ? "online" : ""}`} />
        {snapshot.timer && snapshot.timer.status!=='idle' && page!=='ambient'?<TimerBadge timer={snapshot.timer} onOpen={onTimer}/>:<span className="status-copy">{demoMode ? "Preview" : snapshot.state.phone_connected ? "Connected" : "Standby"}</span>}
      </div>
    </header>
  );
}

function Clock({ snapshot, large = false }: { snapshot: Snapshot; large?: boolean }) {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  const parts = new Intl.DateTimeFormat("en-US", { hour:"numeric", minute:"2-digit", timeZone:snapshot.settings.timezone }).formatToParts(now);
  const digits = parts.filter(part => ["hour", "minute", "literal"].includes(part.type)).map(part=>part.value).join("").trim();
  return (
    <div className={large ? "clock clock-large" : "clock"}>
      <div className="clock-time"><span>{digits}</span><small>{parts.find(part=>part.type === "dayPeriod")?.value}</small></div>
      <div className="clock-date">{formatDay(now, snapshot.settings.timezone)}</div>
    </div>
  );
}

function WeatherHint({weather}:{weather:Weather}){
  const hint=weather.stale?null:weather.nudge;
  return hint?<p className="weather-hint"><strong>{hint.title}</strong><small>{hint.detail} · {hint.window}</small></p>:<p>{weatherLabel(weather.weather_code)}</p>;
}

function WeatherCard({ weather, compact = false }: { weather: Weather | null; compact?: boolean }) {
  if (!weather) return <section className="card weather-card empty"><span>Weather will appear after setup</span></section>;
  return (
    <section className={`card weather-card ${compact ? "compact" : ""}`}>
      {weather.stale && <div className="eyebrow">Last updated</div>}
      <div className="weather-now">
        <WeatherIcon code={weather.weather_code} />
        <span className="temperature">{Math.round(weather.temperature)}°</span>
      </div>
      <WeatherHint weather={weather}/>
      <div className="weather-range"><span>H {Math.round(weather.high)}°</span><span>L {Math.round(weather.low)}°</span></div>
    </section>
  );
}

function eventStyle(event: CalendarEvent): React.CSSProperties {
  const color = event.event_color || event.calendar_color;
  return { "--event-color": color && /^#[0-9a-f]{6}$/i.test(color) ? color : "var(--accent)" } as React.CSSProperties;
}

function EventRow({ event, timezone }: { event: CalendarEvent; index: number; timezone?: string }) {
  const ongoing = new Date(event.start).getTime() <= Date.now() && new Date(event.end).getTime() > Date.now();
  const dateFormat = new Intl.DateTimeFormat("en-US", {month:"short",day:"numeric",timeZone:timezone});
  const date = dateFormat.format(new Date(event.start));
  const today = dateFormat.format(new Date());
  return (
    <article className="event-row" style={eventStyle(event)}>
      <div className="event-time"><span>{event.all_day ? "All day" : formatTime(event.start, timezone)}</span><small>{ongoing && !event.all_day ? "Now" : date !== today ? date : event.all_day ? "Today" : `– ${formatTime(event.end, timezone)}`}</small></div>
      <div className="event-line"><span /><div><h3>{event.summary}</h3>{(event.calendar_name || event.location) && <p>{[event.calendar_name, event.location].filter(Boolean).join(" · ")}</p>}</div></div>
    </article>
  );
}

function AgendaCard({ events, limit = 3, timezone }: { events: CalendarEvent[]; limit?: number; timezone?: string }) {
  const shown = events.slice(0, limit);
  return (
    <section className="card agenda-card">
      <div className="card-heading"><CalendarDays /><span className="eyebrow">Up next</span></div>
      <div className="event-list" style={{ "--rows": Math.max(1, shown.length) } as React.CSSProperties}>
        {shown.map((event, index) => <EventRow key={event.id} event={event} index={index} timezone={timezone} />)}
        {!events.length && <div className="empty-message"><Sun /><span>Time to yourself.</span></div>}
      </div>
    </section>
  );
}

function HomePage({ snapshot }: { snapshot: Snapshot }) {
  return (
    <main className="page home-page">
      <section className="hero card"><Clock snapshot={snapshot} large /></section>
      <WeatherCard weather={snapshot.weather} compact />
      <AgendaCard events={snapshot.calendar} limit={3} timezone={snapshot.settings.timezone} />
    </main>
  );
}

function WeatherPage({ snapshot }: { snapshot: Snapshot }) {
  const weather = snapshot.weather;
  return (
    <main className="page focus-page weather-page">
      <section className="weather-overview"><div><span className="eyebrow">{snapshot.settings.weather_location_label || "Home"}{weather?.stale ? " · Last known" : ""}</span><h1>{weather ? `${Math.round(weather.temperature)}°` : "—"}</h1>{weather?<WeatherHint weather={weather}/>:<p>Set location</p>}</div><WeatherIcon code={weather?.weather_code} />{weather && <div className="weather-detail"><span>High {Math.round(weather.high)}°</span><span>Low {Math.round(weather.low)}°</span></div>}</section>
      <section className="card hourly-card">
        {(weather?.hourly || []).slice(0, 4).map((hour) => <div className="hour" key={hour.time}><span>{new Intl.DateTimeFormat("en-US", {hour:"numeric",timeZone:snapshot.settings.timezone}).format(new Date(hour.time))}</span><WeatherIcon code={hour.weather_code}/><strong>{Math.round(hour.temperature)}°</strong><small><Droplets />{precipitationLabel(hour.precipitation_probability)}</small></div>)}
        {!weather?.hourly.length && <div className="empty-message"><span>Forecast unavailable.</span></div>}
      </section>
      <footer className="attribution">{weather?.attribution}</footer>
    </main>
  );
}

function AmbientPage({ snapshot }: { snapshot: Snapshot }) {
  return <main className="page ambient-page"><AmbientVisual key={snapshot.settings.theme} theme={snapshot.settings.theme}/></main>;
}

function PrivacyStandby({ snapshot }: { snapshot: Snapshot }) {
  return <main className="page privacy-page"><section className="card privacy-clock"><Clock snapshot={snapshot} large /></section><WeatherCard weather={snapshot.weather} compact /><div className="privacy-note"><LockKeyhole/><b>Private standby</b></div></main>;
}

function AssistantOrb({ phase, onClick }: { phase: string; onClick: () => void }) {
  return <button aria-label={phase==='idle'?'Open Luma assistant':`Luma ${phase}`} className={`assistant-orb ${phase}`} onClick={onClick}><LumaGlow /><b aria-live="polite">{phase === "idle" ? "" : phase}</b></button>;
}

function ControlIsland({ snapshot, onUpdate, open, setOpen, onTimer }: { snapshot: Snapshot; onUpdate: (snapshot: Snapshot) => void; open:boolean;setOpen:(open:boolean)=>void;onTimer:()=>void }) {
  const act = async (name: string, value?: unknown) => {
    if (demoMode) {
      if (name === "set_theme") onUpdate({...snapshot, settings:{...snapshot.settings, theme:value as Theme}});
      if (name === "set_brightness" || name === "set_volume") onUpdate({...snapshot,settings:{...snapshot.settings,[name === "set_brightness" ? "brightness" : "volume"]:value}} as Snapshot);
      if (name === "privacy_now") onUpdate({...snapshot,privacy_redacted:true});
      if(name==='good_night' || name==='good_morning' || name==='screen_off')onUpdate({...snapshot,display:previewDisplay(name==='good_night'?'night-clock':name==='screen_off'?'off':'waking',snapshot.settings.brightness),state:{...snapshot.state,display_power:name==='screen_off'?'off':'on'}});
      return;
    }
    onUpdate(await sendCommand(name, value));
  };
  return (
    <div className={`control-island ${open ? "open" : ""}`} onClick={event=>event.stopPropagation()}>
      <button className="island-handle" onClick={() => setOpen(!open)} aria-label="Open controls"><SlidersHorizontal /></button>
      {open && <div className="island-panel">
        <label><Sun/><input aria-label="Brightness" type="range" min="0" max="100" defaultValue={snapshot.settings.brightness} onChange={(event) => act("set_brightness", Number(event.target.value))} /></label>
        <label><Volume2/><input aria-label="Volume" type="range" min="0" max="100" defaultValue={snapshot.settings.volume} onChange={(event) => act("set_volume", Number(event.target.value))} /></label>
        <div className="theme-buttons">{(["luma-glass", "hearth", "neon-grid"] as const).map((theme) => <button key={theme} className={snapshot.settings.theme === theme ? "selected" : ""} onClick={() => act("set_theme", theme)}>{theme === "luma-glass" ? "Glass" : theme === "hearth" ? "Hearth" : "Neon"}</button>)}</div>
        <button className="privacy-button" onClick={() => act("privacy_now")}>Hide private details</button>
        <button className="privacy-button" onClick={onTimer}>Focus timer</button>
        <button className="privacy-button" onClick={()=>act('good_night')}>Good night</button>
        <button className="privacy-button" onClick={()=>act('good_morning')}>Good morning</button>
        <button className="privacy-button" onClick={()=>act('screen_off')}>Screen off</button>
        <a className="calendar-setup-link" href={setupLink(demoMode,snapshot.settings.theme,"google")}><CalendarDays/> Google Calendar</a>
        <a className="calendar-setup-link" href={setupLink(demoMode,snapshot.settings.theme,"device")}><SlidersHorizontal/> Device setup</a>
      </div>}
    </div>
  );
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(demoMode ? initialDemoSnapshot() : null);
  const [page, setPage] = useState<Page>((demoParameters.get("page") as Page | null) || "home");
  const [error, setError] = useState<string>();
  const [overlay,setOverlay] = useState<'controls'|'timer'|'departure'|null>(null);
  const [calendarHoldUntil,setCalendarHoldUntil]=useState(0);
  useDisplayFilter(snapshot,demoMode);
  useEffect(()=>{if(snapshot?.display && snapshot.display.mode!=='day')setOverlay(null);},[snapshot?.display?.mode]);
  useEffect(()=>{
    if(!demoMode || snapshot?.display?.mode!=='waking' || !snapshot.display.ramp)return;
    const timer=setTimeout(()=>setSnapshot(current=>current?{...current,display:previewDisplay('day',current.settings.brightness)}:current),20000);
    return()=>clearTimeout(timer);
  },[snapshot?.display?.ramp?.id]);
  useEffect(()=>{if(snapshot?.privacy_redacted || !snapshot?.departure)setOverlay(current=>current==='departure'?null:current);},[snapshot?.privacy_redacted,snapshot?.departure]);
  useEffect(()=>{
    if(!demoMode || snapshot?.timer?.status!=='running')return;
    const id=snapshot.timer.id;
    const handle=setTimeout(()=>setSnapshot(current=>current?.timer?.id===id && current.timer.status==='running'?{...current,timer:{...current.timer,status:'complete',remaining_seconds:0}}:current),snapshot.timer.remaining_seconds*1000);
    return()=>clearTimeout(handle);
  },[snapshot?.timer]);

  useEffect(() => {
    if (demoMode) return;
    const receive=(next:Snapshot)=>{setSnapshot(next);setError(undefined);};
    fetchSnapshot().then(receive).catch(() => setError("Waiting for the local service."));
    return watchSnapshots(receive, ()=>{
      // A lost control connection must never leave private events on the wall.
      setSnapshot(current=>current ? {...current,room:null,agenda:null,transit:disconnectedTransit(current.transit),countdowns:disconnectedDates(current.countdowns),display:current.display && current.display.mode!=='day'?{...current.display,mode:'off',brightness:0,ramp:null,handoff:{...current.display.handoff,revision:null,needs_frame:false}}:current.display,privacy_redacted:true,departure:null,calendar:[],ongoing:[],todos:[],notifications:[],weather:current.weather?{...current.weather,stale:true,nudge:null}:null,state:{...current.state,phone_connected:false}} : null);
    }, action=>{
      if(action.overlay) setOverlay(action.overlay==='timer'?'timer':'controls');
      if(action.page && ["show_page","next_page","previous_page","good_morning"].includes(action.name)) setPage(action.name === "good_morning" ? "home" : action.page);
    });
  }, []);

  const cycleKey=JSON.stringify(snapshot?.settings.cycle || []);
  const privateMode=snapshot?.privacy_redacted;
  const pausedUntil=snapshot?.state.cycle_paused_until;
  const hasDates=visibleDates(snapshot?.countdowns,!!privateMode).length>0;
  const hasTransit=visibleTransit(snapshot?.transit,!!privateMode).length>0;
  useEffect(() => {
    if (!snapshot || (demoMode && demoParameters.has("hold"))) return;
    const pauseRemaining=Math.max(0,pausedUntil?new Date(pausedUntil).getTime()-Date.now():0,page==='agenda'?calendarHoldUntil-Date.now():0);
    const base:Snapshot["settings"]["cycle"] = privateMode ? STANDBY_CYCLE : JSON.parse(cycleKey);
    const cycle=transitCycle(dateCycle(base,hasDates),hasTransit);
    if(!cycle.length) return;
    const currentIndex = Math.max(0, cycle.findIndex((item) => item.page === page));
    const timer = window.setTimeout(() => setPage(cycle[(currentIndex + 1) % cycle.length].page), pauseRemaining + cycle[currentIndex].seconds * 1000);
    return () => clearTimeout(timer);
  }, [cycleKey, privateMode, pausedUntil, page,hasDates,hasTransit,calendarHoldUntil]);

  const content = useMemo(() => {
    if (!snapshot) return null;
    if(page==='countdowns')return <CountdownsPage snapshot={snapshot}/>;
    if(page==='transit')return <TransitPage snapshot={snapshot} demo={demoMode}/>;
    if (snapshot.privacy_redacted) {
      const safePage=standbyPage(page);
      return safePage==='weather'?<WeatherPage snapshot={snapshot}/>:safePage==='ambient'?<AmbientPage snapshot={snapshot}/>:<PrivacyStandby snapshot={snapshot}/>;
    }
    if (page === "agenda") return <AgendaPage snapshot={snapshot} onInteraction={()=>setCalendarHoldUntil(Date.now()+60000)}/>;
    if (page === "weather") return <WeatherPage snapshot={snapshot} />;
    if (page === "todos") return <TodosPage snapshot={snapshot} demo={demoMode} onUpdate={setSnapshot}/>;
    if (page === "ambient") return <AmbientPage snapshot={snapshot} />;
    return <HomePage snapshot={snapshot} />;
  }, [snapshot, page]);

  const wake=async()=>{if(!snapshot)return;if(demoMode)setSnapshot({...snapshot,display:previewDisplay('waking',snapshot.settings.brightness),state:{...snapshot.state,display_power:'on'}});else setSnapshot(await sendCommand('wake'));};
  const privateSetup=!demoMode&&snapshot?.settings.onboarding_completed===true&&snapshot.privacy_redacted;
  if(snapshot?.display?.mode==='off')return <button className="sleep-screen" onClick={()=>void wake()} aria-label="Wake Luma"/>;
  if(snapshot?.display?.mode==='night-clock' || snapshot?.display?.mode==='waking')return <div className={`app theme-${snapshot.settings.theme} night-screen`}><NightDisplay snapshot={snapshot} onWake={()=>void wake()}/>{snapshot.state.assistant_phase!=='idle'&&<AssistantOrb phase={snapshot.state.assistant_phase} onClick={()=>void wake()}/>}</div>;
  if (demoParameters.get("setup") === "google") return <GoogleSetup demo={demoMode}/>;
  if (demoParameters.get("setup") === "device") return <DeviceSetup demo={demoMode}/>;
  if (demoParameters.get("setup") === "onboarding") return <Onboarding demo={demoMode} locked={privateSetup}/>;
  if (demoParameters.get("setup") === "extras") return <ExtrasSetup demo={demoMode} locked={privateSetup}/>;
  if (error) return <div className="boot-screen error"><LumaGlow/><h1>Luma is reconnecting</h1><p>{error}</p></div>;
  if (!snapshot) return <div className="boot-screen"><LumaGlow/><p>Waking your space…</p></div>;
  if (!demoMode && snapshot.settings.onboarding_completed === false) return <Onboarding demo={false}/>;
  if (snapshot.state.display_power === "off") return <button className="sleep-screen" onClick={()=>void wake()} aria-label="Wake Luma" />;

  return (
    <div className={`app theme-${snapshot.settings.theme}${page === "ambient" ? " is-ambient" : ""}`} onClick={() => {if(page === "ambient") setPage("home");}}>
      <div className="atmosphere" /><StatusBar snapshot={snapshot} page={snapshot.privacy_redacted ? "home" : page} onTimer={()=>setOverlay('timer')} />
      <div className="page-stage" key={`${snapshot.privacy_redacted}-${page}`}>{content}</div>
      {!snapshot.privacy_redacted && <nav className="page-dots" aria-label="Dashboard pages">{(["home", "agenda", "weather", "todos", "ambient",...(hasDates?['countdowns']:[]),...(hasTransit?['transit']:[])] as Page[]).map((item) => <button aria-label={item} className={page === item ? "active" : ""} onClick={() => setPage(item)} key={item} />)}</nav>}
      <AssistantOrb phase={snapshot.state.assistant_phase} onClick={() => setPage("home")} />
      <ControlIsland snapshot={snapshot} onUpdate={setSnapshot} open={overlay==='controls'} setOpen={open=>setOverlay(open?'controls':null)} onTimer={()=>setOverlay('timer')} />
      {overlay==='timer' && <TimerPanel snapshot={snapshot} demo={demoMode} onUpdate={setSnapshot} onClose={()=>setOverlay(null)}/>}
      {overlay==='departure' && !snapshot.privacy_redacted && snapshot.departure && <DeparturePanel key={snapshot.departure.key} snapshot={snapshot} demo={demoMode} onUpdate={setSnapshot} onClose={()=>setOverlay(null)}/>}
      {!overlay && snapshot.timer?.status==='complete' && <TimerComplete timer={snapshot.timer} privateMode={snapshot.privacy_redacted} onOpen={()=>setOverlay('timer')}/>}
      {!overlay && snapshot.timer?.status!=='complete' && !snapshot.privacy_redacted && snapshot.departure && <DepartureNotice reminder={snapshot.departure} serverTime={snapshot.server_time} onOpen={()=>setOverlay('departure')}/>}
      {!overlay && snapshot.timer?.status!=='complete' && !snapshot.departure && !snapshot.privacy_redacted && snapshot.notifications.slice(0,1).filter(item=>Date.now()-new Date(item.received_at).getTime()<45000).map(item=><aside className="phone-notice" role="status" key={item.id}><small>{item.app_name}{item.category==="incoming-call"?" · Incoming call":" · Notification"}</small><strong>{item.title}</strong>{item.body && <p>{item.body}</p>}</aside>)}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
