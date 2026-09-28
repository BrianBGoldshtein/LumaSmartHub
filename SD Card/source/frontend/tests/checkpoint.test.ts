import test from "node:test";
import assert from "node:assert/strict";
import {applyGameCheckpoints,readGameCheckpoints,restoreGame,saveGame,validateGameCheckpoints} from "../src/gameCheckpoint.ts";
import {SnakeGame,BreakerGame,RallyGame,PONG_TEMPO} from "../src/classics.ts";
import {BlocksGame} from "../src/blocks.ts";
const store=()=>{const values=new Map<string,string>();return {getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{values.set(key,value);},removeItem:(key:string)=>{values.delete(key);}};};
test("all games restore their exact paused run into fresh engines",()=>{
  for(const key of ["snake","breaker","rally","blocks"] as const){
    const create=()=>key==="snake"?new SnakeGame():key==="breaker"?new BreakerGame():key==="rally"?new RallyGame():new BlocksGame();
    const before=create(),storage=store();
    for(let i=0;i<65;i++){if(before instanceof SnakeGame || before instanceof BlocksGame)before.step();else before.step(.032);}
    saveGame(key,before,storage);const json=storage.getItem(`luma-game-v1-${key}`);assert.ok(json);
    const after=restoreGame(key,create(),storage);assert.equal(typeof after.step,"function");
    saveGame(key,after,storage);assert.equal(storage.getItem(`luma-game-v1-${key}`),json);
    if(after instanceof SnakeGame || after instanceof BlocksGame)after.step();else after.step(.032);
  }
});
test("corrupt and obsolete checkpoints do not break fresh games",()=>{
  const storage=store(),game=new BreakerGame(()=>.2),board=[...game.bricks];
  storage.setItem("luma-game-v1-breaker",'{"bricks":[true],"score":999}');
  restoreGame("breaker",game,storage);assert.deepEqual(game.bricks,board);assert.equal(game.score,0);
  storage.setItem("luma-game-v1-breaker","not json");assert.equal(restoreGame("breaker",game,storage),game);
});
test("blocked local storage leaves the running game intact",()=>{
  const storage={getItem:()=>{throw Error("disabled");},setItem:()=>{throw Error("full");}},game=new SnakeGame();
  assert.equal(restoreGame("snake",game,storage),game);assert.doesNotThrow(()=>saveGame("snake",game,storage));
});
test("older checkpoints migrate without resetting scores or runs",()=>{
  const storage=store(),game=new SnakeGame(()=>.5);game.score=120;game.step();saveGame("snake",game,storage);
  const old=JSON.parse(storage.getItem("luma-game-v1-snake")!);
  for(const field of ["previousBody","elapsed","moveDelay","moves"])delete old[field];
  storage.setItem("luma-game-v1-snake",JSON.stringify(old));
  const restored=restoreGame("snake",new SnakeGame(),storage);
  assert.equal(restored.score,120);assert.deepEqual(restored.body,game.body);assert.deepEqual(restored.previousBody,game.body);
});
test("breaker checkpoints preserve new layouts and resume the level-twenty loss boundary",()=>{
  const storage=store(),game=new BreakerGame(()=>.99);game.level=20;game.score=game.best=6400;
  game.bricks.fill(false);game.pendingLevel=true;game.y=330;saveGame("breaker",game,storage);
  const restored=restoreGame("breaker",new BreakerGame(),storage);
  assert.equal(restored.layout,19);assert.equal(restored.level,20);assert.equal(restored.score,6400);
  restored.step(.01);assert.equal(restored.lost,true);saveGame("breaker",restored,storage);
  const paused=restoreGame("breaker",new BreakerGame(),storage);paused.step(1.3);
  assert.equal(paused.level,1);assert.equal(paused.score,0);assert.equal(paused.best,6400);
});
test("legacy uncapped breaker saves keep their board and score but finish at the new cap",()=>{
  const storage=store(),game=new BreakerGame(()=>.2);game.level=28;game.score=9000;saveGame("breaker",game,storage);
  const restored=restoreGame("breaker",new BreakerGame(),storage);
  assert.equal(restored.level,20);assert.equal(restored.score,9000);assert.deepEqual(restored.bricks,game.bricks);
});
test("legacy color-match boards clear accumulated mixed rows without corrupting score or saves",()=>{
  const game=new BlocksGame(()=>.5),storage=store();
  for(let y=14;y<20;y++)game.board[y]=Array.from({length:10},(_,x)=>x%2?"J":"L");
  game.active={kind:"O",x:0,y:12,rotation:0};game.phase="lock";game.ticks=3;game.points=100;
  game.step();assert.equal(game.phase,"clear");assert.equal(game.lines,6);assert.equal(game.points,900);
  saveGame("blocks",game,storage);const restored=restoreGame("blocks",new BlocksGame(),storage);
  assert.deepEqual(restored.cleared,[14,15,16,17,18,19]);
  for(let i=0;i<4;i++)restored.step();assert.equal(restored.board.flat().filter(Boolean).length,4);assert.equal(restored.points,900);
});
test("Pong restores shot intent and reaction timing, while older saves retain their match",()=>{
  const storage=store(),game=new RallyGame(()=>.7);game.score=[3,5];game.step(.025);saveGame("rally",game,storage);
  const restored=restoreGame("rally",new RallyGame(),storage);
  assert.equal(restored.shotOffset,game.shotOffset);assert.equal(restored.reactionDelay,game.reactionDelay);assert.equal(restored.receiverSpeed,game.receiverSpeed);
  const old=JSON.parse(storage.getItem("luma-game-v1-rally")!);
  for(const field of ["shotOffset","reactionDelay","receiverSpeed"])delete old[field];
  storage.setItem("luma-game-v1-rally",JSON.stringify(old));const legacy=restoreGame("rally",new RallyGame(),storage);
  assert.deepEqual(legacy.score,[3,5]);assert.equal(legacy.x,game.x);assert.equal(legacy.y,game.y);
});
test("breaker restores filtered aim and seeds older saves from the current paddle position",()=>{
  const storage=store(),game=new BreakerGame(()=>.2);game.paddle=300;game.paddleAim=340;game.score=170;
  saveGame("breaker",game,storage);assert.equal(restoreGame("breaker",new BreakerGame(),storage).paddleAim,340);
  const old=JSON.parse(storage.getItem("luma-game-v1-breaker")!);delete old.paddleAim;
  storage.setItem("luma-game-v1-breaker",JSON.stringify(old));const restored=restoreGame("breaker",new BreakerGame(),storage);
  assert.equal(restored.paddleAim,300);assert.equal(restored.score,170);
});
test("new game pacing survives saves and legacy Pong slows down exactly once",()=>{
  const storage=store(),blocks=new BlocksGame(()=>.5);blocks.decisionTicks=3;saveGame("blocks",blocks,storage);
  assert.equal(restoreGame("blocks",new BlocksGame(),storage).decisionTicks,3);
  const game=new RallyGame(()=>.5);game.vx=400;game.vy=100;game.score=[4,2];saveGame("rally",game,storage);
  const old=JSON.parse(storage.getItem("luma-game-v1-rally")!);delete old.tempoVersion;
  storage.setItem("luma-game-v1-rally",JSON.stringify(old));const restored=restoreGame("rally",new RallyGame(),storage);
  assert.ok(Math.abs(restored.vx-336*PONG_TEMPO)<1e-8);assert.ok(Math.abs(restored.vy-84*PONG_TEMPO)<1e-8);assert.deepEqual(restored.score,[4,2]);assert.equal(restored.x,game.x);
  saveGame("rally",restored,storage);const again=restoreGame("rally",new RallyGame(),storage);
  assert.equal(again.vx,restored.vx);assert.equal(again.vy,restored.vy);
});
test("version-two Pong saves migrate ball and paddle tempo once without losing points",()=>{
  const storage=store(),game=new RallyGame(()=>.5);game.tempoVersion=2;game.vx=220;game.vy=80;game.leftVelocity=200;game.receiverSpeed=250;game.score=[2,7];saveGame("rally",game,storage);
  const restored=restoreGame("rally",new RallyGame(),storage);
  assert.equal(restored.vx,220*PONG_TEMPO);assert.equal(restored.leftVelocity,200*PONG_TEMPO);assert.equal(restored.receiverSpeed,250*PONG_TEMPO);assert.equal(restored.tempoVersion,3);assert.deepEqual(restored.score,[2,7]);
  saveGame("rally",restored,storage);assert.equal(restoreGame("rally",new RallyGame(),storage).vx,restored.vx);
});
test("portable backups capture, validate and restore the four actual game checkpoint schemas",()=>{
  const source=store();
  saveGame("snake",new SnakeGame(()=>.5),source);
  saveGame("breaker",new BreakerGame(()=>.5),source);
  saveGame("rally",new RallyGame(()=>.5),source);
  saveGame("blocks",new BlocksGame(()=>.5),source);
  const games=readGameCheckpoints(source);assert.equal(Object.keys(games).length,4);assert.equal(validateGameCheckpoints(games),true);
  const target=store();applyGameCheckpoints(games,target);
  assert.equal(restoreGame("snake",new SnakeGame(),target).score,0);
  assert.equal(restoreGame("breaker",new BreakerGame(),target).level,1);
  assert.deepEqual(restoreGame("rally",new RallyGame(),target).score,[0,0]);
  assert.equal(restoreGame("blocks",new BlocksGame(),target).points,0);
});
test("portable game checkpoints reject extra fields and roll back browser storage failures",()=>{
  const source=store();saveGame("snake",new SnakeGame(),source);saveGame("blocks",new BlocksGame(),source);const games=readGameCheckpoints(source);
  const unsafe=structuredClone(games);(unsafe.snake as Record<string,unknown>).oauth="secret";
  assert.equal(validateGameCheckpoints(unsafe),false);assert.throws(()=>applyGameCheckpoints(unsafe,store()));
  const values=new Map<string,string>();values.set("luma-game-v1-snake","old-snake");
  let fail=true;const target={getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>{if(key.endsWith("-blocks")&&fail){fail=false;throw Error("storage quota");}values.set(key,value);},removeItem:(key:string)=>{values.delete(key);}};
  assert.throws(()=>applyGameCheckpoints(games,target));assert.equal(values.get("luma-game-v1-snake"),"old-snake");assert.equal(values.has("luma-game-v1-blocks"),false);
});
test("fractional Tetris gravity and score-derived difficulty survive scene reloads",()=>{
  const storage=store(),game=new BlocksGame(()=>.5);game.points=3000;game.step();saveGame("blocks",game,storage);
  const restored=restoreGame("blocks",new BlocksGame(),storage);
  assert.equal(restored.fallProgress,game.fallProgress);assert.equal(restored.visualY(),game.visualY());assert.equal(restored.speedMultiplier(),2.75);
});
