import {useState} from "react";
import {editInput,type KeyboardMode} from "./touchInput";

// Controlled input: no clipboard, persistence, global key listener or telemetry.
export function TouchKeyboard({value,onChange,onClose,maxLength=64,mode="text",onKey,disabled=false}:{value:string;onChange:(value:string)=>void;onClose:()=>void;maxLength?:number;mode?:KeyboardMode;onKey?:(key:string)=>void;disabled?:boolean}){
  const [shift,setShift]=useState(false),[symbols,setSymbols]=useState(false);
  const rows=mode!=="text"?["123","456","789",mode==="decimal"?"-0.":"0"]:symbols?["1234567890","!@#$%^&*()","-_=+[]{}\\|",";:'\",.<>/?`~"]:["1234567890","qwertyuiop","asdfghjkl","zxcvbnm"];
  const keypress=(key:string)=>{if(disabled)return;if(onKey)onKey(key);else onChange(editInput(value,key,value.length,value.length,maxLength,mode).value);};
  const add=(key:string)=>keypress(shift?key.toUpperCase():key);
  return <div className={`touch-keyboard ${mode!=="text"?"numeric-keyboard":""}`} role="group" aria-label="On-screen keyboard">
    {rows.map((row,i)=><div className="keyboard-row" key={i}>{[...row].map(key=><button type="button" disabled={disabled} key={key} onClick={()=>add(key)}>{shift?key.toUpperCase():key}</button>)}</div>)}
    <div className="keyboard-row">{mode==="text" && <><button type="button" disabled={disabled} aria-pressed={shift} onClick={()=>setShift(!shift)}>Shift</button><button type="button" disabled={disabled} onClick={()=>setSymbols(!symbols)}>{symbols?"ABC":"#+="}</button><button type="button" disabled={disabled} className="keyboard-space" onClick={()=>add(" ")}>Space</button></>}<button type="button" disabled={disabled} onClick={()=>keypress("Clear")}>Clear</button><button type="button" disabled={disabled} aria-label="Backspace" onClick={()=>keypress("Backspace")}>⌫</button><button type="button" onClick={onClose}>Done</button></div>
  </div>;
}
