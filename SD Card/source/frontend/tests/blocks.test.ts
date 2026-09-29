import test from "node:test";
import assert from "node:assert/strict";
import {BlocksGame,KINDS,COLORS,cells,emptyBoard,fits,landing,lock,clearRows,rotate,shuffledBag} from "../src/blocks.ts";
const random=(seed:number)=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
test("every bag contains all seven pieces, with seed-dependent order",()=>{
  const a=random(18),b=random(87);
  const sequenceA=Array.from({length:10},()=>shuffledBag(a));
  sequenceA.forEach(bag=>assert.deepEqual([...bag].sort(),[...KINDS].sort()));
  assert.notDeepEqual(sequenceA,Array.from({length:10},()=>shuffledBag(b)));
});
test("every rotation has exactly four cells; colors stay tied to piece kind",()=>{
  for(const kind of KINDS)for(let rotation=0;rotation<4;rotation++)assert.equal(cells({kind,x:0,y:0,rotation}).length,4);
  assert.equal(COLORS.I,"#38cfe4");assert.equal(COLORS.O,"#f6d64a");assert.equal(new Set(Object.values(COLORS)).size,7);
});
test("pieces cannot cross walls, the floor, or occupied cells",()=>{
  const board=emptyBoard();board[19][4]="T";
  assert.equal(fits(board,{kind:"O",x:-1,y:0,rotation:0}),false);
  assert.equal(fits(board,{kind:"O",x:9,y:0,rotation:0}),false);
  assert.equal(fits(board,{kind:"O",x:4,y:19,rotation:0}),false);
  const ghost=landing(board,{kind:"O",x:4,y:0,rotation:0});assert.equal(ghost.y,17);
  assert.equal(lock(board,ghost).board[17][4],"O");
});
test("I rotation kicks away from the left wall",()=>{
  const piece={kind:"I" as const,x:-2,y:4,rotation:1};
  const rotated=rotate(emptyBoard(),piece);
  assert.equal(rotated.rotation,2);assert.equal(rotated.x,0);assert.equal(fits(emptyBoard(),rotated),true);
});
test("complete single-color rows clear and cells above fall by the cleared count",()=>{
  const board=emptyBoard();for(let y=16;y<20;y++)board[y]=Array.from({length:10},(_,x)=>x===4?null:"I");board[15][0]="T";
  const piece=landing(board,{kind:"I",x:2,y:0,rotation:1});
  const result=lock(board,piece);assert.deepEqual(result.rows,[16,17,18,19]);
  const cleared=clearRows(result.board);assert.equal(cleared[19][0],"T");assert.equal(cleared.flat().filter(Boolean).length,1);
});
test("full mixed-color rows flash and clear regardless of piece color",()=>{
  const board=emptyBoard();board[19]=Array.from({length:10},(_,x)=>x===4?null:"J");
  const result=lock(board,landing(board,{kind:"I",x:2,y:0,rotation:1}));
  assert.deepEqual(result.rows,[19]);assert.ok(result.board[19].every(Boolean));
  assert.equal(clearRows(result.board).flat().filter(Boolean).length,3);
});
test("partial rows survive while both monochrome and mixed full rows disappear",()=>{
  const board=emptyBoard();board[19].fill("O");board[18].fill("J");board[18][0]="L";board[17][0]="T";
  const result=clearRows(board);
  assert.deepEqual(result[19],board[17]);
  assert.equal(result.flat().filter(Boolean).length,1);
});
test("top-out never writes outside the board",()=>{
  const result=lock(emptyBoard(),{kind:"O",x:4,y:-1,rotation:0});assert.equal(result.topOut,true);assert.equal(result.board.flat().filter(Boolean).length,0);
});
test("autoplay runs randomized legal games and clears fully occupied rows",()=>{
  for(const seed of [42,91,1701]) {
    const game=new BlocksGame(random(seed));
    for(let i=0;i<6000;i++) {
      game.step();assert.equal(game.board.length,20);assert.ok(game.board.every(row=>row.length===10));
      if(game.phase!=="over" && game.phase!=="clear")assert.ok(fits(game.board,game.active));
      for(const y of game.cleared) assert.ok(game.board[y].every(cell=>cell!==null));
    }
  }
});
test("autoplay recognizes and completes a reachable mixed-color row",()=>{
  const game=new BlocksGame(random(42));game.board[19]=Array.from({length:10},(_,x)=>KINDS[x%7]);
  for(let x=3;x<7;x++)game.board[19][x]=null;
  game.queue.unshift("I");game.next();
  for(let i=0;i<100 && game.lines===0;i++)game.step();
  assert.equal(game.lines,1);assert.deepEqual(game.cleared,[19]);
});
test("falling-block score survives a clear and resets only after top-out",()=>{
  const game=new BlocksGame(random(7));game.board[19].fill("I");game.phase="clear";game.cleared=[19];game.points=500;game.lines=3;
  for(let i=0;i<4;i++)game.step();assert.equal(game.points,500);assert.equal(game.lines,3);
  game.phase="over";game.ticks=0;for(let i=0;i<21;i++)game.step();assert.equal(game.points,0);assert.equal(game.lines,0);
});
test("falling blocks take a short variable thinking pause for each new piece",()=>{
  const delays=new Set<number>();
  for(let seed=1;seed<=20;seed++){
    const game=new BlocksGame(random(seed)),piece={...game.active},delay=game.decisionTicks;delays.add(delay);
    assert.ok(delay>=2 && delay<=4);
    for(let i=0;i<delay;i++){game.step();assert.deepEqual(game.active,piece);}
    game.step();assert.notDeepEqual({...game.active,phase:game.phase},{...piece,phase:"move"});
    game.next();assert.ok(game.decisionTicks>=2 && game.decisionTicks<=4);
  }
  assert.equal(delays.size,3);
});
test("falling blocks can hesitate between inputs without slowing the fall cadence",()=>{
  const game=new BlocksGame(()=>0);game.active={kind:"O",x:4,y:0,rotation:0};game.target={x:6,rotation:0,value:0};game.decisionTicks=0;
  game.step();assert.equal(game.active.x,5);assert.equal(game.decisionTicks,1);
  game.step();assert.equal(game.active.x,5);game.step();assert.equal(game.active.x,6);
  game.phase="fall";game.decisionTicks=4;const y=game.visualY();
  game.step();assert.ok(Math.abs(game.visualY()-y-.2625)<1e-9);game.step();assert.ok(Math.abs(game.visualY()-y-.525)<1e-9);
});
test("Tetris drops only a sixth faster than drift without a double-gravity handoff",()=>{
  const game=new BlocksGame(()=>.5);game.active={kind:"O",x:4,y:0,rotation:0};game.target={x:4,rotation:0,value:0};game.decisionTicks=3;
  for(let i=1;i<=3;i++){game.step();assert.equal(game.active.y,0);assert.ok(Math.abs(game.visualY()-.225*i)<1e-9);}
  const beforeDecision=game.visualY();game.step();assert.equal(game.phase,"fall");assert.ok(Math.abs(game.visualY()-beforeDecision-.225)<1e-9);
  const before=game.visualY();game.step();const drop=game.visualY()-before;
  assert.ok(Math.abs(drop-.2625)<1e-9);assert.ok(Math.abs(drop/.225-7/6)<1e-9);
});
test("score raises both gravity rates without speeding up thinking or inputs",()=>{
  for(const points of [0,1000,6000,12000,18000,100000]){
    const game=new BlocksGame(()=>.5);game.points=points;game.active={kind:"O",x:4,y:0,rotation:0};game.target={x:4,rotation:0,value:0};game.decisionTicks=4;
    assert.equal(game.speedMultiplier(),Math.min(4,2.5+points/12000));
    game.step();assert.equal(game.decisionTicks,3);assert.ok(Math.abs(game.visualY()-.09*game.speedMultiplier())<1e-9);
    game.phase="fall";const before=game.visualY();game.step();assert.ok(Math.abs(game.visualY()-before-.105*game.speedMultiplier())<1e-9);
    game.next();assert.equal(game.decisionTicks,3);assert.equal(game.fallProgress,0);
  }
});
test("starting pace equals the old 22000-point pace without steepening the score ramp",()=>{
  const game=new BlocksGame(()=>.5),oldMultiplier=(points:number)=>Math.min(2.5,1+points/12000);
  assert.equal(game.speedMultiplier(),oldMultiplier(22000));
  for(const points of [100,1000,6000,12000,18000]){
    game.points=points;assert.ok(Math.abs((game.speedMultiplier()-2.5)-(oldMultiplier(points)-1))<1e-9);
  }
});
test("fast gravity checks every crossed row and never tunnels through the stack",()=>{
  const game=new BlocksGame(()=>.5);game.points=100000;game.active={kind:"O",x:4,y:0,rotation:0};game.board[6][4]="I";game.phase="fall";
  for(let i=0;i<12 && game.phase!=="lock";i++)game.step();assert.equal(game.active.y,4);assert.equal(game.visualY(),4);assert.equal(game.phase,"lock");assert.ok(fits(game.board,game.active));
});
test("thinking gravity can reach the stack before a delayed placement is completed",()=>{
  const game=new BlocksGame(()=>.5);game.points=18000;game.active={kind:"O",x:4,y:3,rotation:0};game.board[6][4]="I";game.target={x:0,rotation:0,value:0};game.decisionTicks=4;game.fallProgress=.85;
  game.step();assert.equal(game.active.y,4);assert.equal(game.active.x,4);assert.equal(game.phase,"lock");
});
