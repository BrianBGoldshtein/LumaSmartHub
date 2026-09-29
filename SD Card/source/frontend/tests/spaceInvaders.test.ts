import test from "node:test";
import assert from "node:assert/strict";
import {INVADER_COUNT,INVADER_PLAYER_SPEED,SpaceInvadersGame} from "../src/spaceInvaders.ts";

function quiet(game:SpaceInvadersGame){game.thinkTimer=10;game.enemyTimer=10;game.shootTimer=10;}

test("Space Invaders starts with a full classic formation and lives inside its arena",()=>{
  const game=new SpaceInvadersGame(7);
  assert.equal(game.alive.length,INVADER_COUNT);assert.equal(game.alive.every(Boolean),true);
  assert.equal(game.lives,3);assert.equal(game.score,0);assert.equal(game.wave,1);
  assert.ok(game.playerX>=22&&game.playerX<=618);assert.equal(game.direction,1);
});

test("the formation reverses and descends at the wall instead of wrapping",()=>{
  const game=new SpaceInvadersGame(12);game.fleetX=136;game.direction=1;const before=game.fleetY;
  game.step(1/120);
  assert.equal(game.fleetX,136);assert.equal(game.direction,-1);assert.equal(game.fleetY,before+11);
});

test("a formation breach redeploys survivors without consuming lives or resetting the run",()=>{
  const game=new SpaceInvadersGame(31);game.alive.fill(false);for(const i of [2,8,17,26,45])game.alive[i]=true;
  game.score=420;game.best=500;game.wave=3;game.lives=2;game.fleetX=136;game.fleetY=215;game.direction=1;
  game.shots=[{x:250,y:130,enemy:true},{x:400,y:210,enemy:false}];quiet(game);
  game.step(1/120);
  assert.equal(game.phase,"redeploy");assert.equal(game.lives,2);assert.equal(game.score,420);assert.equal(game.wave,3);
  assert.deepEqual(game.alive.map((alive,index)=>alive?index:-1).filter(index=>index>=0),[2,8,17,26,45]);
  for(let i=0;i<200&&game.phase==="redeploy";i++)game.step(1/120);
  assert.equal(game.phase,"play");assert.equal(game.lives,2);assert.equal(game.score,420);assert.equal(game.wave,3);
  assert.deepEqual(game.alive.map((alive,index)=>alive?index:-1).filter(index=>index>=0),[2,8,17,26,45]);
  assert.equal(game.fleetY,42);assert.equal(game.playerX,320);assert.equal(game.shots.length,0);
});

test("shots hit real invaders, award row scores and preserve a cleared wave",()=>{
  const game=new SpaceInvadersGame(19);game.alive.fill(false);game.alive[54]=true;
  game.fleetX=8;game.fleetY=42;game.shots=[{x:500,y:178,enemy:false}];quiet(game);
  game.step(1/120);
  assert.equal(game.alive.filter(Boolean).length,0);assert.equal(game.score,10);assert.equal(game.best,10);
  assert.equal(game.phase,"wave");
  for(let i=0;i<12;i++)game.step(.1);
  assert.equal(game.phase,"play");assert.equal(game.wave,2);assert.equal(game.score,10);
  assert.equal(game.alive.filter(Boolean).length,INVADER_COUNT);
});

test("an incoming shot costs one life, a real loss resets the run but keeps best",()=>{
  const game=new SpaceInvadersGame(23);game.score=70;game.best=70;game.lives=1;
  game.shots=[{x:320,y:349,enemy:true}];game.shield=0;quiet(game);
  game.step(1/60);
  assert.equal(game.lives,0);assert.equal(game.phase,"lost");assert.equal(game.score,70);
  for(let i=0;i<14;i++)game.step(.1);
  assert.equal(game.phase,"play");assert.equal(game.score,0);assert.equal(game.wave,1);
  assert.equal(game.lives,3);assert.equal(game.best,70);
});

test("the autonomous player moves, fires and scores during a long seeded visit",()=>{
  const game=new SpaceInvadersGame(0x12345678),start=game.playerX;
  for(let i=0;i<3600;i++)game.step(1/30);
  assert.notEqual(game.playerX,start);assert.ok(game.score>0);assert.ok(game.best>=game.score);
  assert.ok(game.alive.length===INVADER_COUNT);assert.ok(game.shots.length<=4);
});

test("the ship glides at one constant speed and respects a cooldown between direction changes",()=>{
  const game=new SpaceInvadersGame(0x5eed),changes:number[]=[];quiet(game);game.enemyTimer=1000;
  let priorDirection=Math.sign(game.playerVelocity),lastChange=-Infinity;
  for(let frame=0;frame<2400;frame++){
    const beforeX=game.playerX,beforePhase=game.phase;
    game.step(1/120);
    assert.equal(Math.abs(game.playerVelocity),INVADER_PLAYER_SPEED);
    assert.ok(game.playerX>=22&&game.playerX<=618);
    if(beforePhase==="play"&&game.phase==="play")assert.notEqual(game.playerX,beforeX,"the ship must never idle while alive");
    const direction=Math.sign(game.playerVelocity);
    if(beforePhase==="play"&&game.phase==="play"&&direction!==priorDirection){
      const time=frame/120;assert.ok(time-lastChange>=.47,`direction changed too soon at ${time.toFixed(2)}s`);
      lastChange=time;changes.push(frame);
    }
    priorDirection=direction;
  }
  assert.ok(changes.length>=5,"the player should keep traversing and turning during a long scene");
});

test("an imminent shot triggers an immediate turn toward the safer predicted position",()=>{
  const game=new SpaceInvadersGame(0xface);game.playerX=320;game.playerVelocity=INVADER_PLAYER_SPEED;
  game.aimX=610;game.turnCooldown=.32;game.thinkTimer=10;game.enemyTimer=10;game.shootTimer=10;
  game.shots=[{x:354,y:300,enemy:true}];
  game.step(1/120);
  assert.equal(game.playerVelocity,-INVADER_PLAYER_SPEED,"the normal cooldown must not force the ship into the shot");
  assert.ok(game.playerX<320,"the ship should immediately move away from the predicted collision lane");
  assert.ok(game.turnCooldown>.47,"after dodging, hold the safer heading for a short glide");
  assert.equal(game.lives,3);
});

test("an ordinary turn is vetoed if it would steer into an incoming shot",()=>{
  const game=new SpaceInvadersGame(0xbeef);game.playerX=320;game.playerVelocity=INVADER_PLAYER_SPEED;
  game.aimX=100;game.turnCooldown=1/120;game.thinkTimer=10;game.enemyTimer=10;game.shootTimer=10;
  // Continuing right clears this lane; the requested left turn intersects it.
  game.shots=[{x:286,y:300,enemy:true}];
  game.step(1/120);
  assert.equal(game.playerVelocity,INVADER_PLAYER_SPEED,"bullet safety must override a newly expired steering cooldown");
  assert.equal(game.lives,3);
});

test("the ship does not dodge one shot by turning into another equally dangerous lane",()=>{
  const game=new SpaceInvadersGame(0xcafe);game.playerX=320;game.playerVelocity=INVADER_PLAYER_SPEED;
  game.aimX=610;game.turnCooldown=.32;game.thinkTimer=10;game.enemyTimer=10;game.shootTimer=10;
  game.shots=[{x:354,y:300,enemy:true},{x:286,y:300,enemy:true}];
  game.step(1/120);
  assert.equal(game.playerVelocity,INVADER_PLAYER_SPEED,"when both paths are equally threatened, avoid a pointless reversal");
});
