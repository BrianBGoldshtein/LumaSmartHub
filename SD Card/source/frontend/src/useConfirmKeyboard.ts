import {useEffect,useRef} from 'react';

/** Keep a touch-first confirmation usable and contained with a keyboard. */
export function useConfirmKeyboard(open:boolean,onDismiss:()=>void){
  const panel=useRef<HTMLDivElement>(null),dismiss=useRef(onDismiss);
  dismiss.current=onDismiss;
  useEffect(()=>{
    if(!open||!panel.current)return;
    const dialog=panel.current;
    const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;
    const controls=()=>[...dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
    // Focus the safe/cancel choice first, never the destructive action.
    (controls().at(-1)||dialog).focus();
    function keydown(event:KeyboardEvent){
      if(event.key==='Escape'){
        event.preventDefault();event.stopPropagation();dismiss.current();return;
      }
      if(event.key!=='Tab')return;
      const buttons=controls();
      if(!buttons.length){event.preventDefault();dialog.focus();return;}
      const first=buttons[0],last=buttons[buttons.length-1],active=document.activeElement;
      if(event.shiftKey&&(active===first||!dialog.contains(active))){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&(active===last||!dialog.contains(active))){event.preventDefault();first.focus();}
    }
    document.addEventListener('keydown',keydown,true);
    return()=>{
      document.removeEventListener('keydown',keydown,true);
      if(previous?.isConnected)previous.focus();
    };
  },[open]);
  return panel;
}
