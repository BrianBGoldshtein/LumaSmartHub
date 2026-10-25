import {useState} from 'react';
import {ChevronLeft,ChevronRight,Smartphone} from 'lucide-react';
import {TouchField} from './TouchField';
import {phonePage,phoneSignal,type PhoneChoice} from './phoneChoices';
import './phonePicker.css';

export function PhonePicker({devices,busy,onSelect}:{devices:PhoneChoice[];busy:boolean;onSelect:(phone:PhoneChoice)=>void}){
  const [query,setQuery]=useState(''),[page,setPage]=useState(0);
  const view=phonePage(devices,query,page);
  return <div className="phone-picker">
    <TouchField label="Find your phone by name or address" value={query} disabled={busy} maxLength={80}
      placeholder="e.g. iPhone" onChange={text=>{setQuery(text);setPage(0);}}/>
    {query&&<button type="button" disabled={busy} onClick={()=>{setQuery('');setPage(0);}}>Clear search</button>}
    <p className="setup-note">Named devices first, then strongest signal. Search or page through every result.</p>
    <p className="phone-picker-count" role="status">{view.total?`${view.start}–${view.end} of ${view.total} devices${query?` (${devices.length} discovered)`:''}`:
      query?'No matches. Clear the search to see every device.':'No devices yet. Keep iPhone Settings → Bluetooth open nearby.'}</p>
    <div className="network-list phone-picker-results" aria-label="Nearby Bluetooth devices">{view.rows.map(phone=>
      <button type="button" key={phone.path} disabled={busy} onClick={()=>onSelect(phone)}>
        <Smartphone aria-hidden="true"/><span><strong>{phone.name}</strong><small>{phone.address}</small>
        <small>{phoneSignal(phone.rssi)}{phone.paired?` · ${phone.trusted?'Previously paired':'Unfinished bond'}`:''}</small></span>
      </button>)}</div>
    {view.pages>1&&<nav className="phone-picker-pages" aria-label="Bluetooth device pages">
      <button type="button" disabled={busy||view.index===0} onClick={()=>setPage(view.index-1)}><ChevronLeft aria-hidden="true"/>Previous</button>
      <span>Page {view.index+1} of {view.pages}</span>
      <button type="button" disabled={busy||view.index===view.pages-1} onClick={()=>setPage(view.index+1)}>Next<ChevronRight aria-hidden="true"/></button>
    </nav>}
    <p className="setup-note">Names and signal strength are hints—not proof of identity. Check the matching code on your phone. Discovery stops after 45 seconds; start another scan if needed.</p>
  </div>;
}
