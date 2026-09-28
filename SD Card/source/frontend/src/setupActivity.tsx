import {createContext,useContext,useEffect} from "react";

// Panels report operations, never credentials or unsaved field contents.
export const SetupActivity=createContext<{busy:(value:boolean)=>void;edited:()=>void}>({busy:()=>{},edited:()=>{}});
export function useSetupActivity(busy:boolean){
  const activity=useContext(SetupActivity);
  useEffect(()=>{activity.busy(busy);return()=>activity.busy(false);},[busy,activity.busy]);
  return activity;
}
