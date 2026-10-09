import {useLayoutEffect,type RefObject} from 'react';

/** Reserve the actual painted label width, including late-loading theme fonts. */
export function useTimelineGutter(ref:RefObject<HTMLElement|null>,selector:string,variable:string,revision:string){
  useLayoutEffect(()=>{
    const root=ref.current;if(!root)return;
    let disposed=false;
    const measure=()=>{
      if(disposed)return;
      const labels=[...root.querySelectorAll<HTMLElement>(selector)];
      if(!labels.length)return;
      const pixel=parseFloat(getComputedStyle(root).getPropertyValue('--pixel'))||1;
      const gap=Math.max(12,root.getBoundingClientRect().width*.018);
      const width=Math.max(...labels.map(label=>{
        const range=document.createRange();range.selectNodeContents(label);
        return range.getBoundingClientRect().width;
      }));
      root.style.setProperty(variable,`${Math.ceil((width+gap)/pixel)*pixel}px`);
    };
    const observer=new ResizeObserver(measure);observer.observe(root);
    measure();void document.fonts.ready.then(measure);
    document.fonts.addEventListener('loadingdone',measure);
    return()=>{disposed=true;observer.disconnect();document.fonts.removeEventListener('loadingdone',measure);};
  },[ref,selector,variable,revision]);
}
