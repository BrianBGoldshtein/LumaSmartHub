import {useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import '@fontsource/manrope/latin-500.css';
import '@fontsource/manrope/latin-700.css';
import '@fontsource/newsreader/latin-700.css';
import '@fontsource/pixelify-sans/latin-700.css';
import '@fontsource/space-grotesk/latin-700.css';
import '../styles.css';
import './settings.css';
import {configureSetupTransport,type SetupResult} from '../setupTransport';
import {DeviceSetup} from '../DeviceSetup';
import {GoogleSetup} from '../GoogleSetup';
import {Onboarding} from '../Onboarding';
import {ExtrasSetup} from '../ExtrasSetup';
import {UsersSetup,PersonalSetup} from '../UserSetup';

const pending=new Map<string,{resolve:(value:SetupResult)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
configureSetupTransport(operation=>new Promise((resolve,reject)=>{
  if(parent===window||pending.size>=64){reject(Error('Open settings from your unlocked primary remote.'));return;}
  const id=crypto.randomUUID(),timer=setTimeout(()=>{pending.delete(id);reject(Error('Luma did not confirm this step. Check its status before retrying.'));},50000);
  pending.set(id,{resolve,reject,timer});
  parent.postMessage({kind:'luma-settings-request',id,operation},location.origin);
}));
window.addEventListener('message',event=>{
  if(event.origin!==location.origin||event.source!==parent||event.data?.kind!=='luma-settings-response')return;
  const item=pending.get(event.data.id);if(!item)return;
  const result=event.data.result;
  if(!result||!Number.isInteger(result.status)||result.status<200||result.status>599)return;
  clearTimeout(item.timer);pending.delete(event.data.id);item.resolve(result);
});
window.addEventListener('pagehide',()=>{for(const item of pending.values()){clearTimeout(item.timer);item.reject(Error('Settings closed.'));}pending.clear();});
function SettingsApp(){
  const [route,setRoute]=useState(()=>location.hash.slice(1));
  useEffect(()=>{const update=()=>setRoute(location.hash.slice(1));window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);},[]);
  const step=route.split('/')[0];
  useEffect(()=>{if(step==='close')parent.postMessage({kind:'luma-settings-close'},location.origin);},[step]);
  const screen=step==='google'?<GoogleSetup demo={false}/>:step==='onboarding'?<Onboarding demo={false}/>:step==='extras'?<ExtrasSetup demo={false}/>:step==='users'?<UsersSetup demo={false}/>:step==='personal'?<PersonalSetup demo={false}/>:<DeviceSetup demo={false}/>;
  return <div className="remote-shared-settings" key={step}>{screen}</div>;
}
createRoot(document.getElementById('root')!).render(<SettingsApp/>);
