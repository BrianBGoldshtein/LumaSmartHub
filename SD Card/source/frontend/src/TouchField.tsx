import {createContext,useContext,useId,useRef,useState,type ReactNode} from "react";
import {TouchKeyboard} from "./TouchKeyboard";
import {editInput,validInput,type KeyboardMode} from "./touchInput";
import {SetupActivity} from "./setupActivity";
import {isRemoteSetup} from './setupTransport';

const KeyboardContext=createContext<{active:string|null;setActive:(id:string|null)=>void}|null>(null);
export function TouchInputProvider({children}:{children:ReactNode}){
  const [active,setActive]=useState<string|null>(null);
  return <KeyboardContext.Provider value={{active,setActive}}>{children}</KeyboardContext.Provider>;
}
type Props={label:string;value:string;onChange:(value:string)=>void;mode?:KeyboardMode;secret?:boolean;required?:boolean;disabled?:boolean;minLength?:number;maxLength?:number;placeholder?:string;pattern?:string;autoComplete?:string};
export function TouchField({label,value,onChange:change,mode="text",secret=false,required=false,disabled=false,minLength,maxLength=80,placeholder,pattern,autoComplete="off"}:Props){
  const activity=useContext(SetupActivity);
  const onChange=(next:string)=>{activity.edited();change(next);};
  const context=useContext(KeyboardContext);
  if(!context)throw Error("TouchField requires TouchInputProvider");
  const id=useId(),input=useRef<HTMLInputElement>(null),selection=useRef({start:value.length,end:value.length});
  const open=!isRemoteSetup()&&context.active===id;
  const key=(key:string)=>{
    const result=editInput(value,key,selection.current.start,selection.current.end,maxLength,mode);
    onChange(result.value);selection.current={start:result.caret,end:result.caret};
    requestAnimationFrame(()=>input.current?.setSelectionRange(result.caret,result.caret));
  };
  return <div className="touch-field"><label htmlFor={id}>{label}<input ref={input} id={id} type={secret?"password":"text"} inputMode={mode==="text"?"text":mode==="digits"?"numeric":"decimal"} required={required} disabled={disabled} minLength={minLength} maxLength={maxLength} pattern={pattern} placeholder={placeholder} autoComplete={autoComplete} autoCapitalize="none" spellCheck={false} value={value} onFocus={()=>context.setActive(id)} onSelect={event=>{selection.current={start:event.currentTarget.selectionStart??value.length,end:event.currentTarget.selectionEnd??value.length};}} onChange={event=>{const next=event.target.value;if(next.length<=maxLength && validInput(next,mode))onChange(next);}}/></label>
    {!isRemoteSetup()&&<button type="button" className="keyboard-toggle" disabled={disabled} aria-expanded={open} aria-controls={`${id}-keyboard`} onClick={()=>{selection.current={start:input.current?.selectionStart??value.length,end:input.current?.selectionEnd??value.length};context.setActive(open?null:id);}}>{open?"Hide keyboard":"Type on screen"}</button>}
    {open && <div id={`${id}-keyboard`}><TouchKeyboard value={value} onChange={onChange} onKey={key} onClose={()=>context.setActive(null)} maxLength={maxLength} mode={mode} disabled={disabled}/></div>}
  </div>;
}
