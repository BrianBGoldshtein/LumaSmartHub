// Small, versioned local checkpoints; never write on every animation frame.
import {BREAKER_LEVEL_LIMIT,BRICK_LAYOUTS,PONG_BALL_TEMPO,PONG_MAX_SPEED,PONG_TEMPO,PONG_TEMPO_VERSION} from "./classics.ts";
import {INVADER_PLAYER_SPEED} from "./spaceInvaders.ts";
export type GameKey="snake"|"breaker"|"rally"|"blocks"|"invaders";
type Store=Pick<Storage,"getItem"|"setItem"|"removeItem">;
let writesPaused=false;
export function pauseGameWrites(value:boolean){writesPaused=value;}
const fields:Record<GameKey,string[]>={
  snake:["body","food","head","score","best","pause","won"],
  breaker:["x","y","vx","vy","paddle","score","level","misses","best","layout","bricks","clearedPause","lost","pendingLevel"],
  rally:["x","y","vx","vy","left","right","score","rallies","pause","matchOver"],
  blocks:["board","queue","active","lines","points","cleared","phase","ticks","target"],
  invaders:["alive","shots","playerX","playerVelocity","turnCooldown","aimX","fleetX","fleetY","direction","score","best","wave","lives","phase","pause","shield","shootTimer","enemyTimer","thinkTimer","rng"],
};
const motionFields:Record<GameKey,string[]>={snake:["previousBody","elapsed","moveDelay","moves"],breaker:["paddleVelocity","paddleAim"],rally:["leftVelocity","rightVelocity","shotOffset","reactionDelay","receiverSpeed","tempoVersion"],blocks:["pieceId","decisionTicks","fallProgress"],invaders:[]};
const number=(v:unknown,min=-1e9,max=1e9)=>typeof v==="number" && Number.isFinite(v) && v>=min && v<=max;
const integer=(v:unknown,min:number,max:number)=>number(v,min,max) && Number.isInteger(v);
const list=(v:unknown,check:(x:unknown)=>boolean,min:number,max=min)=>Array.isArray(v) && v.length>=min && v.length<=max && v.every(check);
const kind=(v:unknown)=>typeof v==="string" && ["I","J","L","O","S","T","Z"].includes(v);
const record=(v:unknown):v is Record<string,unknown>=>!!v && typeof v==="object" && !Array.isArray(v);
function valid(key:GameKey,s:Record<string,unknown>):boolean{
  if(Object.keys(s).some(field=>![...fields[key],...motionFields[key]].includes(field)))return false;
  if(fields[key].some(field=>!(field in s)))return false;
  for(const field of motionFields[key])if(field in s){
    if(field==="previousBody"){if(!list(s[field],v=>integer(v,0,639),1,640))return false;}
    else if(field==="shotOffset"){if(!number(s[field],-80,80))return false;}
    else if(field==="reactionDelay"){if(!number(s[field],0,.2))return false;}
    else if(field==="receiverSpeed"){if(!number(s[field],230*PONG_TEMPO,280))return false;}
    else if(field==="paddleAim"){if(!number(s[field],52,648))return false;}
    else if(field==="decisionTicks"){if(!integer(s[field],0,4))return false;}
    else if(field==="fallProgress"){if(!number(s[field],0,1) || s[field]===1)return false;}
    else if(field==="tempoVersion"){if(s[field]!==2 && s[field]!==3 && s[field]!==4 && s[field]!==PONG_TEMPO_VERSION)return false;}
    else if(!number(s[field],field==="moveDelay"?.01:field.endsWith("Velocity")?-1000:0,field==="moveDelay"?1:1e9))return false;
  }
  if(key==="snake")return list(s.body,v=>integer(v,0,639),1,640) && new Set(s.body as number[]).size===(s.body as number[]).length && s.head===(s.body as number[])[0] && integer(s.food,-1,639) && !(s.body as number[]).includes(s.food as number) && integer(s.score,0,1e9) && integer(s.best,0,1e9) && integer(s.pause,0,20) && typeof s.won==="boolean";
  if(key==="invaders")return list(s.alive,v=>typeof v==="boolean",55) && list(s.shots,v=>record(v)&&Object.keys(v).length===3&&number(v.x,0,640)&&number(v.y,0,400)&&typeof v.enemy==="boolean",0,4) && number(s.playerX,22,618) && (s.playerVelocity===-INVADER_PLAYER_SPEED||s.playerVelocity===INVADER_PLAYER_SPEED) && number(s.turnCooldown,0,1) && number(s.aimX,30,610) && number(s.fleetX,8,136) && number(s.fleetY,42,240) && (s.direction===-1||s.direction===1) && integer(s.score,0,1e9) && integer(s.best,0,1e9) && integer(s.wave,1,1e6) && integer(s.lives,0,3) && ["play","wave","redeploy","lost"].includes(String(s.phase)) && (s.phase==="lost"?s.lives===0:s.lives!==0) && number(s.pause,0,2) && number(s.shield,0,1) && number(s.shootTimer,-2,2) && number(s.enemyTimer,-3,3) && number(s.thinkTimer,0,1) && integer(s.rng,1,0xffffffff);
  if(key==="breaker" || key==="rally"){
    if(!number(s.x,-20,720) || !number(s.y,0,480) || !number(s.vx,-1000,1000) || !number(s.vy,-1000,1000))return false;
    if(key==="breaker")return list(s.bricks,v=>typeof v==="boolean",80) && integer(s.layout,0,BRICK_LAYOUTS.length-1) && integer(s.score,0,1e9) && integer(s.best,0,1e9) && integer(s.level,1,1e9) && integer(s.misses,0,1e9) && number(s.paddle,52,648) && number(s.clearedPause,-1,2) && typeof s.lost==="boolean" && typeof s.pendingLevel==="boolean";
    return list(s.score,v=>integer(v,0,1e9),2) && number(s.left,52,408) && number(s.right,52,408) && integer(s.rallies,0,1e9) && number(s.pause,-1,3) && typeof s.matchOver==="boolean";
  }
  return list(s.board,row=>list(row,v=>v===null || kind(v),10),20) && list(s.queue,kind,1,20) && record(s.active) && Object.keys(s.active).length===4 && kind(s.active.kind) && integer(s.active.x,-4,10) && integer(s.active.y,-4,20) && integer(s.active.rotation,0,3) && integer(s.lines,0,1e9) && integer(s.points,0,1e9) && list(s.cleared,v=>integer(v,0,19),0,20) && ["move","fall","lock","clear","over"].includes(String(s.phase)) && integer(s.ticks,0,30) && record(s.target) && Object.keys(s.target).length===3 && integer(s.target.x,-4,10) && integer(s.target.rotation,0,3) && number(s.target.value,-1e6,1e6);
}
export type GameCheckpoints=Partial<Record<GameKey,Record<string,unknown>>>;
const keys:GameKey[]=["snake","breaker","rally","blocks","invaders"];
export function validateGameCheckpoints(value:unknown):value is GameCheckpoints{
  if(!record(value)||Object.keys(value).some(key=>!keys.includes(key as GameKey)))return false;
  return Object.entries(value).every(([key,data])=>record(data)&&JSON.stringify(data).length<=20000&&valid(key as GameKey,data));
}
export function readGameCheckpoints(store:Store=localStorage):GameCheckpoints{
  const result:GameCheckpoints={};
  for(const key of keys){const raw=store.getItem(`luma-game-v1-${key}`);if(raw===null)continue;if(raw.length>20000)throw Error("A saved game is too large to back up safely.");let data:unknown;try{data=JSON.parse(raw);}catch{throw Error("A saved game checkpoint is unreadable; keep the current hub data and review its game save first.");}if(!record(data)||!valid(key,data))throw Error("A saved game checkpoint failed validation; nothing was exported.");result[key]=data;}
  return result;
}
export function applyGameCheckpoints(value:unknown,store:Store=localStorage):void{
  if(!validateGameCheckpoints(value))throw Error("The game checkpoint in this backup is invalid.");
  const included=keys.filter(key=>!!value[key]);
  const previous=Object.fromEntries(included.map(key=>[key,store.getItem(`luma-game-v1-${key}`)])) as Record<GameKey,string|null>;
  try{for(const key of included)store.setItem(`luma-game-v1-${key}`,JSON.stringify(value[key]));}
  catch(error){for(const key of included){try{const raw=previous[key];if(raw===null)store.removeItem(`luma-game-v1-${key}`);else store.setItem(`luma-game-v1-${key}`,raw);}catch{/* Preserve remaining saves if the browser storage is failing. */}}throw error;}
}
export function saveGame(key:GameKey,game:object,store?:Store){
  if(writesPaused)return;
  try{
    const data=Object.fromEntries([...fields[key],...motionFields[key]].map(field=>[field,(game as Record<string,unknown>)[field]]));
    if(valid(key,data))(store??localStorage).setItem(`luma-game-v1-${key}`,JSON.stringify(data));
  }catch{/* Storage unavailable/full: in-memory continuity still works. */}
}
export function restoreGame<T extends object>(key:GameKey,game:T,store?:Store):T{
  try{
    const raw=(store??localStorage).getItem(`luma-game-v1-${key}`);
    if(!raw || raw.length>20000)return game;
    const data:unknown=JSON.parse(raw);
    if(record(data) && valid(key,data)){
      for(const field of [...fields[key],...motionFields[key]])if(field in data)(game as Record<string,unknown>)[field]=data[field];
      if(key==="snake" && !("previousBody" in data))(game as Record<string,unknown>).previousBody=[...(data.body as number[])];
      // Finish legacy uncapped runs on their current board without erasing progress.
      if(key==="breaker")(game as Record<string,unknown>).level=Math.min(BREAKER_LEVEL_LIMIT,data.level as number);
      if(key==="breaker" && !("paddleAim" in data))(game as Record<string,unknown>).paddleAim=data.paddle;
      if(key==="blocks" && !("decisionTicks" in data))(game as Record<string,unknown>).decisionTicks=0;
      if(key==="rally" && data.tempoVersion!==PONG_TEMPO_VERSION){
        const oldVersion=data.tempoVersion;
        const targetScale=oldVersion===2?PONG_TEMPO*PONG_BALL_TEMPO:oldVersion===3?PONG_BALL_TEMPO:oldVersion===4?PONG_BALL_TEMPO/1.08:.84*PONG_TEMPO*PONG_BALL_TEMPO;
        const speed=Math.hypot(data.vx as number,data.vy as number),scale=speed?Math.min(targetScale,PONG_MAX_SPEED/speed):1;
        (game as Record<string,unknown>).vx=(data.vx as number)*scale;
        (game as Record<string,unknown>).vy=(data.vy as number)*scale;
        // Version 3 already has the current paddle tuning; do not slow or
        // accelerate its paddles just because the ball now has its own tempo.
        if(oldVersion!==3 && oldVersion!==4){
          for(const field of ["leftVelocity","rightVelocity"])if(typeof data[field]==="number")(game as Record<string,unknown>)[field]=data[field]*PONG_TEMPO;
          if(typeof data.receiverSpeed==="number")(game as Record<string,unknown>).receiverSpeed=Math.max(230*PONG_TEMPO,Math.min(280*PONG_TEMPO,data.receiverSpeed*PONG_TEMPO));
          if(typeof data.reactionDelay==="number")(game as Record<string,unknown>).reactionDelay=Math.min(.2,data.reactionDelay/PONG_TEMPO);
        }
        (game as Record<string,unknown>).tempoVersion=PONG_TEMPO_VERSION;
      }
    }
  }catch{/* Incompatible/corrupt saves must not prevent the dashboard starting. */}
  return game;
}
