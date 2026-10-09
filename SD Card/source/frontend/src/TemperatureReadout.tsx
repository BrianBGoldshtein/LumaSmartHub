import {useEffect,useState} from 'react';
import {Thermometer} from 'lucide-react';
import {temperatureView} from './temperatureState';
import type {DeviceTemperature} from './temperatureState';
import './temperature.css';

export function TemperatureReadout({reading,example=false}:{reading?:DeviceTemperature|null;example?:boolean}){
  const [now,setNow]=useState(Date.now);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),5000);return()=>clearInterval(timer);},[]);
  const view=temperatureView(reading,now);
  return <div className={`temperature-readout temperature-${view.status}`} aria-label="Raspberry Pi CPU temperature">
    <div className="temperature-heading"><Thermometer size={24} aria-hidden="true"/><span>Pi temperature<small>CPU sensor · {example?'Example':'Refreshes automatically'}</small></span></div>
    <div className="temperature-value"><strong>{view.value}</strong><small>{view.label}</small></div>
  </div>;
}

export function DeviceTemperaturePanel({demo}:{demo:boolean}){
  const [reading,setReading]=useState<DeviceTemperature|null>(null);
  useEffect(()=>{
    let live=true,controller:AbortController|undefined;
    async function refresh(){
      if(document.hidden||controller)return;
      if(demo){setReading({celsius:56.5,status:'normal',sampled_at:new Date().toISOString()});return;}
      controller=new AbortController();
      const timeout=setTimeout(()=>controller?.abort(),5000);
      try{
        const response=await fetch('/api/v1/device/temperature',{signal:controller.signal,cache:'no-store'});
        if(!response.ok)throw Error();
        const data=await response.json();if(live)setReading(data);
      }catch{if(live)setReading(null);}finally{clearTimeout(timeout);controller=undefined;}
    }
    void refresh();const timer=setInterval(()=>void refresh(),10000);
    document.addEventListener('visibilitychange',refresh);
    return()=>{live=false;controller?.abort();clearInterval(timer);document.removeEventListener('visibilitychange',refresh);};
  },[demo]);
  return <section className="device-temperature-panel"><TemperatureReadout reading={reading} example={demo}/><p className="setup-note">Built-in CPU temperature, not room temperature. No external probe required.</p></section>;
}
import {setupFetch as fetch} from './setupTransport';
