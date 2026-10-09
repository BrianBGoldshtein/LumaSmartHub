import {applyGameCheckpoints,readGameCheckpoints,pauseGameWrites} from './gameCheckpoint';
// Wall entry only. iPhone settings never read or replace phone-local game saves.
export function installWallGameHandoff(){
  let stopped=false,seen='',timer:ReturnType<typeof setTimeout>;
  const controller=new AbortController();
  async function poll(){
    try{
      const response=await fetch('/api/v1/backups/game-handoff',{cache:'no-store',signal:controller.signal});
      if(response.ok){
        const job=await response.json();
        if(!stopped&&typeof job.nonce==='string'&&job.nonce!==seen&&['capture','restore'].includes(job.action)){
          seen=job.nonce;let ok=true,games={};
          try{if(job.action==='capture')games=readGameCheckpoints();else{pauseGameWrites(true);applyGameCheckpoints(job.games);}}catch{ok=false;pauseGameWrites(false);}
          try{
            await fetch('/api/v1/backups/game-handoff',{method:'POST',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({nonce:job.nonce,ok,games}),signal:controller.signal});
          }finally{
            // Old in-memory game objects must not overwrite restored saves
            // during pagehide. Reload only this wall document, not the Pi.
            if(ok&&job.action==='restore')location.reload();
          }
        }
      }
    }catch{/* A restart must not interrupt dashboard startup. */}
    if(!stopped)timer=setTimeout(()=>void poll(),2000);
  }
  void poll();return()=>{stopped=true;controller.abort();clearTimeout(timer);};
}
