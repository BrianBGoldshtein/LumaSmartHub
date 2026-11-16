import {useMemo,useState,type MouseEvent} from 'react';
import {ArrowLeft, AudioLines, CalendarDays, ChevronRight, HardDrive, ListChecks, Monitor, Users, Wifi, Wind} from 'lucide-react';
import {AppearanceSetup} from './AppearanceSetup';
import {DeviceSetup} from './DeviceSetup';
import {ExtrasSetup} from './ExtrasSetup';
import {FanControlPanel} from './FanControlPanel';
import {GoogleSetup} from './GoogleSetup';
import {NetworkSetup} from './NetworkSetup';
import {NotificationSoundSetup} from './NotificationSoundSetup';
import {PiConnectSetup} from './PiConnectSetup';
import {DeviceTemperaturePanel} from './TemperatureReadout';
import {TouchInputProvider} from './TouchField';
import {UpdateSetup} from './UpdateSetup';
import {UsersSetup} from './UserSetup';
import {VoiceSetup} from './VoiceSetup';
import {WifiHotspotSetup} from './WifiHotspotSetup';
import {announceAdminNeeded} from './adminState';
import {SetupActivity} from './setupActivity';
import {setupLink} from './setupTheme';
import {isRemoteSetup,setupFetch} from './setupTransport';
import {settingsDestination,settingsGroups,type SettingsPanelId,type SettingsSection} from './settingsRoutes';
import type {Theme} from './types';
import './settingsHub.css';

const icons = {
  display: Monitor,
  networking: Wifi,
  people: Users,
  calendar: CalendarDays,
  audio: AudioLines,
  room: Wind,
  system: HardDrive,
};

async function coolingRequest<T>(method:string,path:string,body?:unknown):Promise<T> {
  const response=await setupFetch(`/api/v1/${path}`,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){announceAdminNeeded(data);throw Error(typeof data.detail==='string'?data.detail:'Could not reach cooling controls.');}
  return data;
}

type ControlsProps = {
  id:SettingsPanelId;
  demo:boolean;
  theme:Theme;
  onTheme:(theme:Theme)=>void;
  onUnsavedChange:(dirty:boolean)=>void;
};

function SettingsControls({id,demo,theme,onTheme,onUnsavedChange}:ControlsProps) {
  const extra = {demo,embedded:true,onUnsavedChange};
  switch(id) {
    case 'appearance': return <AppearanceSetup demo={demo} theme={theme} onSaved={onTheme}/>;
    case 'location': case 'speaker': case 'bluetooth': case 'iphone-remote': case 'shortcuts': case 'diagnostics':
      return <DeviceSetup demo={demo} section={id}/>;
    case 'privacy-pin': return <DeviceSetup demo={demo} section="privacy"/>;
    case 'wifi': return <NetworkSetup demo={demo}/>;
    case 'hotspot': return <WifiHotspotSetup demo={demo}/>;
    case 'user-accounts': return <UsersSetup demo={demo} embedded/>;
    case 'google-calendar': return <GoogleSetup demo={demo} embedded/>;
    case 'night': case 'departure': case 'countdowns': case 'transit': case 'scenes': case 'backup':
      return <ExtrasSetup {...extra} panel={id}/>;
    case 'weather-hints': return <ExtrasSetup {...extra} panel="weather"/>;
    case 'focus': return <ExtrasSetup {...extra} panel="timer"/>;
    case 'purifier': return <ExtrasSetup {...extra} panel="room"/>;
    case 'voice': return <VoiceSetup demo={demo}/>;
    case 'chimes': return <NotificationSoundSetup demo={demo}/>;
    case 'updates': return <UpdateSetup demo={demo}/>;
    case 'cooling': return <><DeviceTemperaturePanel demo={demo}/><FanControlPanel demo={demo} request={coolingRequest}/></>;
    case 'pi-connect': return <PiConnectSetup demo={demo}/>;
  }
}

export function SettingsHub({demo,theme,section}:{demo:boolean;theme:Theme;section?:string|null}) {
  const destination = settingsDestination(section);
  const group = destination?.group;
  const panel = destination?.panel;
  const [chosenTheme,setChosenTheme] = useState<Theme>();
  const [unsaved,setUnsaved] = useState(false);
  const [busy,setBusy] = useState(false);
  const [notice,setNotice] = useState('');
  const activity = useMemo(()=>({busy:setBusy,edited:()=>{}}),[]);
  const currentTheme = demo||isRemoteSetup()?chosenTheme??theme:theme;
  const link = (target?:SettingsSection)=>setupLink(demo,currentTheme,'device',target);

  function allowNavigation(event:MouseEvent<HTMLAnchorElement>) {
    if(busy){
      event.preventDefault();
      setNotice('Wait for Luma to finish the current operation.');
    } else if(unsaved&&!window.confirm('Leave this page and discard your unsaved changes?')){
      event.preventDefault();
    }
  }

  return <div className={`app theme-${currentTheme} setup-page settings-hub`}>
    <main className="settings-main" aria-labelledby="settings-page-title">
      <nav className="settings-path" aria-label="Settings navigation">
        {group ? <>
          <a href={link()} onClick={allowNavigation}><ArrowLeft aria-hidden="true"/> Settings</a>
          {panel&&<><ChevronRight aria-hidden="true"/><a href={link(group.id)} onClick={allowNavigation}>{group.title}</a></>}
        </> : <a href={setupLink(demo,currentTheme)}><ArrowLeft aria-hidden="true"/>{isRemoteSetup()?'Back to remote':'Dashboard'}</a>}
      </nav>
      <header className="settings-header">
        <h1 id="settings-page-title" tabIndex={-1}>{panel?.title??group?.title??'Settings'}</h1>
      </header>
      {notice&&<p className="settings-navigation-notice" role="status">{notice}</p>}
      {!group&&<nav className="settings-groups" aria-label="Settings categories">
        {settingsGroups.map(item=>{
          const Icon=icons[item.id];
          return <a href={link(item.id)} key={item.id} className="settings-group">
            <Icon aria-hidden="true" className="settings-group-icon"/>
            <strong>{item.title}</strong>
            <ChevronRight aria-hidden="true" className="settings-chevron"/>
            <span>{item.detail}</span>
          </a>;
        })}
        <a className="settings-group settings-guide" href={setupLink(demo,currentTheme,'onboarding')}>
          <ListChecks aria-hidden="true" className="settings-group-icon"/>
          <strong>Guided setup</strong>
          <ChevronRight aria-hidden="true" className="settings-chevron"/>
          <span>Walk through Luma’s setup step by step</span>
        </a>
      </nav>}
      {group&&!panel&&<nav className="settings-options" aria-label={group.title}>
        {group.panels.map(item=><a key={item.id} href={link(item.id)}>
          <strong>{item.title}</strong><span>{item.detail}</span><ChevronRight aria-hidden="true"/>
        </a>)}
      </nav>}
      {panel&&<div className="setup-content device-setup settings-controls" data-panel={panel.id}>
        <SetupActivity.Provider value={activity}>
          <TouchInputProvider>
            <SettingsControls key={panel.id} id={panel.id} demo={demo} theme={currentTheme} onTheme={setChosenTheme} onUnsavedChange={setUnsaved}/>
          </TouchInputProvider>
        </SetupActivity.Provider>
      </div>}
    </main>
  </div>;
}
